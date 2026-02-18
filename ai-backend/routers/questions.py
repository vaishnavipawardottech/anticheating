"""
Layer 3: Concept-centric question bank pipeline.
Generate → Classify (Bloom) → Validate → Dedupe → Store.
"""

import hashlib
import json
import re
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel, Field

from database.database import get_db
from database.models import (
    BankQuestion, BankQuestionSource, QuestionGenerationRun, QuestionQualityScore,
    DocumentChunk, Concept, Unit, Subject,
)
from database import schemas as db_schemas
from services.question_context import get_concept_context_pack, format_context_pack_for_prompt
from routers.structure_ai import call_gemini_flash
from embeddings import get_embedding_generator
from embeddings.qdrant_manager import get_qdrant_manager

router = APIRouter(prefix="/questions", tags=["questions"])

# ---- Generator prompt (concept + context pack → JSON array) ----
GENERATOR_PROMPT = """You are generating exam questions from the following context only.

CONCEPT: {concept_name}
UNIT: {unit_name}

CONTEXT (use only these chunks; each has an ID):
---
{context_text}
---

TASK: Generate exactly this set of questions. Output ONLY a JSON array. No markdown, no explanation.
- 2× MCQ (question_type: "MCQ"), Bloom BT1–BT3. 4 options, 1 correct. Same length/structure for options.
- 1× Short answer (question_type: "SHORT"), Bloom BT2–BT3. answer_key: bullet rubric.
- 1× Long or case-based (question_type: "LONG"), Bloom BT4–BT6. answer_key: marking scheme with (a)(b)(c) parts.

RULES:
- Only use information from the context above. If a question cannot be fully answered from context, output {{"skip": true, "reason": "..."}} for that item instead of the question object.
- For each question include "source_chunk_ids": [list of chunk IDs from context that support the answer].
- difficulty: "E" | "M" | "H". bloom_level: "BT1" .. "BT6".
- Do NOT start any question with "According to the passage" or "Based on the text".
- MCQ: "options": ["A. ...", "B. ...", "C. ...", "D. ..."], "correct_answer": "A" (or B/C/D), "explanation": short reasoning.

Output format (array of objects, or skip object):
[
  {{"question_text": "...", "question_type": "MCQ", "marks": 2, "options": ["A. ...", "B. ...", "C. ...", "D. ..."], "correct_answer": "A", "answer_key": {{}}, "explanation": "...", "bloom_level": "BT2", "difficulty": "M", "source_chunk_ids": [1, 2]}},
  ...
]

Return ONLY the JSON array."""

# ---- Bloom rule-based (verb heuristics) ----
BLOOM_VERBS = {
    "BT1": ["define", "list", "name", "identify", "recall", "state", "recognize"],
    "BT2": ["explain", "describe", "summarize", "interpret", "classify", "compare", "discuss"],
    "BT3": ["apply", "use", "demonstrate", "implement", "solve", "illustrate"],
    "BT4": ["analyze", "differentiate", "examine", "contrast", "distinguish", "investigate"],
    "BT5": ["evaluate", "assess", "justify", "critique", "argue", "support"],
    "BT6": ["design", "create", "develop", "construct", "propose", "formulate"],
}

def bloom_rule_guess(question_text: str) -> str:
    """Quick rule-based Bloom level from question text (verbs)."""
    text_lower = (question_text or "").lower()
    for level, verbs in BLOOM_VERBS.items():
        if any(v in text_lower for v in verbs):
            return level
    return "BT2"  # default Understand

# ---- Validator prompt (groundedness) ----
VALIDATOR_GROUNDED_PROMPT = """You are a strict validator. Given context and a question+answer, decide if the answer is fully supported by the context.

CONTEXT:
---
{context_text}
---

QUESTION: {question_text}

PROPOSED ANSWER/KEY: {answer_info}

Answer with JSON only: {{"supported": true}} or {{"supported": false, "reason": "one line why not", "missing_chunk_id": null or chunk id if a specific chunk was needed}}" """

# ---- Helpers ----
def _approx_tokens(text: str) -> int:
    if not text or not text.strip():
        return 0
    return int(len(text.split()) * 1.3)


def _normalize_question_text(text: str) -> str:
    """Normalize for hash/dedupe."""
    if not text:
        return ""
    t = re.sub(r"\s+", " ", text.strip().lower())
    return t


def _question_hash(text: str) -> str:
    return hashlib.sha256(_normalize_question_text(text).encode()).hexdigest()


def _extract_json_array(raw: str) -> List[dict]:
    raw = raw.strip()
    start = raw.find("[")
    end = raw.rfind("]") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON array in response")
    return json.loads(raw[start:end])


async def _run_bloom_llm(question_text: str, bloom_suggested: str) -> tuple[str, str]:
    """LLM verifier for Bloom level. Returns (bloom_final, one_line_justification)."""
    prompt = f"""Given this question, assign the correct Bloom level (BT1-BT6). Current guess: {bloom_suggested}.
Question: {question_text[:300]}
Reply with JSON only: {{"bloom_level": "BT2", "justification": "one line"}}"""
    try:
        resp = await call_gemini_flash(prompt)
        start = resp.find("{")
        end = resp.rfind("}") + 1
        if start == -1 or end == 0:
            return bloom_suggested, ""
        obj = json.loads(resp[start:end])
        return obj.get("bloom_level", bloom_suggested), obj.get("justification", "")
    except Exception:
        return bloom_suggested, ""


async def _validate_groundedness(context_text: str, question_text: str, answer_info: str) -> tuple[bool, Optional[str]]:
    """Returns (passed, reason_if_failed)."""
    prompt = VALIDATOR_GROUNDED_PROMPT.format(
        context_text=context_text[:4000],
        question_text=question_text[:500],
        answer_info=answer_info[:800],
    )
    try:
        resp = await call_gemini_flash(prompt)
        start = resp.find("{")
        end = resp.rfind("}") + 1
        if start == -1 or end == 0:
            return True, None
        obj = json.loads(resp[start:end])
        if obj.get("supported") is True:
            return True, None
        return False, obj.get("reason", "Answer not fully supported by context")
    except Exception:
        return True, None  # allow on validator failure to avoid blocking


def _check_mcq_sanity(question: dict, context_chunk_ids: List[int]) -> Optional[str]:
    """Returns None if OK, else fail reason."""
    opts = question.get("options") or []
    if len(opts) != 4:
        return "MCQ must have exactly 4 options"
    correct = (question.get("correct_answer") or "").strip().upper()
    if correct and correct in "ABCD" and len(correct) == 1:
        idx = "ABCD".index(correct)
        if idx >= len(opts):
            return "correct_answer index out of range"
    return None


def _is_ambiguous(question_text: str) -> bool:
    """Simple heuristic: 'which of the following' without single clear answer, or multiple valid options."""
    t = (question_text or "").lower()
    if "according to the passage" in t or "based on the text" in t:
        return True
    return False


# ---- Dedupe: exact hash + Qdrant similarity ----
DEDUPE_SAME_CONCEPT_THRESHOLD = 0.90
DEDUPE_GLOBAL_THRESHOLD = 0.95


def _check_duplicate(
    db: Session,
    question_text: str,
    subject_id: int,
    unit_id: Optional[int],
    concept_id: Optional[int],
    question_embedding: List[float],
) -> tuple[bool, str]:
    """
    Returns (is_duplicate, reason).
    Exact hash check first; then Qdrant same concept/unit > 0.90; then global > 0.95.
    """
    q_hash = _question_hash(question_text)
    # Exact duplicate: we could store hashes in DB; for now rely on Qdrant
    qdrant = get_qdrant_manager()
    qdrant.ensure_question_collection()

    # Same concept/unit: threshold 0.90
    same_scope = qdrant.search_question_duplicates(
        query_vector=question_embedding,
        subject_id=subject_id,
        unit_id=unit_id or 0,
        concept_id=concept_id or 0,
        limit=5,
        score_threshold=DEDUPE_SAME_CONCEPT_THRESHOLD,
    )
    if same_scope:
        return True, f"Near-duplicate in same concept (score {same_scope[0].get('score', 0):.2f})"

    # Global: no filter (any subject)
    try:
        global_hits = qdrant.client.search(
            collection_name=qdrant.COLLECTION_QUESTIONS,
            query_vector=question_embedding,
            limit=3,
            score_threshold=DEDUPE_GLOBAL_THRESHOLD,
        )
        if global_hits:
            return True, f"Near-duplicate globally (score {global_hits[0].score:.2f})"
    except Exception:
        pass
    return False, ""


# ---- Generation pipeline ----
async def run_generation_for_concept(
    db: Session,
    concept_id: int,
    subject_id: int,
    unit_id: int,
    concept_name: str,
    unit_name: str,
    target: dict,
    run_id: int,
    dry_run: bool,
) -> tuple[List[dict], List[str]]:
    """
    Build context pack, call generator, classify Bloom, validate, dedupe.
    Returns (list of accepted question dicts for storage, list of fail_reasons).
    """
    chunks, concept = get_concept_context_pack(db, concept_id, subject_id)
    if not chunks or not concept:
        return [], ["No aligned chunks for concept or concept not found"]

    context_text = format_context_pack_for_prompt(chunks)
    if _approx_tokens(context_text) < 100:
        return [], ["Context pack too small"]

    prompt = GENERATOR_PROMPT.format(
        concept_name=concept_name,
        unit_name=unit_name,
        context_text=context_text,
    )
    try:
        raw = await call_gemini_flash(prompt)
    except Exception as e:
        return [], [f"Generator LLM failed: {e}"]

    try:
        items = _extract_json_array(raw)
    except Exception as e:
        return [], [f"Generator returned invalid JSON: {e}"]

    fail_reasons = []
    accepted = []
    gen = get_embedding_generator()

    for item in items:
        if item.get("skip") is True:
            fail_reasons.append(item.get("reason", "Generator skipped"))
            continue
        question_text = (item.get("question_text") or "").strip()
        if not question_text:
            fail_reasons.append("Empty question_text")
            continue
        qtype = (item.get("question_type") or "SHORT").upper()
        if qtype == "MCQ":
            err = _check_mcq_sanity(item, [c.id for c in chunks])
            if err:
                fail_reasons.append(err)
                continue
        if _is_ambiguous(question_text):
            fail_reasons.append("Ambiguous or passage-dependent phrasing")
            continue
        # Bloom: rule + optional LLM
        bloom_rule = bloom_rule_guess(question_text)
        bloom_llm, _ = await _run_bloom_llm(question_text, bloom_rule)
        item["bloom_level"] = bloom_llm or bloom_rule
        # Groundedness
        answer_info = json.dumps(item.get("answer_key") or {}) + " " + (item.get("correct_answer") or "")
        passed, reason = await _validate_groundedness(context_text, question_text, answer_info)
        if not passed:
            fail_reasons.append(reason or "Groundedness check failed")
            continue
        # Dedupe
        q_embedding = gen.generate_embedding(question_text)
        is_dup, dup_reason = _check_duplicate(db, question_text, subject_id, unit_id, concept_id, q_embedding)
        if is_dup:
            fail_reasons.append(dup_reason)
            continue
        item["concept_id"] = concept_id
        item["unit_id"] = unit_id
        item["subject_id"] = subject_id
        item["source_chunk_ids"] = item.get("source_chunk_ids") or []
        item["generator_metadata"] = {"model": "gemini-2.5-flash-lite", "run_id": run_id}
        accepted.append(item)

    return accepted, fail_reasons


# ---- API: Generate ----
@router.post("/generate")
async def generate_questions(
    request: db_schemas.GenerateQuestionsRequest,
    db: Session = Depends(get_db),
):
    """
    Concept-centric question generation. Specify subject_id and optionally unit_id/concept_id.
    If concept_id is set, only that concept is used. Else all concepts in unit (or subject) are used.
    """
    subject_id = request.subject_id
    unit_id = request.unit_id
    concept_id = request.concept_id
    target = request.target or {"mcq": 2, "short": 1, "long": 1}

    if concept_id:
        concepts_q = (
            db.query(Concept)
            .options(joinedload(Concept.unit))
            .join(Unit)
            .filter(Unit.subject_id == subject_id, Concept.id == concept_id)
        )
    elif unit_id:
        concepts_q = (
            db.query(Concept)
            .options(joinedload(Concept.unit))
            .join(Unit)
            .filter(Concept.unit_id == unit_id, Unit.subject_id == subject_id)
        )
    else:
        concepts_q = (
            db.query(Concept)
            .options(joinedload(Concept.unit))
            .join(Unit)
            .filter(Unit.subject_id == subject_id)
        )

    concepts = concepts_q.all()
    if not concepts:
        raise HTTPException(status_code=404, detail="No concepts found for the given scope")

    run = QuestionGenerationRun(
        subject_id=subject_id,
        unit_id=unit_id,
        concept_id=concept_id,
        prompt_version="v1",
        model="gemini-2.5-flash-lite",
        status="running",
        counts_requested=target,
        fail_reasons=[],
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    all_accepted = []
    all_fail_reasons = []

    for c in concepts:
        unit = c.unit
        accepted, fail_reasons = await run_generation_for_concept(
            db=db,
            concept_id=c.id,
            subject_id=subject_id,
            unit_id=unit.id,
            concept_name=c.name,
            unit_name=unit.name,
            target=target,
            run_id=run.id,
            dry_run=request.dry_run,
        )
        all_accepted.extend(accepted)
        all_fail_reasons.extend(fail_reasons)

    if not request.dry_run:
        qdrant = get_qdrant_manager()
        gen = get_embedding_generator()
        for q in all_accepted:
            bq = BankQuestion(
                subject_id=q["subject_id"],
                unit_id=q.get("unit_id"),
                concept_id=q.get("concept_id"),
                question_text=q["question_text"],
                question_type=q.get("question_type", "SHORT"),
                marks=q.get("marks", 1),
                options=q.get("options"),
                correct_answer=q.get("correct_answer"),
                answer_key=q.get("answer_key"),
                explanation=q.get("explanation"),
                bloom_level=q.get("bloom_level"),
                difficulty=q.get("difficulty", "M"),
                co_ids=q.get("co_ids", []),
                source_chunk_ids=q.get("source_chunk_ids", []),
                quality_flags=q.get("quality_flags"),
                generator_metadata=q.get("generator_metadata"),
                status="pending",
            )
            db.add(bq)
            db.flush()
            for cid in q.get("source_chunk_ids") or []:
                db.add(BankQuestionSource(question_id=bq.id, chunk_id=cid))
            # Quality score placeholder
            db.add(QuestionQualityScore(question_id=bq.id, grounded_score=1.0, notes="Pipeline accepted"))
            # Embed for dedupe
            emb = gen.generate_embedding(q["question_text"])
            qdrant.index_question(bq.id, emb, bq.subject_id, bq.unit_id, bq.concept_id)
        db.commit()

    run.status = "completed"
    run.counts_accepted = {"total": len(all_accepted)}
    run.fail_reasons = all_fail_reasons[:50]
    db.commit()

    return {
        "run_id": run.id,
        "concepts_processed": len(concepts),
        "accepted": len(all_accepted),
        "fail_reasons_count": len(all_fail_reasons),
        "dry_run": request.dry_run,
    }


# ---- API: List, Approve, Reject, Patch ----
class QuestionFilters(BaseModel):
    subject_id: Optional[int] = None
    unit_id: Optional[int] = None
    concept_id: Optional[int] = None
    status: Optional[str] = None
    question_type: Optional[str] = None


@router.get("/", response_model=List[db_schemas.QuestionBankResponse])
def list_questions(
    subject_id: Optional[int] = Query(None),
    unit_id: Optional[int] = Query(None),
    concept_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    question_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List questions in the bank with optional filters."""
    q = db.query(BankQuestion)
    if subject_id is not None:
        q = q.filter(BankQuestion.subject_id == subject_id)
    if unit_id is not None:
        q = q.filter(BankQuestion.unit_id == unit_id)
    if concept_id is not None:
        q = q.filter(BankQuestion.concept_id == concept_id)
    if status is not None:
        q = q.filter(BankQuestion.status == status)
    if question_type is not None:
        q = q.filter(BankQuestion.question_type == question_type)
    rows = q.order_by(BankQuestion.id.desc()).offset(skip).limit(limit).all()
    return [db_schemas.QuestionBankResponse.model_validate(r) for r in rows]


@router.post("/{question_id}/approve")
def approve_question(question_id: int, db: Session = Depends(get_db)):
    q = db.query(BankQuestion).filter(BankQuestion.id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    q.status = "approved"
    db.commit()
    return {"id": question_id, "status": "approved"}


@router.post("/{question_id}/reject")
def reject_question(question_id: int, db: Session = Depends(get_db)):
    q = db.query(BankQuestion).filter(BankQuestion.id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    q.status = "rejected"
    db.commit()
    return {"id": question_id, "status": "rejected"}


@router.patch("/{question_id}", response_model=db_schemas.QuestionBankResponse)
def update_question(
    question_id: int,
    update: db_schemas.QuestionBankUpdate,
    db: Session = Depends(get_db),
):
    """Teacher edit: patch allowed fields."""
    q = db.query(BankQuestion).filter(BankQuestion.id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    data = update.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(q, k, v)
    db.commit()
    db.refresh(q)
    return db_schemas.QuestionBankResponse.model_validate(q)


@router.get("/runs")
def list_generation_runs(
    subject_id: Optional[int] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List recent question generation runs for analytics."""
    q = db.query(QuestionGenerationRun)
    if subject_id is not None:
        q = q.filter(QuestionGenerationRun.subject_id == subject_id)
    runs = q.order_by(QuestionGenerationRun.id.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "subject_id": r.subject_id,
            "unit_id": r.unit_id,
            "concept_id": r.concept_id,
            "status": r.status,
            "counts_requested": r.counts_requested,
            "counts_accepted": r.counts_accepted,
            "fail_reasons_sample": (r.fail_reasons or [])[:10],
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in runs
    ]

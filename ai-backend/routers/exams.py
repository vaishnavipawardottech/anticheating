"""
Exam generation: blueprint → context → LLM → validate → store Exam + Questions.
"""

import json
import random
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from database.database import get_db
from database.models import Exam, Question, QuestionSource, DocumentChunk, Document
from routers.context import build_context_impl
from routers.structure_ai import call_gemini_flash

router = APIRouter(prefix="/exams", tags=["exams"])


@router.get("/")
def exams_root():
    """Verify exams API is loaded; returns 200 with info."""
    return {"status": "ok", "message": "POST /exams/generate to create an exam"}


class BlueprintCounts(BaseModel):
    mcq: int = Field(0, ge=0, le=50)
    short: int = Field(0, ge=0, le=20)
    long: int = Field(0, ge=0, le=10)


class ExamGenerateRequest(BaseModel):
    subject_id: int = Field(..., description="Subject ID")
    unit_ids: Optional[List[int]] = Field(None, description="Limit to these units")
    concept_ids: Optional[List[int]] = Field(None, description="Limit to these concepts (overrides unit scope)")
    counts: BlueprintCounts = Field(default_factory=lambda: BlueprintCounts(mcq=10, short=5, long=2))
    difficulty_distribution: Optional[Dict[str, float]] = Field(None, description="e.g. {easy: 0.3, medium: 0.5, hard: 0.2}")
    bloom_distribution: Optional[Dict[str, float]] = Field(None)
    seed: Optional[int] = Field(None, description="For reproducible randomness")
    include_answer_key: bool = Field(True, description="Generate answer keys")


GENERATION_PROMPT = """You are generating an exam from the following context.

CONTEXT (from course material):
---
{context_text}
---

REQUIREMENTS:
- Generate exactly {mcq} MCQ(s), {short} short-answer question(s), {long} long-answer question(s).
- Each question must be answerable from the context above.
- For MCQs: 4 options, exactly one correct. Include "correct_option" (letter A/B/C/D), "why_correct", "why_others_wrong" (brief).
- For short: "expected_answer", "key_points" (3-6 points), "marking_scheme" (optional).
- For long: "answer_outline", "rubric" (criteria and marks).
- Set "difficulty": easy/medium/hard and "bloom_level" (e.g. Remember, Understand, Apply).

Return ONLY a valid JSON array of questions. Each object:
{{
  "type": "mcq" | "short" | "long",
  "text": "question text",
  "options": ["A...", "B...", "C...", "D..."] (only for mcq),
  "difficulty": "easy" | "medium" | "hard",
  "bloom_level": "string",
  "answer_key": {{
    "correct_option": "A" (mcq),
    "why_correct": "...",
    "why_others_wrong": ["..."] (mcq),
    "expected_answer": "...", "key_points": ["..."] (short),
    "answer_outline": "...", "rubric": "..." (long)
  }}
}}

Return ONLY the JSON array. No markdown, no explanation."""


@router.post("/generate")
async def generate_exam(request: ExamGenerateRequest, db: Session = Depends(get_db)):
    """
    Generate exam from blueprint: expand per-concept demand, build context, LLM generates questions,
    validate, store Exam + Questions, return.
    """
    seed = request.seed or random.randint(0, 2**31 - 1)
    random.seed(seed)

    # Build context (no query; filter by unit/concept)
    ctx_resp = await build_context_impl(
        subject_id=request.subject_id,
        db=db,
        unit_id=request.unit_ids[0] if request.unit_ids and len(request.unit_ids) == 1 else None,
        concept_ids=request.concept_ids,
        top_k=20,
        include_neighbors=True,
        max_tokens=4000,
    )
    if not ctx_resp.context_text or ctx_resp.total_tokens < 100:
        raise HTTPException(
            status_code=400,
            detail="Insufficient context for generation. Ingest documents and align concepts first."
        )

    prompt = GENERATION_PROMPT.format(
        context_text=ctx_resp.context_text,
        mcq=request.counts.mcq,
        short=request.counts.short,
        long=request.counts.long,
    )
    try:
        raw = await call_gemini_flash(prompt)
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON array in response")
        items = json.loads(raw[start:end])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM generation failed: {str(e)}")

    # Validate: exactly one correct option for MCQ, type counts
    mcq_count = sum(1 for q in items if q.get("type") == "mcq")
    short_count = sum(1 for q in items if q.get("type") == "short")
    long_count = sum(1 for q in items if q.get("type") == "long")
    for q in items:
        if q.get("type") == "mcq":
            opts = q.get("options") or []
            key = (q.get("answer_key") or {}).get("correct_option")
            if not key or key not in "ABCD" or len(opts) != 4:
                raise HTTPException(status_code=422, detail="Each MCQ must have 4 options and correct_option A/B/C/D")

    # Store exam
    blueprint = {
        "unit_ids": request.unit_ids,
        "concept_ids": request.concept_ids,
        "counts": request.counts.model_dump(),
        "difficulty_distribution": request.difficulty_distribution,
        "bloom_distribution": request.bloom_distribution,
    }
    exam = Exam(subject_id=request.subject_id, blueprint=blueprint, seed=seed)
    db.add(exam)
    db.commit()
    db.refresh(exam)

    citation_chunk_ids = [c.chunk_id for c in ctx_resp.citations]
    for idx, q in enumerate(items):
        qtype = q.get("type", "mcq")
        difficulty = q.get("difficulty") or "medium"
        bloom = q.get("bloom_level") or ""
        text = q.get("text") or ""
        answer_key = q.get("answer_key") if request.include_answer_key else None
        tags = q.get("tags") or []
        question = Question(
            exam_id=exam.id,
            type=qtype,
            difficulty=difficulty,
            bloom_level=bloom,
            text=text,
            explanation=(answer_key or {}).get("why_correct") or (answer_key or {}).get("expected_answer"),
            answer_key=answer_key,
            tags=tags,
        )
        db.add(question)
        db.flush()
        if citation_chunk_ids and idx < len(citation_chunk_ids):
            db.add(QuestionSource(question_id=question.id, chunk_id=citation_chunk_ids[idx]))
    db.commit()

    return {
        "exam_id": exam.id,
        "subject_id": exam.subject_id,
        "questions_generated": len(items),
        "seed": seed,
    }

"""
NL Intake Layer — generation/nl_interpreter.py

Step 0 of the generation pipeline (before retrieval or generation).

Converts a teacher's free-text request into a fully-typed GenerationSpec
(either MCQSpec or SubjectiveSpec) by:
  1. Fetching real unit names + IDs from the DB for the given subject
  2. Sending the request + unit context to GPT with a structured output prompt
  3. Parsing + validating the JSON response
  4. Returning a typed MCQSpec or SubjectiveSpec object

Supported input examples:
  - "Create 10 MCQs from Unit 1 and 2, 2 marks each"
  - "5 questions from unit 1, 10 from unit 2, 1 mark each — MCQ"
  - "Create a 30-mark paper: Q1 from Unit 1, Q2 from Unit 2, Q3 from Unit 3.
     Each has 4 sub-questions, attempt any 2, 5 marks each"
  - "2 long questions from Unit 3, 10 marks each, hard difficulty"
"""

import json
import logging
import re
from typing import List, Optional, Union

import json_repair
from sqlalchemy.orm import Session

from generation.schemas import (
    MCQSpec,
    SubjectiveSpec,
    UnitCountSpec,
    SubjectiveSection,
)

log = logging.getLogger("generation.pipeline")

# ── Type alias ────────────────────────────────────────────────────────────────
GenerationSpec = Union[MCQSpec, SubjectiveSpec]


# ── Prompt ────────────────────────────────────────────────────────────────────

NL_INTERPRETER_PROMPT = """\
You are an exam generation spec parser for a university assessment tool.
Be FLEXIBLE: interpret vague or short requests with sensible defaults (e.g. "give me questions" → 8–10 questions across units, 5 marks each).

Convert the teacher's natural language request into a structured JSON spec.

TEACHER'S REQUEST:
---
{request_text}
---
{question_type_hint}

SUBJECT UNITS AVAILABLE (use exact unit_id values from this list):
{unit_list}

Output ONLY valid JSON — exactly one of these two schemas:

=== MCQ SCHEMA (use when teacher wants MCQ / multiple choice / objective questions) ===
{{
  "type": "mcq",
  "marks_per_question": <int, default 1>,
  "difficulty": "<easy|medium|hard|auto, default auto>",
  "bloom_levels": [<optional list: "remember"|"understand"|"apply"|"analyze"|"evaluate"|"create">],
  "unit_distribution": [
    {{"unit_id": <real_unit_id_from_list>, "count": <int>}},
    ...
  ]
}}

=== SUBJECTIVE SCHEMA (use for short / long / descriptive / essay questions) ===
{{
  "type": "subjective",
  "total_marks": <int>,
  "difficulty": "<easy|medium|hard|auto, default auto>",
  "min_diagram_questions": <int, optional, default 0: minimum number of questions that MUST use a figure/diagram>,
  "sections": [
    {{
      "unit_id": <real_unit_id_from_list>,
      "question_type": "<short|long>",
      "sub_questions": <int: total questions to generate for this section>,
      "attempt": <int: how many the student must answer, same as sub_questions if all compulsory>,
      "marks_per_sub": <int: marks per sub-question>
    }},
    ...
  ]
}}

PARSING RULES:
1. **Question type**: Use the teacher's preference hint if provided. Otherwise: if the request mentions MCQ / multiple choice / objective → type = "mcq"; else → type = "subjective". For "short" → subjective with question_type "short"; "long" → subjective with "long"; "mix" → subjective with a mix of short and long sections.
2. Map unit references ("Unit 1", "unit1", "first unit", "U1", "all units") to real unit_id from the list. If no units mentioned, use ALL units from the list with even distribution.
3. "attempt" = how many sub-questions the student must answer
   - "2 compulsory out of 4" → sub_questions=4, attempt=2
   - "attempt any 2" → attempt=2
   - If not specified → attempt = sub_questions (all compulsory)
4. "short" question: marks_per_sub <= 7. "long" question: marks_per_sub >= 8
5. If marks not specified: MCQ default = 1 mark/question, subjective default = 5 marks/sub
6. bloom_levels: only set if teacher explicitly mentions Bloom's level or cognitive level
7. **IMPORTANT for unit_distribution (MCQ)**: When distributing questions across units, split as EVENLY as possible
   - Example: "15 MCQs from Unit 1 and 2" → split evenly: [7, 8] or [8, 7]
   - Unless teacher specifies exact counts per unit, always prefer even distribution
8. **Vague requests**: "some questions", "make a test", "exam on unit 2" → use sensible defaults: e.g. 8–10 questions, all units or mentioned units, 5 marks each for subjective, 1–2 marks for MCQ.
9. **Diagram questions**: If the teacher asks for "diagram questions", "figure-based questions", "guaranteed diagram questions", "at least N diagram questions", or "include diagram/figure questions", set min_diagram_questions to the requested number (or 2 if no number given). This reserves that many questions to be based on figures/diagrams from the syllabus.
10. Output ONLY the JSON object. No markdown. No explanation.
"""


# ── Unit list builder ──────────────────────────────────────────────────────────

def _build_unit_list(db: Session, subject_id: int) -> tuple[str, dict]:
    """
    Fetch units for a subject from DB.

    Returns:
        unit_list_text: Formatted string for the prompt
        unit_map: {position: unit_id} and {name_lower: unit_id} for fallback
    """
    from database.models import Unit

    units = (
        db.query(Unit)
        .filter(Unit.subject_id == subject_id)
        .order_by(Unit.order)
        .all()
    )

    if not units:
        return "No units found for this subject.", {}

    lines = []
    name_to_id: dict = {}
    for idx, unit in enumerate(units, start=1):
        lines.append(f"  - unit_id={unit.id}, position={idx}, name=\"{unit.name}\"")
        name_to_id[unit.name.lower()] = unit.id
        name_to_id[f"unit {idx}"] = unit.id
        name_to_id[f"unit{idx}"] = unit.id
        name_to_id[f"u{idx}"] = unit.id

    return "\n".join(lines), name_to_id


# ── JSON extraction ───────────────────────────────────────────────────────────

def _extract_json(raw: str) -> dict:
    """Extract + repair JSON from GPT response."""
    raw = raw.strip()
    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
    # Find the JSON object boundaries
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON object in LLM response: {raw[:300]}")
    return json_repair.loads(raw[start:end])


# ── Unit ID normalization (patch for "unit 2" → real unit_id) ──────────────────

def _get_subject_unit_ids_ordered(db: Session, subject_id: int) -> List[int]:
    """Return subject's unit IDs in display order (position 1, 2, 3...)."""
    from database.models import Unit
    units = (
        db.query(Unit)
        .filter(Unit.subject_id == subject_id)
        .order_by(Unit.order)
        .all()
    )
    return [u.id for u in units]


def _normalize_unit_ids(
    data: dict,
    spec_type: str,
    unit_ids_ordered: List[int],
) -> None:
    """
    Map position-based unit references (1, 2, 3...) to real DB unit_id.
    LLM often returns unit_id=2 for 'unit 2' when the real id might be 18.
    Mutates data in place.
    """
    if not unit_ids_ordered:
        return
    valid_ids = set(unit_ids_ordered)
    n = len(unit_ids_ordered)

    def map_uid(uid: int) -> int:
        if uid in valid_ids:
            return uid
        # Treat as 1-based position
        if 1 <= uid <= n:
            return unit_ids_ordered[uid - 1]
        return uid

    if spec_type == "mcq":
        for item in data.get("unit_distribution") or []:
            item["unit_id"] = map_uid(int(item.get("unit_id", 0)))
    elif spec_type == "subjective":
        for sec in data.get("sections") or []:
            sec["unit_id"] = map_uid(int(sec.get("unit_id", 0)))


def _ensure_subjective_defaults(data: dict, unit_ids_ordered: List[int]) -> None:
    """If LLM returns empty sections for vague request, add one sensible section."""
    sections = data.get("sections")
    if sections and len(sections) > 0:
        return
    if not unit_ids_ordered:
        return
    # Default: one section, first unit, 8 questions, 5 marks each
    data["sections"] = [
        {
            "unit_id": unit_ids_ordered[0],
            "question_type": "short",
            "sub_questions": 8,
            "attempt": 8,
            "marks_per_sub": 5,
        }
    ]
    data["total_marks"] = 8 * 5


# ── Spec validator / builder ──────────────────────────────────────────────────

def _build_mcq_spec(data: dict) -> MCQSpec:
    """Validate and build MCQSpec from parsed JSON."""
    dist_raw = data.get("unit_distribution") or []
    if not dist_raw:
        raise ValueError("MCQ spec missing 'unit_distribution'")

    distribution = []
    for item in dist_raw:
        uid = int(item.get("unit_id", 0))
        count = int(item.get("count", 1))
        if uid <= 0:
            raise ValueError(f"Invalid unit_id in distribution: {item}")
        distribution.append(UnitCountSpec(unit_id=uid, count=count))

    return MCQSpec(
        marks_per_question=int(data.get("marks_per_question", 1)),
        difficulty=str(data.get("difficulty", "auto")).lower(),
        bloom_levels=data.get("bloom_levels") or [],
        unit_distribution=distribution,
    )


def _build_subjective_spec(data: dict) -> SubjectiveSpec:
    """Validate and build SubjectiveSpec from parsed JSON."""
    sections_raw = data.get("sections") or []
    if not sections_raw:
        raise ValueError("Subjective spec missing 'sections'")

    total_marks_parsed = int(data.get("total_marks", 0))

    sections = []
    computed_marks = 0
    for sec in sections_raw:
        uid = int(sec.get("unit_id", 0))
        sub_q = int(sec.get("sub_questions", 1))
        attempt = int(sec.get("attempt", sub_q))
        marks_per = int(sec.get("marks_per_sub", 5))
        q_type = str(sec.get("question_type", "short")).lower()

        if uid <= 0:
            raise ValueError(f"Invalid unit_id in section: {sec}")
        if attempt > sub_q:
            attempt = sub_q  # can't attempt more than generated

        sections.append(SubjectiveSection(
            unit_id=uid,
            question_type=q_type if q_type in ("short", "long") else "short",
            sub_questions=sub_q,
            attempt=attempt,
            marks_per_sub=marks_per,
        ))
        computed_marks += attempt * marks_per  # marks = compulsory count × marks_per

    # Use GPT's total_marks if given; otherwise compute from sections
    total = total_marks_parsed if total_marks_parsed > 0 else computed_marks
    min_diagram = max(0, int(data.get("min_diagram_questions", 0)))

    return SubjectiveSpec(
        total_marks=total,
        difficulty=str(data.get("difficulty", "auto")).lower(),
        sections=sections,
        min_diagram_questions=min_diagram,
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def _question_type_hint(preference: Optional[str]) -> str:
    if not preference or not str(preference).strip():
        return ""
    p = str(preference).strip().lower()
    if p == "mcq":
        return 'TEACHER PREFERENCE (follow this): The teacher wants MCQ only. Use type = "mcq" and distribute across units.'
    if p == "short":
        return 'TEACHER PREFERENCE (follow this): The teacher wants short-answer questions only. Use type = "subjective" with question_type = "short" in all sections.'
    if p == "long":
        return 'TEACHER PREFERENCE (follow this): The teacher wants long-answer questions only. Use type = "subjective" with question_type = "long" in all sections.'
    if p == "mix":
        return 'TEACHER PREFERENCE (follow this): The teacher wants a mix of short and long. Use type = "subjective" with some sections question_type "short" and some "long".'
    if p == "subjective":
        return 'TEACHER PREFERENCE (follow this): The teacher wants subjective/descriptive questions. Use type = "subjective"; infer short vs long from request.'
    return ""


async def interpret_nl_request(
    request_text: str,
    subject_id: int,
    db: Session,
    difficulty_override: Optional[str] = None,
    question_type_preference: Optional[str] = None,
) -> GenerationSpec:
    """
    Parse a teacher's free-text generation request into a typed spec.

    Args:
        request_text:       Teacher's natural language description
        subject_id:         Subject ID (used to fetch unit names)
        db:                 SQLAlchemy session
        difficulty_override: If set, overrides the difficulty in the parsed spec
        question_type_preference: Optional "mcq" | "short" | "long" | "mix" | "subjective"

    Returns:
        MCQSpec or SubjectiveSpec

    Raises:
        ValueError: If the LLM output is unparseable or invalid
    """
    from generation.gpt_client import call_gpt

    # Build unit context for the prompt
    unit_list_text, _name_map = _build_unit_list(db, subject_id)
    question_type_hint = _question_type_hint(question_type_preference)
    if question_type_hint:
        question_type_hint = question_type_hint + "\n\n"

    prompt = NL_INTERPRETER_PROMPT.format(
        request_text=request_text.strip(),
        question_type_hint=question_type_hint,
        unit_list=unit_list_text,
    )

    log.info(f"[NL Interpret] Sending request to GPT for subject={subject_id}")
    log.info(f"[NL Interpret] Request: {request_text[:200]}")

    raw = await call_gpt(
        prompt=prompt,
        system="You are a precise exam spec parser. Output only valid JSON matching the given schema.",
        temperature=0.1,   # Very low — we want deterministic structured output
        max_tokens=1000,
    )

    log.info(f"[NL Interpret] Raw GPT output: {raw[:500]}")

    try:
        data = _extract_json(raw)
    except Exception as e:
        raise ValueError(f"NL interpreter returned invalid JSON: {e}\nRaw: {raw[:400]}")

    spec_type = str(data.get("type", "")).lower()
    log.info(f"[NL Interpret] Parsed type: {spec_type}")

    # Patch: map "unit 2" (position) to real unit_id; ensure subjective has sections
    unit_ids_ordered = _get_subject_unit_ids_ordered(db, subject_id)
    if spec_type == "subjective":
        _ensure_subjective_defaults(data, unit_ids_ordered)
    _normalize_unit_ids(data, spec_type, unit_ids_ordered)

    if spec_type == "mcq":
        spec = _build_mcq_spec(data)
    elif spec_type == "subjective":
        spec = _build_subjective_spec(data)
    else:
        raise ValueError(
            f"Unknown spec type '{spec_type}'. Expected 'mcq' or 'subjective'."
        )

    # Apply difficulty override from the API if given
    if difficulty_override and difficulty_override != "auto":
        spec.difficulty = difficulty_override

    log.info(f"[NL Interpret] OK — {spec_type} spec built")
    return spec

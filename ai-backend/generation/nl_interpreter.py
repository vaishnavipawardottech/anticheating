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

Convert the teacher's natural language request into a structured JSON spec.

TEACHER'S REQUEST:
---
{request_text}
---

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
1. If the request mentions MCQ / multiple choice / objective → type = "mcq"
2. Otherwise → type = "subjective"
3. Map unit references ("Unit 1", "unit1", "first unit", "U1") to real unit_id from the list
4. "attempt" = how many sub-questions the student must answer
   - "2 compulsory out of 4" → sub_questions=4, attempt=2
   - "attempt any 2" → attempt=2
   - If not specified → attempt = sub_questions (all compulsory)
5. "short" question: marks_per_sub <= 7. "long" question: marks_per_sub >= 8
6. If marks not specified: MCQ default = 1 mark/question, subjective default = 5 marks/sub
7. bloom_levels: only set if teacher explicitly mentions Bloom's level or cognitive level
8. **IMPORTANT for unit_distribution (MCQ)**: When distributing questions across units, split as EVENLY as possible
   - Example: "15 MCQs from Unit 1 and 2" → split evenly: [7, 8] or [8, 7]
   - Example: "20 MCQs from Unit 1, 2, 3" → [7, 7, 6] or [7, 6, 7] or [6, 7, 7]
   - Unless teacher specifies exact counts per unit, always prefer even distribution
9. Output ONLY the JSON object. No markdown. No explanation.
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

    return SubjectiveSpec(
        total_marks=total,
        difficulty=str(data.get("difficulty", "auto")).lower(),
        sections=sections,
    )


# ── Main entry point ──────────────────────────────────────────────────────────

async def interpret_nl_request(
    request_text: str,
    subject_id: int,
    db: Session,
    difficulty_override: Optional[str] = None,
) -> GenerationSpec:
    """
    Parse a teacher's free-text generation request into a typed spec.

    Args:
        request_text:       Teacher's natural language description
        subject_id:         Subject ID (used to fetch unit names)
        db:                 SQLAlchemy session
        difficulty_override: If set, overrides the difficulty in the parsed spec

    Returns:
        MCQSpec or SubjectiveSpec

    Raises:
        ValueError: If the LLM output is unparseable or invalid
    """
    from generation.gpt_client import call_gpt

    # Build unit context for the prompt
    unit_list_text, _name_map = _build_unit_list(db, subject_id)

    prompt = NL_INTERPRETER_PROMPT.format(
        request_text=request_text.strip(),
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

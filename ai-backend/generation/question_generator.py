"""
Step 4 — Question Generation Engine

Generates one exam question per QuestionSpec using OpenAI GPT.
Supports two generation modes:
  - "mcq"        → 4 options (A/B/C/D) with correct answer labelled
  - "descriptive" → full question + answer key + marking scheme

Output: GeneratedQuestion with all fields populated correctly.
"""

import json
import re
from typing import List

from database.models import DocumentChunk
from generation.schemas import QuestionSpec, GeneratedQuestion, MarkingPoint, MCQOption


# ─── MCQ Generation Prompt ─────────────────────────────────────────────────────

MCQ_PROMPT = """You are an expert university exam question setter.

Generate exactly ONE Multiple Choice Question (MCQ) based on the specifications below.

SPECIFICATIONS:
- Bloom's Level: {bloom_target}
- Marks: {marks}
- Difficulty: {difficulty}
- Topic Nature: {nature}
- Target Units: {units}

CONTEXT (use ONLY information from these chunks; do NOT copy text verbatim):
---
{context_text}
---

OUTPUT FORMAT — respond with ONLY a valid JSON object, no markdown, no explanation:
{{
  "question_text": "<clear, unambiguous MCQ question stem>",
  "bloom_level": "<remember|understand|apply|analyze|evaluate|create>",
  "difficulty": "<easy|medium|hard>",
  "marks": {marks},
  "options": [
    {{"label": "A", "text": "<option text>"}},
    {{"label": "B", "text": "<option text>"}},
    {{"label": "C", "text": "<option text>"}},
    {{"label": "D", "text": "<option text>"}}
  ],
  "answer_key": "<A|B|C|D>",
  "explanation": "<brief explanation of why the answer is correct>",
  "source_chunk_ids": [<chunk_id>, ...]
}}

RULES:
1. The question stem must be complete and self-sufficient — no dangling context
2. All 4 options must be plausible — distractors should be common misconceptions or close alternatives
3. Exactly ONE option must be clearly correct based on the context
4. Do NOT use "All of the above" or "None of the above"
5. Do NOT copy chunk text verbatim
6. source_chunk_ids: list IDs of chunks supporting the answer
7. Return ONLY the JSON object
"""


# ─── Descriptive Generation Prompt ─────────────────────────────────────────────

DESCRIPTIVE_PROMPT = """You are an expert university exam question setter.

Generate exactly ONE descriptive exam question based on the specifications below.

SPECIFICATIONS:
- Bloom's Level: {bloom_target}
- Marks: {marks}
- Difficulty: {difficulty}
- Question Nature: {nature}
- Target Units: {units}

CONTEXT (use ONLY information from these chunks; do NOT copy text verbatim):
---
{context_text}
---

OUTPUT FORMAT — respond with ONLY a valid JSON object, no markdown, no explanation:
{{
  "question_text": "<full question text — may include sub-parts like (a), (b) for high-mark questions>",
  "bloom_level": "<remember|understand|apply|analyze|evaluate|create>",
  "difficulty": "<easy|medium|hard>",
  "marks": {marks},
  "answer_key": "<detailed model answer — LENGTH MUST BE PROPORTIONAL TO MARKS>",
  "marking_scheme": [
    {{"point": "<what to check>", "marks": <int>}},
    ...
  ],
  "source_chunk_ids": [<chunk_id>, ...]
}}

RULES:
1. Bloom level must match the specification: {bloom_target}
2. Marking scheme points must sum to exactly {marks} marks
3. Do NOT start with "According to the passage" or "Based on the text"
4. Do NOT copy chunk text verbatim — paraphrase and synthesise
5. For marks >= 10: include sub-parts (a), (b), (c) or structured parts
6. For marks <= 5: ask a focused, single-concept question
7. source_chunk_ids: list IDs of chunks used

**CRITICAL - ANSWER LENGTH REQUIREMENTS:**
- **2 marks**: 1-2 paragraphs (100-150 words) - Brief but complete answer with key concepts
- **3-4 marks**: 2-3 paragraphs (150-250 words) - Detailed explanation with examples
- **5 marks**: 3 paragraphs (250-350 words) - Comprehensive coverage with examples and explanations
- **6-8 marks**: 4-5 paragraphs (350-500 words) - Extensive discussion, multiple perspectives, detailed examples
- **10+ marks**: 5-7 paragraphs (500-800 words) - In-depth analysis, comprehensive coverage, multiple examples, comparative discussion

Each paragraph should be 3-5 sentences. Higher marks = more depth, more examples, more analysis.

8. Return ONLY the JSON object
"""



# ─── Context formatter ─────────────────────────────────────────────────────────

def _format_context(chunks: List[DocumentChunk]) -> str:
    """Format chunks into labelled context block."""
    parts = []
    for chunk in chunks:
        cid = chunk.id
        unit_label = f"(Unit {chunk.unit_id})" if chunk.unit_id else ""
        bloom_label = f"[{chunk.blooms_level}]" if chunk.blooms_level else ""
        text = (chunk.text or "").strip()
        parts.append(f"[Chunk ID: {cid}] {unit_label} {bloom_label}\n{text}")
    return "\n\n---\n\n".join(parts)


# ─── JSON extraction ───────────────────────────────────────────────────────────

def _extract_json_obj(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON object found: {raw[:200]}")
    return json.loads(raw[start:end])


# ─── MCQ builder ──────────────────────────────────────────────────────────────

def _build_mcq(data: dict, spec: QuestionSpec, chunks: List[DocumentChunk]) -> GeneratedQuestion:
    """Parse GPT MCQ output into a GeneratedQuestion."""
    options = []
    for opt in data.get("options", []):
        label = str(opt.get("label", "")).upper().strip()
        text = str(opt.get("text", "")).strip()
        if label and text:
            options.append(MCQOption(label=label, text=text))

    # Fallback: if GPT didn't give 4 options, something went wrong
    if len(options) < 2:
        raise ValueError("GPT returned fewer than 2 MCQ options")

    answer_key = str(data.get("answer_key", "A")).upper().strip()

    chunk_ids = {c.id for c in chunks}
    source_ids = [int(i) for i in (data.get("source_chunk_ids") or []) if int(i) in chunk_ids] or [c.id for c in chunks]

    return GeneratedQuestion(
        question_type="mcq",
        question_text=data.get("question_text", ""),
        bloom_level=data.get("bloom_level", spec.bloom_targets[0] if spec.bloom_targets else "understand"),
        difficulty=data.get("difficulty", spec.difficulty),
        marks=spec.marks,
        options=options,
        answer_key=answer_key,
        marking_scheme=[],
        source_chunk_ids=source_ids,
        unit_ids=spec.units,
    )


# ─── Descriptive builder ──────────────────────────────────────────────────────

def _build_descriptive(data: dict, spec: QuestionSpec, chunks: List[DocumentChunk]) -> GeneratedQuestion:
    """Parse GPT descriptive output into a GeneratedQuestion."""
    marking_scheme = []
    total_scheme_marks = 0
    for item in (data.get("marking_scheme") or []):
        pt = str(item.get("point", "")).strip()
        m = int(item.get("marks", 0))
        if pt:
            marking_scheme.append(MarkingPoint(point=pt, marks=m))
            total_scheme_marks += m

    # Adjust last item if scheme doesn't sum correctly
    if marking_scheme and total_scheme_marks != spec.marks:
        diff = spec.marks - total_scheme_marks
        marking_scheme[-1].marks = max(0, marking_scheme[-1].marks + diff)

    chunk_ids = {c.id for c in chunks}
    raw_ids = data.get("source_chunk_ids") or []
    source_ids = [int(i) for i in raw_ids if isinstance(i, (int, str)) and str(i).isdigit() and int(i) in chunk_ids]
    if not source_ids:
        source_ids = [c.id for c in chunks]

    return GeneratedQuestion(
        question_type="descriptive",
        question_text=data.get("question_text", ""),
        bloom_level=data.get("bloom_level", spec.bloom_targets[0] if spec.bloom_targets else "understand"),
        difficulty=data.get("difficulty", spec.difficulty),
        marks=spec.marks,
        options=[],
        answer_key=data.get("answer_key", ""),
        marking_scheme=marking_scheme,
        source_chunk_ids=source_ids,
        unit_ids=spec.units,
    )


# ─── Token calculation helper ──────────────────────────────────────────────────

def _calculate_max_tokens(marks: int, is_mcq: bool) -> int:
    """
    Calculate appropriate max_tokens based on question marks.
    
    Token estimates (rough guide):
    - 100 words ≈ 133 tokens
    - 2 marks (150 words) ≈ 200 tokens
    - 5 marks (300 words) ≈ 400 tokens
    - 10 marks (650 words) ≈ 850 tokens
    
    We add buffer for JSON structure, marking scheme, etc.
    """
    if is_mcq:
        # MCQs don't scale much with marks - fixed size
        return 1200
    
    # Descriptive questions scale with marks
    if marks <= 2:
        return 1500  # ~150 words answer + overhead
    elif marks <= 4:
        return 2000  # ~250 words answer + overhead
    elif marks <= 5:
        return 2500  # ~350 words answer + overhead
    elif marks <= 8:
        return 3200  # ~500 words answer + overhead
    else:  # 10+ marks
        return 4000  # ~800 words answer + overhead


# ─── Main generator ────────────────────────────────────────────────────────────

async def generate_question(
    spec: QuestionSpec,
    chunks: List[DocumentChunk],
) -> GeneratedQuestion:
    """
    Step 4: Generate one exam question for a QuestionSpec.

    Routes to MCQ or descriptive generation based on spec.question_type.
    Falls back to a safe error question on complete failure.
    """
    from generation.gpt_client import call_gpt

    context_text = _format_context(chunks)
    bloom_target = ", ".join(spec.bloom_targets) if spec.bloom_targets else "understand"
    is_mcq = spec.question_type == "mcq"
    
    # Scale context length with marks for better quality answers
    context_limit = 5000 if is_mcq else min(6000 + (spec.marks * 200), 12000)

    if is_mcq:
        prompt = MCQ_PROMPT.format(
            bloom_target=bloom_target,
            marks=spec.marks,
            difficulty=spec.difficulty,
            nature=spec.nature or "general",
            units=", ".join(f"Unit {u}" for u in spec.units),
            context_text=context_text[:context_limit],
        )
    else:
        prompt = DESCRIPTIVE_PROMPT.format(
            bloom_target=bloom_target,
            marks=spec.marks,
            difficulty=spec.difficulty,
            nature=spec.nature or "general",
            units=", ".join(f"Unit {u}" for u in spec.units),
            context_text=context_text[:context_limit],
        )

    raw = await call_gpt(
        prompt,
        temperature=0.45 if is_mcq else 0.55,
        max_tokens=_calculate_max_tokens(spec.marks, is_mcq),
    )

    try:
        data = _extract_json_obj(raw)
    except Exception as e:
        # Return a safe fallback on JSON parse failure
        return _fallback_question(spec, chunks, f"JSON parse error: {e}")

    try:
        if is_mcq:
            return _build_mcq(data, spec, chunks)
        else:
            return _build_descriptive(data, spec, chunks)
    except Exception as e:
        return _fallback_question(spec, chunks, f"Build error: {e}")


def _fallback_question(spec: QuestionSpec, chunks: List[DocumentChunk], reason: str) -> GeneratedQuestion:
    """Return a safe placeholder question instead of crashing the pipeline."""
    return GeneratedQuestion(
        question_type=spec.question_type,
        question_text=f"[Q{spec.question_no} — generation failed: {reason}]",
        bloom_level=spec.bloom_targets[0] if spec.bloom_targets else "understand",
        difficulty=spec.difficulty,
        marks=spec.marks,
        answer_key="",
        options=[],
        marking_scheme=[],
        source_chunk_ids=[c.id for c in chunks],
        unit_ids=spec.units,
    )

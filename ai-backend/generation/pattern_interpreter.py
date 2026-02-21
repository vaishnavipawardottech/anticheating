"""
Step 1 — Pattern Processing Layer

Converts free-text exam pattern into a structured ParsedPattern JSON.
Supports:
  Option A: Uploaded pattern PDF → extract text → LLM
  Option B: Plain text prompt pattern → LLM
  Detects: MCQ vs descriptive question types

LLM backend: OpenAI GPT (via generation.gpt_client)
"""

import json
import re
from typing import Optional

from generation.schemas import ParsedPattern, ParsedQuestion


# ─── Prompt ────────────────────────────────────────────────────────────────────

PATTERN_INTERPRETER_PROMPT = """You are an academic exam pattern parser.

Convert the following exam pattern text into structured JSON.
The pattern describes a university exam question layout.

PATTERN TEXT:
---
{pattern_text}
---

TOTAL MARKS: {total_marks}

Output a JSON object ONLY (no markdown, no explanation):
{{
  "total_marks": <number>,
  "questions": [
    {{
      "question_no": <int>,
      "units": [<int>, ...],
      "marks": <int>,
      "question_type": "<mcq|descriptive>",
      "nature": "<basic concepts|application-based|case study|comparison|advanced topics|emerging trends>",
      "expected_bloom": ["<remember|understand|apply|analyze|evaluate|create>", ...],
      "is_or_pair": <true|false>,
      "or_pair_with": <int or null>
    }},
    ...
  ]
}}

RULES:
- question_type: "mcq" if the pattern says MCQ, multiple choice, objective, 1-mark, etc.
  Otherwise "descriptive" (short answer, long answer, essay, case study, etc.)
- "units" = unit numbers mentioned (e.g. "Unit 3" → [3], "Unit 1 & 2" → [1, 2])
  If no unit is specified, distribute evenly: use [1] for odd questions, [2] for even, etc.
- If "Q1 or Q2" appears, set is_or_pair=true for BOTH and set or_pair_with to the paired question number
- expected_bloom: infer from nature and marks. MCQ → [remember, understand]. High-mark descriptive → [analyze, evaluate, create]
- nature: map to the closest of: basic concepts, application-based, case study, comparison, advanced topics, emerging trends
- Output ONLY valid JSON. No markdown fences.
"""


# ─── PDF text extraction ────────────────────────────────────────────────────────

def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract plain text from a PDF byte stream using pypdf."""
    try:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        texts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                texts.append(t.strip())
        return "\n".join(texts)
    except ImportError:
        raise RuntimeError("pypdf not installed. Run: pip install pypdf")
    except Exception as e:
        raise RuntimeError(f"PDF extraction failed: {e}")


# ─── LLM call ──────────────────────────────────────────────────────────────────

async def _call_llm(prompt: str) -> str:
    """Call OpenAI GPT for pattern interpretation."""
    from generation.gpt_client import call_gpt
    return await call_gpt(prompt, temperature=0.1, max_tokens=1500)


def _extract_json(raw: str) -> dict:
    """Extract JSON object from raw LLM response."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON object found in LLM response: {raw[:200]}")
    return json.loads(raw[start:end])


# ─── Main entry point ──────────────────────────────────────────────────────────

async def interpret_pattern(
    pattern_text: str,
    total_marks: int,
) -> ParsedPattern:
    """
    Step 1: Interpret exam pattern text → structured ParsedPattern.
    Detects question_type (mcq or descriptive) from the pattern text.
    """
    prompt = PATTERN_INTERPRETER_PROMPT.format(
        pattern_text=pattern_text.strip(),
        total_marks=total_marks,
    )

    raw = await _call_llm(prompt)

    try:
        data = _extract_json(raw)
    except Exception as e:
        raise ValueError(f"Pattern interpreter returned invalid JSON: {e}\nRaw: {raw[:500]}")

    questions = []
    for q in data.get("questions", []):
        raw_type = str(q.get("question_type", "descriptive")).lower().strip()
        # Normalise question_type: accept mcq, multiple choice, objective → "mcq"
        q_type = "mcq" if any(k in raw_type for k in ["mcq", "multiple", "objective", "1 mark", "one mark"]) else "descriptive"

        questions.append(ParsedQuestion(
            question_no=int(q.get("question_no", 0)),
            units=[int(u) for u in q.get("units", [])],
            marks=int(q.get("marks", 0)),
            nature=q.get("nature"),
            question_type=q_type,
            expected_bloom=q.get("expected_bloom") or [],
            is_or_pair=bool(q.get("is_or_pair", False)),
            or_pair_with=q.get("or_pair_with"),
        ))

    return ParsedPattern(
        total_marks=data.get("total_marks", total_marks),
        questions=questions,
    )


async def interpret_pattern_from_pdf(
    pdf_bytes: bytes,
    total_marks: int,
) -> ParsedPattern:
    """Extract text from PDF then interpret."""
    text = extract_pdf_text(pdf_bytes)
    if not text.strip():
        raise ValueError("Could not extract text from uploaded PDF.")
    return await interpret_pattern(text, total_marks)

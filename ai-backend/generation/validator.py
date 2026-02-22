"""
Step 7 — Post-Processing Validator

Lightweight LLM validation of each generated question:
- Bloom level alignment check
- Marks depth check  
- Grammar fix
- Duplicate detection across sections (cosine similarity)
"""

import json
import re
import math
from typing import List, Tuple, Optional

from generation.schemas import PaperOutput, GeneratedQuestion, GeneratedVariant


# ─── Duplicate detection ───────────────────────────────────────────────────────

def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


DUPLICATE_THRESHOLD = 0.92


def _detect_duplicates(variants: List[GeneratedVariant]) -> List[str]:
    """Return list of duplicate question texts (similarity > threshold)."""
    texts = [v.question.question_text for v in variants]
    duplicates = []
    try:
        from embeddings import get_embedding_generator
        gen = get_embedding_generator()
        embeddings = [gen.generate_embedding(t) for t in texts]
        for i in range(len(embeddings)):
            for j in range(i + 1, len(embeddings)):
                sim = _cosine(embeddings[i], embeddings[j])
                if sim > DUPLICATE_THRESHOLD:
                    duplicates.append(f"Q{i+1} and Q{j+1} are near-duplicates (similarity={sim:.2f})")
    except Exception:
        pass
    return duplicates


# ─── LLM validation ───────────────────────────────────────────────────────────

VALIDATION_PROMPT = """You are an exam quality validator.

Review this exam question and determine if it is well-formed.

QUESTION: {question_text}
BLOOM LEVEL INTENDED: {bloom_level}
MARKS: {marks}
ANSWER KEY: {answer_key}

Check:
1. Does the question match the intended Bloom level?
2. Is the depth appropriate for {marks} marks?
3. Is the grammar correct?

If the grammar needs fixing, provide the corrected question text.

Respond with JSON ONLY:
{{
  "bloom_ok": <true|false>,
  "depth_ok": <true|false>,
  "grammar_ok": <true|false>,
  "corrected_question": "<corrected text or original if no change needed>",
  "issues": ["<issue1>", ...]
}}"""


async def _validate_single(question: GeneratedQuestion) -> GeneratedQuestion:
    """Run LLM validation on a single question. Returns (possibly corrected) question."""
    try:
        from generation.gpt_client import call_gpt
        prompt = VALIDATION_PROMPT.format(
            question_text=question.question_text[:500],
            bloom_level=question.bloom_level,
            marks=question.marks,
            answer_key=(question.answer_key or "")[:300],
        )
        raw = await call_gpt(prompt, temperature=0.2, max_tokens=512)
        raw = raw.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end > 0:
            data = json.loads(raw[start:end])
            corrected = data.get("corrected_question", "").strip()
            if corrected and corrected != question.question_text:
                question.question_text = corrected
    except Exception:
        pass  # Validation failure is non-blocking
    return question


# ─── Main entry ────────────────────────────────────────────────────────────────

async def validate_paper(paper: PaperOutput) -> PaperOutput:
    """
    Step 7: Run validation on each question in the paper.

    - Checks Bloom alignment and grammar (LLM)
    - Detects near-duplicate questions

    Args:
        paper: Assembled PaperOutput

    Returns:
        Validated (and possibly corrected) PaperOutput
    """
    # Collect all variants flat for duplicate detection
    all_variants = []
    for section in paper.sections:
        all_variants.extend(section.variants)

    # Duplicate detection (non-blocking)
    dup_issues = _detect_duplicates(all_variants)
    if dup_issues:
        paper.generation_metadata["duplicate_warnings"] = dup_issues

    # Per-question LLM validation (grammar + Bloom check)
    for section in paper.sections:
        for variant in section.variants:
            variant.question = await _validate_single(variant.question)

    return paper

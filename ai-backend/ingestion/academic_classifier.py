"""
Academic Classifier — Step 7 of the Ingestion Pipeline

Uses OpenAI GPT-3.5-turbo to classify each text chunk with:
  - section_type:    definition | example | derivation | exercise | explanation | summary
  - source_type:     syllabus | lecture_note | textbook | slide
  - blooms_level:    remember | understand | apply | analyze | evaluate | create
  - blooms_level_int: 1–6 (numeric for DB filtering)
  - difficulty:      easy | medium | hard
  - difficulty_score: 0.0–1.0 float

Why GPT-3.5 here:
  - Cost-effective for bulk ingestion ($0.001–0.002 per 1K input tokens)
  - Single structured JSON prompt per chunk → reliable output
  - Semantic awareness that rule-based heuristics cannot match

Design decisions:
  - Batched async: 10 chunks per API call via multi-message prompt
  - Non-blocking: failures return safe defaults, pipeline never stops
  - Only classifies TEXT-category chunks (skips table rows, code, etc.)
  - Default fallback: explanation / textbook / understand / 2 / medium / 0.5
"""

import asyncio
import json
import os
from dataclasses import dataclass
from typing import List, Optional

from openai import AsyncOpenAI

# ── Bloom's taxonomy numeric mapping ──────────────────────────────────────────
BLOOMS_TO_INT = {
    "remember": 1,
    "understand": 2,
    "apply": 3,
    "analyze": 4,
    "evaluate": 5,
    "create": 6,
}

DIFFICULTY_TO_SCORE = {
    "easy": 0.2,
    "medium": 0.5,
    "hard": 0.85,
}

VALID_SECTION_TYPES = {"definition", "example", "derivation", "exercise", "explanation", "summary"}
VALID_SOURCE_TYPES = {"syllabus", "lecture_note", "textbook", "slide"}
VALID_BLOOMS = set(BLOOMS_TO_INT.keys())
VALID_DIFFICULTIES = set(DIFFICULTY_TO_SCORE.keys())

# ── Safe defaults (used when classification fails) ────────────────────────────
DEFAULT_CLASSIFICATION = {
    "section_type": "explanation",
    "source_type": "textbook",
    "blooms_level": "understand",
    "blooms_level_int": 2,
    "difficulty": "medium",
    "difficulty_score": 0.5,
}

# ── Configuration ─────────────────────────────────────────────────────────────
CLASSIFICATION_BATCH_SIZE = 10   # chunks per API call
MAX_CHUNK_TEXT_CHARS = 600       # truncate very long chunks for cost control
MODEL = "gpt-3.5-turbo"
MAX_RETRIES = 2


@dataclass
class ChunkClassification:
    """Classification result for one chunk."""
    section_type: str
    source_type: str
    blooms_level: str
    blooms_level_int: int
    difficulty: str
    difficulty_score: float


def _truncate(text: str, max_chars: int = MAX_CHUNK_TEXT_CHARS) -> str:
    """Truncate text to limit token cost."""
    if not text:
        return ""
    t = text.strip()
    return t[:max_chars] + ("…" if len(t) > max_chars else "")


def _safe_classification(raw: dict) -> ChunkClassification:
    """
    Parse raw dict from LLM into ChunkClassification with validation.
    Falls back to defaults on any invalid value.
    """
    section_type = raw.get("section_type", "")
    if section_type not in VALID_SECTION_TYPES:
        section_type = DEFAULT_CLASSIFICATION["section_type"]

    source_type = raw.get("source_type", "")
    if source_type not in VALID_SOURCE_TYPES:
        source_type = DEFAULT_CLASSIFICATION["source_type"]

    blooms_level = raw.get("blooms_level", "")
    if blooms_level not in VALID_BLOOMS:
        blooms_level = DEFAULT_CLASSIFICATION["blooms_level"]
    blooms_level_int = BLOOMS_TO_INT.get(blooms_level, DEFAULT_CLASSIFICATION["blooms_level_int"])

    difficulty = raw.get("difficulty", "")
    if difficulty not in VALID_DIFFICULTIES:
        difficulty = DEFAULT_CLASSIFICATION["difficulty"]
    difficulty_score = DIFFICULTY_TO_SCORE.get(difficulty, DEFAULT_CLASSIFICATION["difficulty_score"])

    # Allow LLM to override difficulty_score if it's a valid float in [0,1]
    raw_score = raw.get("difficulty_score")
    if isinstance(raw_score, (int, float)):
        clamped = max(0.0, min(1.0, float(raw_score)))
        difficulty_score = round(clamped, 3)

    return ChunkClassification(
        section_type=section_type,
        source_type=source_type,
        blooms_level=blooms_level,
        blooms_level_int=blooms_level_int,
        difficulty=difficulty,
        difficulty_score=difficulty_score,
    )


def _default_classification() -> ChunkClassification:
    return ChunkClassification(**DEFAULT_CLASSIFICATION)


_SYSTEM_PROMPT = """You are an academic content classifier for an exam question generation system.

Given text chunks from academic documents, classify EACH chunk and return a JSON array.
For EACH chunk return exactly this JSON object:
{
  "section_type": "<definition|example|derivation|exercise|explanation|summary>",
  "source_type":  "<syllabus|lecture_note|textbook|slide>",
  "blooms_level": "<remember|understand|apply|analyze|evaluate|create>",
  "blooms_level_int": <1-6>,
  "difficulty":   "<easy|medium|hard>",
  "difficulty_score": <0.0-1.0>
}

Rules:
- section_type: Is this a definition of a term? An example? A derivation/proof? An exercise/question? A general explanation? A summary?
- source_type: Does it look like a syllabus outline, lecture slide, textbook paragraph, or lecture notes?
- blooms_level: What cognitive level does understanding this chunk require?
  1=remember (recall fact), 2=understand (explain), 3=apply (use in problem), 
  4=analyze (break down, compare), 5=evaluate (judge, critique), 6=create (design, formulate)
- difficulty: easy=recall/basic comprehension, medium=requires understanding, hard=requires analysis/application
- difficulty_score: 0.0=very easy, 1.0=very hard (float)

Return ONLY a JSON array with one object per input chunk. No explanation, no markdown.
Example for 2 chunks: [{"section_type":"definition","source_type":"textbook","blooms_level":"remember","blooms_level_int":1,"difficulty":"easy","difficulty_score":0.15}, {...}]"""


async def _classify_batch(
    client: AsyncOpenAI,
    texts: List[str],
) -> List[ChunkClassification]:
    """
    Classify a batch of chunk texts via a single GPT-3.5 call.
    Returns list of ChunkClassification (one per input, same order).
    Falls back to defaults for the whole batch on any error.
    """
    if not texts:
        return []

    # Build numbered user message
    numbered = "\n\n".join(
        f"[Chunk {i+1}]\n{_truncate(t)}"
        for i, t in enumerate(texts)
    )
    user_msg = f"Classify these {len(texts)} academic chunk(s):\n\n{numbered}"

    for attempt in range(MAX_RETRIES):
        try:
            response = await client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.1,
                max_tokens=150 * len(texts),  # ~150 tokens per chunk result
                response_format={"type": "json_object"} if len(texts) == 1 else None,
            )
            content = response.choices[0].message.content.strip()

            # Parse JSON array
            # LLM sometimes wraps with a key — handle both cases
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                # Try common wrapper keys
                for key in ("results", "chunks", "classifications", "data"):
                    if key in parsed and isinstance(parsed[key], list):
                        parsed = parsed[key]
                        break
                else:
                    # Single object for single chunk
                    parsed = [parsed]

            if not isinstance(parsed, list):
                raise ValueError(f"Expected JSON array, got {type(parsed)}")

            # Pad or truncate to match input count
            while len(parsed) < len(texts):
                parsed.append({})

            return [_safe_classification(item) for item in parsed[: len(texts)]]

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(1.0 * (attempt + 1))
            else:
                print(f"   [AcademicClassifier] Batch failed after {MAX_RETRIES} attempts: {e}")
                return [_default_classification() for _ in texts]

    return [_default_classification() for _ in texts]


async def classify_chunks(
    chunk_texts: List[str],
    categories: Optional[List[str]] = None,
) -> List[ChunkClassification]:
    """
    Classify a list of chunk texts using GPT-3.5.

    Args:
        chunk_texts: List of chunk text strings to classify.
        categories:  Optional parallel list of element categories (e.g. 'TEXT', 'TABLE').
                     Only TEXT chunks are classified; others get defaults immediately.

    Returns:
        List of ChunkClassification objects (same length and order as chunk_texts).
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("   [AcademicClassifier] OPENAI_API_KEY not set — using defaults for all chunks")
        return [_default_classification() for _ in chunk_texts]

    client = AsyncOpenAI(api_key=api_key)

    # Identify which chunks need actual classification (TEXT only)
    needs_classify: List[int] = []   # indices into chunk_texts
    for i, text in enumerate(chunk_texts):
        cat = (categories[i] if categories and i < len(categories) else "TEXT") or "TEXT"
        if cat.upper() == "TEXT" and text and text.strip():
            needs_classify.append(i)

    # Pre-fill all results with defaults
    results: List[ChunkClassification] = [_default_classification() for _ in chunk_texts]

    if not needs_classify:
        return results

    print(f"   [AcademicClassifier] Classifying {len(needs_classify)}/{len(chunk_texts)} TEXT chunks...")

    # Split into batches of CLASSIFICATION_BATCH_SIZE
    batches: List[List[int]] = [
        needs_classify[i: i + CLASSIFICATION_BATCH_SIZE]
        for i in range(0, len(needs_classify), CLASSIFICATION_BATCH_SIZE)
    ]

    # Run all batches concurrently (rate-limit: at most 5 concurrent)
    semaphore = asyncio.Semaphore(5)

    async def _run_batch(indices: List[int]) -> List[tuple]:
        async with semaphore:
            texts = [chunk_texts[idx] for idx in indices]
            classifications = await _classify_batch(client, texts)
            return list(zip(indices, classifications))

    batch_tasks = [_run_batch(batch) for batch in batches]
    batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

    for batch_result in batch_results:
        if isinstance(batch_result, Exception):
            print(f"   [AcademicClassifier] Batch gather error: {batch_result}")
            continue
        for idx, classification in batch_result:
            results[idx] = classification

    classified_count = sum(
        1 for i in needs_classify
        if results[i].blooms_level != DEFAULT_CLASSIFICATION["blooms_level"]
        or results[i].section_type != DEFAULT_CLASSIFICATION["section_type"]
    )
    print(f"   [AcademicClassifier] Done — {classified_count}/{len(needs_classify)} non-default results")

    return results

"""
Step 2 — Blueprint Builder

Converts a ParsedPattern into a BlueprintSpec with QuestionSpec objects.
Maps question nature → Bloom taxonomy targets (deterministic, no LLM).

KEY FIX: The pattern interpreter returns unit numbers like [1, 2, 3] (relative
to the exam pattern), but the database stores units with their own primary-key
IDs (e.g., 41, 42, 43). This module resolves the mapping by loading the
subject's units from the DB, sorted by order, and mapping position → real ID.
"""

import logging
from typing import List, Optional, Dict

from sqlalchemy.orm import Session

from generation.schemas import ParsedPattern, ParsedQuestion, BlueprintSpec, QuestionSpec

log = logging.getLogger("generation.pipeline")


# ─── Nature → Bloom mapping (deterministic) ────────────────────────────────────

NATURE_TO_BLOOM: dict = {
    "basic concepts":      ["remember", "understand"],
    "basic":               ["remember", "understand"],
    "application-based":   ["apply"],
    "application":         ["apply"],
    "case study":          ["analyze"],
    "case-study":          ["analyze"],
    "comparison":          ["analyze", "evaluate"],
    "advanced topics":     ["evaluate", "create"],
    "advanced":            ["evaluate", "create"],
    "emerging trends":     ["create"],
    "emerging":            ["create"],
    "design":              ["create"],
    "evaluation":          ["evaluate"],
    "analysis":            ["analyze"],
}

# Bloom string normalisation (LLM may use variations)
BLOOM_ALIASES: dict = {
    "remember":      "remember",
    "recall":        "remember",
    "knowledge":     "remember",
    "understand":    "understand",
    "comprehend":    "understand",
    "comprehension": "understand",
    "apply":         "apply",
    "application":   "apply",
    "analyze":       "analyze",
    "analyse":       "analyze",
    "analysis":      "analyze",
    "evaluate":      "evaluate",
    "evaluation":    "evaluate",
    "create":        "create",
    "synthesis":     "create",
    "design":        "create",
}

DIFFICULTY_MAP = {
    "easy":   "easy",
    "medium": "medium",
    "hard":   "hard",
    "auto":   "medium",
}


def _normalise_bloom(raw: str) -> Optional[str]:
    return BLOOM_ALIASES.get(raw.strip().lower())


def _bloom_from_nature(nature: Optional[str]) -> List[str]:
    """Return Bloom targets for a given nature string."""
    if not nature:
        return ["remember", "understand"]
    key = nature.strip().lower()
    if key in NATURE_TO_BLOOM:
        return NATURE_TO_BLOOM[key]
    for pattern, blooms in NATURE_TO_BLOOM.items():
        if pattern in key or key in pattern:
            return blooms
    return ["understand", "apply"]


def _resolve_bloom(parsed_q: ParsedQuestion) -> List[str]:
    """
    Resolve Bloom targets for a question.
    Priority: explicit expected_bloom (from LLM) > nature mapping.
    """
    if parsed_q.expected_bloom:
        resolved = [_normalise_bloom(b) for b in parsed_q.expected_bloom]
        resolved = [b for b in resolved if b]
        if resolved:
            return resolved
    return _bloom_from_nature(parsed_q.nature)


def _build_unit_number_map(db: Session, subject_id: int) -> Dict[int, int]:
    """
    Build a mapping from pattern unit number (1-based position) → real DB unit ID.

    Units are ordered by their `order` column (ascending). So unit 1 in the
    pattern corresponds to the unit with the smallest order value, etc.

    Returns e.g. {1: 41, 2: 42, 3: 43}
    """
    from database.models import Unit
    units = (
        db.query(Unit)
        .filter(Unit.subject_id == subject_id)
        .order_by(Unit.order)
        .all()
    )
    mapping: Dict[int, int] = {}
    for position_1based, unit in enumerate(units, start=1):
        mapping[position_1based] = unit.id
    log.info(f"[STEP 2] Unit number→ID map for subject {subject_id}: {mapping}")
    return mapping


def _resolve_unit_ids(
    raw_unit_numbers: List[int],
    unit_map: Dict[int, int],
    all_unit_ids: List[int],
) -> List[int]:
    """
    Convert pattern unit numbers like [1, 2] to real DB unit IDs like [41, 42].

    Falls back to all unit IDs if the map is empty or number is out of range.
    """
    if not unit_map:
        # No units in DB — return empty so retrieval does subject-wide fallback
        return []

    resolved = []
    for num in raw_unit_numbers:
        if num in unit_map:
            resolved.append(unit_map[num])
        else:
            # Number out of range (e.g. pattern says unit 5 but only 3 exist)
            # Map to the last unit
            last_id = unit_map[max(unit_map.keys())]
            resolved.append(last_id)
            log.warning(f"[STEP 2] Unit number {num} out of range, mapped to last unit ID {last_id}")

    return list(dict.fromkeys(resolved))  # deduplicate preserving order


def build_blueprint(
    parsed: ParsedPattern,
    subject_id: int,
    difficulty_pref: Optional[str] = None,
    db: Optional[Session] = None,
) -> BlueprintSpec:
    """
    Step 2: Convert ParsedPattern → BlueprintSpec.

    - Maps pattern unit numbers (1, 2, 3) → real DB unit IDs (41, 42, 43)
    - Maps nature → Bloom if bloom not explicitly given
    - Applies global difficulty preference if not per-question
    - Preserves OR-pair linkage (is_or_pair / or_pair_with)

    Args:
        parsed: Output of Step 1 (pattern interpreter)
        subject_id: Target subject ID
        difficulty_pref: Optional global difficulty override
        db: SQLAlchemy session (needed for unit ID resolution)

    Returns:
        BlueprintSpec ready for retrieval and generation
    """
    global_difficulty = DIFFICULTY_MAP.get(
        (difficulty_pref or "auto").lower(), "medium"
    )

    # Build unit number → real DB ID mapping
    unit_map: Dict[int, int] = {}
    all_unit_ids: List[int] = []
    if db is not None:
        unit_map = _build_unit_number_map(db, subject_id)
        all_unit_ids = list(unit_map.values())

    specs: List[QuestionSpec] = []
    for pq in parsed.questions:
        bloom_targets = _resolve_bloom(pq)

        # Resolve raw unit numbers → actual DB unit IDs
        if pq.units and unit_map:
            real_unit_ids = _resolve_unit_ids(pq.units, unit_map, all_unit_ids)
        elif unit_map:
            # No units specified in pattern — use all units
            real_unit_ids = all_unit_ids
        else:
            # No DB session or no units in DB — keep raw numbers as-is
            real_unit_ids = pq.units or []

        specs.append(QuestionSpec(
            question_no=pq.question_no,
            units=real_unit_ids,
            marks=pq.marks,
            bloom_targets=bloom_targets,
            difficulty=global_difficulty,
            nature=pq.nature,
            question_type=pq.question_type,
            is_or_pair=pq.is_or_pair,
            or_pair_with=pq.or_pair_with,
        ))

    return BlueprintSpec(
        subject_id=subject_id,
        total_marks=parsed.total_marks,
        questions=specs,
    )

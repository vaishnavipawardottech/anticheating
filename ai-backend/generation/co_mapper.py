"""
Step 5 — CO (Course Outcome) Mapper

Maps unit_id → CO label from the units table.
Falls back gracefully if no mapping exists.
"""

from typing import List, Optional, Dict
from sqlalchemy.orm import Session

from database.models import Unit


# ─── Default CO map (can be overridden per subject) ───────────────────────────

# Unit order (1-indexed) → CO label
# This is a positional default: Unit 1 → CO1, Unit 2 → CO2, etc.
def _build_default_co_map(db: Session, subject_id: int) -> Dict[int, str]:
    """
    Build CO map from units table: unit.order → CO<n>.
    Unit with order=0 → CO1, order=1 → CO2, etc.
    Also maps by unit.id directly.
    """
    units = db.query(Unit).filter(Unit.subject_id == subject_id).order_by(Unit.order).all()
    co_map: Dict[int, str] = {}
    for idx, unit in enumerate(units, start=1):
        co_label = f"CO{idx}"
        co_map[unit.id] = co_label
    return co_map


def map_co(unit_ids: List[int], db: Session, subject_id: int) -> str:
    """
    Step 5: Map a list of unit IDs to a CO label.

    Uses the primary unit_id (first in list) for CO lookup.
    Falls back to 'CO1' if not found.

    Args:
        unit_ids: List of unit IDs from the question spec
        db: Database session
        subject_id: Subject ID to scope the lookup

    Returns:
        CO label string, e.g. "CO3"
    """
    if not unit_ids:
        return "CO1"

    co_map = _build_default_co_map(db, subject_id)
    primary_unit_id = unit_ids[0]

    if primary_unit_id in co_map:
        return co_map[primary_unit_id]

    # Fallback: return CO{min(unit_ids)}
    return f"CO{min(unit_ids)}"


def get_co_map_for_subject(db: Session, subject_id: int) -> Dict[int, str]:
    """
    Return the full unit_id → CO label map for a subject.
    Used by the frontend to display CO information.
    """
    return _build_default_co_map(db, subject_id)

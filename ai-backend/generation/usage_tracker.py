"""
Step 8 — Usage Tracker

Increments usage_count on DocumentChunk rows that were used in generation.
Prevents repetition in future papers.
"""

from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import text


def increment_usage(db: Session, chunk_ids: List[int]) -> None:
    """
    Step 8: Increment usage_count for each chunk_id used in paper generation.

    Args:
        db: Database session
        chunk_ids: List of chunk IDs that were used as context for generation
    """
    if not chunk_ids:
        return
    try:
        db.execute(
            text(
                "UPDATE document_chunks SET usage_count = usage_count + 1 "
                "WHERE id = ANY(:ids)"
            ),
            {"ids": chunk_ids},
        )
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[UsageTracker] Failed to update usage_count: {e}")


def collect_used_chunk_ids(paper) -> List[int]:
    """
    Extract all chunk IDs used across a generated paper.

    Args:
        paper: PaperOutput object

    Returns:
        Deduplicated list of chunk IDs
    """
    chunk_ids = set()
    for section in paper.sections:
        for variant in section.variants:
            for cid in variant.question.source_chunk_ids or []:
                chunk_ids.add(cid)
    return list(chunk_ids)

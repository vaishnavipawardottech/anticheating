"""
Concept-centric context pack for Layer 3 question generation.
Fetches aligned chunks per concept, diversifies with MMR (maximal marginal relevance), caps at 3–8 chunks.
"""

from typing import List, Optional
from dataclasses import dataclass
from sqlalchemy.orm import Session

from database.models import DocumentChunk, Document, Concept


# Default alignment threshold; chunks below this are not used for generation
DEFAULT_ALIGNMENT_THRESHOLD = 0.65
MIN_CHUNKS = 3
MAX_CHUNKS = 8
# MMR: balance relevance vs diversity (1.0 = only relevance, 0.0 = only diversity)
MMR_LAMBDA = 0.6


@dataclass
class ChunkWithMeta:
    id: int
    text: str
    document_id: int
    section_path: Optional[str]
    page_start: Optional[int]
    page_end: Optional[int]
    alignment_confidence: Optional[float]
    embedding_vector: Optional[List[float]]


def _cosine_sim(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _mmr_select(
    chunks: List[ChunkWithMeta],
    max_count: int,
    lambda_relevance: float = MMR_LAMBDA,
) -> List[ChunkWithMeta]:
    """
    Maximal marginal relevance: iteratively pick the chunk that maximizes
    lambda * relevance - (1 - lambda) * max_similarity_to_selected.
    Relevance = alignment_confidence (normalized 0–1). Diversity = max sim to already selected.
    """
    if not chunks or max_count <= 0:
        return []
    # Normalize relevance to 0–1 (confidence is already 0–1)
    for c in chunks:
        if c.alignment_confidence is None:
            c.alignment_confidence = 0.5
    selected: List[ChunkWithMeta] = []
    remaining = list(chunks)
    has_embeddings = remaining[0].embedding_vector is not None and len(remaining[0].embedding_vector or []) > 0

    while len(selected) < max_count and remaining:
        best_idx = -1
        best_score = -1.0
        for i, c in enumerate(remaining):
            rel = (c.alignment_confidence or 0.0)
            if not has_embeddings or not c.embedding_vector:
                # No embeddings: use only relevance (confidence), take in order
                score = rel
            else:
                max_sim = 0.0
                for s in selected:
                    if s.embedding_vector:
                        sim = _cosine_sim(c.embedding_vector, s.embedding_vector)
                        max_sim = max(max_sim, sim)
                score = lambda_relevance * rel - (1.0 - lambda_relevance) * max_sim
            if score > best_score:
                best_score = score
                best_idx = i
        if best_idx < 0:
            break
        selected.append(remaining.pop(best_idx))
    return selected


def get_concept_context_pack(
    db: Session,
    concept_id: int,
    subject_id: int,
    alignment_threshold: float = DEFAULT_ALIGNMENT_THRESHOLD,
    min_chunks: int = MIN_CHUNKS,
    max_chunks: int = MAX_CHUNKS,
) -> tuple[List[ChunkWithMeta], Optional[Concept]]:
    """
    For a given concept_id, fetch chunks where alignment_confidence >= threshold,
    diversify with MMR, return 3–8 chunks (concept context pack) and the concept.
    """
    concept = db.query(Concept).filter(
        Concept.id == concept_id,
        Concept.unit.has(subject_id=subject_id),
    ).first()
    if not concept:
        return [], None

    chunks_q = (
        db.query(DocumentChunk)
        .join(Document, DocumentChunk.document_id == Document.id)
        .filter(
            Document.subject_id == subject_id,
            DocumentChunk.concept_id == concept_id,
            DocumentChunk.alignment_confidence >= alignment_threshold,
        )
        .order_by(DocumentChunk.alignment_confidence.desc().nullslast())
        .limit(50)  # candidate pool
    )
    rows = chunks_q.all()
    if not rows:
        return [], concept

    with_meta = [
        ChunkWithMeta(
            id=c.id,
            text=(c.text or "").strip(),
            document_id=c.document_id,
            section_path=c.section_path,
            page_start=c.page_start,
            page_end=c.page_end,
            alignment_confidence=c.alignment_confidence,
            embedding_vector=c.embedding_vector if isinstance(c.embedding_vector, list) else None,
        )
        for c in rows
        if (c.text or "").strip()
    ]
    if not with_meta:
        return [], concept

    selected = _mmr_select(with_meta, max_chunks, MMR_LAMBDA)
    if len(selected) < min_chunks and len(with_meta) >= len(selected):
        selected_ids = {c.id for c in selected}
        extra = [c for c in with_meta if c.id not in selected_ids][: min_chunks - len(selected)]
        selected = selected + extra
    return selected[:max_chunks], concept


def format_context_pack_for_prompt(chunks: List[ChunkWithMeta]) -> str:
    """Format context pack as text with chunk IDs for the generator prompt."""
    parts = []
    for c in chunks:
        parts.append(f"[Chunk ID: {c.id}]\n{c.text}")
    return "\n\n---\n\n".join(parts)

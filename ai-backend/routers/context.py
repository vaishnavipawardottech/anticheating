"""
Context builder for RAG / question generation.
Retrieves chunks, optionally adds neighbors, dedupes, caps token budget, returns context + citations.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from database.database import get_db
from database.models import DocumentChunk, Document
from embeddings import get_embedding_generator
from embeddings.qdrant_manager import get_qdrant_manager

router = APIRouter(prefix="/context", tags=["context"])

# Rough tokens: words * 1.3
def _approx_tokens(text: str) -> int:
    if not text or not text.strip():
        return 0
    return int(len(text.split()) * 1.3)


class ContextBuildRequest(BaseModel):
    """Request to build coherent context for generation."""
    subject_id: int = Field(..., description="Subject ID")
    query: Optional[str] = Field(None, description="Natural language query (for semantic retrieval)")
    unit_id: Optional[int] = Field(None, description="Filter by unit")
    concept_ids: Optional[List[int]] = Field(None, description="Filter by concept IDs")
    top_k: int = Field(15, ge=1, le=50, description="Max chunks to retrieve")
    include_neighbors: bool = Field(True, description="Include chunk_index ± 1 from same document")
    max_tokens: int = Field(4000, ge=500, le=16000, description="Cap total context tokens")
    min_score: float = Field(0.3, ge=0.0, le=1.0, description="Min similarity score when using query")


class Citation(BaseModel):
    chunk_id: int
    page_start: Optional[int]
    page_end: Optional[int]
    document_filename: Optional[str]


class ContextBuildResponse(BaseModel):
    context_text: str
    citations: List[Citation]
    total_tokens: int


async def build_context_impl(
    subject_id: int,
    db: Session,
    query: Optional[str] = None,
    unit_id: Optional[int] = None,
    concept_ids: Optional[List[int]] = None,
    top_k: int = 15,
    include_neighbors: bool = True,
    max_tokens: int = 4000,
    min_score: float = 0.3,
) -> ContextBuildResponse:
    """
    Internal: build context (used by route and by exams router).
    """
    qdrant = get_qdrant_manager()
    chunk_ids_and_scores: List[tuple] = []  # (chunk_id, score or 1.0)

    if query:
        gen = get_embedding_generator()
        query_vector = gen.generate_embedding(query)
        raw = qdrant.search(
            query_vector=query_vector,
            limit=top_k,
            subject_id=subject_id,
            unit_id=unit_id,
            concept_ids=concept_ids,
            score_threshold=min_score,
        )
        for r in raw:
            if r.get("point_type") == "chunk" and r.get("chunk_id") is not None:
                chunk_ids_and_scores.append((r["chunk_id"], r.get("score", 0.0)))
    else:
        chunks_q = db.query(DocumentChunk).join(Document, DocumentChunk.document_id == Document.id).filter(
            Document.subject_id == subject_id
        )
        if unit_id is not None:
            chunks_q = chunks_q.filter(DocumentChunk.unit_id == unit_id)
        if concept_ids:
            chunks_q = chunks_q.filter(DocumentChunk.concept_id.in_(concept_ids))
        chunks_q = chunks_q.order_by(DocumentChunk.document_id, DocumentChunk.chunk_index).limit(top_k)
        chunks_from_db = chunks_q.all()
        chunk_ids_and_scores = [(c.id, 1.0) for c in chunks_from_db]

    if not chunk_ids_and_scores:
        return ContextBuildResponse(context_text="", citations=[], total_tokens=0)

    ids_seen = set()
    ordered_chunk_ids: List[int] = []
    for cid, _ in chunk_ids_and_scores:
        if cid not in ids_seen:
            ids_seen.add(cid)
            ordered_chunk_ids.append(cid)

    if include_neighbors:
        chunks = db.query(DocumentChunk).filter(DocumentChunk.id.in_(ordered_chunk_ids)).all()
        by_doc = {}
        for c in chunks:
            by_doc.setdefault(c.document_id, []).append(c)
        extra_ids = set()
        for c in chunks:
            same_doc = by_doc.get(c.document_id, [])
            for other in same_doc:
                if abs(other.chunk_index - c.chunk_index) <= 1 and other.id not in ids_seen:
                    extra_ids.add(other.id)
        for cid in extra_ids:
            if cid not in ids_seen:
                ordered_chunk_ids.append(cid)
                ids_seen.add(cid)

    # Load chunks in order and build text + citations until max_tokens
    chunks_in_order = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.id.in_(ordered_chunk_ids))
        .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
        .all()
    )
    id_to_chunk = {c.id: c for c in chunks_in_order}
    ordered = [id_to_chunk[cid] for cid in ordered_chunk_ids if cid in id_to_chunk]
    docs = {d.id: d for d in db.query(Document).filter(Document.id.in_({c.document_id for c in ordered})).all()}

    parts = []
    citations = []
    total_tokens = 0
    for c in ordered:
        if total_tokens >= max_tokens:
            break
        text = (c.text or "").strip()
        if not text:
            continue
        tok = _approx_tokens(text)
        if total_tokens + tok > max_tokens:
            remain = max_tokens - total_tokens
            words = text.split()
            keep_words = max(0, int(remain / 1.3))
            text = " ".join(words[:keep_words])
            tok = _approx_tokens(text)
        parts.append(text)
        total_tokens += tok
        doc = docs.get(c.document_id)
        citations.append(Citation(
            chunk_id=c.id,
            page_start=c.page_start,
            page_end=c.page_end,
            document_filename=doc.filename if doc else None,
        ))

    context_text = "\n\n---\n\n".join(parts)
    return ContextBuildResponse(
        context_text=context_text,
        citations=citations,
        total_tokens=total_tokens,
    )


@router.post("/build", response_model=ContextBuildResponse)
async def build_context(request: ContextBuildRequest, db: Session = Depends(get_db)):
    """
    Build a coherent context pack for RAG/question generation.
    """
    return await build_context_impl(
        subject_id=request.subject_id,
        db=db,
        query=request.query,
        unit_id=request.unit_id,
        concept_ids=request.concept_ids,
        top_k=request.top_k,
        include_neighbors=request.include_neighbors,
        max_tokens=request.max_tokens,
        min_score=request.min_score,
    )

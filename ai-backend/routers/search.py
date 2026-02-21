"""
Search Router - Semantic and Hybrid Search
- Semantic: vector search (Qdrant) over chunks.
- Hybrid: Postgres FTS (BM25-ish) + Qdrant vector, merge scores (RRF), optional rerank.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, Field
import time
import re

from database.database import get_db
from database.models import ParsedElement, Document, DocumentChunk
from embeddings import get_embedding_generator
from embeddings.qdrant_manager import get_qdrant_manager

router = APIRouter(prefix="/search", tags=["search"])

# RRF constant (reciprocal rank fusion): 1/(k + rank)
RRF_K = 60


# Request/Response Schemas
class SemanticSearchRequest(BaseModel):
    """Request schema for semantic search"""
    query: str = Field(..., description="Natural language search query", min_length=1)
    subject_id: int = Field(..., description="Subject ID to search within")
    category: Optional[str] = Field(None, description="Filter by category (TEXT, DIAGRAM, TABLE, CODE, CHUNK, OTHER)")
    document_id: Optional[int] = Field(None, description="Filter by specific document ID")
    unit_id: Optional[int] = Field(None, description="Filter by unit (chunks only)")
    concept_ids: Optional[List[int]] = Field(None, description="Filter by concept IDs (chunks only)")
    section_path_prefix: Optional[str] = Field(None, description="Exact section_path match (chunks only)")
    limit: int = Field(10, description="Maximum number of results", ge=1, le=100)
    min_score: float = Field(0.0, description="Minimum similarity score (0-1)", ge=0.0, le=1.0)


class HybridSearchRequest(BaseModel):
    """Request for hybrid FTS + vector search with optional rerank and academic filters"""
    query: str = Field(..., description="Search query (natural language or keywords)", min_length=1)
    subject_id: int = Field(..., description="Subject ID to search within")
    document_id: Optional[int] = Field(None, description="Filter by document")
    limit: int = Field(10, description="Final number of results", ge=1, le=100)
    use_fts: bool = Field(True, description="Include Postgres full-text search")
    use_vector: bool = Field(True, description="Include Qdrant vector search")
    rerank_top_n: Optional[int] = Field(None, description="Rerank top N after merge (e.g. 30→8); None = no rerank")
    # ── Academic filters (Step 7 classification) ──
    blooms_level_int_min: Optional[int] = Field(None, description="Minimum Bloom level (1=remember .. 6=create)", ge=1, le=6)
    blooms_level_int_max: Optional[int] = Field(None, description="Maximum Bloom level (1=remember .. 6=create)", ge=1, le=6)
    difficulty: Optional[str] = Field(None, description="Difficulty filter: easy | medium | hard")
    section_type: Optional[str] = Field(None, description="Section type filter: definition | example | derivation | exercise | explanation | summary")
    max_usage_count: Optional[int] = Field(None, description="Exclude chunks used more than this many times", ge=0)


class SearchResult(BaseModel):
    """Single search result (chunk or element)"""
    element_id: int
    score: float
    text: str
    category: str
    page_number: Optional[int]
    document_id: int
    document_filename: str
    subject_id: int
    section_path: Optional[str] = None
    # Academic classification fields (populated for chunks)
    blooms_level: Optional[str] = None
    difficulty: Optional[str] = None
    section_type: Optional[str] = None
    usage_count: Optional[int] = None
    # Score breakdown for debugging / tuning
    bm25_score: Optional[float] = None
    vector_score: Optional[float] = None
    rrf_score: Optional[float] = None


class SemanticSearchResponse(BaseModel):
    """Response schema for semantic search"""
    query: str
    total_results: int
    results: List[SearchResult]
    search_time_ms: float


@router.post("/semantic", response_model=SemanticSearchResponse)
async def semantic_search(
    request: SemanticSearchRequest,
    db: Session = Depends(get_db)
):
    """
    Semantic search using natural language queries
    
    Searches indexed document elements using vector similarity.
    Returns ranked results with relevance scores.
    
    Args:
        request: Search parameters (query, filters, limits)
        db: Database session
    
    Returns:
        Ranked search results with metadata
    
    Example:
        POST /search/semantic
        {
            "query": "What is virtual memory?",
            "subject_id": 1,
            "limit": 5
        }
    """
    start_time = time.time()
    
    try:
        # 1. Generate query embedding
        generator = get_embedding_generator()
        query_embedding = generator.generate_embedding(request.query)
        
        # 2. Search Qdrant (filters passed as named params)
        qdrant = get_qdrant_manager()
        qdrant_results = qdrant.search(
            query_vector=query_embedding,
            limit=request.limit,
            subject_id=request.subject_id,
            category=request.category,
            document_id=request.document_id,
            unit_id=request.unit_id,
            concept_ids=request.concept_ids,
            section_path=request.section_path_prefix,
            score_threshold=request.min_score
        )
        
        # 4. Enrich results with database data (elements or chunks)
        results = []
        for qr in qdrant_results:
            if qr.get("point_type") == "chunk" and qr.get("chunk_id") is not None:
                chunk = db.query(DocumentChunk).filter(DocumentChunk.id == qr["chunk_id"]).first()
                if not chunk:
                    continue
                document = db.query(Document).filter(Document.id == chunk.document_id).first()
                if not document:
                    continue
                results.append(SearchResult(
                    element_id=chunk.id,
                    score=qr["score"],
                    text=chunk.text or "",
                    category="CHUNK",
                    page_number=chunk.page_start,
                    document_id=document.id,
                    document_filename=document.filename,
                    subject_id=document.subject_id,
                    section_path=chunk.section_path,
                ))
            else:
                element = db.query(ParsedElement).filter(
                    ParsedElement.id == qr.get("element_id")
                ).first()
                if not element:
                    continue
                document = db.query(Document).filter(
                    Document.id == element.document_id
                ).first()
                if not document:
                    continue
                results.append(SearchResult(
                    element_id=element.id,
                    score=qr["score"],
                    text=element.text or "",
                    category=element.category,
                    page_number=element.page_number,
                    document_id=document.id,
                    document_filename=document.filename,
                    subject_id=document.subject_id,
                    section_path=getattr(element, "section_path", None),
                ))
        
        search_time = (time.time() - start_time) * 1000
        
        return SemanticSearchResponse(
            query=request.query,
            total_results=len(results),
            results=results,
            search_time_ms=round(search_time, 2)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )


def _rerank_by_keyword_overlap(query: str, chunk_ids: List[int], chunks_by_id: dict) -> List[int]:
    """Simple rerank: boost chunks that contain more query terms. Returns reordered chunk_ids."""
    if not query or not chunk_ids:
        return chunk_ids
    terms = set(re.findall(r"\w+", query.lower()))
    if not terms:
        return chunk_ids

    def score(cid: int) -> float:
        c = chunks_by_id.get(cid)
        if not c or not c.text:
            return 0.0
        text_lower = (c.text or "").lower()
        return sum(1 for t in terms if t in text_lower) / max(len(terms), 1)

    scored = [(cid, score(cid)) for cid in chunk_ids]
    scored.sort(key=lambda x: (-x[1], chunk_ids.index(x[0])))
    return [cid for cid, _ in scored]


@router.post("/hybrid", response_model=SemanticSearchResponse)
async def hybrid_search(
    request: HybridSearchRequest,
    db: Session = Depends(get_db),
):
    """
    Hybrid retrieval: Postgres full-text (BM25-ish) + Qdrant vector search.
    Merges scores with RRF (reciprocal rank fusion). Optionally rerank top-N by keyword overlap.
    Filter by doc/subject when possible.
    """
    start_time = time.time()
    query = request.query.strip()
    subject_id = request.subject_id
    document_id = request.document_id
    limit = request.limit
    rerank_n = request.rerank_top_n

    # 1) FTS: chunk ids and rank from Postgres (if search_vector column exists)
    fts_scores: dict = {}  # chunk_id -> RRF contribution
    try:
        if request.use_fts:
            q_escaped = query.replace("'", "''")

            # Build dynamic WHERE clauses for academic filters
            academic_clauses = []
            academic_params: dict = {"sid": subject_id, "q": q_escaped, "doc_id": document_id}

            if request.blooms_level_int_min is not None:
                academic_clauses.append("AND c.blooms_level_int >= :blooms_min")
                academic_params["blooms_min"] = request.blooms_level_int_min
            if request.blooms_level_int_max is not None:
                academic_clauses.append("AND c.blooms_level_int <= :blooms_max")
                academic_params["blooms_max"] = request.blooms_level_int_max
            if request.difficulty:
                academic_clauses.append("AND c.difficulty = :difficulty")
                academic_params["difficulty"] = request.difficulty
            if request.section_type:
                academic_clauses.append("AND c.section_type = :section_type")
                academic_params["section_type"] = request.section_type
            if request.max_usage_count is not None:
                academic_clauses.append("AND c.usage_count <= :max_usage")
                academic_params["max_usage"] = request.max_usage_count

            extra_where = " ".join(academic_clauses)

            sql = text(f"""
                SELECT c.id
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE d.subject_id = :sid
                AND c.search_vector @@ plainto_tsquery('english', :q)
                AND (:doc_id IS NULL OR c.document_id = :doc_id)
                {extra_where}
                ORDER BY ts_rank_cd(c.search_vector, plainto_tsquery('english', :q)) DESC
                LIMIT 100
            """)
            rows = db.execute(sql, academic_params).fetchall()
            for rank_1based, (cid,) in enumerate(rows, start=1):
                # RRF: 1/(k+rank)
                fts_scores[cid] = 1.0 / (RRF_K + rank_1based)
    except Exception:
        # search_vector column or trigger may not exist yet
        pass

    # 2) Vector: chunk ids and scores from Qdrant
    vector_scores: dict = {}
    if request.use_vector:
        try:
            gen = get_embedding_generator()
            query_vector = gen.generate_embedding(query)
            qdrant = get_qdrant_manager()
            raw = qdrant.search(
                query_vector=query_vector,
                limit=100,
                subject_id=subject_id,
                document_id=document_id,
                score_threshold=0.0,
            )
            print(f"   [HybridSearch] Qdrant returned {len(raw)} raw results")
            for rank_1based, r in enumerate(raw, start=1):
                if r.get("point_type") == "chunk" and r.get("chunk_id") is not None:
                    cid = r["chunk_id"]
                    # Academic filter fields are nested under r["metadata"] (Qdrant payload)
                    meta = r.get("metadata") or {}
                    if request.blooms_level_int_min is not None and (meta.get("blooms_level_int") or 0) < request.blooms_level_int_min:
                        continue
                    if request.blooms_level_int_max is not None and (meta.get("blooms_level_int") or 6) > request.blooms_level_int_max:
                        continue
                    if request.difficulty and meta.get("difficulty") != request.difficulty:
                        continue
                    if request.section_type and meta.get("section_type") != request.section_type:
                        continue
                    if request.max_usage_count is not None and (meta.get("usage_count") or 0) > request.max_usage_count:
                        continue
                    vector_scores[cid] = 1.0 / (RRF_K + rank_1based)
            print(f"   [HybridSearch] Vector candidates after filters: {len(vector_scores)}")
        except Exception as e:
            print(f"   [HybridSearch] Vector search error: {e}")

    # 3) Merge: RRF sum per chunk_id
    all_ids = set(fts_scores.keys()) | set(vector_scores.keys())
    merged = [(cid, fts_scores.get(cid, 0) + vector_scores.get(cid, 0)) for cid in all_ids]
    merged.sort(key=lambda x: -x[1])

    # Build lookup: chunk_id → (rrf_score, bm25_rrf, vector_rrf)
    scores_map: dict = {
        cid: {
            "rrf": fts_scores.get(cid, 0) + vector_scores.get(cid, 0),
            "bm25": round(fts_scores.get(cid, 0), 6),
            "vector": round(vector_scores.get(cid, 0), 6),
        }
        for cid in all_ids
    }

    ordered_chunk_ids = [cid for cid, _ in merged[: limit * 3]]

    # 4) Optional rerank: take top rerank_n, rerank by keyword overlap, then top limit
    if rerank_n and ordered_chunk_ids:
        top_for_rerank = ordered_chunk_ids[: rerank_n]
        chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.id.in_(top_for_rerank))
            .all()
        )
        chunks_by_id = {c.id: c for c in chunks}
        ordered_chunk_ids = _rerank_by_keyword_overlap(query, top_for_rerank, chunks_by_id)

    ordered_chunk_ids = ordered_chunk_ids[: limit]

    # 5) Enrich from DB — include academic classification fields + real scores
    # Batch-fetch all needed chunks in one query (avoids N+1)
    chunk_map = {
        c.id: c
        for c in db.query(DocumentChunk).filter(DocumentChunk.id.in_(ordered_chunk_ids)).all()
    }
    doc_map = {
        d.id: d
        for d in db.query(Document).filter(
            Document.id.in_([c.document_id for c in chunk_map.values()])
        ).all()
    }

    results = []
    for cid in ordered_chunk_ids:
        chunk = chunk_map.get(cid)
        if not chunk:
            continue
        doc = doc_map.get(chunk.document_id)
        if not doc:
            continue
        sc = scores_map.get(cid, {})
        rrf = sc.get("rrf", 0.0)
        results.append(SearchResult(
            element_id=chunk.id,
            score=round(rrf, 6),          # ← real RRF score, not 1.0
            text=chunk.text or "",
            category="CHUNK",
            page_number=chunk.page_start,
            document_id=doc.id,
            document_filename=doc.filename,
            subject_id=doc.subject_id,
            section_path=chunk.section_path,
            blooms_level=getattr(chunk, "blooms_level", None),
            difficulty=getattr(chunk, "difficulty", None),
            section_type=getattr(chunk, "section_type", None),
            usage_count=getattr(chunk, "usage_count", None),
            bm25_score=sc.get("bm25"),
            vector_score=sc.get("vector"),
            rrf_score=round(rrf, 6),
        ))

    search_time = (time.time() - start_time) * 1000
    return SemanticSearchResponse(
        query=query,
        total_results=len(results),
        results=results,
        search_time_ms=round(search_time, 2),
    )


@router.get("/health")
def search_health():
    """Check if search service is available"""
    try:
        generator = get_embedding_generator()
        qdrant = get_qdrant_manager()
        info = qdrant.get_collection_info()
        chunks_info = info.get("chunks") or {}
        total_vectors = (chunks_info.get("points_count") or 0) + (
            (info.get("elements") or {}).get("points_count") or 0
        )
        return {
            "status": "healthy",
            "embedding_model": generator.get_model_info()["model_name"],
            "embedding_dim": generator.get_model_info().get("embedding_dimension", 384),
            "qdrant_chunks": chunks_info.get("collection_name"),
            "qdrant_elements": (info.get("elements") or {}).get("collection_name"),
            "vector_size": chunks_info.get("vector_size", 384),
            "indexed_vectors": total_vectors,
            "chunks_count": chunks_info.get("points_count", 0),
            "elements_count": (info.get("elements") or {}).get("points_count", 0),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

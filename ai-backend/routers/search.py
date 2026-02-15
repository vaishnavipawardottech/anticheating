"""
Search Router - Semantic Search Endpoint
Provides natural language search across indexed documents
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
import time

from database.database import get_db
from database.models import ParsedElement, Document
from embeddings import get_embedding_generator
from embeddings.qdrant_manager import get_qdrant_manager

router = APIRouter(prefix="/search", tags=["search"])


# Request/Response Schemas
class SemanticSearchRequest(BaseModel):
    """Request schema for semantic search"""
    query: str = Field(..., description="Natural language search query", min_length=1)
    subject_id: int = Field(..., description="Subject ID to search within")
    category: Optional[str] = Field(None, description="Filter by category (TEXT, DIAGRAM, TABLE, CODE, OTHER)")
    document_id: Optional[int] = Field(None, description="Filter by specific document ID")
    limit: int = Field(10, description="Maximum number of results", ge=1, le=100)
    min_score: float = Field(0.0, description="Minimum similarity score (0-1)", ge=0.0, le=1.0)


class SearchResult(BaseModel):
    """Single search result"""
    element_id: int
    score: float
    text: str
    category: str
    page_number: Optional[int]
    document_id: int
    document_filename: str
    subject_id: int


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
        
        # 2. Build Qdrant filter
        qdrant_filter = {
            "subject_id": request.subject_id
        }
        
        if request.category:
            qdrant_filter["category"] = request.category
        
        if request.document_id:
            qdrant_filter["document_id"] = request.document_id
        
        # 3. Search Qdrant
        qdrant = get_qdrant_manager()
        qdrant_results = qdrant.search(
            query_vector=query_embedding,
            limit=request.limit,
            score_threshold=request.min_score,
            subject_id=request.subject_id,
            category=request.category,
            document_id=request.document_id
        )
        
        # 4. Enrich results with database data
        results = []
        for qr in qdrant_results:
            # Get element from database
            element = db.query(ParsedElement).filter(
                ParsedElement.id == qr["element_id"]
            ).first()
            
            if not element:
                continue  # Skip if element not found
            
            # Get document metadata
            document = db.query(Document).filter(
                Document.id == element.document_id
            ).first()
            
            if not document:
                continue  # Skip if document not found
            
            results.append(SearchResult(
                element_id=element.id,
                score=qr["score"],
                text=element.text or "",
                category=element.category,
                page_number=element.page_number,
                document_id=document.id,
                document_filename=document.filename,
                subject_id=document.subject_id
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


@router.get("/health")
def search_health():
    """Check if search service is available"""
    try:
        # Check embedding generator
        generator = get_embedding_generator()
        
        # Check Qdrant
        qdrant = get_qdrant_manager()
        info = qdrant.get_collection_info()
        
        return {
            "status": "healthy",
            "embedding_model": generator.get_model_info()["model_name"],
            "qdrant_collection": info.get("collection_name", "academic_elements"),
            "indexed_vectors": info.get("points_count", 0)
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

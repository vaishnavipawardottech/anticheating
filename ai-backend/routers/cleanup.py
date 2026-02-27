"""
Simple Cleanup Router
Accept parsed JSON, return cleaned JSON
"""

from fastapi import APIRouter, HTTPException
from typing import List
from pydantic import BaseModel

from ingestion.schemas import SemanticElement, CleanupStatistics
from ingestion.cleanup import cleanup_elements

router = APIRouter(prefix="/cleanup", tags=["cleanup"])


class CleanupRequest(BaseModel):
    """Request with parsed elements"""
    elements: List[SemanticElement]


class CleanupResponse(BaseModel):
    """Response with cleaned elements"""
    elements: List[SemanticElement]
    statistics: CleanupStatistics


@router.post("/", response_model=CleanupResponse)
def clean_elements(request: CleanupRequest):
    """
    Clean parsed elements - remove noise
    
    Simply paste your parsed JSON from /documents/parse
    and get back cleaned elements
    """
    try:
        result = cleanup_elements(request.elements)
        
        return CleanupResponse(
            elements=result.elements,
            statistics=CleanupStatistics(**result.statistics.to_dict())
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

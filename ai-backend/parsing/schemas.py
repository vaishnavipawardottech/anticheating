"""
Pydantic schemas for document parsing
Semantic element representation with proper typing and validation
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class SemanticElement(BaseModel):
    """
    A single semantic element extracted from a document
    
    Represents structured content like Title, NarrativeText, ListItem, Image, etc.
    Preserves order, text, page number, and metadata.
    """
    order: int = Field(..., ge=0, description="Position in document (0-indexed, guaranteed stable)")
    element_type: str = Field(..., description="Element class name from unstructured (e.g., Title, NarrativeText)")
    text: Optional[str] = Field(None, description="Extracted text content (None for images/non-text elements)")
    page_number: Optional[int] = Field(None, ge=1, description="Page number where element appears (if available)")
    source_filename: str = Field(..., description="Original filename for traceability")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Element metadata (coordinates, confidence, etc.)")

    class Config:
        json_schema_extra = {
            "example": {
                "order": 0,
                "element_type": "Title",
                "text": "Operating Systems",
                "page_number": 1,
                "source_filename": "os_syllabus.pdf",
                "metadata": {
                    "coordinates": {"points": [[100, 50], [500, 100]]},
                    "detection_origin": "pdfminer"
                }
            }
        }


class CleanupStatistics(BaseModel):
    """Statistics about cleanup operation"""
    total_elements: int = Field(..., ge=0, description="Total elements before cleanup")
    removed_elements: int = Field(..., ge=0, description="Number of elements removed")
    kept_elements: int = Field(..., ge=0, description="Number of elements kept")
    removal_reasons: Dict[str, int] = Field(default_factory=dict, description="Breakdown of removal reasons")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_elements": 269,
                "removed_elements": 15,
                "kept_elements": 254,
                "removal_reasons": {
                    "header_footer": 5,
                    "page_number": 3,
                    "toc_leader": 2,
                    "pure_numeric": 3,
                    "empty_whitespace": 2
                }
            }
        }


class DocumentParseResponse(BaseModel):
    """
    Complete response from document parsing
    Contains all extracted semantic elements in order
    """
    filename: str = Field(..., description="Original filename")
    file_type: str = Field(..., description="Document type (pdf, pptx, docx)")
    file_size_bytes: int = Field(..., ge=0, description="File size in bytes")
    total_elements: int = Field(..., ge=0, description="Total number of extracted elements from document")
    total_pages: Optional[int] = Field(None, ge=1, description="Total pages (if available)")
    elements: List[SemanticElement] = Field(..., description="Ordered list of semantic elements")
    truncated: bool = Field(default=False, description="True if results were limited (not all elements returned)")
    returned_elements: int = Field(..., ge=0, description="Number of elements actually returned in this response")
    cleanup_applied: bool = Field(default=False, description="True if cleanup filters were applied")
    cleanup_statistics: Optional[CleanupStatistics] = Field(None, description="Cleanup operation statistics (if cleanup applied)")

    class Config:
        json_schema_extra = {
            "example": {
                "filename": "os_syllabus.pdf",
                "file_type": "pdf",
                "file_size_bytes": 245760,
                "total_elements": 150,
                "total_pages": 3,
                "elements": [],
                "truncated": True,
                "returned_elements": 100,
                "cleanup_applied": True,
                "cleanup_statistics": {
                    "total_elements": 150,
                    "removed_elements": 12,
                    "kept_elements": 138,
                    "removal_reasons": {"header_footer": 6, "page_number": 6}
                }
            }
        }


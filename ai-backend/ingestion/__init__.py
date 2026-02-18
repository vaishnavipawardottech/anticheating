"""
Ingestion Pipeline Package

Complete 10-step document processing pipeline:
1. Parse (Unstructured) → raw elements
2. Normalize (unicode/text cleanup) → clean text
3. Caption Images (GPT-4o) → image descriptions
4. Format Tables (LLM) → Markdown tables
5. Cleanup (remove noise) → filtered elements
6. Classify (TEXT/DIAGRAM/CODE) → categorized elements
7. Chunk (section-aware) → retrieval-optimized chunks
8. Embed (MiniLM) → vector representations
9. Index (PostgreSQL + Qdrant) → stored & searchable
10. Align (Gemini) → concept mapping

Each step is designed to run independently with proper error handling.
"""

from .parser import DocumentParser
from .normalizer import normalize_text, normalize_elements
from .image_captioner import caption_images, ImageCaptioner
from .table_formatter import format_tables, TableFormatter
from .cleanup import cleanup_elements
from .classifier import ElementClassifier
from .chunker import chunk_elements, compute_section_paths_for_elements, table_to_row_chunks
from .schemas import SemanticElement

__all__ = [
    # Step 1: Parse
    "DocumentParser",
    
    # Step 2: Normalize
    "normalize_text",
    "normalize_elements",
    
    # Step 3: Caption Images
    "caption_images",
    "ImageCaptioner",
    
    # Step 4: Format Tables
    "format_tables",
    "TableFormatter",
    
    # Step 5: Cleanup
    "cleanup_elements",
    
    # Step 6: Classify
    "ElementClassifier",
    
    # Step 7: Chunk
    "chunk_elements",
    "compute_section_paths_for_elements",
    "table_to_row_chunks",
    
    # Schemas
    "SemanticElement",
]

"""
Ingestion Pipeline Package

Default (simple): Parse (fast) → Normalize → Cleanup → Classify → Chunk → Embed → Index → Align.
Math option: adds image captioning, table formatting, assets, visual chunks (parse stays fast).
"""

from .parser import DocumentParser
from .normalizer import normalize_text, normalize_elements
from .image_captioner import caption_images, ImageCaptioner
from .table_formatter import format_tables, TableFormatter
from .cleanup import cleanup_elements
from .classifier import ElementClassifier, classify_elements
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
    "classify_elements",
    
    # Step 7: Chunk
    "chunk_elements",
    "compute_section_paths_for_elements",
    "table_to_row_chunks",
    
    # Schemas
    "SemanticElement",
]

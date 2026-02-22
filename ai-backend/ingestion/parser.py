"""
Document Parser using unstructured library
Extracts semantic elements from PDF, PPTX, DOCX files

CONSTRAINTS:
- Deterministic: Same file → same output
- Isolated: No external API calls, no LLM, no embeddings
- No chunking: Raw semantic elements only
- No DB writes: Pure parsing function
"""

import os
import logging
from typing import List, Optional, Dict, Any
from pathlib import Path

from .schemas import SemanticElement

# Suppress verbose PDF parsing warnings (pdfminer color space issues)
logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("PIL").setLevel(logging.ERROR)
logging.getLogger("unstructured").setLevel(logging.WARNING)

log = logging.getLogger(__name__)


class DocumentParser:
    """
    Deterministic document parser using unstructured library
    """
    
    # Supported file types with explicit parsers
    SUPPORTED_TYPES = {
        "pdf": "application/pdf",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }
    
    @staticmethod
    def parse_document(
        file_path: str,
        filename: str,
        pdf_strategy: str = "fast",
    ) -> List[SemanticElement]:
        """
        Parse document and extract ordered semantic elements

        Args:
            file_path: Absolute path to document file
            filename: Original filename for traceability
            pdf_strategy: For PDF only: "fast" (text only, no image detection) or
                "hi_res" (layout + image detection; needs unstructured[local-inference] for full support).
                Use "hi_res" when the PDF has diagrams/figures you want to caption and index.

        Returns:
            List of SemanticElement objects in document order

        Raises:
            ValueError: If file type is unsupported
            RuntimeError: If parsing fails
        """
        log.info("Step 1 (parse): start file=%s strategy=%s", filename, pdf_strategy)
        # Determine file type from extension
        file_ext = Path(file_path).suffix.lower().lstrip(".")

        if file_ext not in DocumentParser.SUPPORTED_TYPES:
            raise ValueError(f"Unsupported file type: {file_ext}")

        # Use explicit parser based on file type (NOT partition_auto)
        if file_ext == "pdf":
            elements = DocumentParser._parse_pdf(file_path, strategy=pdf_strategy)
        elif file_ext == "pptx":
            elements = DocumentParser._parse_pptx(file_path)
        elif file_ext == "docx":
            elements = DocumentParser._parse_docx(file_path)
        else:
            raise ValueError(f"No parser available for: {file_ext}")
        
        # Convert to SemanticElement objects with explicit ordering
        semantic_elements = []
        for idx, element in enumerate(elements):
            semantic_element = DocumentParser._extract_element_data(
                element=element,
                order=idx,
                source_filename=filename
            )
            semantic_elements.append(semantic_element)

        log.info("Step 1 (parse): done elements=%s", len(semantic_elements))
        return semantic_elements
    
    @staticmethod
    def _parse_pdf(file_path: str, strategy: str = "fast") -> List:
        """
        Parse PDF using unstructured.partition.pdf.

        - strategy="fast": text only, no image/layout detection (~100x faster).
        - strategy="hi_res": layout + image detection (extracts Image/Table elements);
          requires unstructured[local-inference] for full support; falls back to fast on failure.
        """
        try:
            from unstructured.partition.pdf import partition_pdf
        except ImportError:
            raise RuntimeError(
                "PDF parsing requires: pip install unstructured[pdf]"
            )

        use_hi_res = (strategy or "fast").lower() in ("hi_res", "auto")
        if use_hi_res:
            try:
                elements = partition_pdf(
                    filename=file_path,
                    strategy=strategy if strategy else "hi_res",
                    include_page_breaks=False,
                )
                return elements
            except Exception as e:
                logging.warning(
                    "PDF hi_res/auto parsing failed (%s), falling back to fast. "
                    "For image detection install: pip install unstructured[local-inference]",
                    str(e),
                )
                use_hi_res = False

        if not use_hi_res:
            elements = partition_pdf(
                filename=file_path,
                strategy="fast",
                include_page_breaks=False,
            )
        return elements
    
    @staticmethod
    def _parse_pptx(file_path: str) -> List:
        """
        Parse PPTX using unstructured.partition.pptx
        Explicit parser for deterministic behavior
        """
        try:
            from unstructured.partition.pptx import partition_pptx
            
            elements = partition_pptx(
                filename=file_path,
                include_page_breaks=False
            )
            return elements
            
        except ImportError:
            raise RuntimeError(
                "PPTX parsing requires: pip install unstructured[pptx] python-pptx"
            )
        except Exception as e:
            raise RuntimeError(f"PPTX parsing failed: {str(e)}")
    
    @staticmethod
    def _parse_docx(file_path: str) -> List:
        """
        Parse DOCX using unstructured.partition.docx
        Explicit parser for deterministic behavior
        """
        try:
            from unstructured.partition.docx import partition_docx
            
            elements = partition_docx(
                filename=file_path,
                include_page_breaks=False
            )
            return elements
            
        except ImportError:
            raise RuntimeError(
                "DOCX parsing requires: pip install unstructured[docx] python-docx"
            )
        except Exception as e:
            raise RuntimeError(f"DOCX parsing failed: {str(e)}")
    
    @staticmethod
    def _extract_element_data(
        element,
        order: int,
        source_filename: str
    ) -> SemanticElement:
        """
        Convert unstructured element to SemanticElement schema
        
        Safely extracts:
        - Element type (using __class__.__name__)
        - Text content (with None fallback)
        - Page number (with safe extraction)
        - Metadata (filtered to avoid serialization issues)
        
        Args:
            element: Unstructured element object
            order: Position in document (0-indexed)
            source_filename: Original filename
            
        Returns:
            SemanticElement object
        """
        # Extract element type from class name (canonical way)
        element_type = element.__class__.__name__
        
        # Extract text safely (may be None for images, tables, etc.)
        text = getattr(element, "text", None)
        if text is not None:
            text = str(text).strip()
            if not text:  # Empty string → None
                text = None
        
        # Extract page number safely (not all elements have this)
        page_number = None
        if hasattr(element, "metadata") and hasattr(element.metadata, "page_number"):
            page_number = element.metadata.page_number
        
        # Extract metadata safely (avoid non-serializable objects)
        metadata = DocumentParser._extract_safe_metadata(element)
        
        return SemanticElement(
            order=order,
            element_type=element_type,
            text=text,
            page_number=page_number,
            source_filename=source_filename,
            metadata=metadata
        )
    
    @staticmethod
    def _extract_safe_metadata(element) -> Dict[str, Any]:
        """
        Extract metadata in JSON-serializable format
        
        Avoids non-serializable objects by explicitly extracting known fields
        Returns empty dict if no metadata available
        
        Args:
            element: Unstructured element object
            
        Returns:
            Dict with safe metadata fields
        """
        if not hasattr(element, "metadata"):
            return {}
        
        metadata_obj = element.metadata
        safe_metadata = {}
        
        # Helper to ensure value is serializable
        def make_serializable(value):
            """Convert value to JSON-serializable type"""
            if value is None:
                return None
            if isinstance(value, (str, int, float, bool)):
                return value
            if isinstance(value, (list, tuple)):
                return [make_serializable(v) for v in value]
            if isinstance(value, dict):
                return {k: make_serializable(v) for k, v in value.items()}
            # For anything else, convert to string
            return str(value)
        
        # Extract coordinates (if available)
        if hasattr(metadata_obj, "coordinates"):
            coords = metadata_obj.coordinates
            if coords is not None:
                try:
                    safe_metadata["coordinates"] = {
                        "points": make_serializable(getattr(coords, "points", None)),
                        "system": make_serializable(getattr(coords, "system", None))
                    }
                except:
                    pass  # Skip if serialization fails
        
        # Extract detection origin
        if hasattr(metadata_obj, "detection_origin"):
            origin = metadata_obj.detection_origin
            if origin is not None:
                safe_metadata["detection_origin"] = str(origin)
        
        # Extract confidence/probability
        if hasattr(metadata_obj, "detection_class_prob"):
            prob = metadata_obj.detection_class_prob
            if prob is not None and isinstance(prob, (int, float)):
                safe_metadata["detection_class_prob"] = float(prob)
        
        # Extract filename from metadata (different from source_filename)
        if hasattr(metadata_obj, "filename"):
            meta_filename = metadata_obj.filename
            if meta_filename is not None:
                safe_metadata["original_filename"] = str(meta_filename)
        
        # Extract file directory
        if hasattr(metadata_obj, "file_directory"):
            file_dir = metadata_obj.file_directory
            if file_dir is not None:
                safe_metadata["file_directory"] = str(file_dir)
        
        # Extract emphasized text runs (for bold, italic, etc.)
        if hasattr(metadata_obj, "emphasized_text_contents"):
            emphasized = metadata_obj.emphasized_text_contents
            if emphasized is not None and emphasized:
                safe_metadata["emphasized_text_contents"] = make_serializable(emphasized)
        
        # Extract emphasized text tags
        if hasattr(metadata_obj, "emphasized_text_tags"):
            tags = metadata_obj.emphasized_text_tags
            if tags is not None and tags:
                safe_metadata["emphasized_text_tags"] = make_serializable(tags)
        
        # Filter out None values
        safe_metadata = {k: v for k, v in safe_metadata.items() if v is not None}
        
        return safe_metadata

    @staticmethod
    def get_total_pages(elements: List) -> Optional[int]:
        """
        Extract total page count from elements.

        Returns:
            Max page number found, or None if no page numbers
        """
        max_page = None
        for element in elements:
            if hasattr(element, "metadata") and hasattr(element.metadata, "page_number"):
                page_num = element.metadata.page_number
                if page_num is not None and (max_page is None or page_num > max_page):
                    max_page = page_num
        return max_page


def bbox_from_metadata(metadata: Dict[str, Any]) -> Optional[List[float]]:
    """
    Derive [x1, y1, x2, y2] from element metadata for use as Asset.bbox.
    Parser already preserves coordinates in metadata["coordinates"]["points"]; this converts to bbox.
    Returns None if metadata has no coordinates or points are invalid.
    """
    if not metadata or not isinstance(metadata.get("coordinates"), dict):
        return None
    points = metadata.get("coordinates", {}).get("points")
    if not points or not isinstance(points, (list, tuple)):
        return None
    try:
        xs = [float(p[0]) for p in points if isinstance(p, (list, tuple)) and len(p) >= 2]
        ys = [float(p[1]) for p in points if isinstance(p, (list, tuple)) and len(p) >= 2]
        if not xs or not ys:
            return None
        return [min(xs), min(ys), max(xs), max(ys)]
    except (TypeError, ValueError):
        return None



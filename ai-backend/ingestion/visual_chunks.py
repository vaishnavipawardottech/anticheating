"""
Visual Chunk pipeline: create and caption only Unstructured-detected Image/Table/Figure elements.

Uses ParsedElement (Image/Table/Figure) from DB → render only those pages → crop by bbox →
caption only the crop (not full page) to minimize vision token usage.
"""

import logging
from pathlib import Path
from typing import List

from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

from database.models import VisualChunk, ParsedElement
from ingestion.page_renderer import render_pdf_pages, RENDER_DPI, cap_image_size
from ingestion.parser import bbox_from_metadata
from ingestion.asset_extractor import _crop_page_image
from ingestion.image_captioner import ImageCaptioner

# Subdirectory under uploads for visual assets (could be MinIO path later)
VISUALS_SUBDIR = "visuals"


def _is_visual_element(element: ParsedElement) -> bool:
    """True if element should get a visual chunk (Image, Figure, or Table)."""
    etype = (element.element_type or "").strip()
    cat = (element.category or "").strip()
    return etype in ("Image", "Figure", "Table") or cat == "TABLE"


async def build_visual_chunks_for_document(
    db: Session,
    document_id: int,
    file_path: str,
    subject_id: int,
    file_extension: str,
    filename: str = "",
) -> List[VisualChunk]:
    """
    Create VisualChunk rows only for Unstructured-detected Image/Table/Figure elements.

    Renders only pages that contain such elements, crops each element by bbox, captions
    the crop (not the full page) to reduce vision token usage. If no visual elements
    exist, returns [] (no full-page fallback).
    """
    ext = (file_extension or "").lower().strip()
    if ext != "pdf":
        log.info("Step 9c (visual chunks): skipped (not PDF)")
        return []

    log.info("Step 9c (visual chunks): start document_id=%s", document_id)
    # Load only Image/Table/Figure elements (same as Phase 2 asset logic)
    visual_elements = (
        db.query(ParsedElement)
        .filter(ParsedElement.document_id == document_id)
        .filter(
            (ParsedElement.element_type.in_(["Image", "Figure", "Table"]))
            | (ParsedElement.category == "TABLE")
        )
        .order_by(ParsedElement.order_index)
        .all()
    )
    if not visual_elements:
        log.info("Step 9c (visual chunks): done no visual elements")
        return []

    output_dir = str(Path("uploads") / VISUALS_SUBDIR)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    page_numbers = list({e.page_number for e in visual_elements if e.page_number})
    if not page_numbers:
        return []

    rendered = render_pdf_pages(file_path, output_dir, document_id, page_numbers=page_numbers)
    if not rendered:
        return []

    page_paths = {pno: path for pno, path in rendered}
    scale = RENDER_DPI / 72.0
    captioner = ImageCaptioner()
    created: List[VisualChunk] = []

    for element in visual_elements:
        page_no = element.page_number or 1
        page_path = page_paths.get(page_no)
        if not page_path:
            continue

        bbox = bbox_from_metadata(element.element_metadata or {})
        img = _crop_page_image(page_path, bbox, scale)
        if img is None:
            continue
        img = cap_image_size(img)

        crop_path = Path(output_dir) / f"doc_{document_id}_elem_{element.order_index}.png"
        try:
            img.save(str(crop_path))
        except Exception:
            continue

        context = f"Document: {filename or Path(file_path).name}, Page {page_no}. Figure/table region."
        try:
            caption = await captioner.caption_image(image_path=str(crop_path), context=context)
        except Exception as e:
            caption = f"[Caption failed: {e}]"
        if not caption or caption.startswith("[Image description unavailable"):
            caption = f"Page {page_no} figure/table (element {element.order_index})."

        asset_type = "TABLE" if (element.element_type == "Table" or element.category == "TABLE") else "DIAGRAM"
        vc = VisualChunk(
            document_id=document_id,
            page_no=page_no,
            asset_type=asset_type,
            image_path=str(crop_path),
            caption_text=caption,
            ocr_text=None,
            structured_json=None,
            concept_id=None,
            unit_id=None,
            alignment_confidence=None,
            usage_count=0,
        )
        db.add(vc)
        db.flush()
        created.append(vc)

    if created:
        db.commit()
        for vc in created:
            db.refresh(vc)
    log.info("Step 9c (visual chunks): done created=%s", len(created))
    return created

"""
Phase 2: Extract per-element assets when subject.math_mode is True.

- Renders PDF pages, crops Image/Table elements (or uses full page if no bbox).
- Creates Asset rows (document_id, page_no, bbox, sha256, asset_url, asset_type, source_element_order).
- Optionally runs vision on up to vision_budget images and sets caption, kind.
"""

import hashlib
import logging
import os
from pathlib import Path
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

from database.models import Asset
from ingestion.page_renderer import render_pdf_pages, RENDER_DPI, cap_image_size
from ingestion.parser import bbox_from_metadata
from ingestion.image_captioner import ImageCaptioner

# Subdir per document: uploads/assets/doc_{id}/
ASSETS_BASE = "uploads/assets"


def _scale_bbox_to_pixels(bbox: List[float], scale: float) -> List[int]:
    """Convert bbox [x0,y0,x1,y1] in PDF points to pixel ints."""
    return [
        max(0, int(bbox[0] * scale)),
        max(0, int(bbox[1] * scale)),
        max(0, int(bbox[2] * scale)),
        max(0, int(bbox[3] * scale)),
    ]


def _crop_page_image(page_path: str, bbox_points: Optional[List[float]], scale: float) -> Optional[tuple]:
    """
    Crop page image to bbox (in PDF points). Returns (pil_image, path_to_save) or None.
    If bbox is None, returns full page image.
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    path = Path(page_path)
    if not path.exists():
        return None
    try:
        img = Image.open(page_path).convert("RGB")
    except Exception:
        return None
    w, h = img.size
    if bbox_points and len(bbox_points) >= 4:
        left, top, right, bottom = _scale_bbox_to_pixels(bbox_points, scale)
        left = min(left, w - 1)
        top = min(top, h - 1)
        right = min(max(right, left + 1), w)
        bottom = min(max(bottom, top + 1), h)
        img = img.crop((left, top, right, bottom))
    return img


def _is_asset_element(element: Any) -> bool:
    """True if element should become an Asset (Image, Figure, or Table)."""
    etype = getattr(element, "element_type", "") or ""
    cat = getattr(element, "category", "") or ""
    return etype in ("Image", "Figure", "Table") or cat == "TABLE"


async def build_assets_for_document(
    db: Session,
    document_id: int,
    file_path: str,
    cleaned_elements: List[Any],
    file_extension: str,
    vision_budget: Optional[int] = None,
    page_numbers: Optional[List[int]] = None,
    subject_name: Optional[str] = None,
) -> int:
    """
    When math_mode: render PDF pages, create one Asset per Image/Table element, optionally run vision.

    - Only runs for PDF. Returns count of assets created.
    - Saves images under uploads/assets/doc_{document_id}/ (page_*.png, elem_*.png).
    - vision_budget: max number of image-type assets to send to vision (caption + kind); None = no vision.
    - page_numbers: if set, only render these 1-based page numbers (e.g. [2,3,4] when testing first 3 pages).
    - subject_name: when provided, added to the GPT-4o vision prompt for subject-specific diagram descriptions.
    """
    ext = (file_extension or "").lower().strip()
    if ext != "pdf":
        log.info("Step 6c (asset extraction): skipped (not PDF)")
        return 0

    log.info("Step 6c (asset extraction): start document_id=%s elements=%s", document_id, len(cleaned_elements))
    try:
        import fitz
    except ImportError:
        log.warning("Step 6c (asset extraction): PyMuPDF not installed, skipping")
        return 0

    out_dir = Path(ASSETS_BASE) / f"doc_{document_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    scale = RENDER_DPI / 72.0

    rendered = render_pdf_pages(file_path, str(out_dir), document_id, page_numbers=page_numbers)
    if not rendered:
        print("   [AssetExtractor] No pages rendered.")
        return 0
    page_paths: Dict[int, str] = {pno: path for pno, path in rendered}

    # Collect (order, element) for Image/Table
    asset_elements = [
        (getattr(el, "order", idx), el)
        for idx, el in enumerate(cleaned_elements)
        if _is_asset_element(el)
    ]

    created: List[Asset] = []
    captioner = ImageCaptioner()

    for order, element in asset_elements:
        page_no = getattr(element, "page_number", None) or 1
        page_path = page_paths.get(page_no)
        if not page_path or not os.path.exists(page_path):
            continue

        bbox = bbox_from_metadata(getattr(element, "metadata", {}) or {})
        atype = "table" if (getattr(element, "element_type", "") == "Table" or getattr(element, "category", "") == "TABLE") else "image"

        # Crop or use full page; cap size to 200x200 before save
        img = _crop_page_image(page_path, bbox, scale)
        if img is None:
            continue
        img = cap_image_size(img)
        elem_path = out_dir / f"elem_{order}.png"
        try:
            img.save(str(elem_path))
        except Exception as e:
            print(f"   [AssetExtractor] Save elem_{order} failed: {e}")
            continue

        with open(elem_path, "rb") as f:
            sha256 = hashlib.sha256(f.read()).hexdigest()

        asset_url = str(elem_path)
        bbox_json = bbox if bbox else None

        asset = Asset(
            document_id=document_id,
            page_no=page_no,
            bbox=bbox_json,
            sha256=sha256,
            asset_url=asset_url,
            asset_type=atype,
            source_element_order=order,
            kind=None,
            caption=None,
            structured_json=None,
        )
        db.add(asset)
        db.flush()
        created.append(asset)

    # Fallback: if no element-level images were found (e.g. presentation-style PDFs where
    # images are embedded in page content rather than as separate parser elements), create
    # one Asset per rendered page so that GPT-4o can still describe page diagrams.
    if not created and page_paths:
        log.info("Step 6c (asset extraction): no Image elements found — falling back to page-level assets")
        for page_no in sorted(page_paths.keys()):
            page_path = page_paths[page_no]
            if not os.path.exists(page_path):
                continue
            try:
                from PIL import Image as PILImage
                img = PILImage.open(page_path)
                img = cap_image_size(img)
                page_asset_path = out_dir / f"page_{page_no}_asset.png"
                img.save(str(page_asset_path))
            except Exception as e:
                log.warning("Step 6c: page asset save failed page=%s: %s", page_no, e)
                continue
            with open(page_asset_path, "rb") as f:
                sha256 = hashlib.sha256(f.read()).hexdigest()
            asset = Asset(
                document_id=document_id,
                page_no=page_no,
                bbox=None,
                sha256=sha256,
                asset_url=str(page_asset_path),
                asset_type="image",
                source_element_order=page_no,
                kind=None,
                caption=None,
                structured_json=None,
            )
            db.add(asset)
            db.flush()
            created.append(asset)

    if not created:
        return 0

    db.commit()
    for a in created:
        db.refresh(a)

    # Treat Vision "no content" / "blank" / error-style responses as no caption (crop may be wrong or empty)
    def _is_blank_vision_response(c: str) -> bool:
        if not c or not c.strip():
            return True
        lower = c.strip().lower()
        return (
            "no visible content" in lower
            or "no visible" in lower
            or "image is blank" in lower
            or "image you provided" in lower
            or "seems there is no" in lower
            or "i'm sorry" in lower
            or "upload the image again" in lower
            or "please check" in lower
            or "provide more context" in lower
        )

    # Vision: up to vision_budget image-type assets
    if vision_budget is not None and vision_budget > 0 and captioner.enabled:
        # Build a subject-aware hint so GPT-4o knows what kind of diagrams to expect
        if subject_name:
            subject_hint = (
                f" Subject: {subject_name}."
                " Possible diagram types: Venn diagram, set diagram, function mapping arrow diagram,"
                " Hasse diagram / partial-order diagram, bipartite graph, directed graph,"
                " truth table, Euler diagram, lattice diagram, tree diagram."
                " Describe the diagram precisely using correct mathematical terminology."
            )
        else:
            subject_hint = ""

        image_assets = [a for a in created if a.asset_type == "image"][:vision_budget]
        for asset in image_assets:
            try:
                cap = await captioner.caption_image(
                    image_path=asset.asset_url,
                    context=f"Document page {asset.page_no}. Academic figure/diagram.{subject_hint}",
                )
                if cap and not cap.startswith("[Image description") and not _is_blank_vision_response(cap):
                    asset.caption = cap[:4000] if len(cap) > 4000 else cap
                    asset.kind = "diagram_other"
                elif _is_blank_vision_response(cap):
                    asset.caption = None  # Surrogate will use fallback "Figure"
            except Exception as e:
                log.warning("Step 6c (asset extraction): vision for asset %s failed: %s", asset.id, e)
        db.commit()

    log.info("Step 6c (asset extraction): done created=%s vision_budget=%s", len(created), vision_budget)
    return len(created)


# Phase 3: attach assets to chunks and inject figure surrogates into chunk text
SURROGATE_CAPTION_MAX = 200


def attach_assets_to_chunks(
    db: Session,
    document_id: int,
    doc_chunks: List[Any],
) -> List[List[int]]:
    """
    Link chunks to assets by source_element_order overlap; inject [[FIGURE: kind | caption]] into chunk text.

    Modifies each chunk's .text in place (appends surrogate lines). Returns one list of asset IDs per chunk
    (same order as doc_chunks) for storing in DocumentChunk.source_asset_ids and Qdrant payload.
    """
    assets = db.query(Asset).filter(Asset.document_id == document_id).all()
    if not assets:
        return [[] for _ in doc_chunks]

    order_to_assets: Dict[int, List[Asset]] = {}
    for a in assets:
        if a.source_element_order is not None:
            order_to_assets.setdefault(a.source_element_order, []).append(a)

    chunk_asset_ids: List[List[int]] = []
    for chunk in doc_chunks:
        orders = getattr(chunk, "source_element_orders", None) or []
        if not isinstance(orders, (list, tuple)):
            orders = []
        linked: List[Asset] = []
        for o in orders:
            linked.extend(order_to_assets.get(o, []))
        ids = list({a.id for a in linked})
        chunk_asset_ids.append(ids)

        if not ids:
            continue
        # Load caption/kind for surrogate (we have assets in memory)
        asset_by_id = {a.id: a for a in assets}
        parts = []
        for aid in ids:
            a = asset_by_id.get(aid)
            if not a:
                continue
            cap = (a.caption or "").strip()
            if not cap:
                continue  # Skip assets without a real GPT-4o caption to avoid noise
            if len(cap) > SURROGATE_CAPTION_MAX:
                cap = cap[: SURROGATE_CAPTION_MAX - 3] + "..."
            parts.append(f'FIG: "{cap}"')
        if parts:
            surrogate = "\n\n" + "\n".join(parts)
            chunk.text = (chunk.text or "").strip() + surrogate

    linked_count = sum(1 for ids in chunk_asset_ids if ids)
    log.info("Step 6d (attach assets): linked to %s chunks", linked_count)
    return chunk_asset_ids

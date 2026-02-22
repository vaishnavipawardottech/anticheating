"""
Page/Slide renderer for Visual Chunk pipeline.

Renders each document page (or slide) to PNG so we can:
- Treat whole page as one DIAGRAM asset (hackathon-friendly)
- Later: run layout detection to crop TABLE/EQUATION regions

PDF: PyMuPDF (fitz) renders each page to PNG.
PPTX: Requires LibreOffice to convert to PDF then render; otherwise we skip or use
      extracted images from parser. For minimal path we only render PDF.
"""

from pathlib import Path
from typing import List, Tuple, Optional, Any

# DPI for rendering (200-300 is decent for diagrams)
RENDER_DPI = 200

# Max dimensions for crops sent to Vision / stored (reduces tokens and cost)
MAX_IMAGE_WIDTH = 200
MAX_IMAGE_HEIGHT = 200


def cap_image_size(img: Any, max_w: int = MAX_IMAGE_WIDTH, max_h: int = MAX_IMAGE_HEIGHT) -> Any:
    """
    Resize PIL Image to fit within max_w x max_h, preserving aspect ratio.
    Returns the same image object (modified in place) or a new thumbnail. Use for crops before Vision/save.
    """
    try:
        from PIL import Image
    except ImportError:
        return img
    if img is None:
        return img
    w, h = img.size
    if w <= max_w and h <= max_h:
        return img
    ratio = min(max_w / w, max_h / h)
    new_w = max(1, int(w * ratio))
    new_h = max(1, int(h * ratio))
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)


def render_pdf_pages(
    file_path: str,
    output_dir: str,
    document_id: int,
    page_numbers: Optional[List[int]] = None,
) -> List[Tuple[int, str]]:
    """
    Render PDF page(s) to PNG files.

    Args:
        file_path: Path to the PDF file.
        output_dir: Directory to write PNGs (e.g. uploads/visuals).
        document_id: Document ID for naming (doc_{id}_page_{n}.png).
        page_numbers: Optional 1-based page numbers to render; if None, render all pages.

    Returns:
        List of (page_no, image_path) with page_no 1-based.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("   [VisualChunk] PyMuPDF not installed; run pip install pymupdf. Skipping page render.")
        return []

    path = Path(file_path)
    if not path.exists():
        return []

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    results: List[Tuple[int, str]] = []

    try:
        doc = fitz.open(file_path)
        total = len(doc)
        indices = (
            [p - 1 for p in page_numbers if 1 <= p <= total]
            if page_numbers is not None
            else list(range(total))
        )
        for i in indices:
            page_no = i + 1
            page = doc[i]
            mat = fitz.Matrix(RENDER_DPI / 72, RENDER_DPI / 72)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_path = out / f"doc_{document_id}_page_{page_no}.png"
            pix.save(str(img_path))
            results.append((page_no, str(img_path)))
        doc.close()
    except Exception as e:
        print(f"   [VisualChunk] PDF render failed: {e}")
        return []

    return results


def render_pptx_slides(file_path: str, output_dir: str, document_id: int) -> List[Tuple[int, str]]:
    """
    Render PPTX slides to PNG.

    Minimal path: try to use pdf2image if we have a PDF conversion step.
    Without LibreOffice/uno we cannot render PPTX to images reliably.
    Returns empty list so ingestion continues without visual chunks for PPTX.
    """
    return []


def render_document_pages(
    file_path: str, output_dir: str, document_id: int, file_extension: str
) -> List[Tuple[int, str]]:
    """
    Render each page/slide of the document to PNG.

    Args:
        file_path: Path to document.
        output_dir: Directory for PNGs.
        document_id: Document ID for naming.
        file_extension: pdf, pptx, or docx.

    Returns:
        List of (page_no, image_path). Empty if unsupported or error.
    """
    ext = (file_extension or "").lower().strip()
    if ext == "pdf":
        return render_pdf_pages(file_path, output_dir, document_id)
    if ext == "pptx":
        return render_pptx_slides(file_path, output_dir, document_id)
    # DOCX: no simple page-render in standard libs; skip
    return []

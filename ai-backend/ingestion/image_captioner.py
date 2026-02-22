"""
Image Captioning with GPT-4o Vision
Step 3 in ingestion pipeline: Generate text descriptions for images.

For PDFs: when Image/Figure elements have layout coordinates (bbox), we render the page,
crop the region, and send the crop to Vision with an "exact text" prompt so element.text
holds accurate text instead of noisy OCR.
"""

import logging
import os
import base64
import tempfile
import shutil
from typing import List, Optional
from pathlib import Path
import httpx

from .schemas import SemanticElement
from .parser import bbox_from_metadata
from .page_renderer import render_pdf_pages, RENDER_DPI, cap_image_size

log = logging.getLogger(__name__)


# Scale for bbox (PDF points) → pixels on rendered page
def _crop_page_to_image(page_path: str, bbox_points: Optional[List[float]], scale: float):
    """Crop page image to bbox (PDF points). Returns PIL Image or None."""
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
        left = max(0, int(bbox_points[0] * scale))
        top = max(0, int(bbox_points[1] * scale))
        right = min(w, int(bbox_points[2] * scale))
        bottom = min(h, int(bbox_points[3] * scale))
        right = max(right, left + 1)
        bottom = max(bottom, top + 1)
        img = img.crop((left, top, right, bottom))
    return img


class ImageCaptioner:
    """
    Generate detailed text descriptions for images using GPT-4o Vision API.
    
    Workflow:
    1. Identify Image elements from parsed document
    2. Extract image data (from metadata or file path)
    3. Send to GPT-4o for description
    4. Store description in element.text and metadata
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize image captioner.
        
        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            print("   Warning: OPENAI_API_KEY not set. Image captioning disabled.")
            self.enabled = False
        else:
            self.enabled = True
        
        self.api_url = "https://api.openai.com/v1/chat/completions"
        self.model = "gpt-4o"  # GPT-4o has vision capabilities
    
    async def caption_image(
        self,
        image_path: Optional[str] = None,
        image_url: Optional[str] = None,
        image_base64: Optional[str] = None,
        context: str = "",
        use_exact_text_prompt: bool = False,
    ) -> str:
        """
        Generate description or exact text for a single image.

        Args:
            image_path: Local file path to image
            image_url: Public URL to image
            image_base64: Base64-encoded image data
            context: Additional context (page number, surrounding text, etc.)
            use_exact_text_prompt: If True, ask Vision to extract all text exactly as shown
                (for diagram/figure regions cropped from PDF; replaces noisy OCR).

        Returns:
            Description or exact extracted text.
        """
        if not self.enabled:
            return "[Image description unavailable - API key not configured]"

        # Prepare image content
        if image_path and Path(image_path).exists():
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
            image_content = {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{image_data}"}
            }
        elif image_url:
            image_content = {
                "type": "image_url",
                "image_url": {"url": image_url}
            }
        elif image_base64:
            image_content = {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{image_base64}"}
            }
        else:
            return "[Image description unavailable - no image data provided]"

        if use_exact_text_prompt:
            system_prompt = """You are an expert at extracting text from academic images (diagrams, figures, slides).

Your task: extract ALL text in this image EXACTLY as shown.
- Include every label, number, symbol, equation, and word. Preserve spelling and symbols (e.g. ∀, ∃, →).
- Preserve structure: use line breaks for separate lines; keep bullet points and indentation where visible.
- If the image is a diagram or figure: on the first line give a one-line description (e.g. "Binary tree diagram with nodes A,B,C"). Then on the next line write "---" and then list all text verbatim.
- Output plain text only. No markdown, no extra commentary after the text."""
            user_prompt = "Extract all text in this image exactly as shown. Include every label, number, and word. If it is a diagram, first one line description then '---' then all text verbatim."
            if context:
                user_prompt += f"\n\nContext: {context}"
            max_tokens = 1200
        else:
            system_prompt = """You are an expert at describing academic diagrams, charts, and images from educational documents.

Generate a detailed, technical description that:
1. Identifies the type of visual (diagram, flowchart, screenshot, photo, chart, etc.)
2. Describes key components, labels, and relationships
3. Explains what concept or process is being illustrated
4. Mentions any text, equations, or annotations visible
5. Is clear enough that someone could understand the concept without seeing the image

Be precise, technical, and comprehensive. This description will be used for:
- Search and retrieval in an educational system
- Generating exam questions about the visual content
- Making content accessible to visually impaired students"""
            user_prompt = "Describe this academic image in detail."
            if context:
                user_prompt += f"\n\nContext: {context}"
            max_tokens = 500

        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(
                    self.api_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": user_prompt},
                                    image_content
                                ]
                            }
                        ],
                        "max_tokens": max_tokens,
                        "temperature": 0.2
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    description = result["choices"][0]["message"]["content"].strip()
                    label = context or image_path or (image_url and "(url)") or "image"
                    print(f"   [Vision] {label[:60]} -> {description[:80]}...")
                    return description
                else:
                    print(f"   GPT-4o error: {response.status_code} - {response.text[:200]}")
                    return f"[Image description failed: {response.status_code}]"
        except Exception as e:
            print(f"   Image captioning error: {str(e)}")
            return f"[Image description error: {str(e)}]"
    
    async def caption_elements(
        self,
        elements: List[SemanticElement],
        document_path: str = ""
    ) -> List[SemanticElement]:
        """
        Process all image elements: for PDFs with bbox, crop region → Vision (exact text);
        otherwise use image_path/image_url from metadata with describe prompt.
        """
        if not self.enabled:
            log.info("Step 3 (caption images): skipped (API key not configured)")
            return elements

        image_elements = [
            (idx, elem) for idx, elem in enumerate(elements)
            if elem.element_type in ("Image", "Figure", "FigureCaption")
        ]
        log.info("Step 3 (caption images): start image_elements=%s", len(image_elements))
        if not image_elements:
            log.info("Step 3 (caption images): done no images to caption")
            return elements

        doc_path = Path(document_path) if document_path else None
        is_pdf = doc_path and doc_path.suffix.lower() == ".pdf" and doc_path.exists()
        scale = RENDER_DPI / 72.0
        temp_dir = None
        page_paths: dict = {}

        # PDF path: render pages that have image elements with bbox, then crop → Vision exact text
        if is_pdf:
            with_bbox = [
                (idx, el) for idx, el in image_elements
                if (el.page_number and bbox_from_metadata(el.metadata or {}))
            ]
            if with_bbox:
                try:
                    temp_dir = tempfile.mkdtemp(prefix="caption_crops_")
                    rendered = render_pdf_pages(
                        str(doc_path), temp_dir, document_id=0,
                        page_numbers=list({el.page_number for _, el in with_bbox})
                    )
                    page_paths = {pno: path for pno, path in rendered}
                    log.info("Step 3 (caption images): cropping %s image regions from PDF", len(with_bbox))
                except Exception as e:
                    log.warning("Step 3 (caption images): PDF render for crop failed: %s", e)
                    page_paths = {}
                    with_bbox = []

        captioned_count = 0
        for idx, element in image_elements:
            context_parts = [f"Doc: {doc_path.name}" if doc_path else ""]
            if element.page_number:
                context_parts.append(f"Page {element.page_number}")
            if idx > 0 and elements[idx - 1].text:
                context_parts.append(f"Before: {elements[idx - 1].text[:80]}")
            if idx < len(elements) - 1 and elements[idx + 1].text:
                context_parts.append(f"After: {elements[idx + 1].text[:80]}")
            context = " | ".join(filter(None, context_parts))

            image_path = None
            image_url = None
            if element.metadata:
                image_path = element.metadata.get("image_path")
                image_url = element.metadata.get("image_url")

            # Prefer: PDF crop → Vision exact text
            if temp_dir and page_paths and element.page_number and bbox_from_metadata(element.metadata or {}):
                page_path = page_paths.get(element.page_number)
                bbox = bbox_from_metadata(element.metadata or {})
                if page_path and bbox:
                    crop_img = _crop_page_to_image(page_path, bbox, scale)
                    if crop_img is not None:
                        crop_img = cap_image_size(crop_img)
                        crop_path = Path(temp_dir) / f"crop_{element.order}.png"
                        try:
                            crop_img.save(str(crop_path))
                            description = await self.caption_image(
                                image_path=str(crop_path),
                                context=context,
                                use_exact_text_prompt=True
                            )
                            if not description.startswith("[Image"):
                                element.text = description.strip()
                                if not element.metadata:
                                    element.metadata = {}
                                element.metadata["image_description"] = description
                                element.metadata["captioned_by"] = "gpt-4o-exact-text"
                                captioned_count += 1
                        except Exception as e:
                            log.warning("Step 3 (caption images): vision crop order=%s: %s", element.order, e)
                    continue

            # Fallback: existing image_path / image_url with describe prompt
            if image_path or image_url:
                description = await self.caption_image(
                    image_path=image_path,
                    image_url=image_url,
                    context=context
                )
                if not description.startswith("[Image"):
                    element.text = (element.text or "").strip() and f"{description}\n\n{element.text}" or description
                    if not element.metadata:
                        element.metadata = {}
                    element.metadata["image_description"] = description
                    element.metadata["captioned_by"] = "gpt-4o"
                    captioned_count += 1

        if temp_dir and Path(temp_dir).exists():
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass

        log.info("Step 3 (caption images): done captioned=%s/%s", captioned_count, len(image_elements))
        return elements


# Global instance (lazy initialization)
_captioner: Optional[ImageCaptioner] = None


async def caption_images(elements: List[SemanticElement], document_path: str = "") -> List[SemanticElement]:
    """
    Convenience function to caption images in elements.
    
    This is Step 3 in the ingestion pipeline:
    Parse → Normalize → Caption Images (this) → Format Tables → Cleanup → ...
    
    Args:
        elements: Parsed elements
        document_path: Source document path
        
    Returns:
        Elements with image descriptions
    """
    global _captioner
    
    if _captioner is None:
        _captioner = ImageCaptioner()
    
    return await _captioner.caption_elements(elements, document_path)

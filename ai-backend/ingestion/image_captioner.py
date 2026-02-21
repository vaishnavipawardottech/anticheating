"""
Image Captioning with GPT-4o Vision
Step 3 in ingestion pipeline: Generate text descriptions for images
"""

import os
import base64
from typing import List, Optional
from pathlib import Path
import httpx

from .schemas import SemanticElement


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
        context: str = ""
    ) -> str:
        """
        Generate description for a single image.
        
        Args:
            image_path: Local file path to image
            image_url: Public URL to image
            image_base64: Base64-encoded image data
            context: Additional context (page number, surrounding text, etc.)
            
        Returns:
            Detailed text description of the image
        """
        if not self.enabled:
            return "[Image description unavailable - API key not configured]"
        
        # Prepare image content
        if image_path and Path(image_path).exists():
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
            image_content = {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{image_data}"
                }
            }
        elif image_url:
            image_content = {
                "type": "image_url",
                "image_url": {"url": image_url}
            }
        elif image_base64:
            image_content = {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{image_base64}"
                }
            }
        else:
            return "[Image description unavailable - no image data provided]"
        
        # Build prompt
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
        
        # Call GPT-4o Vision API
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.api_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": system_prompt
                            },
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": user_prompt},
                                    image_content
                                ]
                            }
                        ],
                        "max_tokens": 500,
                        "temperature": 0.3  # Lower temperature for more consistent descriptions
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    description = result["choices"][0]["message"]["content"].strip()
                    return description
                else:
                    error_msg = response.text
                    print(f"   GPT-4o error: {response.status_code} - {error_msg}")
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
        Process all image elements and generate descriptions.
        
        Args:
            elements: Parsed elements (some may be images)
            document_path: Path to source document (for context)
            
        Returns:
            Elements with image descriptions added to .text field
        """
        if not self.enabled:
            print("   Image captioning skipped (API key not configured)")
            return elements
        
        image_elements = [
            (idx, elem) for idx, elem in enumerate(elements)
            if elem.element_type in ("Image", "Figure", "FigureCaption")
        ]
        
        if not image_elements:
            print("   No images found to caption")
            return elements
        
        print(f"   Captioning {len(image_elements)} images with GPT-4o...")
        
        captioned_count = 0
        for idx, element in image_elements:
            # Build context from surrounding elements
            context_parts = [f"Document: {Path(document_path).name}"]
            if element.page_number:
                context_parts.append(f"Page {element.page_number}")
            
            # Get text from nearby elements for additional context
            if idx > 0 and elements[idx - 1].text:
                context_parts.append(f"Preceding text: {elements[idx - 1].text[:100]}")
            if idx < len(elements) - 1 and elements[idx + 1].text:
                context_parts.append(f"Following text: {elements[idx + 1].text[:100]}")
            
            context = " | ".join(context_parts)
            
            # Extract image data from metadata
            image_path = None
            image_url = None
            if element.metadata:
                # Unstructured stores image path or coordinates
                image_path = element.metadata.get("image_path")
                image_url = element.metadata.get("image_url")
            
            # Generate description
            description = await self.caption_image(
                image_path=image_path,
                image_url=image_url,
                context=context
            )
            
            # Store description
            if not description.startswith("[Image description"):
                # Prepend to existing text (if any, like figure caption)
                if element.text:
                    element.text = f"{description}\n\nOriginal caption: {element.text}"
                else:
                    element.text = description
                
                # Store in metadata for reference
                if not element.metadata:
                    element.metadata = {}
                element.metadata["image_description"] = description
                element.metadata["captioned_by"] = "gpt-4o"
                
                captioned_count += 1
        
        print(f"   Captioned {captioned_count}/{len(image_elements)} images")
        
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

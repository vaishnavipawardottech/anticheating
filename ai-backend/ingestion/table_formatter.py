"""
Table Formatting with LLM
Step 4 in ingestion pipeline: Convert table elements to clean Markdown
"""

import logging
import os
from typing import List, Optional
import httpx

from .schemas import SemanticElement

log = logging.getLogger(__name__)


class TableFormatter:
    """
    Convert Unstructured table elements into clean Markdown format using LLM.
    
    Why:
    - Unstructured's table output can be messy HTML or malformed text
    - LLM can intelligently parse and reformat as clean Markdown
    - Markdown tables are easier to:
      * Search and retrieve
      * Display in UI
      * Generate questions from
      * Convert to other formats
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        """
        Initialize table formatter.
        
        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: Model to use (gpt-4o-mini is fast and cheap for this task)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            print("   Warning: OPENAI_API_KEY not set. Table formatting disabled.")
            self.enabled = False
        else:
            self.enabled = True
        
        self.api_url = "https://api.openai.com/v1/chat/completions"
        self.model = model
    
    async def format_table(self, table_text: str, context: str = "") -> str:
        """
        Convert table text to clean Markdown format.
        
        Args:
            table_text: Raw table text/HTML from Unstructured
            context: Additional context (page, surrounding text)
            
        Returns:
            Clean Markdown table string
        """
        if not self.enabled:
            return table_text  # Return as-is if LLM not available
        
        system_prompt = """You are an expert at formatting tables from academic documents.

Your task: Convert the given table into clean Markdown format.

Requirements:
1. Use standard Markdown table syntax with | and -
2. Align columns properly
3. Preserve all data and headers
4. If the table has a title/caption, include it above the table
5. Clean up any HTML tags, extra whitespace, or formatting artifacts
6. If the table is malformed or unclear, do your best to reconstruct it logically

Example output:
```markdown
Table 1: Comparison of Algorithms

| Algorithm | Time Complexity | Space Complexity |
|-----------|----------------|------------------|
| BubbleSort | O(n²) | O(1) |
| QuickSort | O(n log n) | O(log n) |
```

Return ONLY the formatted Markdown table. No explanations."""
        
        user_prompt = f"""Convert this table to Markdown:

{table_text}"""
        
        if context:
            user_prompt += f"\n\nContext: {context}"
        
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
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
                            {"role": "user", "content": user_prompt}
                        ],
                        "max_tokens": 1000,
                        "temperature": 0.1  # Very low temperature for consistent formatting
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    markdown_table = result["choices"][0]["message"]["content"].strip()
                    
                    # Remove markdown code block wrapper if present
                    if markdown_table.startswith("```markdown"):
                        markdown_table = markdown_table[11:]
                    if markdown_table.startswith("```"):
                        markdown_table = markdown_table[3:]
                    if markdown_table.endswith("```"):
                        markdown_table = markdown_table[:-3]
                    
                    return markdown_table.strip()
                else:
                    print(f"   Table formatting error: {response.status_code}")
                    return table_text  # Fallback to original
                    
        except Exception as e:
            print(f"   Table formatting exception: {str(e)}")
            return table_text  # Fallback to original
    
    async def format_table_elements(
        self,
        elements: List[SemanticElement],
        document_path: str = ""
    ) -> List[SemanticElement]:
        """
        Process all table elements and convert to Markdown.
        
        Args:
            elements: Parsed elements (some may be tables)
            document_path: Path to source document (for context)
            
        Returns:
            Elements with tables converted to Markdown
        """
        if not self.enabled:
            log.info("Step 4 (format tables): skipped (API key not configured)")
            return elements
        
        table_elements = [
            (idx, elem) for idx, elem in enumerate(elements)
            if elem.element_type == "Table" and elem.text
        ]
        log.info("Step 4 (format tables): start table_elements=%s", len(table_elements))
        if not table_elements:
            log.info("Step 4 (format tables): done no tables to format")
            return elements
        
        formatted_count = 0
        for idx, element in table_elements:
            # Build context
            context_parts = []
            if element.page_number:
                context_parts.append(f"Page {element.page_number}")
            
            # Get surrounding text for context
            if idx > 0 and elements[idx - 1].text:
                context_parts.append(f"Preceding: {elements[idx - 1].text[:100]}")
            
            context = " | ".join(context_parts) if context_parts else ""
            
            # Format table
            original_text = element.text
            markdown_table = await self.format_table(original_text, context)
            
            # Update element
            if markdown_table != original_text:
                element.text = markdown_table
                
                # Store both versions in metadata
                if not element.metadata:
                    element.metadata = {}
                element.metadata["original_table"] = original_text
                element.metadata["formatted_by"] = self.model
                
                formatted_count += 1
        
        log.info("Step 4 (format tables): done formatted=%s/%s", formatted_count, len(table_elements))
        return elements


# Global instance (lazy initialization)
_formatter: Optional[TableFormatter] = None


async def format_tables(elements: List[SemanticElement], document_path: str = "") -> List[SemanticElement]:
    """
    Convenience function to format tables in elements.
    
    This is Step 4 in the ingestion pipeline:
    Parse → Normalize → Caption Images → Format Tables (this) → Cleanup → ...
    
    Args:
        elements: Parsed elements
        document_path: Source document path
        
    Returns:
        Elements with tables formatted as Markdown
    """
    global _formatter
    
    if _formatter is None:
        _formatter = TableFormatter()
    
    return await _formatter.format_table_elements(elements, document_path)

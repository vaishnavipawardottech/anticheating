"""
Unicode and Text Normalization
Step 2 in ingestion pipeline: Clean text immediately after Unstructured parsing
"""

import re
from typing import List
from .schemas import SemanticElement


def normalize_text(text: str) -> str:
    """
    Normalize text to remove PDF/PPT artifacts and clean up formatting.
    
    This runs EARLY in the pipeline (Step 2) to ensure:
    - Clean text for embeddings
    - Better cleanup/classification downstream
    - Consistent text format across all elements
    
    Removes:
    - CID artifacts from PDF: (cid:123)
    - Private Use Area characters (custom PDF symbols/bullets)
    - Unicode control characters and zero-width spaces
    - Multiple spaces/tabs/newlines → single space
    - Bullet point artifacts (•, ■, □, ◦, etc.)
    
    Normalizes:
    - Different types of spaces → regular space
    - Different types of hyphens/dashes → regular hyphen
    - Smart quotes → straight quotes
    - Punctuation spacing
    """
    if not text or not text.strip():
        return text
    
    # Remove CID artifacts (PDF encoding errors like "(cid:123)")
    text = re.sub(r'\(cid:\d+\)', '', text)
    
    # Remove Private Use Area (PUA) characters: U+E000..U+F8FF
    # These are custom symbols/bullets from PDFs (e.g., \uf07d)
    text = re.sub(r'[\uE000-\uF8FF]', '', text)
    
    # Remove common bullet/box artifacts when standalone at start of line
    text = re.sub(r'^[\u2022\u25A0\u25A1\u25C6\u25E6\u2023\u2043\u00B7\u2219]+\s*', '', text)
    
    # Remove unicode control characters and zero-width spaces
    text = re.sub(r'[\u0000-\u001F\u007F-\u009F\u200B-\u200D\uFEFF]', '', text)
    
    # Normalize different types of spaces to regular space
    # Includes: non-breaking space, en space, em space, thin space, etc.
    text = re.sub(r'[\u00A0\u2000-\u200A\u202F\u205F]', ' ', text)
    
    # Normalize different types of hyphens/dashes to regular hyphen
    # Includes: figure dash, en dash, em dash, horizontal bar
    text = re.sub(r'[\u2010-\u2015\u2212]', '-', text)
    
    # Normalize quotes
    text = re.sub(r'[\u201C\u201D]', '"', text)  # Smart double quotes → "
    text = re.sub(r'[\u2018\u2019]', "'", text)  # Smart single quotes → '
    
    # Remove multiple spaces, tabs, newlines → single space
    text = re.sub(r'\s+', ' ', text)
    
    # Fix spacing around punctuation (common PDF artifact)
    # Remove space before punctuation: "word ." → "word."
    text = re.sub(r'\s+([.,;:!?)])', r'\1', text)
    
    # Ensure space after punctuation if followed by word: "word.next" → "word. next"
    text = re.sub(r'([.,;:!?)])([A-Za-z])', r'\1 \2', text)
    
    # Remove space after opening brackets: "( word" → "(word"
    text = re.sub(r'([\(\[])\s+', r'\1', text)
    
    # Remove space before closing brackets: "word )" → "word)"
    text = re.sub(r'\s+([\)\]])', r'\1', text)
    
    return text.strip()


def normalize_elements(elements: List[SemanticElement]) -> List[SemanticElement]:
    """
    Normalize text in all parsed elements.
    
    This is Step 2 in the ingestion pipeline:
    Parse (Unstructured) → Normalize (this function) → Cleanup → Classify → ...
    
    Args:
        elements: Raw elements from Unstructured parser
        
    Returns:
        Elements with normalized text
    """
    normalized_count = 0
    
    for element in elements:
        if element.text and element.text.strip():
            original = element.text
            element.text = normalize_text(element.text)
            
            if original != element.text:
                normalized_count += 1
    
    print(f"   Normalized {normalized_count}/{len(elements)} elements")
    
    return elements

"""
Unicode and Text Normalization
Step 2 in ingestion pipeline: Clean text immediately after Unstructured parsing.

When formula_mode is True (e.g. Discrete Mathematics): we preserve math/logic symbols
(∀, ∃, ∧, ∨, →, ↔, ¬, and minus U+2212) and avoid normalizations that would alter equations.
"""

import logging
import re
from typing import List
from .schemas import SemanticElement

log = logging.getLogger(__name__)

# Logic/math symbols we must never strip or corrupt (for formula_mode / DM).
# ∀ ∃ ∧ ∨ ¬ → ↔ ← and minus sign U+2212 are preserved by not including them in strip patterns.
MATH_LOGIC_UNICODE = "\u2200\u2203\u2227\u2228\u00AC\u2192\u2194\u2190\u2212"  # ∀ ∃ ∧ ∨ ¬ → ↔ ← −


def normalize_text(text: str, formula_mode: bool = False) -> str:
    """
    Normalize text to remove PDF/PPT artifacts and clean up formatting.

    When formula_mode=True (e.g. subject is Discrete Mathematics): preserves math symbols
    and avoids replacing minus sign (U+2212) so equations stay correct.

    Removes:
    - CID artifacts from PDF: (cid:123)
    - Private Use Area characters (custom PDF symbols/bullets)
    - Unicode control characters and zero-width spaces
    - Bullet point artifacts at start of line

    Normalizes:
    - Spaces, hyphens (unless formula_mode: then keep U+2212), quotes, punctuation spacing.
    """
    if not text or not text.strip():
        return text

    # Remove CID artifacts (PDF encoding errors like "(cid:123)")
    text = re.sub(r'\(cid:\d+\)', '', text)

    # Remove Private Use Area (PUA) characters: U+E000..U+F8FF
    text = re.sub(r'[\uE000-\uF8FF]', '', text)

    # Remove common bullet/box artifacts when standalone at start of line
    text = re.sub(r'^[\u2022\u25A0\u25A1\u25C6\u25E6\u2023\u2043\u00B7\u2219]+\s*', '', text)

    # Remove unicode control characters and zero-width spaces
    text = re.sub(r'[\u0000-\u001F\u007F-\u009F\u200B-\u200D\uFEFF]', '', text)

    # Normalize different types of spaces to regular space
    text = re.sub(r'[\u00A0\u2000-\u200A\u202F\u205F]', ' ', text)

    # Normalize hyphens/dashes to regular hyphen; in formula_mode keep U+2212 (minus) for equations
    if formula_mode:
        text = re.sub(r'[\u2010-\u2015]', '-', text)  # en/em dash etc. → hyphen; leave U+2212
    else:
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


def normalize_elements(
    elements: List[SemanticElement],
    formula_mode: bool = False,
) -> List[SemanticElement]:
    """
    Normalize text in all parsed elements.

    formula_mode: when True (e.g. Discrete Mathematics), preserve math/logic symbols and minus sign.
    """
    log.info("Step 2 (normalize): start elements=%s formula_mode=%s", len(elements), formula_mode)
    normalized_count = 0
    for element in elements:
        if element.text and element.text.strip():
            original = element.text
            element.text = normalize_text(element.text, formula_mode=formula_mode)
            if original != element.text:
                normalized_count += 1
    log.info("Step 2 (normalize): done normalized=%s/%s", normalized_count, len(elements))
    return elements

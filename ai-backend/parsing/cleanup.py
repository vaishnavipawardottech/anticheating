"""
Pre-Alignment Cleanup Module
Deterministic filters to remove noise elements before alignment

NO AI/LLM usage - all filters are pattern-based and deterministic
"""

from typing import List, Dict
from parsing.schemas import SemanticElement
import re


class CleanupStatistics:
    """Statistics about cleanup operation"""
    
    def __init__(self):
        self.total_elements = 0
        self.removed_elements = 0
        self.kept_elements = 0
        self.removal_reasons: Dict[str, int] = {}
    
    def add_removal(self, reason: str):
        """Record an element removal"""
        self.removed_elements += 1
        self.removal_reasons[reason] = self.removal_reasons.get(reason, 0) + 1
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "total_elements": self.total_elements,
            "removed_elements": self.removed_elements,
            "kept_elements": self.kept_elements,
            "removal_reasons": self.removal_reasons
        }


class CleanupResult:
    """Result of cleanup operation"""
    
    def __init__(self, elements: List[SemanticElement], statistics: CleanupStatistics):
        self.elements = elements
        self.statistics = statistics
        self.original_count = statistics.total_elements
        self.cleaned_count = statistics.kept_elements


class DocumentCleanup:
    """
    Deterministic document cleanup filters
    
    Removes noise elements:
    - Headers/Footers
    - Page numbers
    - TOC dotted leaders
    - Pure numeric elements
    - Empty/whitespace-only elements
    - PDF encoding artifacts (CID)
    """
    
    # Page number patterns
    PAGE_NUMBER_PATTERNS = [
        r'^\d+$',                    # Just a number: "5"
        r'^page\s+\d+$',             # "page 5"
        r'^\d+\s*/\s*\d+$',          # "5 / 10"
        r'^\[\s*\d+\s*\]$',          # "[5]"
    ]
    
    # TOC leader patterns (dotted lines)
    TOC_LEADER_PATTERNS = [
        r'\.{4,}',                   # Four or more dots: "....."
        r'_{4,}',                    # Four or more underscores
        r'-{4,}',                    # Four or more dashes
    ]
    
    # CID artifact pattern (PDF encoding issue)
    CID_PATTERN = r'\(cid:\d+\)'
    
    @staticmethod
    def is_header_footer(element: SemanticElement) -> bool:
        """
        Detect header/footer elements
        
        Uses element_type classification from unstructured library
        """
        return element.element_type in ["Header", "Footer"]
    
    @staticmethod
    def is_page_number(text: str) -> bool:
        """
        Detect standalone page numbers
        
        Conservative: only removes obvious page numbers
        Keeps: "Chapter 1", "Figure 2.3", "Section 1.2"
        """
        if not text:
            return False
        
        text_clean = text.strip().lower()
        
        # Check against page number patterns
        for pattern in DocumentCleanup.PAGE_NUMBER_PATTERNS:
            if re.match(pattern, text_clean, re.IGNORECASE):
                return True
        
        return False
    
    @staticmethod
    def is_toc_leader(text: str) -> bool:
        """
        Detect TOC dotted leaders
        
        Examples: "Introduction ........ 5", "Chapter 1 _____ 10"
        """
        if not text:
            return False
        
        for pattern in DocumentCleanup.TOC_LEADER_PATTERNS:
            if re.search(pattern, text):
                return True
        
        return False
    
    @staticmethod
    def is_pure_numeric(text: str) -> bool:
        """
        Detect pure numeric elements (likely noise)
        
        Conservative: only removes standalone numbers/punctuation
        Keeps: "x = 2y + 3", "2.5 GHz", "Chapter 1"
        """
        if not text:
            return False
        
        text_clean = text.strip()
        
        # Must be very short (1-5 chars) and only digits/punctuation
        if len(text_clean) > 5:
            return False
        
        # Only digits and basic punctuation (no letters)
        if re.match(r'^[\d\.\,\-\s]+$', text_clean):
            return True
        
        return False
    
    @staticmethod
    def is_empty_or_whitespace(element: SemanticElement) -> bool:
        """
        Detect empty or whitespace-only elements
        """
        if element.text is None:
            return False  # Images/tables with no text are legitimate
        
        return len(element.text.strip()) == 0
    
    @staticmethod
    def has_cid_artifact(text: str) -> bool:
        """
        Detect PDF CID encoding artifacts
        
        Example: "(cid:0)" - PDF character encoding issue
        """
        if not text:
            return False
        
        return bool(re.search(DocumentCleanup.CID_PATTERN, text))
    
    @staticmethod
    def cleanup_elements(elements: List[SemanticElement]) -> CleanupResult:
        """
        Apply all cleanup filters to element list
        
        Args:
            elements: List of semantic elements from document parser
            
        Returns:
            CleanupResult with filtered elements and statistics
        """
        stats = CleanupStatistics()
        stats.total_elements = len(elements)
        
        cleaned_elements = []
        
        for element in elements:
            # Apply filters in order of specificity
            
            # Filter 1: Header/Footer elements
            if DocumentCleanup.is_header_footer(element):
                stats.add_removal("header_footer")
                continue
            
            # Filter 2: Empty/whitespace-only
            if DocumentCleanup.is_empty_or_whitespace(element):
                stats.add_removal("empty_whitespace")
                continue
            
            # Remaining filters need text
            if element.text is None:
                cleaned_elements.append(element)
                continue
            
            # Filter 3: Page numbers
            if DocumentCleanup.is_page_number(element.text):
                stats.add_removal("page_number")
                continue
            
            # Filter 4: TOC leaders
            if DocumentCleanup.is_toc_leader(element.text):
                stats.add_removal("toc_leader")
                continue
            
            # Filter 5: Pure numeric
            if DocumentCleanup.is_pure_numeric(element.text):
                stats.add_removal("pure_numeric")
                continue
            
            # Filter 6: CID artifacts (remove from text, keep element)
            if DocumentCleanup.has_cid_artifact(element.text):
                # Clean the text but keep the element
                element.text = re.sub(DocumentCleanup.CID_PATTERN, '', element.text).strip()
                # If cleaning removed all text, skip element
                if not element.text:
                    stats.add_removal("cid_artifact_only")
                    continue
                stats.add_removal("cid_artifact_cleaned")
            
            # Element passed all filters
            cleaned_elements.append(element)
        
        stats.kept_elements = len(cleaned_elements)
        
        return CleanupResult(cleaned_elements, stats)


# Convenience function for direct use
def cleanup_elements(elements: List[SemanticElement]) -> CleanupResult:
    """
    Apply cleanup filters to semantic elements
    
    Convenience wrapper around DocumentCleanup.cleanup_elements()
    """
    return DocumentCleanup.cleanup_elements(elements)

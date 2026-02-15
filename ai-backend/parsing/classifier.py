"""
Element Classifier
Categorizes parsed elements into: TEXT, DIAGRAM, TABLE, CODE, FORMULA, OTHER
Uses rule-based heuristics (no AI/LLM)
"""

from typing import Optional
from parsing.schemas import SemanticElement
import re


class ElementCategory:
    """Element category constants"""
    TEXT = "TEXT"
    DIAGRAM = "DIAGRAM"
    TABLE = "TABLE"
    CODE = "CODE"
    FORMULA = "FORMULA"
    OTHER = "OTHER"


class ElementClassifier:
    """
    Classifies semantic elements into categories
    Uses deterministic rules based on element type and content
    """
    
    # Keywords that suggest diagram/figure content
    DIAGRAM_KEYWORDS = [
        "figure", "diagram", "architecture", "flowchart", "uml",
        "schema", "graph", "chart", "illustration", "drawing",
        "model", "structure", "topology", "layout"
    ]
    
    # Keywords that suggest code content
    CODE_KEYWORDS = [
        "function", "class", "def ", "public ", "private ",
        "void ", "int ", "return ", "import ", "include ",
        "{", "}", "//", "/*", "*/", "#include", "package "
    ]
    
    # Patterns for mathematical formulas
    FORMULA_PATTERNS = [
        r'[∑∏∫∂∇]',  # Math symbols
        r'\$.*\$',     # LaTeX inline
        r'\\[a-z]+\{', # LaTeX commands
        r'[a-zA-Z]\s*=\s*[a-zA-Z0-9\+\-\*/\(\)]+',  # Equations
    ]
    
    @staticmethod
    def classify(element: SemanticElement) -> str:
        """
        Classify element into a category
        
        Args:
            element: Semantic element to classify
            
        Returns:
            Category string (TEXT, DIAGRAM, TABLE, CODE, FORMULA, OTHER)
        """
        element_type = element.element_type
        text = element.text or ""
        
        # 1. Check element type first (most reliable)
        if element_type == "Table":
            return ElementCategory.TABLE
        
        if element_type in ["Image", "FigureCaption"]:
            # Check if it's a diagram or just an image
            if ElementClassifier._is_diagram(text, element):
                return ElementCategory.DIAGRAM
            return ElementCategory.OTHER
        
        # 2. Check for code blocks
        if element_type == "CodeSnippet" or ElementClassifier._is_code(text):
            return ElementCategory.CODE
        
        # 3. Check for formulas
        if ElementClassifier._is_formula(text):
            return ElementCategory.FORMULA
        
        # 4. Text elements
        if element_type in ["Title", "NarrativeText", "ListItem", "Text"]:
            return ElementCategory.TEXT
        
        # 5. Default to OTHER
        return ElementCategory.OTHER
    
    @staticmethod
    def _is_diagram(text: str, element: SemanticElement) -> bool:
        """
        Determine if an image/figure is a diagram (technical content)
        
        Checks:
        - Caption text for diagram keywords
        - Nearby text context (if available in metadata)
        """
        if not text:
            return False
        
        text_lower = text.lower()
        
        # Check for diagram keywords in caption
        for keyword in ElementClassifier.DIAGRAM_KEYWORDS:
            if keyword in text_lower:
                return True
        
        # Check if caption starts with "Figure X" or "Fig X"
        if re.match(r'^(figure|fig\.?)\s+\d+', text_lower):
            return True
        
        return False
    
    @staticmethod
    def _is_code(text: str) -> bool:
        """
        Determine if text is a code block
        
        Checks:
        - Code keywords
        - Indentation patterns
        - Syntax characters
        """
        if not text or len(text) < 10:
            return False
        
        text_lower = text.lower()
        
        # Check for code keywords
        keyword_count = sum(1 for kw in ElementClassifier.CODE_KEYWORDS if kw in text_lower)
        if keyword_count >= 2:
            return True
        
        # Check for code-like patterns
        # Multiple lines with consistent indentation
        lines = text.split('\n')
        if len(lines) >= 3:
            indented_lines = sum(1 for line in lines if line.startswith('    ') or line.startswith('\t'))
            if indented_lines >= len(lines) * 0.5:  # 50% of lines indented
                return True
        
        # Check for curly braces (common in many languages)
        if '{' in text and '}' in text:
            return True
        
        return False
    
    @staticmethod
    def _is_formula(text: str) -> bool:
        """
        Determine if text contains mathematical formulas
        
        Checks:
        - LaTeX syntax
        - Math symbols
        - Equation patterns
        """
        if not text or len(text) < 3:
            return False
        
        # Check formula patterns
        for pattern in ElementClassifier.FORMULA_PATTERNS:
            if re.search(pattern, text):
                return True
        
        return False
    
    @staticmethod
    def is_diagram_critical(element: SemanticElement) -> bool:
        """
        Determine if element is diagram-critical
        
        An element is diagram-critical if:
        - It's a diagram itself
        - It references diagrams heavily
        - It's near diagram elements (future enhancement)
        
        Args:
            element: Semantic element to check
            
        Returns:
            True if element is diagram-critical
        """
        category = ElementClassifier.classify(element)
        
        # Diagrams are always diagram-critical
        if category == ElementCategory.DIAGRAM:
            return True
        
        # Check if text heavily references diagrams
        if element.text:
            text_lower = element.text.lower()
            diagram_references = sum(1 for kw in ["figure", "diagram", "shown in", "as illustrated"]
                                    if kw in text_lower)
            if diagram_references >= 2:
                return True
        
        return False


# Convenience function
def classify_element(element: SemanticElement) -> str:
    """Classify a semantic element into a category"""
    return ElementClassifier.classify(element)

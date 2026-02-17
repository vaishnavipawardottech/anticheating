"""
Smart section-aware chunker: clean → normalize → accumulate → chunk.
Optional: semantic split (embedding-based) so we break at topic boundaries, not mid-thought.

Strategy:
1. Prepare: drop junk, normalize text (remove PDF/PPT artifacts), join broken sentences, de-duplicate.
2. Structure: heading stack → section_path for metadata.
3. Accumulate: collect content until we reach optimal chunk size.
4. Normalize: clean extra whitespace, remove CID artifacts, fix punctuation spacing.
5. Chunk when target size reached, with proper minimum enforcement.
6. Overlap: maintain 100-character overlap between consecutive chunks for continuity.

Production principles:
- Chunks must be 600-1000 characters for optimal retrieval
- Every chunk includes full sentences - no mid-sentence breaks
- Overlapping provides context continuity between chunks
- Simple, predictable accumulation logic

Target: 600–1000 characters per chunk, 100-character overlap for continuity.
"""

from dataclasses import dataclass, field
from typing import List, Any, Tuple, Callable, Optional
import re

# Chunk size: character count for direct control over chunk size.
# Production settings: balanced for context and search performance.
TARGET_CHUNK_MIN_CHARS = 600   # minimum chunk size in characters
TARGET_CHUNK_MAX_CHARS = 1000  # maximum chunk size in characters
OVERLAP_CHARS = 100            # overlap between consecutive chunks in characters
MAX_FRAGMENT_WORDS = 4         # treat as fragment if ≤ this many words and no sentence end
SENTENCE_END = re.compile(r"[.!?]\s*$")
JUNK_PATTERN = re.compile(r"^[\s\-—_·•■□]+$")
FIGURE_TABLE_CAPTION = re.compile(r"^(Figure|Fig\.?|Table)\s+[\d.]+\s*", re.I)
MAJOR_HEADING = re.compile(r"^(Unit\s+[IVXLCDM0-9]+|\d+[-.]\s*\d*|\d+\s*[-.]\s*\d*)", re.I)
# Institutional boilerplate patterns to exclude from section paths (college names, departments, etc.)
INSTITUTIONAL_BOILERPLATE = re.compile(
    r"(Department of Computer Engineering|BRACT'?S|Vishwakarma Institute|"
    r"Institute of Information Technology|Pune-?\d+|"
    r"An Autonomous Institute|affiliated to|Savitribai Phule|"
    r"University|College|Department|Faculty)", re.I
)


@dataclass
class DocumentChunkInfo:
    """One chunk of document content with section context"""
    text: str
    section_path: str
    page_start: int
    page_end: int
    source_element_orders: List[int] = field(default_factory=list)
    chunk_type: str = "text"  # "text", "table_row", "table_schema"
    table_id: int | None = None   # element order of table (for table_row / table_schema)
    row_id: int | None = None    # 0-based row index (for table_row only)


@dataclass
class _NormElem:
    """Normalized element after clean + fragment merge + dedup (internal)."""
    text: str
    source_orders: List[int]
    page_number: int | None
    element_type: str
    category: str


def _normalize_text(text: str) -> str:
    """
    Normalize text to remove PDF/PPT artifacts and clean up formatting.
    
    Removes:
    - Multiple spaces/tabs/newlines → single space
    - CID artifacts from PDF: (cid:123)
    - Unicode control characters
    - Private Use Area characters (custom PDF symbols/bullets)
    - Extra spaces around punctuation
    - Bullet point artifacts (•, ■, □, ◦, etc.)
    """
    if not text or not text.strip():
        return text
    
    # Remove CID artifacts (PDF encoding errors)
    text = re.sub(r'\(cid:\d+\)', '', text)
    
    # Remove Private Use Area (PUA) characters: U+E000..U+F8FF
    # These are custom symbols/bullets from PDFs (e.g., \uf07d)
    text = re.sub(r'[\uE000-\uF8FF]', '', text)
    
    # Remove common bullet/box artifacts when standalone
    text = re.sub(r'^[\u2022\u25A0\u25A1\u25C6\u25E6\u2023\u2043\u00B7\u2219]+\s*', '', text)
    
    # Remove unicode control characters and zero-width spaces
    text = re.sub(r'[\u0000-\u001F\u007F-\u009F\u200B-\u200D\uFEFF]', '', text)
    
    # Normalize different types of spaces to regular space
    text = re.sub(r'[\u00A0\u2000-\u200A\u202F\u205F]', ' ', text)
    
    # Normalize different types of hyphens/dashes to regular hyphen
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
    text = re.sub(r'([(])\s+', r'\1', text)
    
    # Remove space before closing brackets: "word )" → "word)"
    text = re.sub(r'\s+([)])', r'\1', text)
    
    return text.strip()


def _is_junk_token(text: str) -> bool:
    """Drop: literal —, empty, repeated separators."""
    if not text or not text.strip():
        return True
    s = text.strip()
    if s in ("—", "–", "−", " "):
        return True
    if JUNK_PATTERN.match(s):
        return True
    return False


def _is_sentence_fragment(text: str) -> bool:
    """True if short (1–4 words) and does not end with . ! ?"""
    if not text or not text.strip():
        return False
    s = text.strip()
    words = s.split()
    if len(words) > MAX_FRAGMENT_WORDS:
        return False
    return not bool(SENTENCE_END.search(s))


def _is_figure_or_table_caption(text: str, element_type: str) -> bool:
    """True if this is a figure/table caption (attach to next body, don't embed alone)."""
    if not text or not text.strip():
        return False
    if element_type in ("FigureCaption", "Table", "Image"):
        return True
    if element_type == "Title" and FIGURE_TABLE_CAPTION.match(text.strip()):
        return True
    return False


def _is_label_only_heading(text: str, element_type: str) -> bool:
    """Note, Example 2.4, etc. — attach to next content, don't push section stack."""
    if not text or not text.strip():
        return False
    s = text.strip().lower()
    if element_type != "Title":
        return False
    if s in ("note", "notes", "example", "summary", "key point", "key points"):
        return True
    if re.match(r"^example\s+[\d.]+\s*", s):
        return True
    return False


def prepare_for_chunking(elements: List[Any]) -> List[_NormElem]:
    """
    Clean → join fragments → dedup → normalize. Must run before chunk_elements.
    - Drops junk tokens (—, empty, separator-only).
    - Normalizes text to remove PDF/PPT artifacts.
    - Aggressively merges small consecutive fragments (< 150 chars) regardless of type.
    - Handles broken Unstructured output where sentences are split mid-way.
    - De-duplicates consecutive identical text.
    Returns list of _NormElem with source_orders for each merged block.
    """
    if not elements:
        return []
    # Build list of (text, order, page, type, category)
    rows: List[Tuple[str, int, Any, str, str]] = []
    for i, elem in enumerate(elements):
        text = (getattr(elem, "text", None) or "").strip()
        if _is_junk_token(text):
            continue
        # Normalize text to remove PDF/PPT artifacts
        text = _normalize_text(text)
        if not text:  # Skip if normalization resulted in empty text
            continue
        page = getattr(elem, "page_number", None)
        etype = getattr(elem, "element_type", "") or ""
        cat = getattr(elem, "category", "OTHER")
        rows.append((text, i, page, etype, cat))

    # AGGRESSIVE MERGE: Merge ANY consecutive small fragments (< 150 chars)
    # This fixes Unstructured library breaking sentences mid-way
    # Example: "Human : a user, a group of users , or" (60 chars)
    #        + "an organization, trying to get the job done with the" (52 chars)
    #        + "technology." (11 chars)
    # → "Human : a user, a group of users , or an organization, trying to get the job done with the technology."
    merged: List[Tuple[str, List[int], Any, str, str]] = []
    i = 0
    while i < len(rows):
        text, order, page, etype, cat = rows[i]
        orders = [order]
        
        # Keep merging as long as current text is small (< 150 chars)
        while len(text) < 150 and i + 1 < len(rows):
            next_text, next_order, next_page, next_etype, next_cat = rows[i + 1]
            # Only merge TEXT category elements
            if cat != "TEXT" or next_cat != "TEXT":
                break
            # Merge if next is also small (< 150 chars) - both are likely fragments
            if len(next_text) < 150:
                text = text + " " + next_text
                orders.append(next_order)
                page = next_page or page
                i += 1
            else:
                # Next is large, stop merging
                break
        
        # De-duplicate: if same text as previous, skip (keep first occurrence)
        if merged and merged[-1][0] == text:
            i += 1
            continue
        merged.append((text, orders, page, etype, cat))
        i += 1

    return [
        _NormElem(text=t, source_orders=o, page_number=p, element_type=et, category=c)
        for t, o, p, et, c in merged
    ]


def compute_section_paths_for_elements(elements: List[Any]) -> List[str]:
    """
    DISABLED: Section path logic is broken - creates 2500+ char garbage paths.
    
    Issue: Unstructured library breaks sentences into fragments marked as "Title".
    These fragments get added to section path, creating massive corrupted paths.
    
    Example broken path (2500+ chars):
    "Human Computer Interaction > large-scale computer system. > Interaction: any communication..."
    (thousands of chars of body text incorrectly treated as headings)
    
    TODO: Re-enable after fixing Unstructured parser or implementing better heading detection.
    For now, return empty paths for all elements.
    """
    # COMMENTED OUT - BROKEN LOGIC
    # paths: List[str] = []
    # section_path_parts: List[str] = []
    # for elem in elements:
    #     elem_type = getattr(elem, "element_type", "") or ""
    #     text = (getattr(elem, "text", None) or "").strip()
    #     if _is_heading_type(elem_type) and text:
    #         section_path_parts = [t.strip() for t in section_path_parts if t.strip()]
    #         # Skip institutional boilerplate (college names, departments, etc.)
    #         if not _is_institutional_boilerplate(text):
    #             section_path_parts.append(text)
    #     section_path = " > ".join(section_path_parts) if section_path_parts else ""
    #     paths.append(section_path)
    # return paths
    
    # Return empty paths for all elements
    return [""] * len(elements)


def table_to_row_chunks(
    table_text: str,
    section_path: str,
    page: int,
    element_order: int,
    include_schema_chunk: bool = True,
) -> List[DocumentChunkInfo]:
    """
    Turn a table into: optional table_schema chunk (column meanings) + one chunk per row.
    Row chunks are retrieval-friendly (e.g. "Coax type: RG-58 | use: ... | impedance: 50 Ω").
    Payload can store table_id, row_id, section_path for query-time boosting.
    """
    if not table_text or not table_text.strip():
        return []
    lines = [ln.strip() for ln in table_text.strip().splitlines() if ln.strip()]
    if not lines:
        return []
    first = lines[0]
    delim = "|" if "|" in first else ("\t" if "\t" in first else ",")
    result: List[DocumentChunkInfo] = []

    # Optional: table schema chunk (what columns mean + how to use)
    if include_schema_chunk and lines:
        header_cells = [c.strip() for c in lines[0].split(delim) if c.strip()]
        if header_cells:
            schema_text = "Table columns: " + " | ".join(header_cells)
            result.append(DocumentChunkInfo(
                text=schema_text,
                section_path=section_path,
                page_start=page or 1,
                page_end=page or 1,
                source_element_orders=[element_order],
                chunk_type="table_schema",
                table_id=element_order,
                row_id=None,
            ))

    for i, line in enumerate(lines):
        cells = [c.strip() for c in line.split(delim) if c.strip()]
        if not cells:
            continue
        row_text = " | ".join(cells)
        if not row_text or _is_trivial_text(row_text):
            continue
        result.append(DocumentChunkInfo(
            text=row_text,
            section_path=section_path,
            page_start=page or 1,
            page_end=page or 1,
            source_element_orders=[element_order],
            chunk_type="table_row",
            table_id=element_order,
            row_id=i,
        ))
    return result


def _is_heading_type(element_type: str) -> bool:
    """True if element should update section path (Title, Heading, Header)."""
    if not element_type:
        return False
    et = element_type.strip().lower()
    return et in ("title", "heading", "header") or "heading" in et or "header" in et


def _approx_chars(text: str) -> int:
    """Character count for chunk size calculation."""
    if not text or not text.strip():
        return 0
    return len(text.strip())


def _is_institutional_boilerplate(text: str) -> bool:
    """
    True if text is institutional boilerplate (college name, department, etc.)
    that should be excluded from section paths.
    """
    if not text or not text.strip():
        return False
    return bool(INSTITUTIONAL_BOILERPLATE.search(text.strip()))


def _clean_section_path(section_path: str) -> str:
    """
    Remove institutional boilerplate from section path.
    
    Example:
    Input:  "Unit I > Business Intelligence > Department of Computer Engineering BRACT'S, Vishwakarma Institute"
    Output: "Unit I > Business Intelligence"
    """
    if not section_path:
        return section_path
    
    parts = [p.strip() for p in section_path.split(">") if p.strip()]
    # Filter out parts that are institutional boilerplate
    cleaned_parts = [p for p in parts if not _is_institutional_boilerplate(p)]
    return " > ".join(cleaned_parts) if cleaned_parts else ""


def _is_trivial_text(text: str) -> bool:
    """
    True if element text is noise: bullets, boxes, symbol-only, or too short to be useful.
    Such elements are skipped when building chunks (no separate chunk, not merged as sole content).
    """
    if not text or not text.strip():
        return True
    s = text.strip()
    if len(s) <= 1:
        return True
    # Strip common decorative/symbol chars; if nothing meaningful remains, skip
    stripped = re.sub(r"[\s\u25A0\u25A1\u25C6\u2022\u00B7\-_*■□•·]+", "", s)  # boxes, bullets, dashes
    if not stripped or len(stripped) < 2:
        return True
    # Single "word" that is only symbols/digits (e.g. "1.", "■")
    words = s.split()
    if len(words) <= 2 and not re.search(r"[a-zA-Z]{2,}", s):
        return True
    return False


def _is_structural_heading(text: str, element_type: str) -> bool:
    """True if this heading should update section path (Unit, 1.1, etc.). Excludes Note/Example/Figure/Table captions."""
    if not text or not text.strip():
        return False
    if not _is_heading_type(element_type):
        return False
    if _is_label_only_heading(text, element_type) or _is_figure_or_table_caption(text, element_type):
        return False
    # CRITICAL FIX: Ignore very short "Title" fragments (likely PDF parsing errors or sentence continuations)
    # A real structural heading should be at least 3 words or match major patterns (Unit I, 1.1, etc.)
    stripped = text.strip()
    word_count = len(stripped.split())
    if word_count < 3 and not MAJOR_HEADING.match(stripped):
        # Short fragment that doesn't match major heading pattern → treat as regular text, not heading
        return False
    return True


def _enrich_chunk_text(body: str, section_path: str) -> str:
    """Return chunk text without Path prefix (section_path is stored separately in metadata)."""
    if not body or not body.strip():
        return body
    return body.strip()


def _cosine_sim(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors. Assumes non-zero norm."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)


def _best_semantic_split_index(
    parts: List[str],
    embed_fn: Callable[[List[str]], List[List[float]]],
) -> int:
    """
    Find the best index to split parts so the first chunk ends at a topic boundary.
    Uses embedding similarity: split at the boundary where consecutive parts have
    *lowest* similarity (topic shift). Returns index i so parts[0:i+1] is first chunk.
    """
    if len(parts) < 2:
        return 0
    try:
        embeddings = embed_fn(parts)
        if not embeddings or len(embeddings) != len(parts):
            return 0
        best_i = 0
        min_sim = 1.0
        for i in range(len(parts) - 1):
            sim = _cosine_sim(embeddings[i], embeddings[i + 1])
            if sim < min_sim:
                min_sim = sim
                best_i = i
        return best_i
    except Exception:
        return 0


def chunk_elements(
    elements: List[Any],
    embed_fn: Optional[Callable[[List[str]], List[List[float]]]] = None,
) -> List[DocumentChunkInfo]:
    """
    Production-ready chunking: clean → normalize → accumulate → chunk with overlap.
    
    FIXED Behavior:
    - Checks size BEFORE adding text (prevents exceeding 1000 max)
    - Creates chunks with proper 100-char overlap
    - Enforces strict 600-1000 character range
    - Resets page tracking after each chunk
    - Section paths disabled (set to empty string)
    
    Result: Consistent 600-1000 char chunks with proper overlap, no garbage paths.
    """
    normalized = prepare_for_chunking(elements)
    # DISABLED: section_path_parts: List[str] = []  # Section paths commented out - broken logic
    chunks: List[DocumentChunkInfo] = []
    
    # Current chunk being built
    current_text_parts: List[str] = []
    current_orders: List[int] = []
    current_page_start: int | None = None
    current_page_end: int | None = None

    def create_chunk_with_overlap():
        """Create a chunk from accumulated text and set up overlap for next chunk."""
        nonlocal current_text_parts, current_orders, current_page_start, current_page_end
        
        if not current_text_parts:
            return
        
        # Combine all text parts
        combined_text = " ".join(current_text_parts)
        combined_text = _normalize_text(combined_text).strip()
        
        # Skip if too small (shouldn't happen but safety check)
        if len(combined_text) < TARGET_CHUNK_MIN_CHARS:
            return
        
        # Create chunk with EMPTY section_path (disabled)
        section_path = ""  # DISABLED: section paths create garbage
        chunk_text = _enrich_chunk_text(combined_text, section_path)
        
        chunks.append(DocumentChunkInfo(
            text=chunk_text,
            section_path=section_path,
            page_start=current_page_start or 1,
            page_end=current_page_end or 1,
            source_element_orders=list(current_orders),
            chunk_type="text",
        ))
        
        # FIXED: Set up proper overlap for next chunk
        if len(combined_text) > OVERLAP_CHARS:
            # Keep last OVERLAP_CHARS characters for continuity
            overlap_text = combined_text[-OVERLAP_CHARS:]
            # Find a good break point (space) to avoid mid-word splits
            space_idx = overlap_text.find(" ")
            if space_idx > 0:
                overlap_text = overlap_text[space_idx+1:].strip()  # Skip the space itself
            
            if overlap_text:  # Only use overlap if non-empty after trimming
                current_text_parts = [overlap_text]
                # Keep the last order for continuity
                if current_orders:
                    current_orders = [current_orders[-1]]
            else:
                current_text_parts = []
                current_orders = []
        else:
            # Chunk too small for overlap, start fresh
            current_text_parts = []
            current_orders = []
        
        # FIXED: Reset page tracking for next chunk
        current_page_start = None
        current_page_end = None

    # Process all normalized elements
    for norm in normalized:
        text = norm.text.strip()
        orders = norm.source_orders
        page = norm.page_number
        etype = norm.element_type
        category = norm.category

        # Skip non-text or trivial content
        if category != "TEXT" or not text or _is_trivial_text(text):
            continue

        # DISABLED: Section path building (was creating garbage)
        # if _is_structural_heading(text, etype):
        #     section_path_parts = [t.strip() for t in section_path_parts if t.strip()]
        #     if not _is_institutional_boilerplate(text):
        #         section_path_parts.append(text)
        
        # FIXED: Check size BEFORE adding text (prevent exceeding 1000 max)
        current_size = len(" ".join(current_text_parts))
        text_size = len(text)
        
        # If adding this text would exceed max, create chunk first
        if current_text_parts and (current_size + text_size + 1) > TARGET_CHUNK_MAX_CHARS:
            # Current chunk would be too large, finalize it first
            if current_size >= TARGET_CHUNK_MIN_CHARS:
                create_chunk_with_overlap()
            else:
                # Too small to chunk, must include this text even if over max
                pass
        
        # Add text to current chunk
        current_text_parts.append(text)
        current_orders.extend(orders)
        
        # Track page range
        if page is not None:
            if current_page_start is None:
                current_page_start = page
            current_page_end = page
    
    # Handle remaining content
    if current_text_parts:
        combined_text = " ".join(current_text_parts)
        combined_text = _normalize_text(combined_text).strip()
        
        if len(combined_text) >= TARGET_CHUNK_MIN_CHARS:
            # Large enough for its own chunk
            section_path = ""  # DISABLED: section paths
            chunk_text = _enrich_chunk_text(combined_text, section_path)
            chunks.append(DocumentChunkInfo(
                text=chunk_text,
                section_path=section_path,
                page_start=current_page_start or 1,
                page_end=current_page_end or 1,
                source_element_orders=list(current_orders),
                chunk_type="text",
            ))
        elif chunks:
            # Too small - append to last chunk
            last_chunk = chunks[-1]
            last_chunk.text = last_chunk.text + " " + combined_text
            last_chunk.source_element_orders.extend(current_orders)
            if current_page_end:
                last_chunk.page_end = current_page_end
    
    return chunks

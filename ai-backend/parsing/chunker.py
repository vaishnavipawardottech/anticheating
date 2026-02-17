"""
Smart section-aware chunker: clean → structure → merge → enrich.
Optional: semantic split (embedding-based) so we break at topic boundaries, not mid-thought.

Strategy:
1. Prepare: drop junk, join broken sentences (PDF line-break fragments), de-duplicate.
2. Structure: heading stack → section_path; attach labels (Note, Figure, Example) to next body.
3. Merge: NarrativeText + ListItem by meaning; new chunk at major headings (Unit / numbered section).
4. Optional semantic split: when hitting size limit, use embeddings to find lowest-similarity
   boundary between consecutive parts and break there (topic shift) instead of arbitrary cut.
5. Enrich: prefix chunk text with "Path: Unit I > ..." for embedding so retrieval gets context.

Target: ~500–1000 tokens per chunk (flow.md style), ~100-token overlap for continuity.
"""

from dataclasses import dataclass, field
from typing import List, Any, Tuple, Callable, Optional
import re

# Chunk size: word count as proxy for tokens (~1 word ≈ 1.3 tokens).
# 500–1000 tokens ≈ 385–770 words; overlap ~100 tokens ≈ 77 words.
TARGET_CHUNK_MIN_WORDS = 400   # ~520 tokens
TARGET_CHUNK_MAX_WORDS = 800   # ~1040 tokens
OVERLAP_WORDS = 100            # ~130 tokens overlap between consecutive chunks
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
    Clean → join fragments → dedup. Must run before chunk_elements.
    - Drops junk tokens (—, empty, separator-only).
    - Merges consecutive sentence fragments (e.g. "the message" + "is going" + "to pass").
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
        page = getattr(elem, "page_number", None)
        etype = getattr(elem, "element_type", "") or ""
        cat = getattr(elem, "category", "OTHER")
        rows.append((text, i, page, etype, cat))

    # Merge fragments: if current is fragment and next is TEXT, merge into one
    merged: List[Tuple[str, List[int], Any, str, str]] = []
    i = 0
    while i < len(rows):
        text, order, page, etype, cat = rows[i]
        orders = [order]
        while i + 1 < len(rows) and cat == "TEXT" and _is_sentence_fragment(text):
            next_text, next_order, next_page, next_etype, next_cat = rows[i + 1]
            if next_cat != "TEXT":
                break
            text = text + " " + next_text
            orders.append(next_order)
            page = next_page or page
            i += 1
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
    Build section_path for each element index by scanning in order and keeping
    a stack of the latest Title/Heading/Header. Attach that path to each downstream
    element until the next heading.
    Returns a list of length len(elements); heading indices get the path including themselves.
    
    Filters out institutional boilerplate (college names, departments, etc.) from paths.
    """
    paths: List[str] = []
    section_path_parts: List[str] = []
    for elem in elements:
        elem_type = getattr(elem, "element_type", "") or ""
        text = (getattr(elem, "text", None) or "").strip()
        if _is_heading_type(elem_type) and text:
            section_path_parts = [t.strip() for t in section_path_parts if t.strip()]
            # Skip institutional boilerplate (college names, departments, etc.)
            if not _is_institutional_boilerplate(text):
                section_path_parts.append(text)
        section_path = " > ".join(section_path_parts) if section_path_parts else ""
        paths.append(section_path)
    return paths


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
            if section_path:
                schema_text = f"Path: {section_path}\n\n{schema_text}"
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


def _approx_tokens(text: str) -> int:
    """Rough token count (word count * 1.3)."""
    if not text or not text.strip():
        return 0
    return int(len(text.split()) * 1.3)


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
    """Prefix with Path: ... for embedding so retrieval gets hierarchy context."""
    if not body or not body.strip():
        return body
    if section_path and section_path.strip():
        # Clean institutional boilerplate from section path before enriching
        cleaned_path = _clean_section_path(section_path.strip())
        if cleaned_path:
            return f"Path: {cleaned_path}\n\n{body.strip()}"
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
    Smart chunking: clean → structure → merge → enrich.
    If embed_fn is provided, when we hit the size limit we break at the *semantic*
    boundary (lowest similarity between consecutive parts) instead of an arbitrary cut.
    """
    normalized = prepare_for_chunking(elements)
    section_path_parts: List[str] = []
    chunks: List[DocumentChunkInfo] = []
    # Each item: (text, orders for this part) so we can semantic-split and keep orders correct
    current_parts: List[Tuple[str, List[int]]] = []
    current_page_start: int | None = None
    current_page_end: int | None = None
    current_tokens = 0
    pending_label: str | None = None

    def _parts_to_text_orders(
        parts: List[Tuple[str, List[int]]],
    ) -> Tuple[str, List[int]]:
        texts = [p[0] for p in parts]
        orders = [o for _, ords in parts for o in ords]
        return "\n\n".join(texts).strip(), orders

    def flush_parts(parts: List[Tuple[str, List[int]]], keep_overlap: bool = False):
        nonlocal current_parts, current_page_start, current_page_end, current_tokens
        if not parts:
            return
        section_path = " > ".join(section_path_parts) if section_path_parts else ""
        body, ords = _parts_to_text_orders(parts)
        if body:
            enriched = _enrich_chunk_text(body, section_path)
            chunks.append(DocumentChunkInfo(
                text=enriched,
                section_path=section_path,
                page_start=current_page_start or 1,
                page_end=current_page_end or 1,
                source_element_orders=list(ords),
                chunk_type="text",
            ))
            if keep_overlap and OVERLAP_WORDS > 0 and len(parts) > 0:
                # Overlap: keep last part (or last N words of body) for continuity
                words = body.split()
                if len(words) > OVERLAP_WORDS:
                    overlap_text = " ".join(words[-OVERLAP_WORDS:])
                    last_ords = parts[-1][1]
                    current_parts = [(overlap_text, last_ords[-1:] if last_ords else [])]
                    current_page_start = current_page_end
                    current_tokens = _approx_tokens(overlap_text)
                    return
        current_parts = []
        current_page_start = None
        current_page_end = None
        current_tokens = 0

    def flush_chunk(keep_overlap: bool = False):
        flush_parts(current_parts, keep_overlap=keep_overlap)

    for norm in normalized:
        text = norm.text.strip()
        orders = norm.source_orders
        page = norm.page_number
        etype = norm.element_type
        category = norm.category

        if _is_structural_heading(text, etype):
            flush_chunk(keep_overlap=False)
            pending_label = None
            section_path_parts = [t.strip() for t in section_path_parts if t.strip()]
            # Skip institutional boilerplate in section paths (college names, departments, etc.)
            if not _is_institutional_boilerplate(text):
                section_path_parts.append(text)
            continue

        if (category == "TEXT" and _is_label_only_heading(text, etype)) or _is_figure_or_table_caption(text, etype):
            flush_chunk(keep_overlap=False)
            pending_label = text
            continue

        if category != "TEXT" or not text:
            flush_chunk(keep_overlap=False)
            pending_label = None
            continue

        if _is_trivial_text(text):
            continue

        if pending_label:
            text = pending_label + ": " + text
            pending_label = None
        current_parts.append((text, list(orders)))
        if page is not None:
            if current_page_start is None:
                current_page_start = page
            current_page_end = page
        current_tokens += _approx_tokens(text)

        if current_tokens >= TARGET_CHUNK_MAX_WORDS:
            if embed_fn and len(current_parts) >= 2:
                # Semantic split: break at topic boundary (lowest similarity between consecutive parts)
                parts_texts = [p[0] for p in current_parts]
                split_idx = _best_semantic_split_index(parts_texts, embed_fn)
                first_chunk_words = sum(
                    _approx_tokens(current_parts[i][0]) for i in range(split_idx + 1)
                )
                # Only use semantic split if first chunk is not too small
                if first_chunk_words >= TARGET_CHUNK_MIN_WORDS:
                    flush_parts(current_parts[: split_idx + 1], keep_overlap=False)
                    current_parts = current_parts[split_idx + 1 :]
                    current_tokens = sum(
                        _approx_tokens(p[0]) for p in current_parts
                    )
                else:
                    flush_chunk(keep_overlap=True)
            else:
                flush_chunk(keep_overlap=True)

    flush_chunk(keep_overlap=False)
    return chunks

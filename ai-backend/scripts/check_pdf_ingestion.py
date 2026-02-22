#!/usr/bin/env python3
"""
One-off script to check what the ingestion pipeline would extract from a PDF.
Usage:
  python scripts/check_pdf_ingestion.py "/path/to/file.pdf"
  python scripts/check_pdf_ingestion.py "/path/to/file.pdf" hi_res   # detect images (slower; may need unstructured[local-inference])
Uses unstructured directly to avoid full app dependencies.
"""
import sys
from pathlib import Path
from collections import Counter

def main():
    if len(sys.argv) < 2:
        print("Usage: python check_pdf_ingestion.py <path-to-pdf> [fast|hi_res|auto]")
        sys.exit(1)
    path = Path(sys.argv[1])
    strategy = (sys.argv[2] if len(sys.argv) > 2 else "fast").lower()
    if strategy not in ("fast", "hi_res", "auto"):
        strategy = "fast"
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    try:
        from unstructured.partition.pdf import partition_pdf
    except ImportError:
        print("Install: pip install 'unstructured[pdf]'")
        sys.exit(1)

    print(f"Parsing: {path.name} (strategy={strategy})\n")
    elements = partition_pdf(
        filename=str(path),
        strategy=strategy,
        include_page_breaks=False,
    )
    print(f"Total elements: {len(elements)}")
    types = Counter(type(e).__name__ for e in elements)
    print("By element_type:", dict(types))
    pages = set()
    for e in elements:
        if hasattr(e, "metadata") and hasattr(e.metadata, "page_number") and e.metadata.page_number:
            pages.add(e.metadata.page_number)
    print(f"Pages: {min(pages) if pages else 0} - {max(pages) if pages else 0}\n")
    print("First 30 elements:")
    for i, e in enumerate(elements[:30]):
        name = type(e).__name__
        text = (getattr(e, "text", None) or "")
        text = text[:60].replace("\n", " ").strip() if text else "(no text)"
        page = getattr(e.metadata, "page_number", None) if hasattr(e, "metadata") else None
        print(f"  {i:3} {name:20} p={page} | {text}")
    print("\nSample mid-doc (elements 40-55):")
    for i, e in enumerate(elements[40:56]):
        idx = 40 + i
        name = type(e).__name__
        text = (getattr(e, "text", None) or "")
        text = text[:60].replace("\n", " ").strip() if text else "(no text)"
        print(f"  {idx:3} {name:20} | {text}")
    return 0

if __name__ == "__main__":
    sys.exit(main())

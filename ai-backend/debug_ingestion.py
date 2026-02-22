"""
DEBUG SCRIPT: Test NEW 10-step ingestion pipeline
Run this to see output at each stage without uploading through API

New Pipeline:
1. Parse (Unstructured)
2. Normalize (Unicode/text cleanup)
3. Caption Images (GPT-4o) - optional
4. Format Tables (LLM) - optional
5. Cleanup (Remove noise)
6. Classify (TEXT/DIAGRAM/CODE)
7. Chunk (Section-aware, 600-1000 chars)
8. Embed (all-MiniLM-L6-v2) - skipped in debug
9. Index (PostgreSQL + Qdrant) - skipped in debug
10. Align (Gemini → Concepts) - skipped in debug

Usage:
    python debug_ingestion.py path/to/your/document.pdf
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from ingestion import (
    DocumentParser,
    normalize_elements,
    cleanup_elements,
    ElementClassifier,
    compute_section_paths_for_elements,
    prepare_for_chunking,
    chunk_elements,
    table_to_row_chunks
)


def debug_step_1_parse(file_path: str):
    """Step 1: Parse with Unstructured library"""
    print("\n" + "="*80)
    print("STEP 1: PARSING WITH UNSTRUCTURED LIBRARY")
    print("="*80)
    
    filename = Path(file_path).name
    elements = DocumentParser.parse_document(file_path, filename)
    
    print(f"\nParsed {len(elements)} raw elements")
    
    # Export ALL parsed elements to JSON for detailed inspection
    json_output = []
    for i, elem in enumerate(elements):
        elem_data = {
            "index": i,
            "element_type": elem.element_type,
            "text": elem.text,
            "text_length": len(elem.text) if elem.text else 0,
            "page_number": elem.page_number,
            "metadata": elem.metadata if hasattr(elem, 'metadata') else {}
        }
        json_output.append(elem_data)
    
    # Save to JSON file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("parsing/output")
    output_dir.mkdir(exist_ok=True)
    json_file = output_dir / f"unstructured_output_{timestamp}.json"
    
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(json_output, f,indent=2, ensure_ascii=False)
    
    print(f"\nFULL JSON OUTPUT saved to: {json_file}")
    print(f"   Contains all {len(elements)} elements with complete text and metadata")
    
    print(f"\nFirst 10 elements:")
    print("-" * 80)
    
    for i, elem in enumerate(elements[:10]):
        text_preview = elem.text[:150] if elem.text else "(empty)"
        print(f"\n[{i:3d}] Type: {elem.element_type:20s} Page: {elem.page_number or 'N/A'}")
        print(f"      Text: {text_preview}")
        if len(elem.text) > 150:
            print(f"      ... ({len(elem.text)} total chars)")
    
    # Check for broken text
    print("\n" + "-" * 80)
    print("ANALYSIS: Are elements already broken?")
    short_elements = [e for e in elements if e.text and len(e.text) < 100]
    print(f"  • Elements < 100 chars: {len(short_elements)} / {len(elements)}")
    print(f"  • Average element length: {sum(len(e.text) for e in elements if e.text) / len(elements):.0f} chars")
    
    return elements


def debug_step_2_cleanup(elements):
    """Step 2: Cleanup filters"""
    print("\n" + "="*80)
    print("STEP 2: CLEANUP FILTERS")
    print("="*80)
    
    cleanup_result = cleanup_elements(elements)
    cleaned = cleanup_result.elements
    stats = cleanup_result.statistics
    
    print(f"\nBefore: {len(elements)} elements")
    print(f"After:  {len(cleaned)} elements")
    print(f"Removed: {stats.removed_elements}, Kept: {stats.kept_elements}")
    
    # Export cleaned elements to JSON
    json_output = []
    for i, elem in enumerate(cleaned):
        elem_data = {
            "index": i,
            "element_type": elem.element_type,
            "text": elem.text,
            "text_length": len(elem.text) if elem.text else 0,
            "page_number": elem.page_number,
            "metadata": elem.metadata if hasattr(elem, 'metadata') else {}
        }
        json_output.append(elem_data)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("parsing/output")
    json_file = output_dir / f"cleaned_elements_{timestamp}.json"
    
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(json_output, f, indent=2, ensure_ascii=False)
    
    print(f"\nCleaned elements saved to: {json_file}")
    
    print(f"\nFirst 10 cleaned elements:")
    print("-" * 80)
    
    for i, elem in enumerate(cleaned[:10]):
        text_preview = elem.text[:150] if elem.text else "(empty)"
        print(f"\n[{i:3d}] Type: {elem.element_type:20s}")
        print(f"      Text: {text_preview}")
    
    return cleaned


def debug_step_3_classify(elements):
    """Step 3: Classification"""
    print("\n" + "="*80)
    print("STEP 3: CLASSIFICATION")
    print("="*80)
    
    classifier = ElementClassifier()
    
    for elem in elements:
        elem.category = classifier.classify(elem)
        elem.is_diagram_critical = classifier.is_diagram_critical(elem)
    
    # Count by category
    category_counts = {}
    for elem in elements:
        cat = getattr(elem, 'category', 'OTHER')
        category_counts[cat] = category_counts.get(cat, 0) + 1
    
    print(f"\nClassification complete")
    print(f"Category counts: {category_counts}")
    
    # Show TEXT elements
    text_elements = [e for e in elements if e.category == 'TEXT']
    print(f"\nFirst 5 TEXT elements:")
    print("-" * 80)
    
    for i, elem in enumerate(text_elements[:5]):
        text_preview = elem.text[:150] if elem.text else "(empty)"
        print(f"\n[{i:3d}] Type: {elem.element_type:20s}")
        print(f"      Text: {text_preview}")
    
    return elements


def debug_step_4_section_paths(elements):
    """Step 4: Build section paths"""
    print("\n" + "="*80)
    print("STEP 4: SECTION PATH BUILDING")
    print("="*80)
    
    section_paths = compute_section_paths_for_elements(elements)
    
    print(f"\nGenerated {len(section_paths)} section paths")
    print(f"\nFirst 20 elements with paths:")
    print("-" * 80)
    
    for i in range(min(20, len(section_paths))):
        elem = elements[i]
        path = section_paths[i]
        text_preview = elem.text[:80] if elem.text else "(empty)"
        print(f"\n[{i:3d}] Type: {elem.element_type:15s}")
        print(f"      Path: {path or '(no path)'}")
        print(f"      Text: {text_preview}")
    
    # Check for weird paths
    print("\n" + "-" * 80)
    print("ANALYSIS: Are section paths clean?")
    long_paths = [p for p in section_paths if p and len(p) > 200]
    print(f"  • Paths > 200 chars: {len(long_paths)}")
    if long_paths:
        print(f"  • Example long path: {long_paths[0][:300]}...")
    
    return section_paths


def debug_step_5_prepare_chunking(elements):
    """Step 5: Prepare for chunking (normalize, merge fragments)"""
    print("\n" + "="*80)
    print("STEP 5: PREPARE FOR CHUNKING")
    print("="*80)
    
    normalized = prepare_for_chunking(elements)
    
    print(f"\nInput: {len(elements)} elements")
    print(f"Output: {len(normalized)} normalized elements (after merging fragments)")
    
    print(f"\nFirst 10 normalized elements:")
    print("-" * 80)
    
    for i, norm in enumerate(normalized[:10]):
        text_preview = norm.text[:150] if norm.text else "(empty)"
        print(f"\n[{i:3d}] Type: {norm.element_type:20s} Category: {norm.category}")
        print(f"      Orders: {norm.source_orders}")
        print(f"      Text: {text_preview}")
        print(f"      Length: {len(norm.text)} chars")
    
    return normalized


def debug_step_6_chunking(elements):
    """Step 6: CHUNKING - The critical step!"""
    print("\n" + "="*80)
    print("STEP 6: CHUNKING (CRITICAL STEP)")
    print("="*80)
    
    # Try to get embedding function (optional)
    try:
        from embeddings.generator import get_embedding_generator
        emb_gen = get_embedding_generator()
        embed_fn = emb_gen.generate_embeddings_batch
        print("Using semantic splitting with embeddings")
    except Exception as e:
        embed_fn = None
        print(f"Semantic splitting disabled: {e}")
    
    chunks = chunk_elements(elements, embed_fn=embed_fn)
    
    print(f"\nCreated {len(chunks)} chunks")
    
    # Export chunks to JSON
    json_output = []
    for i, chunk in enumerate(chunks):
        chunk_data = {
            "chunk_index": i,
            "text": chunk.text,
            "text_length": len(chunk.text),
            "section_path": chunk.section_path,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "source_element_orders": chunk.source_element_orders,
            "chunk_type": chunk.chunk_type
        }
        json_output.append(chunk_data)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("parsing/output")
    json_file = output_dir / f"chunks_output_{timestamp}.json"
    
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(json_output, f, indent=2, ensure_ascii=False)
    
    print(f"\nChunks saved to: {json_file}")
    
    # Analyze chunk sizes
    chunk_sizes = [len(c.text) for c in chunks]
    avg_size = sum(chunk_sizes) / len(chunk_sizes) if chunk_sizes else 0
    min_size = min(chunk_sizes) if chunk_sizes else 0
    max_size = max(chunk_sizes) if chunk_sizes else 0
    
    print(f"\nCHUNK SIZE ANALYSIS:")
    print(f"  • Average: {avg_size:.0f} chars")
    print(f"  • Min: {min_size} chars")
    print(f"  • Max: {max_size} chars")
    print(f"  • Target: 600-1000 chars")
    
    # Count chunks by size range
    tiny = len([s for s in chunk_sizes if s < 300])
    small = len([s for s in chunk_sizes if 300 <= s < 600])
    good = len([s for s in chunk_sizes if 600 <= s <= 1000])
    large = len([s for s in chunk_sizes if s > 1000])
    
    print(f"\n  Size distribution:")
    print(f"  • < 300 chars (too small): {tiny}")
    print(f"  • 300-600 chars: {small}")
    print(f"  • 600-1000 chars (TARGET): {good}")
    print(f"  • > 1000 chars: {large}")
    
    print(f"\nFirst 5 chunks:")
    print("-" * 80)
    
    for i, chunk in enumerate(chunks[:5]):
        text_preview = chunk.text[:200] if chunk.text else "(empty)"
        print(f"\n[Chunk {i}]")
        print(f"  Size: {len(chunk.text)} chars")
        print(f"  Section: {chunk.section_path or '(no path)'}")
        print(f"  Pages: {chunk.page_start}-{chunk.page_end}")
        print(f"  Text: {text_preview}")
        if len(chunk.text) > 200:
            print(f"  ... ({len(chunk.text)} total chars)")
    
    # Check for overlap (compare consecutive chunks)
    if len(chunks) >= 2:
        print(f"\nOVERLAP CHECK (first 2 chunks):")
        chunk1_end = chunks[0].text[-100:] if len(chunks[0].text) >= 100 else chunks[0].text
        chunk2_start = chunks[1].text[:100] if len(chunks[1].text) >= 100 else chunks[1].text
        
        # Simple overlap detection
        overlap_chars = 0
        for i in range(1, min(len(chunk1_end), len(chunk2_start)) + 1):
            if chunk1_end[-i:] == chunk2_start[:i]:
                overlap_chars = i
        
        print(f"  • Overlap between chunks 0 and 1: {overlap_chars} chars")
        print(f"  • Target overlap: 100 chars")
        
        if overlap_chars > 0:
            print(f"  • Overlap text: ...{chunk1_end[-overlap_chars:]}")
    
    return chunks


def main():
    if len(sys.argv) < 2:
        print("Usage: python debug_ingestion.py path/to/document.pdf")
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    if not Path(file_path).exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    
    print("\n" + "="*80)
    print(f"DEBUGGING DOCUMENT INGESTION PIPELINE")
    print(f"File: {file_path}")
    print("="*80)
    
    try:
        # Run all steps
        elements = debug_step_1_parse(file_path)
        cleaned = debug_step_2_cleanup(elements)
        classified = debug_step_3_classify(cleaned)
        section_paths = debug_step_4_section_paths(classified)
        normalized = debug_step_5_prepare_chunking(classified)
        chunks = debug_step_6_chunking(classified)
        
        print("\n" + "="*80)
        print("FINAL SUMMARY")
        print("="*80)
        print(f"Parsed: {len(elements)} raw elements")
        print(f"Cleaned: {len(cleaned)} elements")
        print(f"Classified: {len(classified)} elements")
        print(f"Normalized: {len(normalized)} elements")
        print(f"Chunks: {len(chunks)} chunks")
        
        print(f"\nJSON FILES SAVED:")
        print(f"   All JSON outputs are in: parsing/output/")
        print(f"   - unstructured_output_*.json (raw parsed elements)")
        print(f"   - cleaned_elements_*.json (after cleanup)")
        print(f"   - chunks_output_*.json (final chunks)")
        
        # Final verdict
        chunk_sizes = [len(c.text) for c in chunks]
        good_chunks = len([s for s in chunk_sizes if 600 <= s <= 1000])
        bad_chunks = len([s for s in chunk_sizes if s < 600])
        
        print(f"\nVERDICT:")
        if good_chunks > len(chunks) * 0.7:
            print(f"GOOD: {good_chunks}/{len(chunks)} chunks in target range (600-1000 chars)")
        else:
            print(f"BAD: Only {good_chunks}/{len(chunks)} chunks in target range")
            print(f"   {bad_chunks} chunks are too small (< 600 chars)")
            print(f"\n   This indicates a problem in the chunking logic!")
            print(f"   Check the JSON files to see where content is breaking.")
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

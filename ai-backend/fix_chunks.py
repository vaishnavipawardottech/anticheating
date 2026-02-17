"""
Fix poor-quality chunks caused by PDF parsing fragmentation.

PROBLEM:
- PDF parser (unstructured library) sometimes fragments text incorrectly
- Small fragments like "technology." get misclassified as Title elements
- Chunker treats every Title as a new section, creating tiny chunks with only paths
- Institutional boilerplate (college names, departments) pollutes every chunk

SOLUTION:
- Updated chunker.py to ignore short Title fragments (< 3 words) unless they match major heading patterns
- Filter out institutional boilerplate from section paths (college names, departments, etc.)
- This script re-processes existing documents with the fixed chunker

USAGE:
    python fix_chunks.py [--document-id DOC_ID] [--all]

OPTIONS:
    --document-id DOC_ID    Re-chunk specific document only
    --all                   Re-chunk ALL documents (WARNING: may take time)
    --dry-run               Show what would be re-chunked without making changes
"""

import argparse
import sys
from typing import Optional
from sqlalchemy.orm import Session

from database.database import SessionLocal
from database.models import Document, ParsedElement, DocumentChunk
from parsing.chunker import chunk_elements, compute_section_paths_for_elements, table_to_row_chunks
from embeddings import get_embedding_generator
from embeddings.qdrant_manager import get_qdrant_manager
from datetime import datetime


def re_chunk_document(document_id: int, db: Session, dry_run: bool = False) -> dict:
    """
    Re-chunk a document using the fixed chunker logic.
    
    Steps:
    1. Load parsed elements from database
    2. Re-run section-aware chunking with fixed logic
    3. Delete old chunks and Qdrant vectors
    4. Save new chunks and generate embeddings
    5. Index to Qdrant
    
    Returns:
        dict with before/after stats
    """
    # Load document
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise ValueError(f"Document {document_id} not found")
    
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Processing document {document_id}: {document.filename}")
    
    # Get old chunk count
    old_chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).all()
    old_count = len(old_chunks)
    print(f"  Old chunks: {old_count}")
    
    # Sample old chunk text lengths
    if old_chunks:
        old_lengths = [len(c.text or "") for c in old_chunks[:10]]
        avg_old_len = sum(old_lengths) / len(old_lengths)
        print(f"  Avg old chunk length (sample): {avg_old_len:.0f} chars")
    
    if dry_run:
        print("  [DRY RUN] Skipping actual re-chunking")
        return {
            "document_id": document_id,
            "filename": document.filename,
            "old_chunks": old_count,
            "new_chunks": "N/A (dry run)",
            "improved": False
        }
    
    # Load parsed elements
    elements = db.query(ParsedElement)\
        .filter(ParsedElement.document_id == document_id)\
        .order_by(ParsedElement.order_index)\
        .all()
    
    if not elements:
        print(f"  ⚠ No parsed elements found for document {document_id}")
        return {
            "document_id": document_id,
            "filename": document.filename,
            "old_chunks": old_count,
            "new_chunks": 0,
            "improved": False
        }
    
    print(f"  Loaded {len(elements)} parsed elements")
    
    # Re-compute section paths
    section_paths = compute_section_paths_for_elements(elements)
    
    # Re-chunk with fixed logic
    try:
        emb_gen = get_embedding_generator()
        embed_fn = emb_gen.generate_embeddings_batch
    except Exception:
        embed_fn = None
    
    new_doc_chunks = chunk_elements(elements, embed_fn=embed_fn)
    
    # Add table chunks
    for idx, element in enumerate(elements):
        if getattr(element, "category", "OTHER") == "TABLE" and element.text:
            path = section_paths[idx] if idx < len(section_paths) else ""
            page = getattr(element, "page_number", None) or 1
            new_doc_chunks.extend(table_to_row_chunks(element.text, path, page, idx))
    
    new_doc_chunks.sort(key=lambda c: (c.page_start or 0, c.source_element_orders[0] if c.source_element_orders else 0))
    
    print(f"  New chunks: {len(new_doc_chunks)} (improvement: {len(new_doc_chunks) - old_count:+d})")
    
    # Sample new chunk text lengths
    if new_doc_chunks:
        new_lengths = [len(c.text or "") for c in new_doc_chunks[:10]]
        avg_new_len = sum(new_lengths) / len(new_lengths)
        print(f"  Avg new chunk length (sample): {avg_new_len:.0f} chars")
    
    # Delete old chunks and their Qdrant vectors
    try:
        qdrant = get_qdrant_manager()
        # Delete only chunk vectors (point_type='chunk')
        old_chunk_ids = [c.id for c in old_chunks]
        if old_chunk_ids:
            qdrant.client.delete(
                collection_name=qdrant.collection_name,
                points_selector={
                    "filter": {
                        "must": [
                            {"key": "document_id", "match": {"value": document_id}},
                            {"key": "point_type", "match": {"value": "chunk"}}
                        ]
                    }
                }
            )
            print(f"  ✓ Deleted {len(old_chunk_ids)} old chunk vectors from Qdrant")
    except Exception as e:
        print(f"  ⚠ Qdrant cleanup warning: {str(e)}")
    
    db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
    db.commit()
    print(f"  ✓ Deleted {old_count} old chunks from database")
    
    # Save new chunks
    MAX_SECTION_PATH_LEN = 500
    for chunk_index, cinfo in enumerate(new_doc_chunks):
        sp = (cinfo.section_path or "").strip() or None
        if sp and len(sp) > MAX_SECTION_PATH_LEN:
            sp = sp[: MAX_SECTION_PATH_LEN - 3] + "..."
        token_count = int(len((cinfo.text or "").split()) * 1.3)
        db_chunk = DocumentChunk(
            document_id=document_id,
            chunk_index=chunk_index,
            text=cinfo.text,
            section_path=sp,
            page_start=cinfo.page_start,
            page_end=cinfo.page_end,
            source_element_orders=cinfo.source_element_orders,
            token_count=token_count,
            chunk_type=getattr(cinfo, "chunk_type", "text"),
            table_id=getattr(cinfo, "table_id", None),
            row_id=getattr(cinfo, "row_id", None),
            unit_id=None,
            concept_id=None,
        )
        db.add(db_chunk)
    
    db.commit()
    print(f"  ✓ Saved {len(new_doc_chunks)} new chunks to database")
    
    # Generate embeddings and index to Qdrant
    saved_chunks = db.query(DocumentChunk)\
        .filter(DocumentChunk.document_id == document_id)\
        .order_by(DocumentChunk.chunk_index)\
        .all()
    
    chunk_texts = [c.text for c in saved_chunks]
    
    try:
        embedding_gen = get_embedding_generator()
        chunk_embeddings = embedding_gen.generate_embeddings_batch(chunk_texts, batch_size=32)
        
        chunk_ids = []
        embeddings_list = []
        metadatas = []
        
        model_name = embedding_gen.model_name
        dim = embedding_gen.EMBEDDING_DIM
        now = datetime.now()
        
        for c, emb in zip(saved_chunks, chunk_embeddings):
            c.embedding_vector = emb
            if emb is None or not isinstance(emb, list) or len(emb) != 384:
                continue
            
            chunk_ids.append(c.id)
            embeddings_list.append(emb)
            
            sp = (c.section_path or "")[:MAX_SECTION_PATH_LEN]
            meta = {
                "subject_id": document.subject_id,
                "document_id": document_id,
                "unit_id": c.unit_id,
                "concept_id": c.concept_id,
                "section_path": sp,
                "page_start": c.page_start or 0,
                "page_end": c.page_end or 0,
                "point_type": "chunk",
                "chunk_type": getattr(c, "chunk_type", "text") or "text",
            }
            if getattr(c, "table_id", None) is not None:
                meta["table_id"] = c.table_id
            if getattr(c, "row_id", None) is not None:
                meta["row_id"] = c.row_id
            metadatas.append(meta)
        
        if chunk_ids:
            db.commit()
            qdrant = get_qdrant_manager()
            qdrant.index_chunks_batch(chunk_ids, embeddings_list, metadatas)
            
            indexed_chunk_ids = set(chunk_ids)
            for c in saved_chunks:
                if c.id in indexed_chunk_ids:
                    c.vector_id = f"chunk_{c.id}"
                    c.indexed_at = now
                    c.embedding_model = model_name
                    c.embedding_dim = dim
                    c.embedded_at = now
            
            db.commit()
            print(f"  ✓ Indexed {len(chunk_ids)} new chunks to Qdrant")
        else:
            db.commit()
            print(f"  ⚠ No chunk embeddings to index (skipped)")
    
    except Exception as e:
        print(f"  ⚠ Chunk embedding/indexing failed: {str(e)}")
        db.commit()  # Still commit the chunks even if embedding fails
    
    improved = len(new_doc_chunks) < old_count * 0.8  # Significant reduction = improvement
    
    return {
        "document_id": document_id,
        "filename": document.filename,
        "old_chunks": old_count,
        "new_chunks": len(new_doc_chunks),
        "improved": improved
    }


def main():
    parser = argparse.ArgumentParser(
        description="Re-chunk documents with fixed chunker logic",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("--document-id", type=int, help="Re-chunk specific document")
    parser.add_argument("--all", action="store_true", help="Re-chunk ALL documents")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    
    args = parser.parse_args()
    
    if not args.document_id and not args.all:
        parser.print_help()
        print("\nERROR: Must specify either --document-id or --all")
        sys.exit(1)
    
    db = SessionLocal()
    
    try:
        if args.document_id:
            # Re-chunk single document
            result = re_chunk_document(args.document_id, db, dry_run=args.dry_run)
            print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Summary:")
            print(f"  Document {result['document_id']}: {result['filename']}")
            print(f"  Chunks: {result['old_chunks']} → {result['new_chunks']}")
            if result['improved']:
                print(f"  ✅ IMPROVED (fewer, more meaningful chunks)")
            else:
                print(f"  ℹ️  Chunks count similar (may still have better content)")
        
        elif args.all:
            # Re-chunk all documents
            documents = db.query(Document).all()
            
            if not documents:
                print("No documents found in database")
                sys.exit(0)
            
            print(f"{'[DRY RUN] ' if args.dry_run else ''}Re-chunking {len(documents)} documents...")
            
            results = []
            for doc in documents:
                try:
                    result = re_chunk_document(doc.id, db, dry_run=args.dry_run)
                    results.append(result)
                except Exception as e:
                    print(f"  ❌ ERROR processing document {doc.id}: {str(e)}")
                    results.append({
                        "document_id": doc.id,
                        "filename": doc.filename,
                        "old_chunks": 0,
                        "new_chunks": 0,
                        "improved": False,
                        "error": str(e)
                    })
            
            # Summary
            print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Summary:")
            print(f"  Total documents: {len(results)}")
            improved = sum(1 for r in results if r.get('improved', False))
            print(f"  Improved: {improved}")
            print(f"  Failed: {sum(1 for r in results if 'error' in r)}")
            
            if not args.dry_run:
                print(f"\n✅ Re-chunking complete!")
                print(f"   Navigate to VectorsExplorer to see improved chunks")
    
    finally:
        db.close()


if __name__ == "__main__":
    main()

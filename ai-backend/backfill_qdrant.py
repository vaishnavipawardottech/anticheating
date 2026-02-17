"""
Backfill Script: Index Existing Embeddings to Qdrant
Finds all ParsedElements with embeddings but no vector_id and indexes them to Qdrant
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

# Import models and Qdrant manager
from database.models import ParsedElement, Document
from embeddings.qdrant_manager import get_qdrant_manager

# Build database URL
POSTGRES_USER = os.getenv("POSTGRES_USER", "academic_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "academic_pass")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "academic_structure")

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Create engine and session
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def backfill_qdrant(dry_run=False, batch_size=100):
    """
    Backfill Qdrant with existing embeddings
    
    Args:
        dry_run: If True, only show what would be indexed without actually indexing
        batch_size: Number of elements to process in each batch
    """
    db = SessionLocal()
    
    try:
        print("=" * 70)
        print("QDRANT BACKFILL: Index Existing Embeddings")
        print("=" * 70)
        
        # Find elements with embeddings but no vector_id
        unindexed_elements = db.query(ParsedElement).filter(
            ParsedElement.embedding_vector.isnot(None),
            ParsedElement.vector_id.is_(None)
        ).all()
        
        total_elements = len(unindexed_elements)
        
        if total_elements == 0:
            print("\n✓ No elements to backfill. All embeddings are already indexed!")
            return
        
        print(f"\nFound {total_elements} elements with embeddings but no vector_id")
        
        if dry_run:
            print("\n[DRY RUN MODE] - No changes will be made")
            print("\nElements to be indexed:")
            
            # Group by document
            doc_counts = {}
            for elem in unindexed_elements:
                doc_id = elem.document_id
                doc_counts[doc_id] = doc_counts.get(doc_id, 0) + 1
            
            for doc_id, count in doc_counts.items():
                document = db.query(Document).get(doc_id)
                print(f"  Document {doc_id} ({document.filename if document else 'Unknown'}): {count} elements")
            
            print(f"\nTotal: {total_elements} elements would be indexed")
            return
        
        # Initialize Qdrant and ensure collection exists
        print("\nConnecting to Qdrant...")
        qdrant = get_qdrant_manager()
        qdrant.create_collection()
        print("✓ Connected to Qdrant")
        
        # Process in batches
        indexed_count = 0
        failed_count = 0
        
        for i in range(0, total_elements, batch_size):
            batch = unindexed_elements[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total_elements + batch_size - 1) // batch_size
            
            print(f"\nProcessing batch {batch_num}/{total_batches} ({len(batch)} elements)...")
            
            try:
                # Prepare batch data
                element_ids = []
                embeddings_list = []
                metadatas = []
                
                for elem in batch:
                    # Get document for subject_id
                    document = db.query(Document).get(elem.document_id)
                    
                    element_ids.append(elem.id)
                    embeddings_list.append(elem.embedding_vector)
                    metadatas.append({
                        "document_id": elem.document_id,
                        "subject_id": document.subject_id if document else 0,
                        "category": elem.category,
                        "page_number": elem.page_number or 0,
                        "element_type": elem.element_type
                    })
                
                # Batch index to Qdrant
                vector_ids = qdrant.index_elements_batch(
                    element_ids, embeddings_list, metadatas
                )
                
                # Update database with vector_ids
                for elem_id, vector_id in zip(element_ids, vector_ids):
                    elem = db.query(ParsedElement).get(elem_id)
                    elem.vector_id = vector_id
                    elem.indexed_at = datetime.now()
                
                db.commit()
                
                indexed_count += len(batch)
                print(f"  ✓ Indexed {len(batch)} elements")
                
            except Exception as e:
                print(f"  ✗ Batch failed: {str(e)}")
                failed_count += len(batch)
                db.rollback()
        
        print("\n" + "=" * 70)
        print("BACKFILL COMPLETE")
        print("=" * 70)
        print(f"✓ Successfully indexed: {indexed_count} elements")
        if failed_count > 0:
            print(f"✗ Failed to index: {failed_count} elements")
        print(f"Total processed: {indexed_count + failed_count}/{total_elements}")
        
    except Exception as e:
        print(f"\n✗ Backfill failed: {str(e)}")
        db.rollback()
    
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    
    # Check for dry-run flag
    dry_run = "--dry-run" in sys.argv or "-d" in sys.argv
    
    # Get batch size from args
    batch_size = 100
    for arg in sys.argv:
        if arg.startswith("--batch-size="):
            batch_size = int(arg.split("=")[1])
    
    backfill_qdrant(dry_run=dry_run, batch_size=batch_size)

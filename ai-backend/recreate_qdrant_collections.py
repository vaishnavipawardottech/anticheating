"""
Recreate Qdrant collections with correct dimensions (384 for all-MiniLM-L6-v2)
Run this if you see: "Vector dimension error: expected dim: 768, got 384"

WARNING: This will DELETE all existing vectors and recreate collections.

Usage:
    python recreate_qdrant_collections.py
"""

from embeddings.qdrant_manager import get_qdrant_manager

if __name__ == "__main__":
    print("\n" + "="*60)
    print("QDRANT COLLECTION RECREATE SCRIPT")
    print("="*60)
    print("\nWARNING: This will DELETE all existing vectors!")
    print("Collections to recreate:")
    print("  - academic_elements (384 dims)")
    print("  - academic_chunks (384 dims)")
    print("\nExisting vectors will be LOST. You'll need to re-ingest documents.")
    print("="*60)
    
    confirm = input("\nType 'YES' to proceed: ").strip()
    
    if confirm != "YES":
        print("\nAborted. No changes made.")
        exit(0)
    
    print("\nRecreating collections...")
    qm = get_qdrant_manager()
    qm.create_collection(recreate=True)
    
    print("\n" + "="*60)
    print("COLLECTIONS RECREATED SUCCESSFULLY")
    print("="*60)
    
    # Show info
    for collection in [qm.COLLECTION_ELEMENTS, qm.COLLECTION_CHUNKS]:
        try:
            info = qm.client.get_collection(collection)
            dims = info.config.params.vectors.size
            count = info.points_count
            print(f"\n{collection}:")
            print(f"  Dimensions: {dims}")
            print(f"  Points: {count}")
        except Exception as e:
            print(f"\n{collection}: Error - {e}")
    
    print("\n" + "="*60)
    print("NEXT STEPS:")
    print("="*60)
    print("1. Re-upload your documents through the UI")
    print("2. Vectors will be indexed with correct 384 dimensions")
    print("3. Semantic search will work properly")
    print("="*60 + "\n")

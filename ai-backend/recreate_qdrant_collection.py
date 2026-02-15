"""
Setup Script: Recreate Qdrant Collection with New Dimensions
Run this ONCE after switching to BGE-M3 model
"""

from embeddings.qdrant_manager import get_qdrant_manager

def recreate_collection():
    """Recreate Qdrant collection with new dimensions (1024 for BGE-M3)"""
    
    print("="*70)
    print("  RECREATING QDRANT COLLECTION")
    print("="*70)
    
    print("\nThis will:")
    print("  1. Delete existing 'academic_elements' collection (384-dim)")
    print("  2. Create new 'academic_elements' collection (1024-dim for BGE-M3)")
    print("  3. All existing vectors will be lost")
    
    response = input("\nContinue? (yes/no): ")
    if response.lower() != 'yes':
        print("Aborted.")
        return
    
    try:
        qdrant = get_qdrant_manager()
        
        # Recreate collection
        print("\nRecreating collection...")
        qdrant.create_collection(recreate=True)
        
        print("\n✅ Collection recreated successfully!")
        print(f"   Collection: {qdrant.COLLECTION_NAME}")
        print(f"   Dimensions: {qdrant.EMBEDDING_DIM}")
        print(f"   Distance: Cosine")
        
        print("\nNext steps:")
        print("  1. Restart API server: python structure_api.py")
        print("  2. Upload documents via Swagger UI")
        print("  3. Test search: python test_complete_flow.py")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False
    
    return True


if __name__ == "__main__":
    recreate_collection()

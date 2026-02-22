"""
One-off script: Create the Qdrant collection so it appears in the dashboard.
Run from ai-backend with venv active:
  python create_qdrant_collection.py
"""
from embeddings.qdrant_manager import get_qdrant_manager

if __name__ == "__main__":
    qm = get_qdrant_manager()
    qm.create_collection()
    info = qm.get_collection_info()
    print(f"Collection '{info['collection_name']}' is ready.")
    print(f"  Vectors: {info['vector_size']} dimensions, points: {info['points_count']}")

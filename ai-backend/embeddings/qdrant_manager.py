"""
Qdrant Vector Database Manager
Handles vector storage and retrieval for semantic search
"""

from typing import List, Dict, Optional, Any
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue, SearchRequest
)
import os


class QdrantManager:
    """
    Manages Qdrant vector database operations
    
    Collection: academic_elements
    - Stores embeddings for parsed document elements
    - Metadata: document_id, subject_id, concept_id, category, page_number
    """
    
    COLLECTION_NAME = "academic_elements"
    EMBEDDING_DIM = 768  # BGE-base-en-v1.5 dimension
    
    def __init__(
        self,
        host: str = None,
        port: int = None,
        url: str = None
    ):
        """
        Initialize Qdrant client
        
        Args:
            host: Qdrant host (default: localhost)
            port: Qdrant port (default: 6333)
            url: Full URL (overrides host/port)
        """
        if url:
            self.client = QdrantClient(url=url)
        else:
            host = host or os.getenv("QDRANT_HOST", "localhost")
            port = port or int(os.getenv("QDRANT_PORT", "6333"))
            self.client = QdrantClient(host=host, port=port)
        
        print(f"✓ Connected to Qdrant at {host}:{port}")
    
    def create_collection(self, recreate: bool = False):
        """
        Create the academic_elements collection
        
        Args:
            recreate: If True, delete existing collection and recreate
        """
        # Check if collection exists
        collections = self.client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if self.COLLECTION_NAME in collection_names:
            if recreate:
                print(f"Deleting existing collection: {self.COLLECTION_NAME}")
                self.client.delete_collection(self.COLLECTION_NAME)
            else:
                print(f"✓ Collection already exists: {self.COLLECTION_NAME}")
                return
        
        # Create collection
        self.client.create_collection(
            collection_name=self.COLLECTION_NAME,
            vectors_config=VectorParams(
                size=self.EMBEDDING_DIM,
                distance=Distance.COSINE  # Cosine similarity for semantic search
            )
        )
        
        # Create payload indexes for efficient filtering
        self.client.create_payload_index(
            collection_name=self.COLLECTION_NAME,
            field_name="document_id",
            field_schema="integer"
        )
        
        self.client.create_payload_index(
            collection_name=self.COLLECTION_NAME,
            field_name="subject_id",
            field_schema="integer"
        )
        
        self.client.create_payload_index(
            collection_name=self.COLLECTION_NAME,
            field_name="category",
            field_schema="keyword"
        )
        
        print(f"✓ Created collection: {self.COLLECTION_NAME}")
    
    def index_element(
        self,
        element_id: int,
        embedding: List[float],
        metadata: Dict[str, Any]
    ) -> str:
        """
        Index a single element
        
        Args:
            element_id: Database element ID
            embedding: Vector embedding
            metadata: Element metadata (document_id, subject_id, etc.)
            
        Returns:
            Vector ID (same as element_id)
        """
        point = PointStruct(
            id=element_id,
            vector=embedding,
            payload=metadata
        )
        
        self.client.upsert(
            collection_name=self.COLLECTION_NAME,
            points=[point]
        )
        
        return str(element_id)
    
    def index_elements_batch(
        self,
        element_ids: List[int],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Index multiple elements in batch
        
        Args:
            element_ids: List of database element IDs
            embeddings: List of vector embeddings
            metadatas: List of element metadata dicts
            
        Returns:
            List of vector IDs
        """
        if not (len(element_ids) == len(embeddings) == len(metadatas)):
            raise ValueError("element_ids, embeddings, and metadatas must have same length")
        
        # Filter out None embeddings (safety check)
        valid_data = [
            (eid, emb, meta) 
            for eid, emb, meta in zip(element_ids, embeddings, metadatas)
            if emb is not None and len(emb) == self.EMBEDDING_DIM
        ]
        
        if not valid_data:
            print("⚠ No valid embeddings to index")
            return []
        
        points = [
            PointStruct(
                id=element_id,
                vector=embedding,
                payload=metadata
            )
            for element_id, embedding, metadata in valid_data
        ]
        
        self.client.upsert(
            collection_name=self.COLLECTION_NAME,
            points=points
        )
        
        print(f"✓ Indexed {len(points)} elements to Qdrant")
        
        return [str(eid) for eid, _, _ in valid_data]
    
    def search(
        self,
        query_vector: List[float],
        limit: int = 10,
        subject_id: Optional[int] = None,
        category: Optional[str] = None,
        document_id: Optional[int] = None,
        score_threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Semantic search with optional filters
        
        Args:
            query_vector: Query embedding
            limit: Max results to return
            subject_id: Filter by subject
            category: Filter by category (TEXT, DIAGRAM, etc.)
            document_id: Filter by document
            score_threshold: Minimum similarity score
            
        Returns:
            List of search results with scores and metadata
        """
        # Build filter conditions
        must_conditions = []
        
        if subject_id is not None:
            must_conditions.append(
                FieldCondition(
                    key="subject_id",
                    match=MatchValue(value=subject_id)
                )
            )
        
        if category is not None:
            must_conditions.append(
                FieldCondition(
                    key="category",
                    match=MatchValue(value=category)
                )
            )
        
        if document_id is not None:
            must_conditions.append(
                FieldCondition(
                    key="document_id",
                    match=MatchValue(value=document_id)
                )
            )
        
        # Build filter
        search_filter = Filter(must=must_conditions) if must_conditions else None
        
        # Search using query_points
        search_result = self.client.query_points(
            collection_name=self.COLLECTION_NAME,
            query=query_vector,
            query_filter=search_filter,
            limit=limit,
            score_threshold=score_threshold
        )
        
        # Format results
        formatted_results = []
        for result in search_result.points:
            formatted_results.append({
                "element_id": result.id,
                "score": result.score,
                "metadata": result.payload
            })
        
        return formatted_results
    
    def delete_by_document(self, document_id: int):
        """Delete all vectors for a document"""
        self.client.delete(
            collection_name=self.COLLECTION_NAME,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id)
                    )
                ]
            )
        )
        print(f"✓ Deleted vectors for document {document_id}")
    
    def get_collection_info(self) -> Dict[str, Any]:
        """Get collection statistics"""
        info = self.client.get_collection(self.COLLECTION_NAME)
        return {
            "name": info.config.params.vectors.size,
            "vectors_count": info.vectors_count,
            "points_count": info.points_count,
            "status": info.status
        }


# Singleton instance
_qdrant_manager: Optional[QdrantManager] = None


def get_qdrant_manager() -> QdrantManager:
    """Get singleton Qdrant manager instance"""
    global _qdrant_manager
    if _qdrant_manager is None:
        _qdrant_manager = QdrantManager()
    return _qdrant_manager

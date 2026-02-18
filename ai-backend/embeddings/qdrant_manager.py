"""
Qdrant Vector Database Manager
Handles vector storage and retrieval for semantic search
"""

from typing import List, Dict, Optional, Any
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue, MatchAny
)
import os


class QdrantManager:
    """
    Manages Qdrant vector database operations.

    Two collections (one per retrieval unit; same dim = same model):
    - academic_chunks: main retrieval index (chunk-level embeddings)
    - academic_elements: optional element-level index for special cases
    """

    COLLECTION_ELEMENTS = "academic_elements"
    COLLECTION_CHUNKS = "academic_chunks"
    COLLECTION_QUESTIONS = "question_embeddings"
    COLLECTION_NAME = "academic_elements"  # default/legacy alias for elements
    EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 dimension
    CHUNK_ID_OFFSET = 2**31  # Point IDs for chunks: chunk_id + OFFSET (avoids collision with element IDs)
    QUESTION_ID_OFFSET = 2**30  # Point IDs for questions: question_id + OFFSET
    
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
    
    def _create_collection_if_needed(
        self,
        collection_name: str,
        recreate: bool = False,
        payload_indexes: list = None,
    ):
        collections = self.client.get_collections().collections
        names = [c.name for c in collections]
        if collection_name in names:
            if recreate:
                self.client.delete_collection(collection_name)
                print(f"Deleted existing: {collection_name}")
            else:
                print(f"✓ Collection exists: {collection_name}")
                return
        self.client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=self.EMBEDDING_DIM,
                distance=Distance.COSINE,
            ),
        )
        for field, schema in payload_indexes or []:
            self.client.create_payload_index(
                collection_name=collection_name,
                field_name=field,
                field_schema=schema,
            )
        print(f"✓ Created collection: {collection_name}")

    def create_collection(self, recreate: bool = False):
        """
        Create academic_elements and academic_chunks collections.
        One collection per retrieval unit; same dim = same embedding model.
        """
        elem_indexes = [
            ("document_id", "integer"),
            ("subject_id", "integer"),
            ("category", "keyword"),
            ("concept_id", "integer"),
            ("unit_id", "integer"),
            ("section_path", "keyword"),
        ]
        chunk_indexes = [
            ("document_id", "integer"),
            ("subject_id", "integer"),
            ("concept_id", "integer"),
            ("unit_id", "integer"),
            ("section_path", "keyword"),
            ("chunk_type", "keyword"),
        ]
        self._create_collection_if_needed(
            self.COLLECTION_ELEMENTS, recreate=recreate, payload_indexes=elem_indexes
        )
        self._create_collection_if_needed(
            self.COLLECTION_CHUNKS, recreate=recreate, payload_indexes=chunk_indexes
        )
        question_indexes = [
            ("subject_id", "integer"),
            ("unit_id", "integer"),
            ("concept_id", "integer"),
        ]
        self._create_collection_if_needed(
            self.COLLECTION_QUESTIONS, recreate=recreate, payload_indexes=question_indexes
        )

    def ensure_question_collection(self):
        """Ensure question_embeddings collection exists (for dedupe)."""
        self._create_collection_if_needed(
            self.COLLECTION_QUESTIONS,
            payload_indexes=[
                ("subject_id", "integer"),
                ("unit_id", "integer"),
                ("concept_id", "integer"),
            ],
        )

    def index_question(
        self,
        question_id: int,
        embedding: List[float],
        subject_id: int,
        unit_id: Optional[int] = None,
        concept_id: Optional[int] = None,
    ):
        """Index a single question for dedupe/search. Point id = question_id + QUESTION_ID_OFFSET."""
        self.ensure_question_collection()
        point = PointStruct(
            id=question_id + self.QUESTION_ID_OFFSET,
            vector=embedding,
            payload={
                "question_id": question_id,
                "subject_id": subject_id,
                "unit_id": unit_id or 0,
                "concept_id": concept_id or 0,
            },
        )
        self.client.upsert(collection_name=self.COLLECTION_QUESTIONS, points=[point])

    def search_question_duplicates(
        self,
        query_vector: List[float],
        subject_id: Optional[int] = None,
        unit_id: Optional[int] = None,
        concept_id: Optional[int] = None,
        limit: int = 10,
        score_threshold: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar questions (for dedupe).
        Returns list of {question_id, score, ...}.
        Use score_threshold=0.90 for same concept/unit dedupe, 0.95 for global.
        """
        self.ensure_question_collection()
        must = [FieldCondition(key="subject_id", match=MatchValue(value=subject_id))] if subject_id else []
        if unit_id is not None:
            must.append(FieldCondition(key="unit_id", match=MatchValue(value=unit_id)))
        if concept_id is not None:
            must.append(FieldCondition(key="concept_id", match=MatchValue(value=concept_id)))
        search_filter = Filter(must=must) if must else None
        try:
            results = self.client.search(
                collection_name=self.COLLECTION_QUESTIONS,
                query_vector=query_vector,
                query_filter=search_filter,
                limit=limit,
                score_threshold=score_threshold,
            )
            return [
                {
                    "question_id": r.payload.get("question_id"),
                    "score": r.score,
                    "subject_id": r.payload.get("subject_id"),
                    "unit_id": r.payload.get("unit_id"),
                    "concept_id": r.payload.get("concept_id"),
                }
                for r in results
            ]
        except Exception:
            return []

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
            collection_name=self.COLLECTION_ELEMENTS,
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
        
        points = [
            PointStruct(
                id=element_id,
                vector=embedding,
                payload=metadata
            )
            for element_id, embedding, metadata in zip(element_ids, embeddings, metadatas)
        ]
        
        self.client.upsert(
            collection_name=self.COLLECTION_ELEMENTS,
            points=points
        )
        
        print(f"✓ Indexed {len(points)} elements to Qdrant")
        
        return [str(eid) for eid in element_ids]
    
    def index_chunks_batch(
        self,
        chunk_ids: List[int],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Index document chunks with unit/concept/section metadata.
        Uses point id = chunk_id + CHUNK_ID_OFFSET. Stores in academic_chunks collection.
        Metadata should include: subject_id, document_id, unit_id, concept_id, section_path, page_start, page_end.
        """
        if not (len(chunk_ids) == len(embeddings) == len(metadatas)):
            raise ValueError("chunk_ids, embeddings, and metadatas must have same length")
        points = [
            PointStruct(
                id=chunk_id + self.CHUNK_ID_OFFSET,
                vector=emb,
                payload={**meta, "point_type": "chunk", "chunk_id": chunk_id}
            )
            for chunk_id, emb, meta in zip(chunk_ids, embeddings, metadatas)
        ]
        self.client.upsert(collection_name=self.COLLECTION_CHUNKS, points=points)
        print(f"✓ Indexed {len(points)} chunks to Qdrant")
        return [str(cid) for cid in chunk_ids]
    
    def search(
        self,
        query_vector: List[float],
        limit: int = 10,
        subject_id: Optional[int] = None,
        category: Optional[str] = None,
        document_id: Optional[int] = None,
        unit_id: Optional[int] = None,
        concept_ids: Optional[List[int]] = None,
        section_path: Optional[str] = None,
        score_threshold: float = 0.5,
        search_chunks: bool = True,
        search_elements: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search. By default searches academic_chunks (main retrieval).
        Set search_elements=True to also search academic_elements (special cases).
        """
        must_conditions = []
        if subject_id is not None:
            must_conditions.append(
                FieldCondition(key="subject_id", match=MatchValue(value=subject_id))
            )
        if category is not None:
            must_conditions.append(
                FieldCondition(key="category", match=MatchValue(value=category))
            )
        if document_id is not None:
            must_conditions.append(
                FieldCondition(key="document_id", match=MatchValue(value=document_id))
            )
        if unit_id is not None:
            must_conditions.append(
                FieldCondition(key="unit_id", match=MatchValue(value=unit_id))
            )
        if concept_ids:
            must_conditions.append(
                FieldCondition(key="concept_id", match=MatchAny(any=concept_ids))
            )
        if section_path is not None and section_path != "":
            must_conditions.append(
                FieldCondition(key="section_path", match=MatchValue(value=section_path))
            )
        search_filter = Filter(must=must_conditions) if must_conditions else None

        formatted_results: List[Dict[str, Any]] = []

        if search_chunks:
            try:
                collections = self.client.get_collections().collections
                if any(c.name == self.COLLECTION_CHUNKS for c in collections):
                    chunk_results = self.client.search(
                        collection_name=self.COLLECTION_CHUNKS,
                        query_vector=query_vector,
                        query_filter=search_filter,
                        limit=limit,
                        score_threshold=score_threshold,
                    )
                    for result in chunk_results:
                        payload = result.payload or {}
                        formatted_results.append({
                            "point_type": "chunk",
                            "chunk_id": payload.get("chunk_id"),
                            "element_id": None,
                            "score": result.score,
                            "metadata": payload,
                        })
            except Exception:
                pass

        if search_elements and len(formatted_results) < limit:
            try:
                collections = self.client.get_collections().collections
                if any(c.name == self.COLLECTION_ELEMENTS for c in collections):
                    elem_results = self.client.search(
                        collection_name=self.COLLECTION_ELEMENTS,
                        query_vector=query_vector,
                        query_filter=search_filter,
                        limit=limit - len(formatted_results),
                        score_threshold=score_threshold,
                    )
                    for result in elem_results:
                        formatted_results.append({
                            "point_type": "element",
                            "element_id": result.id,
                            "chunk_id": None,
                            "score": result.score,
                            "metadata": result.payload or {},
                        })
            except Exception:
                pass

        # Sort by score descending and cap at limit
        formatted_results.sort(key=lambda x: x.get("score") or 0, reverse=True)
        return formatted_results[:limit]
    
    def delete_by_document(self, document_id: int):
        """Delete all vectors for a document from both chunks and elements collections."""
        doc_filter = Filter(
            must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
        )
        for coll_name in (self.COLLECTION_CHUNKS, self.COLLECTION_ELEMENTS):
            try:
                collections = self.client.get_collections().collections
                if not any(c.name == coll_name for c in collections):
                    continue
                self.client.delete(collection_name=coll_name, points_selector=doc_filter)
                print(f"✓ Deleted vectors for document {document_id} from {coll_name}")
            except Exception as e:
                if "doesn't exist" in str(e) or "404" in str(e) or "Not found" in str(e):
                    continue
                raise

    def get_collection_info(self) -> Dict[str, Any]:
        """Get collection statistics for chunks (main) and elements."""
        out = {"chunks": None, "elements": None}
        for name, key in [(self.COLLECTION_CHUNKS, "chunks"), (self.COLLECTION_ELEMENTS, "elements")]:
            try:
                info = self.client.get_collection(name)
                out[key] = {
                    "collection_name": name,
                    "vector_size": (
                        info.config.params.vectors.size
                        if info.config and info.config.params
                        else self.EMBEDDING_DIM
                    ),
                    "points_count": info.points_count,
                    "status": info.status,
                }
            except Exception:
                out[key] = {"collection_name": name, "points_count": 0, "status": "missing"}
        return out


# Singleton instance
_qdrant_manager: Optional[QdrantManager] = None


def get_qdrant_manager() -> QdrantManager:
    """Get singleton Qdrant manager instance"""
    global _qdrant_manager
    if _qdrant_manager is None:
        _qdrant_manager = QdrantManager()
    return _qdrant_manager

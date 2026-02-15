"""
Embeddings package
Handles text-to-vector conversion using SentenceTransformers
"""

from .generator import (
    EmbeddingGenerator,
    get_embedding_generator,
    generate_embedding,
    generate_embeddings_batch
)

__all__ = [
    "EmbeddingGenerator",
    "get_embedding_generator",
    "generate_embedding",
    "generate_embeddings_batch"
]

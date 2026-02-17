"""
Embedding Generator
Converts text to vector embeddings using SentenceTransformers
Uses all-MiniLM-L6-v2 model (384 dimensions, fast, good quality)
"""

from typing import List, Optional
from sentence_transformers import SentenceTransformer
import numpy as np


class EmbeddingGenerator:
    """
    Generate embeddings for text using SentenceTransformers
    
    Model: all-MiniLM-L6-v2
    - Dimensions: 384
    - Speed: Fast (~14,000 sentences/sec on GPU)
    - Quality: Good for semantic search
    - Size: ~80MB
    """
    
    # Model configuration
    DEFAULT_MODEL = "all-MiniLM-L6-v2"
    EMBEDDING_DIM = 384
    
    def __init__(self, model_name: str = DEFAULT_MODEL):
        """
        Initialize embedding generator
        
        Args:
            model_name: HuggingFace model name
        """
        print(f"Loading embedding model: {model_name}...")
        self.model = SentenceTransformer(model_name)
        self.model_name = model_name
        print(f"✓ Model loaded: {model_name}")
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text
        
        Args:
            text: Input text
            
        Returns:
            List of floats (embedding vector)
        """
        if not text or not text.strip():
            # Return zero vector for empty text
            return [0.0] * self.EMBEDDING_DIM
        
        # Generate embedding
        embedding = self.model.encode(text, convert_to_numpy=True)
        
        # Convert to list
        return embedding.tolist()
    
    def generate_embeddings_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        Generate embeddings for multiple texts (batched for efficiency)
        
        Args:
            texts: List of input texts
            batch_size: Batch size for processing
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        # Handle empty texts
        processed_texts = [text if text and text.strip() else " " for text in texts]
        
        # Generate embeddings in batches
        embeddings = self.model.encode(
            processed_texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            show_progress_bar=len(texts) > 100  # Show progress for large batches
        )
        
        # Convert to list of lists
        return embeddings.tolist()
    
    def get_embedding_dimension(self) -> int:
        """Get the dimension of embeddings"""
        return self.EMBEDDING_DIM
    
    def get_model_info(self) -> dict:
        """Get information about the loaded model"""
        return {
            "model_name": self.model_name,
            "embedding_dimension": self.EMBEDDING_DIM,
            "max_sequence_length": self.model.max_seq_length
        }


# Singleton instance for reuse
_embedding_generator: Optional[EmbeddingGenerator] = None


def get_embedding_generator() -> EmbeddingGenerator:
    """
    Get singleton embedding generator instance
    Lazy initialization - model loaded on first call
    """
    global _embedding_generator
    if _embedding_generator is None:
        _embedding_generator = EmbeddingGenerator()
    return _embedding_generator


def generate_embedding(text: str) -> List[float]:
    """Convenience function to generate single embedding"""
    generator = get_embedding_generator()
    return generator.generate_embedding(text)


def generate_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Convenience function to generate batch embeddings"""
    generator = get_embedding_generator()
    return generator.generate_embeddings_batch(texts)

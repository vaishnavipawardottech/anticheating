"""
Embedding Generator - Brain Upgrade
Converts text to vector embeddings using OpenAI text-embedding-3-small
Upgraded from all-MiniLM-L6-v2 (384-dim) to text-embedding-3-small (1536-dim)

Architecture:
- Model: text-embedding-3-small (OpenAI)
- Dimensions: 1536 (vs 384 before)
- Cost: ~$0.02 per 1M tokens
- Quality: Superior semantic understanding
"""

from typing import List, Optional
import os
from openai import OpenAI
from tqdm import tqdm


class EmbeddingGenerator:
    """
    Generate embeddings for text using OpenAI text-embedding-3-small
    
    Model: text-embedding-3-small
    - Dimensions: 1536
    - Cost: $0.02 per 1M tokens
    - Quality: Excellent for semantic search
    - Speed: ~3000 tokens/sec via API
    """
    
    # Model configuration - Brain Upgrade
    DEFAULT_MODEL = "text-embedding-3-small"
    EMBEDDING_DIM = 1536  # Upgraded from 384
    
    def __init__(self, model_name: str = DEFAULT_MODEL, api_key: str = None):
        """
        Initialize embedding generator with OpenAI
        
        Args:
            model_name: OpenAI model name
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
        """
        self.model_name = model_name
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        
        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY not set. Please set environment variable or pass api_key parameter."
            )
        
        self.client = OpenAI(api_key=self.api_key)
        print(f"Loading embedding model: {model_name}...")
        print(f"Model loaded: {model_name} (1536-dim)")
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text
        
        Args:
            text: Input text
            
        Returns:
            List of floats (embedding vector, 1536-dim)
        """
        if not text or not text.strip():
            # Return zero vector for empty text
            return [0.0] * self.EMBEDDING_DIM
        
        try:
            response = self.client.embeddings.create(
                input=text,
                model=self.model_name
            )
            embedding = response.data[0].embedding
            return embedding
        except Exception as e:
            print(f"   Warning: Embedding generation failed: {str(e)}")
            return [0.0] * self.EMBEDDING_DIM
    
    def generate_embeddings_batch(
        self, 
        texts: List[str], 
        batch_size: int = 100,
        show_progress: bool = True
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts (batched for efficiency)
        
        OpenAI API supports up to 2048 texts per request, but we use smaller batches
        for better error handling and progress tracking.
        
        Args:
            texts: List of input texts
            batch_size: Batch size for API calls (max 2048, recommended 100)
            show_progress: Show progress bar
            
        Returns:
            List of embedding vectors (each 1536-dim)
        """
        if not texts:
            return []
        
        # Handle empty texts
        processed_texts = [text if text and text.strip() else " " for text in texts]
        
        all_embeddings = []
        
        # Process in batches
        batches = [
            processed_texts[i:i + batch_size] 
            for i in range(0, len(processed_texts), batch_size)
        ]
        
        iterator = tqdm(batches, desc="Batches") if show_progress and len(batches) > 1 else batches
        
        for batch in iterator:
            try:
                response = self.client.embeddings.create(
                    input=batch,
                    model=self.model_name
                )
                # Extract embeddings in order
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)
            except Exception as e:
                print(f"   Warning: Batch embedding failed: {str(e)}")
                # Return zero vectors for failed batch
                all_embeddings.extend([[0.0] * self.EMBEDDING_DIM] * len(batch))
        
        return all_embeddings
    
    def get_embedding_dimension(self) -> int:
        """Get the dimension of embeddings"""
        return self.EMBEDDING_DIM
    
    def get_model_info(self) -> dict:
        """Get information about the loaded model"""
        return {
            "model_name": self.model_name,
            "embedding_dimension": self.EMBEDDING_DIM,
            "provider": "openai",
            "cost_per_1m_tokens": 0.02
        }


# Singleton instance for reuse
_embedding_generator: Optional[EmbeddingGenerator] = None


def get_embedding_generator() -> EmbeddingGenerator:
    """
    Get singleton embedding generator instance
    Lazy initialization - client created on first call
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

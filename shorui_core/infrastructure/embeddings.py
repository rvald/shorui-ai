"""
Embedding Model Infrastructure

Provides a singleton wrapper around sentence-transformers for efficient
text embedding generation across the application.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


class EmbeddingModelSingleton:
    """
    Singleton wrapper for the embedding model.
    
    Ensures only one instance of the embedding model is loaded in memory,
    providing efficient embedding generation across the application.
    
    Usage:
        model = EmbeddingModelSingleton()
        embeddings = model(["text1", "text2"])
        
        # Or access properties
        print(model.model_id)
        print(model.embedding_size)
    """
    
    _instance: "EmbeddingModelSingleton | None" = None
    _model: "SentenceTransformer | None" = None
    
    # Default model configuration
    DEFAULT_MODEL_ID = "intfloat/e5-large-unsupervised"
    DEFAULT_DEVICE = "cpu"
    
    def __new__(cls, model_id: str | None = None, device: str | None = None):
        """
        Create or return the singleton instance.
        
        Args:
            model_id: HuggingFace model ID (default: e5-large-unsupervised)
            device: Device to load model on (default: cpu)
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize(
                model_id or cls.DEFAULT_MODEL_ID,
                device or cls.DEFAULT_DEVICE
            )
        return cls._instance
    
    def _initialize(self, model_id: str, device: str) -> None:
        """Initialize the embedding model."""
        from sentence_transformers import SentenceTransformer
        
        self._model_id = model_id
        self._device = device
        
        logger.info(f"Loading embedding model: {model_id} on {device}")
        self._model = SentenceTransformer(model_id, device=device)
        self._embedding_size = self._model.get_sentence_embedding_dimension()
        logger.info(f"Embedding model loaded. Dimension: {self._embedding_size}")
    
    @property
    def model_id(self) -> str:
        """Get the model identifier."""
        return self._model_id
    
    @property
    def embedding_size(self) -> int:
        """Get the embedding vector dimension."""
        return self._embedding_size
    
    @property
    def device(self) -> str:
        """Get the device the model is loaded on."""
        return self._device
    
    def __call__(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed.
            
        Returns:
            List of embedding vectors as lists of floats.
        """
        if not texts:
            return []
        
        # sentence-transformers returns numpy arrays, convert to lists
        embeddings = self._model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        
        return [emb.tolist() for emb in embeddings]
    
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Alias for __call__ for explicit API."""
        return self(texts)
    
    def embed_single(self, text: str) -> list[float]:
        """Embed a single text string."""
        return self([text])[0]

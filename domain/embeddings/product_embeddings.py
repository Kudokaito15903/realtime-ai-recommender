"""
Product embedding generation using SentenceTransformer.
"""
import os
import sys
import time
import threading
from typing import List, Dict, Any
import numpy as np
from loguru import logger
from sentence_transformers import SentenceTransformer

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import VECTOR_DIMENSION


class ProductEmbeddingModel:
    """
    SentenceTransformer-based embedding model for products.
    - Product embedding: semantic only (NO weight, NO numeric)
    """

    _instance = None
    _lock = threading.Lock()

    MODEL_NAME = "all-MiniLM-L6-v2" 

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                start_time = time.time()
                logger.info("Loading SentenceTransformer model...")

                cls._instance = super().__new__(cls)
                cls._instance.model = SentenceTransformer(
                    cls.MODEL_NAME,
                    device="cpu"  # change to "cuda" if available
                )

                cls._instance.dimension = (
                    cls._instance.model.get_sentence_embedding_dimension()
                )

                if cls._instance.dimension != VECTOR_DIMENSION:
                    logger.warning(
                        f"VECTOR_DIMENSION={VECTOR_DIMENSION} "
                        f"!= model dimension={cls._instance.dimension}"
                    )

                logger.info(
                    f"Model loaded in {time.time() - start_time:.2f}s "
                    f"(dim={cls._instance.dimension})"
                )

            return cls._instance

    def get_embedding(self, text: str) -> np.ndarray:
        """Generate embedding for a single text."""
        if not text or not text.strip():
            return np.zeros(self.dimension, dtype=np.float32)

        embedding = self.model.encode(
            text,
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).astype(np.float32)

        return embedding

    def get_embeddings(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings for a batch of texts."""
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)

        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).astype(np.float32)

        return embeddings

    def build_product_text(self, product: Dict[str, Any]) -> str:
        """Build clean semantic text for a product. Only include semantic fields."""
        parts: List[str] = []

        # Core semantic fields
        if product.get("name"):
            parts.append(product["name"])

        if product.get("description"):
            parts.append(product["description"])

        # Optional but semantic
        if product.get("color"):
            parts.append(f"Color: {product['color']}")

        # Specifications (very important)
        specs = product.get("specifications")
        if isinstance(specs, dict):
            for k, v in specs.items():
                if v:
                    parts.append(f"{k}: {v}")

        return ". ".join(parts)

    def get_product_embedding(self, product: Dict[str, Any]) -> np.ndarray:
        """Generate semantic embedding for a product."""
        text = self.build_product_text(product)
        return self.get_embedding(text)

    @property
    def embedding_dimension(self) -> int:
        return self.dimension


# Singleton accessor
def get_product_embedding_model() -> ProductEmbeddingModel:
    return ProductEmbeddingModel()


# Alias for backward compatibility
def get_embedding_model() -> ProductEmbeddingModel:
    return get_product_embedding_model()


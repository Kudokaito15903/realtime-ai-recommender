"""
Product embedding generation using SentenceTransformer.
Semantic-only, product-level embeddings.
"""

import os
import sys
import time
import threading
from typing import List
import numpy as np
from loguru import logger
from sentence_transformers import SentenceTransformer

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from config import VECTOR_DIMENSION


class ProductEmbeddingModel:
    """
    SentenceTransformer-based embedding model.

    Principles:
    - Input: CLEAN SEMANTIC TEXT ONLY
    - No price, rating, SKU, IDs
    - Product-level (NOT variant-level)
    """

    _instance = None
    _lock = threading.Lock()

    MODEL_NAME = "all-MiniLM-L6-v2"

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                start_time = time.time()
                logger.info("Loading SentenceTransformer model...")

                instance = super().__new__(cls)
                instance.model = SentenceTransformer(
                    cls.MODEL_NAME, device="cpu"  # change to "cuda" if available
                )

                instance.dimension = instance.model.get_sentence_embedding_dimension()

                if instance.dimension != VECTOR_DIMENSION:
                    logger.warning(
                        f"VECTOR_DIMENSION={VECTOR_DIMENSION} "
                        f"!= model dimension={instance.dimension}"
                    )

                logger.info(
                    f"Model loaded in {time.time() - start_time:.2f}s "
                    f"(dim={instance.dimension})"
                )

                cls._instance = instance

            return cls._instance

    # =========================
    # Embedding API
    # =========================

    def embed_text(self, text: str) -> np.ndarray:
        """
        Generate embedding for semantic text.
        """
        if not text or not text.strip():
            return np.zeros(self.dimension, dtype=np.float32)

        return self.model.encode(
            text,
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).astype(np.float32)

    def embed_batch(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings for a batch of texts.
        """
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)

        return self.model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).astype(np.float32)

    @property
    def embedding_dimension(self) -> int:
        return self.dimension


# =========================
# Singleton accessors
# =========================


def get_product_embedding_model() -> ProductEmbeddingModel:
    return ProductEmbeddingModel()


# Backward compatibility
def get_embedding_model() -> ProductEmbeddingModel:
    return get_product_embedding_model()

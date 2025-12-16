import os
import numpy as np
from typing import List, Dict, Any
import time
import threading
from loguru import logger
from sentence_transformers import SentenceTransformer

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import VECTOR_DIMENSION


class EmbeddingModel:
    """
    Embedding model using SentenceTransformer (semantic embeddings)
    """
    _instance = None
    _lock = threading.Lock()

    MODEL_NAME = "all-MiniLM-L6-v2"  # 384-dim, fast, production-ready

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                logger.info("Initializing SentenceTransformer embedding model")
                start_time = time.time()

                cls._instance = super(EmbeddingModel, cls).__new__(cls)

                # Load transformer model
                cls._instance.model = SentenceTransformer(
                    cls.MODEL_NAME,
                    device="cpu"  # change to "cuda" if available
                )

                cls._instance.dimension = cls._instance.model.get_sentence_embedding_dimension()

                if cls._instance.dimension != VECTOR_DIMENSION:
                    logger.warning(
                        f"VECTOR_DIMENSION ({VECTOR_DIMENSION}) "
                        f"!= model dimension ({cls._instance.dimension})"
                    )

                logger.info(
                    f"SentenceTransformer loaded in "
                    f"{time.time() - start_time:.2f}s "
                    f"(dim={cls._instance.dimension})"
                )

            return cls._instance

    # --------------------------------------------------
    # Core embedding methods
    # --------------------------------------------------

    def get_embedding(self, text: str) -> np.ndarray:
        """
        Generate embedding for a single text
        """
        start_time = time.time()

        if not text or not text.strip():
            embedding = np.zeros(self.dimension, dtype=np.float32)
        else:
            embedding = self.model.encode(
                text,
                normalize_embeddings=True,  # IMPORTANT for cosine similarity
                convert_to_numpy=True
            ).astype(np.float32)

        logger.debug(
            f"Embedding generated in {time.time() - start_time:.4f}s"
        )
        return embedding

    def get_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings for a batch of texts
        """
        start_time = time.time()

        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)

        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True
        ).astype(np.float32)

        logger.debug(
            f"Batch embeddings ({len(texts)} items) generated in "
            f"{time.time() - start_time:.4f}s"
        )
        return embeddings

    # --------------------------------------------------
    # Product helpers
    # --------------------------------------------------

    def get_product_embedding(self, product: Dict[str, Any]) -> np.ndarray:
        """
        Generate embedding for a product by combining fields
        """
        parts = [
            product.get("name", ""),
            product.get("description", ""),
            f"Category: {product.get('category', '')}"
        ]

        # Optional attributes
        attributes = product.get("attributes")
        if isinstance(attributes, dict):
            for k, v in attributes.items():
                if isinstance(v, (str, int, float)):
                    parts.append(f"{k}: {v}")

        product_text = " ".join(parts)
        return self.get_embedding(product_text)

    def get_text_embedding(self, text: str) -> np.ndarray:
        """
        Alias for get_embedding
        """
        return self.get_embedding(text)

    @property
    def embedding_dimension(self) -> int:
        return self.dimension


# --------------------------------------------------
# Singleton accessor
# --------------------------------------------------

def get_embedding_model() -> EmbeddingModel:
    return EmbeddingModel()

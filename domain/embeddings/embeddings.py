import os
import sys
import time
import threading
from typing import List, Dict, Any
import numpy as np
from loguru import logger
from sentence_transformers import SentenceTransformer

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import VECTOR_DIMENSION
class EmbeddingModel:
    """
    SentenceTransformer-based embedding model.
    - Product embedding: semantic only (NO weight, NO numeric)
    - User vector: weighted aggregation of product embeddings
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

    # --------------------------------------------------
    # Core embedding
    # --------------------------------------------------

    def get_embedding(self, text: str) -> np.ndarray:
        """
        Generate embedding for a single text.
        """
        if not text or not text.strip():
            return np.zeros(self.dimension, dtype=np.float32)

        embedding = self.model.encode(
            text,
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).astype(np.float32)

        return embedding

    def get_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings for a batch of texts.
        """
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)

        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).astype(np.float32)

        return embeddings

    # --------------------------------------------------
    # Product embedding (SEMANTIC ONLY)
    # --------------------------------------------------

    def build_product_text(self, product: Dict[str, Any]) -> str:
        """
        Build clean semantic text for a product.
        Only include semantic fields.
        """
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
        """
        Generate semantic embedding for a product.
        """
        text = self.build_product_text(product)
        return self.get_embedding(text)

    # --------------------------------------------------
    # User interest vector (WEIGHTED)
    # --------------------------------------------------

    def build_user_interest_vector(
        self,
        interacted_products: List[Dict[str, Any]],
        default_weight: float = 1.0,
    ) -> np.ndarray:
        """
        Build user interest vector using weighted average.

        interacted_products example:
        [
            {
                "product": {...},
                "weight": 3.0,   # add-to-cart / purchase weight
                # optional:
                "embedding": np.ndarray
            }
        ]
        """
        if not interacted_products:
            return np.zeros(self.dimension, dtype=np.float32)

        accumulator = np.zeros(self.dimension, dtype=np.float32)
        total_weight = 0.0

        for item in interacted_products:
            weight = float(item.get("weight", default_weight))
            embedding = item.get("embedding")

            if embedding is None:
                product = item.get("product")
                if not product:
                    continue
                embedding = self.get_product_embedding(product)

            accumulator += embedding * weight
            total_weight += weight

        if total_weight == 0:
            return np.zeros(self.dimension, dtype=np.float32)

        user_vector = accumulator / total_weight

        # Normalize
        norm = np.linalg.norm(user_vector)
        if norm > 0:
            user_vector /= norm

        return user_vector.astype(np.float32)

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------

    @property
    def embedding_dimension(self) -> int:
        return self.dimension


# ==================================================
# Singleton accessor
# ==================================================

def get_embedding_model() -> EmbeddingModel:
    return EmbeddingModel()


# ==================================================
# Re-ranking utilities
# ==================================================

def rerank_with_weight(
    results: List[Dict[str, Any]],
    similarity_key: str = "similarity_score",
    business_weight_key: str = "business_score",
    alpha: float = 0.7,
) -> List[Dict[str, Any]]:
    """
    Combine semantic similarity with business score.

    final_score = alpha * similarity + (1 - alpha) * business_score
    """
    for item in results:
        similarity = float(item.get(similarity_key, item.get("score", 0.0)))
        business_score = float(item.get(business_weight_key, 1.0))

        item["final_score"] = (
            alpha * similarity +
            (1.0 - alpha) * business_score
        )

    return sorted(
        results,
        key=lambda x: x.get("final_score", 0.0),
        reverse=True,
    )

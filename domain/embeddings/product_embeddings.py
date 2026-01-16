"""
Product embedding generation using SentenceTransformer.
Semantic-only, product-level embeddings.
"""

import os
import sys
import time
import threading
from typing import List, Dict, Any
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

    MODEL_NAME = "intfloat/multilingual-e5-base"

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

    def get_product_embedding(self, product_data: Dict[str, Any]) -> np.ndarray:
        """
        Generate embedding for product data.
        Combines semantic text fields (name, description, brand, specifications, etc.)
        and generates a normalized embedding vector.
        """

        # Extract text fields for embedding
        text_parts = []

        # Basic product info
        if product_data.get("name"):
            text_parts.append(str(product_data["name"]))

        if product_data.get("description"):
            text_parts.append(str(product_data["description"]))

        if product_data.get("brand"):
            text_parts.append(f"Brand: {product_data['brand']}")

        # Category information
        category_id = product_data.get("categoriesId")
        if category_id:
            if isinstance(category_id, list):
                text_parts.append(f"Categories: {', '.join(category_id)}")
            else:
                text_parts.append(f"Category: {category_id}")

        if product_data.get("category"):
            text_parts.append(f"Category: {product_data['category']}")

        IMPORTANT_SPECS = {
            "battery life",
            "screen size",
            "ram",
            "storage",
            "weight",
            "dimensions",
            "processor",
        }

        # Specifications
        specifications = product_data.get("specifications")
        spec_texts = []

        for spec in specifications:
            key = spec.get("key", "").lower()
            value = spec.get("value")
            if key and value and key in IMPORTANT_SPECS:
                spec_texts.append(f"{spec['key']}: {value}")
        if spec_texts:
            text_parts.append("Key specs: " + ", ".join(spec_texts))

        variants = product_data.get("productVariants", [])
        variant_perf_specs = set()

        for v in variants:
            for spec in v.get("bestSpecifications", []):
                key = spec.get("key", "").lower()
                value = spec.get("value")
                if key and value and key in IMPORTANT_SPECS:
                    variant_perf_specs.add(f"{spec['key']}: {value}")

        if variant_perf_specs:
            text_parts.append("Performance features: " + ", ".join(variant_perf_specs))

        combined_text = " ".join(text_parts)

        return self.embed_text(combined_text)

    def get_embedding(self, text: str) -> np.ndarray:
        """
        Alias for embed_text for backward compatibility.
        """
        return self.embed_text(text)

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

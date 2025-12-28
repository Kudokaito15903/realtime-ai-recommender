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

        if product_data.get("brandName"):
            text_parts.append(f"Brand: {product_data['brandName']}")

        # Category information
        category_id = product_data.get("categoryId")
        if category_id:
            if isinstance(category_id, list):
                text_parts.append(f"Categories: {', '.join(category_id)}")
            else:
                text_parts.append(f"Category: {category_id}")

        if product_data.get("category"):
            text_parts.append(f"Category: {product_data['category']}")

        # Specifications
        specifications = product_data.get("specifications")
        if specifications:
            if isinstance(specifications, list):
                # Handle list of Specification objects
                spec_texts = []
                for spec in specifications:
                    if isinstance(spec, dict):
                        key = spec.get("key", "")
                        value = spec.get("value", "")
                        group = spec.get("group", "")
                        if key and value:
                            spec_texts.append(f"{key}: {value}")
                if spec_texts:
                    text_parts.append(f"Specifications: {', '.join(spec_texts)}")
            elif isinstance(specifications, dict):
                # Handle legacy dict format
                spec_texts = [f"{k}: {v}" for k, v in specifications.items()]
                if spec_texts:
                    text_parts.append(f"Specifications: {', '.join(spec_texts)}")

        # Product variants info (include variant names and colors)
        variants = product_data.get("productVariants")
        if variants and isinstance(variants, list):
            variant_info = []
            for variant in variants:
                if isinstance(variant, dict):
                    variant_name = variant.get("variantName", "")
                    color = variant.get("color", "")
                    if variant_name:
                        variant_info.append(variant_name)
                    if color:
                        variant_info.append(f"Color: {color}")
            if variant_info:
                text_parts.append(f"Variants: {', '.join(variant_info)}")

        # Combine all text parts
        combined_text = " ".join(text_parts)

        # Generate embedding
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

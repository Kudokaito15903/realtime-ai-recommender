"""
User vector building from interaction history.
"""
import numpy as np
from typing import List, Dict, Any
from loguru import logger

from .product_embeddings import get_product_embedding_model


def build_user_interest_vector(
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
    embedding_model = get_product_embedding_model()
    dimension = embedding_model.embedding_dimension
    
    if not interacted_products:
        return np.zeros(dimension, dtype=np.float32)

    accumulator = np.zeros(dimension, dtype=np.float32)
    total_weight = 0.0

    for item in interacted_products:
        weight = float(item.get("weight", default_weight))
        embedding = item.get("embedding")

        if embedding is None:
            product = item.get("product")
            if not product:
                continue
            embedding = embedding_model.get_product_embedding(product)

        accumulator += embedding * weight
        total_weight += weight

    if total_weight == 0:
        return np.zeros(dimension, dtype=np.float32)

    user_vector = accumulator / total_weight

    # Normalize
    norm = np.linalg.norm(user_vector)
    if norm > 0:
        user_vector /= norm

    return user_vector.astype(np.float32)


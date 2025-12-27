"""
Embedding service for generating and managing embeddings.
"""

from typing import List, Dict, Any
import numpy as np
from loguru import logger

from domain.embeddings.product_embeddings import get_product_embedding_model
from adapters.factory import get_vector_store


class EmbeddingService:
    """Service for managing product embeddings."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EmbeddingService, cls).__new__(cls)
            cls._instance.embedding_model = get_product_embedding_model()
            cls._instance.vector_store = get_vector_store()
            logger.info("Embedding Service initialized")
        return cls._instance

    def generate_product_embedding(self, product: Dict[str, Any]) -> np.ndarray:
        """Generate and store product embedding."""
        embedding = self.embedding_model.get_product_embedding(product)
        product_id = product.get("id") or product.get("product_id")

        if product_id:
            metadata = {
                "name": product.get("name"),
                "category": product.get("category"),
                "price": product.get("price"),
            }
            self.vector_store.store_product_embedding(
                product_id=str(product_id), embedding=embedding, metadata=metadata
            )

        return embedding

    def batch_generate_embeddings(
        self, products: List[Dict[str, Any]]
    ) -> List[np.ndarray]:
        """Generate embeddings for multiple products."""
        embeddings = []
        for product in products:
            emb = self.generate_product_embedding(product)
            embeddings.append(emb)
        return embeddings

    def get_text_embedding(self, text: str) -> np.ndarray:
        """Generate embedding for a text query."""
        return self.embedding_model.get_embedding(text)


def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()

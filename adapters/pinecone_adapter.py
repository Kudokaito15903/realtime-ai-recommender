"""
Pinecone adapter for vector storage and similarity search.
This replaces Redis vector search with Pinecone cloud service.
"""

import os
import time
import numpy as np
from typing import List, Dict, Any, Optional
from loguru import logger
from pinecone import Pinecone, ServerlessSpec

from .interfaces import VectorStoreInterface


class PineconeVectorStore(VectorStoreInterface):
    """Pinecone cloud vector store implementation"""

    def __init__(self, api_key: str, environment: str = "us-east-1-aws",
                 index_name: str = "product-recommendations", dimension: int = 384):
        self.api_key = api_key
        self.environment = environment
        self.index_name = index_name
        self.dimension = dimension

        # Initialize Pinecone client
        self.pc = Pinecone(api_key=api_key)

        # Create or connect to index
        self._ensure_index_exists()
        self.index = self.pc.Index(index_name)

        logger.info(f"Pinecone Vector Store initialized: {index_name} ({environment})")

    def _ensure_index_exists(self) -> None:
        """Ensure the Pinecone index exists, create if it doesn't"""
        try:
            # Check if index exists
            existing_indexes = [index.name for index in self.pc.list_indexes()]

            if self.index_name not in existing_indexes:
                logger.info(f"Creating Pinecone index: {self.index_name}")

                # Create index with serverless spec (free tier compatible)
                self.pc.create_index(
                    name=self.index_name,
                    dimension=self.dimension,
                    metric="cosine",
                    spec=ServerlessSpec(
                        cloud="aws",
                        region=self.environment
                    )
                )

                # Wait for index to be ready
                while not self.pc.describe_index(self.index_name).status['ready']:
                    logger.info("Waiting for index to be ready...")
                    time.sleep(1)

                logger.info(f"Created Pinecone index: {self.index_name}")
            else:
                logger.info(f"Pinecone index already exists: {self.index_name}")

        except Exception as e:
            logger.error(f"Error creating Pinecone index: {e}")
            raise

    def store_product_embedding(self, product_id: str, embedding: np.ndarray,
                               metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Store a product embedding in Pinecone"""
        try:
            # Prepare the vector data
            vector_data = {
                "id": product_id,
                "values": embedding.tolist(),
                "metadata": metadata or {}
            }

            # Add timestamp to metadata
            vector_data["metadata"]["updated_at"] = time.time()

            # Upsert to Pinecone (insert or update)
            self.index.upsert(vectors=[vector_data])

            logger.debug(f"Stored embedding for product {product_id} in Pinecone")
            return True

        except Exception as e:
            logger.error(f"Error storing embedding for product {product_id}: {e}")
            return False

    def find_similar_products(self, embedding: np.ndarray,
                             limit: int = 10,
                             min_score: float = 0.75) -> List[Dict[str, Any]]:
        """Find similar products using Pinecone similarity search"""
        try:
            # Query Pinecone for similar vectors
            query_result = self.index.query(
                vector=embedding.tolist(),
                top_k=limit,
                include_metadata=True,
                include_values=False
            )

            # Process results
            similar_products = []
            for match in query_result['matches']:
                # Pinecone returns similarity scores (higher = more similar)
                similarity_score = match['score']

                # Only include results above threshold
                if similarity_score >= min_score:
                    similar_products.append({
                        'product_id': match['id'],
                        'similarity_score': similarity_score,
                        'metadata': match.get('metadata', {}),
                        'embedding_updated_at': match.get('metadata', {}).get('updated_at')
                    })

            logger.debug(f"Found {len(similar_products)} similar products in Pinecone")
            return similar_products

        except Exception as e:
            logger.error(f"Error searching for similar products: {e}")
            return []

    def get_product_embedding(self, product_id: str) -> Optional[np.ndarray]:
        """Retrieve a product embedding from Pinecone"""
        try:
            # Fetch vector by ID (updated API for pinecone v7+)
            fetch_result = self.index.fetch(ids=[product_id])

            # Check if we have vectors in the response
            if hasattr(fetch_result, 'vectors') and fetch_result.vectors:
                if product_id in fetch_result.vectors:
                    vector_data = fetch_result.vectors[product_id]
                    if hasattr(vector_data, 'values') and vector_data.values:
                        embedding = np.array(vector_data.values, dtype=np.float32)
                        return embedding

            # Alternative: check if it's a dict-like response
            elif isinstance(fetch_result, dict) and 'vectors' in fetch_result:
                if product_id in fetch_result['vectors']:
                    vector_data = fetch_result['vectors'][product_id]
                    if 'values' in vector_data:
                        embedding = np.array(vector_data['values'], dtype=np.float32)
                        return embedding

            return None

        except Exception as e:
            logger.error(f"Error retrieving embedding for product {product_id}: {e}")
            return None

    def delete_product_embedding(self, product_id: str) -> bool:
        """Delete a product embedding from Pinecone"""
        try:
            self.index.delete(ids=[product_id])
            logger.debug(f"Deleted embedding for product {product_id} from Pinecone")
            return True

        except Exception as e:
            logger.error(f"Error deleting embedding for product {product_id}: {e}")
            return False

    def get_index_stats(self) -> Dict[str, Any]:
        """Get statistics about the Pinecone index"""
        try:
            stats = self.index.describe_index_stats()
            return {
                'total_vector_count': stats.get('total_vector_count', 0),
                'dimension': stats.get('dimension', 0),
                'index_fullness': stats.get('index_fullness', 0),
                'namespaces': stats.get('namespaces', {})
            }
        except Exception as e:
            logger.error(f"Error getting index stats: {e}")
            return {}


def get_pinecone_vector_store() -> PineconeVectorStore:
    """Factory function to create Pinecone vector store with config from environment"""
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise ValueError("PINECONE_API_KEY environment variable is required")

    environment = os.getenv("PINECONE_ENVIRONMENT", "us-east-1-aws")
    index_name = os.getenv("PINECONE_INDEX_NAME", "product-recommendations")
    dimension = int(os.getenv("VECTOR_DIMENSION", "384"))

    return PineconeVectorStore(
        api_key=api_key,
        environment=environment,
        index_name=index_name,
        dimension=dimension
    )
"""
Elasticsearch adapter for vector storage and similarity search.
"""

import os
import time
import numpy as np
from typing import List, Dict, Any, Optional
from loguru import logger
from elasticsearch import Elasticsearch, NotFoundError

from adapters.interfaces import VectorStoreInterface


class ElasticsearchVectorStore(VectorStoreInterface):
    """Elasticsearch vector store implementation"""

    def __init__(
        self,
        url: str,
        api_key: Optional[str] = None,
        index_name: str = "product-recommendations",
        dimension: int = 384,
    ):
        self.url = url
        self.index_name = index_name
        self.dimension = dimension
        
        # Initialize Elasticsearch client
        if api_key:
            self.es = Elasticsearch(url, api_key=api_key)
        else:
            self.es = Elasticsearch(url)

        # Create or connect to index
        self._ensure_index_exists()

        logger.info(f"Elasticsearch Vector Store initialized: {index_name} ({url})")

    def _ensure_index_exists(self) -> None:
        """Ensure the Elasticsearch index exists, create if it doesn't"""
        try:
            if not self.es.indices.exists(index=self.index_name):
                logger.info(f"Creating Elasticsearch index: {self.index_name}")

                # Define index mapping
                mapping = {
                    "mappings": {
                        "properties": {
                            "embedding": {
                                "type": "dense_vector",
                                "dims": self.dimension,
                                "index": True,
                                "similarity": "cosine"
                            },
                            "metadata": {
                                "type": "object",
                                "dynamic": True
                            },
                            "updated_at": {
                                "type": "date"
                            }
                        }
                    }
                }

                self.es.indices.create(index=self.index_name, body=mapping)
                logger.info(f"Created Elasticsearch index: {self.index_name}")
            else:
                logger.info(f"Elasticsearch index already exists: {self.index_name}")

        except Exception as e:
            logger.error(f"Error creating Elasticsearch index: {e}")
            raise

    def store_product_embedding(
        self,
        product_id: str,
        embedding: np.ndarray,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Store a product embedding in Elasticsearch"""
        try:
            # Prepare the document
            doc = {
                "embedding": embedding.tolist(),
                "metadata": metadata or {},
                "updated_at": int(time.time() * 1000)  # ES uses milliseconds for epoch_millis or just store as number
            }

            # Index the document
            self.es.index(index=self.index_name, id=product_id, document=doc)

            logger.debug(f"Stored embedding for product {product_id} in Elasticsearch")
            return True

        except Exception as e:
            logger.error(f"Error storing embedding for product {product_id}: {e}")
            return False

    def find_similar_products(
        self, embedding: np.ndarray, limit: int = 10, min_score: float = 0.75
    ) -> List[Dict[str, Any]]:
        """Find similar products using Elasticsearch k-NN search"""
        try:
            # Construct k-NN query
            query = {
                "knn": {
                    "field": "embedding",
                    "query_vector": embedding.tolist(),
                    "k": limit,
                    "num_candidates": 100
                },
                "_source": ["metadata", "updated_at"]
            }

            response = self.es.search(index=self.index_name, body=query)

            # Process results
            similar_products = []
            for hit in response["hits"]["hits"]:
                similarity_score = hit["_score"]

                # Note: ES cosine similarity is usually (1 + cosine) / 2 or similar depending on version, 
                # but "similarity": "cosine" in mapping usually returns range [0, 1] if vectors are normalized?
                # Actually in ES 8.x cosine similarity returns score in range [0, 1] for dense_vector.
                
                # Double check score normalization if needed, but assuming user provided threshold works for 0-1 range.
                if similarity_score >= min_score:
                    similar_products.append(
                        {
                            "product_id": hit["_id"],
                            "similarity_score": similarity_score,
                            "metadata": hit["_source"].get("metadata", {}),
                            "embedding_updated_at": hit["_source"].get("updated_at"),
                        }
                    )

            logger.debug(f"Found {len(similar_products)} similar products in Elasticsearch")
            return similar_products

        except Exception as e:
            logger.error(f"Error searching for similar products: {e}")
            return []

    def get_product_embedding(self, product_id: str) -> Optional[np.ndarray]:
        """Retrieve a product embedding from Elasticsearch"""
        try:
            response = self.es.get(index=self.index_name, id=product_id)
            if response["found"]:
                embedding_list = response["_source"].get("embedding")
                if embedding_list:
                    return np.array(embedding_list, dtype=np.float32)
            
            return None

        except NotFoundError:
            return None
        except Exception as e:
            logger.error(f"Error retrieving embedding for product {product_id}: {e}")
            return None

    def delete_product_embedding(self, product_id: str) -> bool:
        """Delete a product embedding from Elasticsearch"""
        try:
            self.es.delete(index=self.index_name, id=product_id)
            logger.debug(f"Deleted embedding for product {product_id} from Elasticsearch")
            return True

        except NotFoundError:
            logger.warning(f"Product {product_id} not found for deletion")
            return False
        except Exception as e:
            logger.error(f"Error deleting embedding for product {product_id}: {e}")
            return False

    def get_index_stats(self) -> Dict[str, Any]:
        """Get statistics about the Elasticsearch index"""
        try:
            stats = self.es.indices.stats(index=self.index_name)
            index_stats = stats["indices"][self.index_name]
            return {
                "total_vector_count": index_stats["total"]["docs"]["count"],
                "dimension": self.dimension,
                "index_size_bytes": index_stats["total"]["store"]["size_in_bytes"],
            }
        except Exception as e:
            logger.error(f"Error getting index stats: {e}")
            return {}


def get_elasticsearch_vector_store() -> ElasticsearchVectorStore:
    """Factory function to create Elasticsearch vector store with config from environment"""
    url = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
    api_key = os.getenv("ELASTICSEARCH_API_KEY")
    index_name = os.getenv("ELASTICSEARCH_INDEX_NAME", "product-recommendations")
    dimension = int(os.getenv("VECTOR_DIMENSION", "384"))

    return ElasticsearchVectorStore(
        url=url,
        api_key=api_key,
        index_name=index_name,
        dimension=dimension,
    )

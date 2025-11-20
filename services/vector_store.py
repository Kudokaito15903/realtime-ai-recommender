import os
import json
import numpy as np
import redis
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
import time
from loguru import logger

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_DB,
    VECTOR_DIMENSION, VECTOR_INDEX_NAME, SIMILARITY_THRESHOLD
)


class RedisVectorStore:
    """Vector store implementation using Redis for real-time similarity search"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisVectorStore, cls).__new__(cls)
            
            # Initialize Redis client
            cls._instance.redis = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                password=REDIS_PASSWORD,
                db=REDIS_DB,
                decode_responses=False  # We need binary responses for vectors
            )
            
            # Initialize properties
            cls._instance._ensure_vector_index()
            
            logger.info(f"Redis Vector Store initialized: {REDIS_HOST}:{REDIS_PORT}")
        return cls._instance
    
    def _ensure_vector_index(self) -> None:
        """Ensure the vector index exists in Redis"""
        try:
            # Check if index exists
            indices = self.redis.execute_command("FT._LIST")
            if indices and VECTOR_INDEX_NAME.encode() in indices:
                logger.info(f"Vector index {VECTOR_INDEX_NAME} already exists")
                return
            
            # Create the index with HNSW algorithm for approximate nearest neighbors
            self.redis.execute_command(
                "FT.CREATE", VECTOR_INDEX_NAME, "ON", "HASH", "PREFIX", 1, "product:embedding:", 
                "SCHEMA", "vector", "VECTOR", "HNSW", 6, "TYPE", "FLOAT32", 
                "DIM", VECTOR_DIMENSION, "DISTANCE_METRIC", "COSINE"
            )
            logger.info(f"Created vector index {VECTOR_INDEX_NAME}")
        except redis.exceptions.ResponseError as e:
            if "Index already exists" in str(e):
                logger.info(f"Vector index {VECTOR_INDEX_NAME} already exists")
            else:
                logger.error(f"Error creating vector index: {e}")
                raise
    
    def store_product_embedding(self, product_id: str, embedding: np.ndarray, 
                               metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Store a product embedding in Redis"""
        # Prepare the embedding as binary data
        vector_bytes = embedding.astype(np.float32).tobytes()
        
        # Base data to store
        data = {
            'vector': vector_bytes,
            'updated_at': datetime.utcnow().isoformat()
        }
        
        # Add any additional metadata
        if metadata:
            # Convert all metadata values to strings for Redis compatibility
            for k, v in metadata.items():
                if isinstance(v, (dict, list)):
                    data[k] = json.dumps(v)
                else:
                    data[k] = str(v)
        
        # Store in Redis
        try:
            self.redis.hset(f"product:embedding:{product_id}", mapping=data)
            logger.debug(f"Stored embedding for product {product_id}")
            return True
        except Exception as e:
            logger.error(f"Error storing embedding for product {product_id}: {e}")
            return False
    
    def find_similar_products(self, embedding: np.ndarray, 
                             limit: int = 10, 
                             min_score: float = SIMILARITY_THRESHOLD) -> List[Dict[str, Any]]:
        """Find similar products using vector similarity search"""
        # Prepare the query embedding
        query_vector = embedding.astype(np.float32).tobytes()
        
        start_time = time.time()
        try:
            # Perform the vector search
            results = self.redis.execute_command(
                "FT.SEARCH", VECTOR_INDEX_NAME,
                f"*=>[KNN {limit} @vector $query_vector AS score]",
                "PARAMS", 2, "query_vector", query_vector,
                "SORTBY", "score", "RETURN", 4, "id", "score", "category", "updated_at"
            )
            
            # Process results
            similar_products = []
            if results and isinstance(results, list) and len(results) > 1:
                # Skip the first element (count)
                for i in range(1, len(results), 2):
                    product_key = results[i].decode('utf-8')  # Key like 'product:embedding:123'
                    product_id = product_key.split(':')[-1]  # Extract ID
                    
                    # Extract properties
                    properties = results[i + 1]
                    similarity_score = None
                    category = None
                    updated_at = None
                    
                    # Process properties to extract values
                    for j in range(0, len(properties), 2):
                        if j+1 < len(properties):
                            prop_name = properties[j].decode('utf-8')
                            if prop_name == 'score':
                                # Convert similarity score (1 is best, 0 is worst)
                                similarity_score = float(properties[j+1])
                            elif prop_name == 'category':
                                category = properties[j+1].decode('utf-8')
                            elif prop_name == 'updated_at':
                                updated_at = properties[j+1].decode('utf-8')
                    
                    # Only include results above threshold
                    if similarity_score is not None and similarity_score >= min_score:
                        similar_products.append({
                            'product_id': product_id,
                            'similarity_score': similarity_score,
                            'category': category,
                            'embedding_updated_at': updated_at
                        })
            
            logger.debug(f"Similar product search completed in {time.time() - start_time:.4f} seconds")
            return similar_products
        except Exception as e:
            logger.error(f"Error searching for similar products: {e}")
            return []
    
    def get_product_embedding(self, product_id: str) -> Optional[np.ndarray]:
        """Retrieve a product embedding from Redis"""
        try:
            # Get the vector bytes
            vector_bytes = self.redis.hget(f"product:embedding:{product_id}", 'vector')
            if not vector_bytes:
                return None
            
            # Convert bytes back to numpy array
            vector = np.frombuffer(vector_bytes, dtype=np.float32)
            return vector
        except Exception as e:
            logger.error(f"Error retrieving embedding for product {product_id}: {e}")
            return None
    
    def delete_product_embedding(self, product_id: str) -> bool:
        """Delete a product embedding from Redis"""
        try:
            self.redis.delete(f"product:embedding:{product_id}")
            logger.debug(f"Deleted embedding for product {product_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting embedding for product {product_id}: {e}")
            return False


# Convenience function to get the singleton instance
def get_vector_store() -> RedisVectorStore:
    return RedisVectorStore()
import os
import json
import numpy as np
import redis
from typing import List, Dict, Any, Optional
from datetime import datetime
from loguru import logger

from config import (
    REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_DB,
    PRODUCT_STREAM_KEY, PRODUCT_STREAM_GROUP, PRODUCT_STREAM_CONSUMER
)

VECTOR_INDEX_NAME = "product:vectors"
VECTOR_PREFIX = "product:embedding:"
VECTOR_DIMENSION = 384   # PHẢI TRÙNG FT.INFO
DISTANCE_METRIC = "COSINE"


# =========================
# REDIS VECTOR STORE
# =========================
class RedisVectorStore:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)

            cls._instance.redis = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                password=REDIS_PASSWORD,
                db=REDIS_DB,
                decode_responses=False,  # BẮT BUỘC cho vector
            )

            cls._instance._ensure_index()
            logger.info("RedisVectorStore initialized")

        return cls._instance

    # =========================
    # INDEX
    # =========================
    def _ensure_index(self):
        try:
            indices = self.redis.execute_command("FT._LIST")
            if VECTOR_INDEX_NAME.encode() in indices:
                logger.info(f"Index {VECTOR_INDEX_NAME} already exists")
                return

            logger.info(f"Creating index {VECTOR_INDEX_NAME}")

            self.redis.execute_command(
                "FT.CREATE", VECTOR_INDEX_NAME,
                "ON", "HASH",
                "PREFIX", 1, VECTOR_PREFIX,
                "SCHEMA",
                "vector", "VECTOR", "HNSW", 6,
                "TYPE", "FLOAT32",
                "DIM", VECTOR_DIMENSION,
                "DISTANCE_METRIC", DISTANCE_METRIC,
                "M", 16,
                "EF_CONSTRUCTION", 200
            )

            logger.success(f"Index {VECTOR_INDEX_NAME} created")

        except redis.exceptions.ResponseError as e:
            if "Index already exists" in str(e):
                pass
            else:
                raise

    # =========================
    # STORE
    # =========================
    def store_embedding(
        self,
        product_id: int,
        embedding: np.ndarray,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:

        assert embedding.shape[0] == VECTOR_DIMENSION, \
            f"Embedding dim mismatch: {embedding.shape[0]} != {VECTOR_DIMENSION}"

        key = f"{VECTOR_PREFIX}{product_id}"

        data = {
            "vector": embedding.astype(np.float32).tobytes(),
            "updated_at": datetime.utcnow().isoformat()
        }

        if metadata:
            for k, v in metadata.items():
                data[k] = json.dumps(v) if isinstance(v, (dict, list)) else str(v)

        self.redis.hset(key, mapping=data)

    # =========================
    # GET VECTOR
    # =========================
    def get_embedding(self, product_id: int) -> Optional[np.ndarray]:
        key = f"{VECTOR_PREFIX}{product_id}"
        raw = self.redis.hget(key, "vector")
        if raw is None:
            return None
        return np.frombuffer(raw, dtype=np.float32)

    # =========================
    # KNN SEARCH BY VECTOR
    # =========================
    def knn_search(
        self,
        query_vector: np.ndarray,
        k: int = 5,
        min_similarity: float = 0.0
    ) -> List[Dict[str, Any]]:

        query_blob = query_vector.astype(np.float32).tobytes()

        results = self.redis.execute_command(
            "FT.SEARCH", VECTOR_INDEX_NAME,
            f"*=>[KNN {k} @vector $vec AS score]",
            "PARAMS", 2, "vec", query_blob,
            "SORTBY", "score",
            "RETURN", 3, "score", "updated_at", "category",
            "DIALECT", 2
        )

        return self._parse_results(results, min_similarity)

    # =========================
    # KNN SEARCH BY PRODUCT ID
    # =========================
    def find_similar_products(
        self,
        product_id: int,
        k: int = 5,
        min_similarity: float = 0.7
    ) -> List[Dict[str, Any]]:

        vector = self.get_embedding(product_id)
        if vector is None:
            logger.warning(f"Product {product_id} has no embedding")
            return []

        # +1 để loại chính nó
        results = self.knn_search(vector, k + 1, min_similarity)

        return [
            r for r in results
            if r["product_id"] != str(product_id)
        ]

    # =========================
    # RESULT PARSER
    # =========================
    def _parse_results(self, results, min_similarity):
        items = []

        for i in range(1, len(results), 2):
            key = results[i].decode()
            props = results[i + 1]

            score = None
            meta = {}

            for j in range(0, len(props), 2):
                field = props[j].decode()
                value = props[j + 1]

                if field == "score":
                    score = float(value)
                else:
                    meta[field] = value.decode()

            similarity = 1 - score

            if similarity >= min_similarity:
                items.append({
                    "product_id": key.split(":")[-1],
                    "distance": score,
                    "similarity": similarity,
                    **meta
                })

        return items


# =========================
# DEMO
# =========================
if __name__ == "__main__":
    store = RedisVectorStore()
    vec = store.get_embedding(31)
    print("Vector exists:", vec is not None)
    print("Vector shape:", vec.shape if vec is not None else None)
    similar = store.find_similar_products(
        product_id=31,
        k=5,
        min_similarity=0.3
    )

    for item in similar:
        print(item)
       
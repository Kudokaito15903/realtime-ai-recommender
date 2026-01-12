import os
import sys
import numpy as np
from loguru import logger

# Add project root to path
sys.path.append(os.getcwd())

from adapters.vector_store.elasticsearch_adapter import get_elasticsearch_vector_store
import config

def verify_elasticsearch():
    """Verify Elasticsearch vector store implementation"""
    logger.info("Verifying Elasticsearch Vector Store...")
    
    # Force enable debug logging
    logger.add(sys.stderr, level="DEBUG")

    # Override config for testing if needed
    if not os.getenv("ELASTICSEARCH_URL"):
        logger.warning("ELASTICSEARCH_URL not set, using default http://localhost:9200")
    
    try:
        # 1. Initialize
        store = get_elasticsearch_vector_store()
        logger.info("Successfully initialized store")

        # 2. Store Embedding
        product_id = "test-product-001"
        embedding = np.random.rand(384).astype(np.float32)
        metadata = {"name": "Test Product", "category": "electronics"}
        
        logger.info(f"Storing embedding for {product_id}...")
        success = store.store_product_embedding(product_id, embedding, metadata)
        
        if success:
            logger.success("✅ Stored embedding successfully")
        else:
            logger.error("❌ Failed to store embedding (check ES logs)")
            return

        # 3. Retrieve Embedding
        logger.info(f"Retrieving embedding for {product_id}...")
        retrieved_emb = store.get_product_embedding(product_id)
        
        if retrieved_emb is not None and len(retrieved_emb) == 384:
            logger.success("✅ Retrieved embedding successfully")
        else:
            logger.error("❌ Failed to retrieve embedding or wrong dimension")

        # 4. Search Similar
        logger.info("Searching for similar products...")
        results = store.find_similar_products(embedding, limit=5)
        
        if len(results) > 0:
            logger.success(f"✅ Found {len(results)} similar products")
            logger.info(f"Top match: {results[0]['product_id']} (score: {results[0]['similarity_score']})")
        else:
            logger.warning("⚠️ No similar products found (might be due to immediate search before refresh interval)")

        # 5. Delete
        logger.info(f"Deleting {product_id}...")
        del_success = store.delete_product_embedding(product_id)
        
        if del_success:
            logger.success("✅ Deleted embedding successfully")
        else:
            logger.error("❌ Failed to delete embedding")

    except Exception as e:
        logger.error(f"❌ Verification failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_elasticsearch()

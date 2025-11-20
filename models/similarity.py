 
import os
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
import time
from loguru import logger

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.embeddings import get_embedding_model
from services.vector_store import get_vector_store


class SimilaritySearch:
    """Service for finding similar products by various methods"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SimilaritySearch, cls).__new__(cls)
            
            # Initialize services
            cls._instance.vector_store = get_vector_store()
            cls._instance.embedding_model = get_embedding_model()
            
            logger.info("Similarity Search service initialized")
        return cls._instance
    
    def search_by_product_id(self, product_id: str, 
                           limit: int = 10, 
                           threshold: float = 0.7) -> List[Dict[str, Any]]:
        """Find similar products to the given product ID"""
        start_time = time.time()
        
        # Get the product embedding
        embedding = self.vector_store.get_product_embedding(product_id)
        if embedding is None:
            logger.warning(f"No embedding found for product {product_id}")
            return []
        
        # Find similar products
        similar_products = self.vector_store.find_similar_products(
            embedding=embedding,
            limit=limit + 1,  # Add 1 to account for the product itself
            min_score=threshold
        )
        
        # Filter out the product itself
        results = [
            p for p in similar_products if p['product_id'] != product_id
        ][:limit]
        
        logger.info(f"Found {len(results)} similar products in {time.time() - start_time:.4f}s")
        return results
    
    def search_by_text(self, query_text: str, 
                     limit: int = 10, 
                     threshold: float = 0.6,
                     categories: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Find products similar to the given text query"""
        start_time = time.time()
        
        # Generate embedding for the query text
        query_embedding = self.embedding_model.get_embedding(query_text)
        
        # Find similar products
        similar_products = self.vector_store.find_similar_products(
            embedding=query_embedding,
            limit=limit * 2,  # Get more results for filtering
            min_score=threshold
        )
        
        # Filter by categories if specified
        if categories and len(categories) > 0:
            filtered_results = [
                p for p in similar_products 
                if p.get('category') in categories
            ]
            results = filtered_results[:limit]
        else:
            results = similar_products[:limit]
        
        logger.info(f"Found {len(results)} products for text query in {time.time() - start_time:.4f}s")
        return results
    
    def search_by_product_attributes(self, attributes: Dict[str, Any], 
                                   limit: int = 10, 
                                   threshold: float = 0.65) -> List[Dict[str, Any]]:
        """Find products similar to the given attributes"""
        # Convert attributes to a descriptive text for embedding
        attr_text = " ".join([f"{k}: {v}" for k, v in attributes.items() if v])
        
        if not attr_text:
            logger.warning("No valid attributes provided for search")
            return []
        
        # Use text search with the attribute string
        return self.search_by_text(attr_text, limit, threshold)
    
    def hybrid_search(self, 
                    query_text: str, 
                    price_range: Optional[Tuple[float, float]] = None,
                    categories: Optional[List[str]] = None,
                    limit: int = 10) -> List[Dict[str, Any]]:
        """Perform a hybrid search combining semantic similarity with filters"""
        # First get semantic matches
        results = self.search_by_text(
            query_text=query_text,
            limit=limit * 3,  # Get more results for filtering
            threshold=0.6,
            categories=categories
        )
        
        # Apply price filter if specified
        if price_range and len(price_range) == 2:
            min_price, max_price = price_range
            
            # Filter results by price range
            filtered_results = []
            for product in results:
                try:
                    price = float(product.get('price', 0))
                    if min_price <= price <= max_price:
                        filtered_results.append(product)
                except (ValueError, TypeError):
                    # Skip products with invalid price
                    continue
            
            results = filtered_results
        
        # Return top results after all filters
        return results[:limit]


# Convenience function to get the singleton instance
def get_similarity_search() -> SimilaritySearch:
    return SimilaritySearch()
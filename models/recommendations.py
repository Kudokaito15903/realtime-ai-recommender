 
import os
import numpy as np
from typing import List, Dict, Any, Optional
from datetime import datetime
import time
from loguru import logger
import redis
import json

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_DB, 
    SIMILARITY_THRESHOLD
)
from services.vector_store import get_vector_store
from models.embeddings import get_embedding_model


class ProductRecommender:
    """Service for generating real-time product recommendations"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProductRecommender, cls).__new__(cls)
            
            # Initialize services
            cls._instance.vector_store = get_vector_store()
            cls._instance.embedding_model = get_embedding_model()
            
            # Initialize Redis client for additional data
            cls._instance.redis = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                password=REDIS_PASSWORD,
                db=REDIS_DB,
                decode_responses=True
            )
            
            logger.info("Product Recommender service initialized")
        return cls._instance
    
    def get_similar_products(self, product_id: str, limit: int = 6) -> List[Dict[str, Any]]:
        """Get similar products based on vector similarity"""
        start_time = time.time()
        
        # Get the product embedding
        embedding = self.vector_store.get_product_embedding(product_id)
        if embedding is None:
            logger.warning(f"No embedding found for product {product_id}")
            return []
        
        # Find similar products
        similar_products = self.vector_store.find_similar_products(
            embedding=embedding,
            limit=limit + 1,  # Add one to account for the product itself
            min_score=SIMILARITY_THRESHOLD
        )
        
        # Filter out the product itself
        filtered_results = [
            {
                'product_id': p['product_id'],
                'score': p['similarity_score'],
                'recommendation_type': 'similar'
            }
            for p in similar_products
            if p['product_id'] != product_id
        ][:limit]
        
        logger.debug(f"Found {len(filtered_results)} similar products in {time.time() - start_time:.4f}s")
        return filtered_results
    
    def get_similar_products_by_text(self, query_text: str, limit: int = 6) -> List[Dict[str, Any]]:
        """Get similar products based on a text query"""
        start_time = time.time()
        
        # Generate embedding for the query text
        query_embedding = self.embedding_model.get_embedding(query_text)
        
        # Find similar products
        similar_products = self.vector_store.find_similar_products(
            embedding=query_embedding,
            limit=limit,
            min_score=SIMILARITY_THRESHOLD * 0.8  # Slightly lower threshold for text queries
        )
        
        results = [
            {
                'product_id': p['product_id'],
                'score': p['similarity_score'],
                'recommendation_type': 'search'
            }
            for p in similar_products
        ][:limit]
        
        logger.debug(f"Found {len(results)} products for text query in {time.time() - start_time:.4f}s")
        return results
    
    def get_popular_in_category(self, category: str, limit: int = 6) -> List[Dict[str, Any]]:
        """Get popular products in a category"""
        # In a real system, this would use real-time popularity metrics
        # For this example, we'll simulate with a simple category lookup
        
        # Using sorted set in Redis to track popular products by category
        redis_key = f"popular:category:{category}"
        
        # Get the top products from Redis
        popular_products = self.redis.zrevrange(
            redis_key, 
            0, limit-1, 
            withscores=True
        )
        
        if not popular_products:
            logger.debug(f"No popular products found for category: {category}")
            return []
        
        results = [
            {
                'product_id': product_id,
                'score': float(score) / 100.0,  # Normalize score
                'recommendation_type': 'popular_in_category'
            }
            for product_id, score in popular_products
        ]
        
        logger.debug(f"Found {len(results)} popular products in category {category}")
        return results
    
    def get_personalized_recommendations(self, 
                                       user_id: str, 
                                       limit: int = 10) -> List[Dict[str, Any]]:
        """Get personalized recommendations for a user"""
        # In a real system, this would use user behavior and preferences
        # For this prototype, we'll use recently viewed products as a signal
        
        # Get recently viewed products from Redis
        redis_key = f"user:{user_id}:recently_viewed"
        recently_viewed = self.redis.lrange(redis_key, 0, 4)  # Last 5 viewed
        
        if not recently_viewed:
            logger.debug(f"No recently viewed products for user {user_id}")
            return []
        
        # Get similar products for each recently viewed item
        all_recommendations = []
        for product_id in recently_viewed:
            similar = self.get_similar_products(product_id, limit=3)
            all_recommendations.extend(similar)
        
        # Deduplicate by product_id and keep highest score
        seen_products = set()
        unique_recommendations = []
        
        for rec in sorted(all_recommendations, key=lambda x: x['score'], reverse=True):
            if rec['product_id'] not in seen_products:
                seen_products.add(rec['product_id'])
                unique_recommendations.append(rec)
        
        # Filter out products the user has already viewed
        filtered_recommendations = [
            rec for rec in unique_recommendations 
            if rec['product_id'] not in recently_viewed
        ]
        
        logger.debug(f"Generated {len(filtered_recommendations)} personalized recommendations for user {user_id}")
        return filtered_recommendations[:limit]
    
    def track_product_view(self, user_id: str, product_id: str) -> None:
        """Track that a user viewed a product for future recommendations"""
        if not user_id or not product_id:
            return
        
        # Add to recently viewed list
        redis_key = f"user:{user_id}:recently_viewed"
        
        pipe = self.redis.pipeline()
        # Add to the front of the list
        pipe.lpush(redis_key, product_id)
        # Trim to last 20 viewed
        pipe.ltrim(redis_key, 0, 19)
        # Set expiration (30 days)
        pipe.expire(redis_key, 60*60*24*30)
        
        # Increment category popularity counter
        try:
            # Get product category
            category = self.redis.hget(f"product:{product_id}", "category")
            if category:
                # Increment score in sorted set
                pipe.zincrby(f"popular:category:{category}", 1, product_id)
        except Exception as e:
            logger.error(f"Error updating category popularity: {e}")
        
        # Execute all commands
        pipe.execute()
        
        logger.debug(f"Tracked product view: user={user_id}, product={product_id}")


# Convenience function to get the singleton instance
def get_product_recommender() -> ProductRecommender:
    return ProductRecommender()
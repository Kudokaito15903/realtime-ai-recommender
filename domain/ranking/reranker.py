"""
Reranker - Domain Layer
Core reranking logic for recommendation results.
"""

import numpy as np
from typing import List, Dict, Any, Optional
from loguru import logger


def calculate_rerank_score(
    product: Dict[str, Any],
    similarity_score: float,
    weights: Optional[Dict[str, float]] = None
) -> float:
    """
    Calculate rerank score for a product.
    
    Args:
        product: Product data with metadata
        similarity_score: Base similarity score
        weights: Optional weights for different factors
        
    Returns:
        Final rerank score
    """
    if weights is None:
        weights = {
            "similarity": 0.6,
            "popularity": 0.2,
            "rating": 0.15,
            "recency": 0.05,
        }
    
    # Extract features
    similarity = similarity_score
    popularity = float(product.get("sold", 0) or 0)
    rating = float(product.get("avgRating", 0) or 0)
    recency = float(product.get("recency_score", 1.0) or 1.0)
    
    # Normalize features
    popularity_norm = min(np.log1p(popularity) / 10.0, 1.0)
    rating_norm = min(rating / 5.0, 1.0)
    
    # Calculate weighted score
    score = (
        weights["similarity"] * similarity +
        weights["popularity"] * popularity_norm +
        weights["rating"] * rating_norm +
        weights["recency"] * recency
    )
    
    return float(score)


def rerank_products(
    products: List[Dict[str, Any]],
    weights: Optional[Dict[str, float]] = None,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Rerank a list of products based on multiple factors.
    
    Args:
        products: List of products with similarity scores
        weights: Optional weights for reranking factors
        limit: Optional limit for results
        
    Returns:
        Reranked list of products
    """
    if not products:
        return []
    
    # Calculate rerank scores
    reranked = []
    for product in products:
        similarity_score = float(product.get("similarity_score", product.get("score", 0.0)))
        rerank_score = calculate_rerank_score(product, similarity_score, weights)
        
        reranked.append({
            **product,
            "rerank_score": rerank_score,
            "original_score": similarity_score,
        })
    
    # Sort by rerank score
    reranked.sort(key=lambda x: x["rerank_score"], reverse=True)
    
    if limit:
        reranked = reranked[:limit]
    
    return reranked


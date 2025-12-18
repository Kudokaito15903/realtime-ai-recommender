import os
import sys
import time
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Path, Depends, Header
from pydantic import BaseModel
from loguru import logger

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from data.schemas import RecommendationResponse
from models.recommendations import get_product_recommender


# Initialize router
router = APIRouter()

# Initialize service
product_recommender = get_product_recommender()

@router.get("/{product_id}/similar", response_model=RecommendationResponse)
async def get_product_recommendations(
    product_id: str = Path(..., description="The ID of the product to get recommendations for"),
    limit: int = Query(6, description="Maximum number of recommendations to return"),
    user_id: Optional[str] = Header(None, description="User ID for personalization")
):
    """Get recommendations similar to a specific product"""
    try:
        # Track product view for the user if user_id is provided
        if user_id:
            product_recommender.track_product_view(user_id, product_id)
        
        # Get similar product recommendations
        similar_products = product_recommender.get_similar_products(
            product_id=product_id,
            limit=limit
        )
        
        # Create response
        response = RecommendationResponse(
            recommendations=similar_products
        )
        
        return response
    
    except Exception as e:
        logger.error(f"Error getting similar product recommendations: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to get recommendations: {str(e)}"
        )


@router.get("/category/{category}", response_model=RecommendationResponse)
async def get_category_recommendations(
    category: str = Path(..., description="The category to get recommendations for"),
    limit: int = Query(10, description="Maximum number of recommendations to return")
):
    """Get popular products in a specific category"""
    try:
        # Get popular products in the category
        popular_products = product_recommender.get_popular_in_category(
            category=category,
            limit=limit
        )
        
        # Create response
        response = RecommendationResponse(
            recommendations=popular_products
        )
        
        return response
    
    except Exception as e:
        logger.error(f"Error getting category recommendations: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to get category recommendations: {str(e)}"
        )


@router.get("/personalized", response_model=RecommendationResponse)
async def get_personalized_recommendations(
    user_id: str = Header(..., description="User ID for personalization"),
    limit: int = Query(10, description="Maximum number of recommendations to return"),
    method: str = Query(
        "hybrid",
        description="Recommendation method: vector | als | session | hybrid",
    ),
    recent_k: int = Query(
        5,
        description="Number of recent interactions to use for session-based recommendations",
    ),
):
    """Get personalized recommendations for a specific user"""
    try:
        m = (method or "hybrid").strip().lower()
        if m == "vector":
            recommendations = product_recommender.get_personalized_recommendations(user_id=user_id, limit=limit)
        elif m == "als":
            recommendations = product_recommender.get_als_recommendations(user_id=user_id, limit=limit, train_if_missing=True)
        elif m == "session":
            recommendations = product_recommender.get_session_based_recommendations(user_id=user_id, limit=limit, recent_k=recent_k)
        elif m == "hybrid":
            recommendations = product_recommender.get_hybrid_recommendations(user_id=user_id, limit=limit)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown method: {method}")
        
        # Create response
        response = RecommendationResponse(
            recommendations=recommendations
        )
        
        return response
    
    except Exception as e:
        logger.error(f"Error getting personalized recommendations: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to get personalized recommendations: {str(e)}"
        )


@router.post("/track-view", response_model=Dict[str, Any])
async def track_product_view(
    product_id: str = Query(..., description="The ID of the product viewed"),
    user_id: str = Header(..., description="User ID for tracking")
):
    """Track that a user viewed a product (for recommendation engine)"""
    try:
        # Track the product view
        product_recommender.track_product_view(user_id, product_id)
        
        return {
            "status": "success",
            "message": "Product view tracked successfully",
            "product_id": product_id,
            "user_id": user_id,
            "timestamp": time.time()
        }
    
    except Exception as e:
        logger.error(f"Error tracking product view: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to track product view: {str(e)}"
        )


@router.get("/search", response_model=RecommendationResponse)
async def search_recommendations(
    query: str = Query(..., description="Text query to search for recommendations"),
    limit: int = Query(10, description="Maximum number of recommendations to return"),
    user_id: Optional[str] = Header(None, description="User ID for personalization")
):
    """Get recommendations based on a text search query"""
    try:
        # Get recommendations by text query
        recommendations = product_recommender.get_similar_products_by_text(
            query_text=query,
            limit=limit
        )
        
        # Create response
        response = RecommendationResponse(
            recommendations=recommendations
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error searching for recommendations: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to search for recommendations: {str(e)}"
        )
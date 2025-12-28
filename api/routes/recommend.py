"""
Recommendation API routes.
This module provides endpoints for product recommendations.
"""

import os
import sys
import time
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Path, Depends, Header
from pydantic import BaseModel
from loguru import logger

# Add project root to path
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from data.schemas import RecommendationResponse
from services.recommendation_service import get_recommendation_service
from services.variant_selector import get_variant_selector
from adapters.factory import get_user_behavior
from utils.ab_testing import ABVariant, assign_variant
from utils.metrics import log_recommendation_event


# Initialize router
router = APIRouter()

# Initialize service
product_recommender = get_recommendation_service()


@router.get("/{product_id}/similar", response_model=RecommendationResponse)
async def get_product_recommendations(
    product_id: str = Path(
        ..., description="The ID of the product to get recommendations for"
    ),
    limit: int = Query(6, description="Maximum number of recommendations to return"),
    user_id: Optional[str] = Header(None, description="User ID for personalization"),
):
    """Get recommendations similar to a specific product"""
    try:
        # Track product view for the user if user_id is provided
        if user_id:
            product_recommender.track_product_view(user_id, product_id)

        # Get similar product recommendations
        similar_products = product_recommender.get_similar_products(
            product_id=product_id, limit=limit
        )

        # Create response
        response = RecommendationResponse(recommendations=similar_products)

        return response

    except Exception as e:
        logger.error(f"Error getting similar product recommendations: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get recommendations: {str(e)}"
        )


@router.get("/category/{category}", response_model=RecommendationResponse)
async def get_category_recommendations(
    category: str = Path(..., description="The category to get recommendations for"),
    limit: int = Query(10, description="Maximum number of recommendations to return"),
):
    """Get popular products in a specific category"""
    try:
        # Get popular products in the category
        popular_products = product_recommender.get_popular_in_category(
            category=category, limit=limit
        )

        # Create response
        response = RecommendationResponse(recommendations=popular_products)

        return response

    except Exception as e:
        logger.error(f"Error getting category recommendations: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get category recommendations: {str(e)}"
        )


@router.get("/trending", response_model=RecommendationResponse)
async def get_trending_recommendations(
    limit: int = Query(10, description="Maximum number of recommendations to return"),
    category: Optional[str] = Query(
        None,
        description="Optional category filter. If omitted, returns global trending products.",
    ),
):
    """
    Get trending (popular) products.

    - If `category` is provided: popular products within that category.
    - If `category` is omitted: globally popular products.
    """
    try:
        popular_products = product_recommender.get_popular_in_category(
            category=category,
            limit=limit,
        )

        response = RecommendationResponse(recommendations=popular_products)
        return response
    except Exception as e:
        logger.error(f"Error getting trending recommendations: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get trending recommendations: {str(e)}",
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
    ab_experiment: Optional[str] = Header(
        None,
        description=(
            "Optional A/B experiment name. If provided, the backend will "
            "bucket the user into variants (e.g., different recommendation methods)."
        ),
    ),
):
    """Get personalized recommendations for a specific user"""
    start_time = time.time()
    variant = "control"

    try:
        # A/B testing: optionally override 'method' based on experiment & user bucket
        m = (method or "hybrid").strip().lower()
        if ab_experiment:
            experiments = {
                "rec_method": {
                    "A": ABVariant(name="A", traffic_share=0.5),
                    "B": ABVariant(name="B", traffic_share=0.5),
                }
            }
            assignment = assign_variant(user_id, experiments)
            variant = assignment.get("rec_method", "control")
            if variant == "A":
                m = "hybrid"
            elif variant == "B":
                # Example: compare ALS vs hybrid
                m = "als"

        if m == "vector":
            recommendations = product_recommender.get_personalized_recommendations(
                user_id=user_id, limit=limit
            )
        elif m == "als":
            recommendations = product_recommender.get_als_recommendations(
                user_id=user_id, limit=limit, train_if_missing=True
            )
        elif m == "session":
            recommendations = product_recommender.get_session_based_recommendations(
                user_id=user_id, limit=limit, recent_k=recent_k
            )
        elif m == "hybrid":
            recommendations = product_recommender.get_hybrid_recommendations(
                user_id=user_id, limit=limit
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unknown method: {method}")

        # Layer 2: Variant Selection (enrich with recommended variants)
        try:
            user_behavior = get_user_behavior()
            user_history = (
                user_behavior.get_user_history(user_id, limit=50) if user_id else None
            )

            variant_selector = get_variant_selector()
            recommendations = variant_selector.enrich_recommendations_with_variants(
                recommendations=recommendations,
                user_id=user_id,
                user_history=user_history,
            )
        except Exception as e:
            logger.warning(f"Failed to enrich recommendations with variants: {e}")
            # Continue without variant enrichment

        # Create response
        response = RecommendationResponse(recommendations=recommendations)

        # Metrics logging
        elapsed_ms = (time.time() - start_time) * 1000.0
        log_recommendation_event(
            event_type="personalized_recommendation",
            user_id=user_id,
            method=m,
            variant=variant,
            num_results=len(recommendations),
            latency_ms=elapsed_ms,
        )

        return response

    except Exception as e:
        logger.error(f"Error getting personalized recommendations: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get personalized recommendations: {str(e)}",
        )


@router.get("/personalized/recency-weighted", response_model=RecommendationResponse)
async def get_recency_weighted_recommendations(
    user_id: str = Header(..., description="User ID for personalization"),
    result_limit: int = Query(
        10, description="Maximum number of recommendations to return"
    ),
    top_k_interactions: int = Query(
        20,
        description="Number of most important recent interactions to build the user vector",
    ),
    search_limit: int = Query(
        40,
        description="Number of semantic candidates to retrieve before re-ranking",
    ),
):
    """
    Personalized recommendations dùng lịch sử tương tác + độ mới (recency-weighted semantic).

    - Dùng các tương tác gần đây nhất của user để build user embedding.
    - Tìm sản phẩm tương tự theo embedding và re-rank theo độ giống, bán chạy, rating, và gần giá mục tiêu.
    """
    start_time = time.time()

    if not user_id:
        raise HTTPException(status_code=400, detail="Missing user_id header")

    try:
        recommendations = product_recommender.get_recency_weighted_recommendations(
            user_id=user_id,
            top_k_interactions=top_k_interactions,
            search_limit=search_limit,
            result_limit=result_limit,
        )

        response = RecommendationResponse(recommendations=recommendations)

        # Optional: metric logging (reuse generic event type)
        try:
            elapsed_ms = (time.time() - start_time) * 1000.0
            log_recommendation_event(
                event_type="recency_weighted_recommendation",
                user_id=user_id,
                method="recency_weighted",
                variant="control",
                num_results=len(recommendations),
                latency_ms=elapsed_ms,
            )
        except Exception as e:
            logger.warning(
                f"Failed to log recency-weighted recommendation metrics: {e}"
            )

        return response
    except HTTPException:
        # Re-raise HTTPExceptions untouched
        raise
    except Exception as e:
        logger.error(f"Error getting recency-weighted recommendations: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get recency-weighted recommendations: {str(e)}",
        )


@router.post("/track-view", response_model=Dict[str, Any])
async def track_product_view(
    product_id: str = Query(..., description="The ID of the product viewed"),
    user_id: str = Header(..., description="User ID for tracking"),
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
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"Error tracking product view: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to track product view: {str(e)}"
        )


@router.post("/track-click", response_model=Dict[str, Any])
async def track_product_click(
    product_id: str = Query(..., description="The ID of the product clicked"),
    user_id: str = Header(..., description="User ID for tracking"),
):
    """Track that a user clicked a product"""
    try:
        product_recommender.track_product_click(user_id, product_id)

        return {
            "status": "success",
            "message": "Product click tracked successfully",
            "product_id": product_id,
            "user_id": user_id,
            "timestamp": time.time(),
        }
    except Exception as e:
        logger.error(f"Error tracking product click: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to track product click: {str(e)}",
        )


@router.post("/track-add-to-cart", response_model=Dict[str, Any])
async def track_add_to_cart(
    product_id: str = Query(..., description="The ID of the product added to cart"),
    variant_id: Optional[str] = Query(
        None, description="The SKU/variant ID (recommended for conversion tracking)"
    ),
    user_id: str = Header(..., description="User ID for tracking"),
):
    """Track that a user added a product to cart. variant_id recommended for conversion tracking"""
    try:
        user_behavior = get_user_behavior()
        user_behavior.track_add_to_cart(user_id, product_id, variant_id)

        return {
            "status": "success",
            "message": "Add-to-cart tracked successfully",
            "product_id": product_id,
            "variant_id": variant_id,
            "user_id": user_id,
            "timestamp": time.time(),
        }
    except Exception as e:
        logger.error(f"Error tracking add-to-cart: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to track add-to-cart: {str(e)}",
        )


@router.post("/track-purchase", response_model=Dict[str, Any])
async def track_purchase(
    product_id: str = Query(..., description="The ID of the product purchased"),
    variant_id: Optional[str] = Query(
        None, description="The SKU/variant ID (recommended for conversion tracking)"
    ),
    user_id: str = Header(..., description="User ID for tracking"),
):
    """Track that a user purchased a product. variant_id recommended for conversion tracking"""
    try:
        user_behavior = get_user_behavior()
        user_behavior.track_purchase(user_id, product_id, variant_id)

        return {
            "status": "success",
            "message": "Purchase tracked successfully",
            "product_id": product_id,
            "variant_id": variant_id,
            "user_id": user_id,
            "timestamp": time.time(),
        }
    except Exception as e:
        logger.error(f"Error tracking purchase: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to track purchase: {str(e)}",
        )


@router.get("/search", response_model=RecommendationResponse)
async def search_recommendations(
    query: str = Query(..., description="Text query to search for recommendations"),
    limit: int = Query(10, description="Maximum number of recommendations to return"),
    user_id: Optional[str] = Header(None, description="User ID for personalization"),
):
    """Get recommendations based on a text search query"""
    try:
        # Get recommendations by text query
        recommendations = product_recommender.get_similar_products_by_text(
            query_text=query, limit=limit
        )

        # Create response
        response = RecommendationResponse(recommendations=recommendations)

        return response

    except Exception as e:
        logger.error(f"Error searching for recommendations: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to search for recommendations: {str(e)}"
        )


@router.get("/models/als-info", response_model=Dict[str, Any])
async def get_als_model_info():
    """
    Return basic information about the current ALS model artifact,
    useful for monitoring and operations.
    """
    try:
        info = product_recommender.get_als_model_info()
        return info
    except Exception as e:
        logger.error(f"Error getting ALS model info: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get ALS model info: {str(e)}",
        )

"""
Hybrid recommender combining multiple recommendation strategies.
"""
from typing import List, Dict, Any
from loguru import logger


class HybridRecommender:
    """Combines session-based, ALS, and vector-based recommendations."""
    
    def __init__(self, recommendation_service):
        self.recommendation_service = recommendation_service
    
    def get_hybrid_recommendations(
        self, 
        user_id: str, 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Hybrid ranking: session + ALS (if available) + vector-based history as a fallback.
        """
        if not user_id:
            return []

        candidates: List[Dict[str, Any]] = []

        # Session-based (fast, no training)
        try:
            candidates.extend(
                self.recommendation_service.get_session_based_recommendations(
                    user_id=user_id, 
                    limit=max(limit, 20)
                )
            )
        except Exception as e:
            logger.warning(f"Session recommendations failed: {e}")

        # ALS (do NOT force-train here; use if already available)
        try:
            candidates.extend(
                self.recommendation_service.get_als_recommendations(
                    user_id=user_id, 
                    limit=max(limit, 20), 
                    train_if_missing=False
                )
            )
        except Exception as e:
            logger.warning(f"ALS recommendations failed: {e}")

        # Vector-history (existing)
        try:
            candidates.extend(
                self.recommendation_service.get_personalized_recommendations(
                    user_id=user_id, 
                    limit=max(limit, 20)
                )
            )
        except Exception as e:
            logger.warning(f"Vector-history recommendations failed: {e}")

        # Deduplicate and keep best score per product (within each method scale)
        best: Dict[str, Dict[str, Any]] = {}
        for rec in candidates:
            pid = rec.get("product_id")
            if not pid:
                continue
            prev = best.get(pid)
            if prev is None or float(rec.get("score", 0.0)) > float(prev.get("score", 0.0)):
                best[pid] = rec

        ranked = sorted(best.values(), key=lambda x: float(x.get("score", 0.0)), reverse=True)
        return ranked[:limit]


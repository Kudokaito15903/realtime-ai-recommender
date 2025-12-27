"""
Interaction Service - Application Layer
Handles user interaction tracking and retrieval.
"""

import os
import sys
from typing import List, Dict, Any, Optional
from loguru import logger

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.factory import get_user_behavior


class InteractionService:
    """Service for managing user interactions"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(InteractionService, cls).__new__(cls)
            cls._instance.user_behavior = get_user_behavior()
            logger.info("Interaction Service initialized")
        return cls._instance

    def track_view(self, user_id: str, product_id: str) -> None:
        """Track a product view interaction"""
        if not user_id or not product_id:
            return
        self.user_behavior.track_view(user_id, product_id)
        logger.debug(f"Tracked view: user={user_id}, product={product_id}")

    def track_click(self, user_id: str, product_id: str) -> None:
        """Track a product click interaction"""
        if not user_id or not product_id:
            return
        self.user_behavior.track_click(user_id, product_id)
        logger.debug(f"Tracked click: user={user_id}, product={product_id}")

    def track_add_to_cart(self, user_id: str, product_id: str) -> None:
        """Track an add-to-cart interaction"""
        if not user_id or not product_id:
            return
        self.user_behavior.track_add_to_cart(user_id, product_id)
        logger.debug(f"Tracked add-to-cart: user={user_id}, product={product_id}")

    def track_purchase(self, user_id: str, product_id: str) -> None:
        """Track a purchase interaction"""
        if not user_id or not product_id:
            return
        self.user_behavior.track_purchase(user_id, product_id)
        logger.debug(f"Tracked purchase: user={user_id}, product={product_id}")

    def get_user_history(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get user interaction history"""
        if not user_id:
            return []
        return self.user_behavior.get_user_history(user_id, limit=limit)

    def get_recent_interactions(
        self, limit: int = 100, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get recent interactions across all users"""
        if not hasattr(self.user_behavior, "get_recent_interactions"):
            logger.warning("Behavior store does not support get_recent_interactions")
            return []
        return self.user_behavior.get_recent_interactions(limit=limit, offset=offset)

    def get_interaction_counts(self, limit: int = 10000) -> List[Dict[str, Any]]:
        """Get interaction counts for ALS training"""
        if not hasattr(self.user_behavior, "get_interaction_counts"):
            logger.warning("Behavior store does not support get_interaction_counts")
            return []
        return self.user_behavior.get_interaction_counts(limit=limit)


# Singleton accessor
def get_interaction_service() -> InteractionService:
    """Get the singleton InteractionService instance"""
    return InteractionService()

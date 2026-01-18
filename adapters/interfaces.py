"""
Abstract interfaces for the modern stack adapters.
This allows easy switching between different backends (Redis, Cloud, etc.)
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable
import numpy as np


class ProductStoreError(Exception):
    """Base exception for product store errors"""

    pass


class VectorStoreInterface(ABC):
    """Abstract interface for vector storage and similarity search"""

    @abstractmethod
    def store_product_embedding(
        self,
        product_id: str,
        embedding: np.ndarray,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Store a product embedding with optional metadata"""
        pass

    @abstractmethod
    def find_similar_products(
        self, embedding: np.ndarray, limit: int = 10, min_score: float = 0.75
    ) -> List[Dict[str, Any]]:
        """Find similar products using vector similarity search"""
        pass

    @abstractmethod
    def get_product_embedding(self, product_id: str) -> Optional[np.ndarray]:
        """Retrieve a product embedding by ID"""
        pass

    @abstractmethod
    def delete_product_embedding(self, product_id: str) -> bool:
        """Delete a product embedding"""
        pass


class EventProcessorInterface(ABC):
    """Abstract interface for event streaming/processing"""

    @abstractmethod
    def publish_product_created(self, product_data: Dict[str, Any]) -> Optional[str]:
        """Publish a product created event"""
        pass

    @abstractmethod
    def publish_product_updated(
        self, product_id: str, update_data: Dict[str, Any]
    ) -> Optional[str]:
        """Publish a product updated event"""
        pass

    @abstractmethod
    def publish_product_deleted(self, product_id: str) -> Optional[str]:
        """Publish a product deleted event"""
        pass

    @abstractmethod
    def publish_event(self, event_data: Dict[str, Any]) -> Optional[str]:
        """Publish a generic event"""
        pass

    @abstractmethod
    def start_consumer(self, consumer_id: Optional[str] = None) -> None:
        """Start consuming events"""
        pass

    @abstractmethod
    def stop_consumer(self) -> None:
        """Stop consuming events"""
        pass

    @abstractmethod
    def add_event_handler(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Add a function to handle incoming events"""
        pass


class ProductStoreInterface(ABC):
    """Abstract interface for product data storage"""

    @abstractmethod
    def store_product(self, product_data: Dict[str, Any]) -> bool:
        """Store or update a product"""
        pass

    @abstractmethod
    def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a product by ID"""
        pass

    @abstractmethod
    def delete_product(self, product_id: str) -> bool:
        """Delete a product"""
        pass

    @abstractmethod
    def list_products(
        self, category: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """List products with optional filtering"""
        pass

    @abstractmethod
    def search_products(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search products by text query"""
        pass


class UserBehaviorInterface(ABC):
    """Abstract interface for user behavior tracking"""

    @abstractmethod
    def track_view(
        self, user_id: str, product_id: str, variant_id: Optional[str] = None
    ) -> bool:
        """Track a product view by user. variant_id optional (for product-level tracking)"""
        pass

    @abstractmethod
    def track_click(
        self, user_id: str, product_id: str, variant_id: Optional[str] = None
    ) -> bool:
        """Track a product click by user. variant_id optional"""
        pass

    @abstractmethod
    def track_add_to_cart(
        self, user_id: str, product_id: str, variant_id: Optional[str] = None
    ) -> bool:
        """Track a product add-to-cart by user. variant_id recommended for conversion tracking"""
        pass

    @abstractmethod
    def track_purchase(
        self, user_id: str, product_id: str, variant_id: Optional[str] = None
    ) -> bool:
        """Track a product purchase by user. variant_id recommended for conversion tracking"""
        pass

    @abstractmethod
    def get_user_history(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get user's recent product views"""
        pass

    @abstractmethod
    def get_popular_products(
        self, category: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get popular products by view count"""
        pass

    # ---------------------------------------------------------
    # Optional methods (not all backends must implement)
    # ---------------------------------------------------------
    def get_recent_interactions(
        self,
        limit: int = 10000,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Optional: Return recent interaction events (e.g., views).
        Expected keys per item: user_id, product_id, timestamp.
        """
        raise NotImplementedError

    def get_interaction_counts(
        self,
        limit: int = 50000,
    ) -> List[Dict[str, Any]]:
        """
        Optional: Return aggregated interaction counts for training CF models.
        Expected keys per item: user_id, product_id, count.
        """
        raise NotImplementedError


class ContentStoreInterface(ABC):
    """Abstract interface for content data storage (CMS)"""

    @abstractmethod
    def store_content(self, content_data: Dict[str, Any]) -> bool:
        """Store or update content"""
        pass

    @abstractmethod
    def get_content(self, content_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve content by ID"""
        pass

    @abstractmethod
    def update_content(self, content_id: str, update_data: Dict[str, Any]) -> bool:
        """Update content"""
        pass

    @abstractmethod
    def delete_content(self, content_id: str) -> bool:
        """Delete content"""
        pass

    @abstractmethod
    def list_content(
        self,
        category: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List content with optional filtering"""
        pass

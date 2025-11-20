"""
Abstract interfaces for the modern stack adapters.
This allows easy switching between different backends (Redis, Cloud, etc.)
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable
import numpy as np


class VectorStoreInterface(ABC):
    """Abstract interface for vector storage and similarity search"""

    @abstractmethod
    def store_product_embedding(self, product_id: str, embedding: np.ndarray,
                               metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Store a product embedding with optional metadata"""
        pass

    @abstractmethod
    def find_similar_products(self, embedding: np.ndarray,
                             limit: int = 10,
                             min_score: float = 0.75) -> List[Dict[str, Any]]:
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
    def publish_product_updated(self, product_id: str, update_data: Dict[str, Any]) -> Optional[str]:
        """Publish a product updated event"""
        pass

    @abstractmethod
    def publish_product_deleted(self, product_id: str) -> Optional[str]:
        """Publish a product deleted event"""
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
    def set_event_handler(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Set the function to handle incoming events"""
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
    def list_products(self, category: Optional[str] = None,
                      limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """List products with optional filtering"""
        pass

    @abstractmethod
    def search_products(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search products by text query"""
        pass


class UserBehaviorInterface(ABC):
    """Abstract interface for user behavior tracking"""

    @abstractmethod
    def track_view(self, user_id: str, product_id: str) -> bool:
        """Track a product view by user"""
        pass

    @abstractmethod
    def get_user_history(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get user's recent product views"""
        pass

    @abstractmethod
    def get_popular_products(self, category: Optional[str] = None,
                            limit: int = 10) -> List[Dict[str, Any]]:
        """Get popular products by view count"""
        pass
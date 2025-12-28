"""
MongoDB adapter for product store and user behavior tracking.
"""

import os
import sys
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger
from pymongo import MongoClient
from pymongo.errors import PyMongoError

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

import config
from adapters.interfaces import ProductStoreInterface, UserBehaviorInterface


def _get_mongodb_client() -> MongoClient:
    """Get MongoDB client connection"""
    if config.MONGODB_URI:
        return MongoClient(config.MONGODB_URI)
    
    # Build connection string from individual settings
    if config.MONGODB_USER and config.MONGODB_PASSWORD:
        uri = f"mongodb://{config.MONGODB_USER}:{config.MONGODB_PASSWORD}@{config.MONGODB_HOST}:{config.MONGODB_PORT}/{config.MONGODB_DB}?authSource={config.MONGODB_AUTH_SOURCE}"
    else:
        uri = f"mongodb://{config.MONGODB_HOST}:{config.MONGODB_PORT}/{config.MONGODB_DB}"
    
    return MongoClient(uri)


def _get_mongodb_db():
    """Get MongoDB database instance"""
    client = _get_mongodb_client()
    return client[config.MONGODB_DB]


class MongoDBProductStore(ProductStoreInterface):
    """MongoDB product data storage implementation"""

    def __init__(self):
        try:
            self.db = _get_mongodb_db()
            self.collection = self.db.products
            # Create indexes
            self.collection.create_index("product_id", unique=True)
            self.collection.create_index("category")
            self.collection.create_index("name")
            logger.info(f"MongoDB Product Store initialized: {config.MONGODB_HOST}:{config.MONGODB_PORT}/{config.MONGODB_DB}")
        except Exception as e:
            logger.error(f"Failed to initialize MongoDB Product Store: {e}")
            raise

    def store_product(self, product_data: Dict[str, Any]) -> bool:
        """Store or update a product in MongoDB"""
        try:
            # Extract category from categoryId if category is not provided
            category = product_data.get("category")
            if not category and product_data.get("categoryId"):
                category_id = product_data.get("categoryId")
                if isinstance(category_id, list) and len(category_id) > 0:
                    category = category_id[0]
                elif isinstance(category_id, str):
                    category = category_id
            
            # Extract price from first variant if not at product level
            price = product_data.get("price")
            if price is None and product_data.get("productVariants"):
                variants = product_data.get("productVariants")
                if variants and len(variants) > 0:
                    first_variant = variants[0]
                    if isinstance(first_variant, dict):
                        price = first_variant.get("price")
            
            # Prepare product document
            product_doc = {
                "product_id": product_data["id"],
                "name": product_data.get("name", ""),
                "description": product_data.get("description", ""),
                "category": category or "",
                "price": float(price or 0),
                "updated_at": datetime.utcnow(),
            }
            
            # Store all other fields in a metadata/document field
            metadata = {
                k: v
                for k, v in product_data.items()
                if k not in ["id", "name", "description", "category", "price", "created_at", "updated_at"]
            }
            product_doc.update(metadata)
            
            # Upsert (insert or update)
            result = self.collection.update_one(
                {"product_id": product_doc["product_id"]},
                {"$set": product_doc},
                upsert=True
            )
            
            logger.debug(f"Stored product {product_data['id']} in MongoDB")
            return True
            
        except PyMongoError as e:
            logger.error(f"Error storing product {product_data.get('id')}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error storing product {product_data.get('id')}: {e}")
            return False

    def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a product by ID from MongoDB"""
        try:
            doc = self.collection.find_one({"product_id": product_id})
            if not doc:
                return None
            
            # Convert MongoDB document to dict and restore 'id' field
            product = dict(doc)
            product["id"] = product.pop("product_id", product_id)
            product.pop("_id", None)  # Remove MongoDB _id field
            
            return product
            
        except PyMongoError as e:
            logger.error(f"Error retrieving product {product_id}: {e}")
            return None

    def delete_product(self, product_id: str) -> bool:
        """Delete a product from MongoDB"""
        try:
            result = self.collection.delete_one({"product_id": product_id})
            if result.deleted_count > 0:
                logger.debug(f"Deleted product {product_id} from MongoDB")
                return True
            return False
            
        except PyMongoError as e:
            logger.error(f"Error deleting product {product_id}: {e}")
            return False

    def list_products(
        self, category: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """List products with optional filtering"""
        try:
            query = {}
            if category:
                query["category"] = category
            
            cursor = self.collection.find(query).skip(offset).limit(limit)
            products = []
            
            for doc in cursor:
                product = dict(doc)
                product["id"] = product.pop("product_id", None)
                product.pop("_id", None)
                products.append(product)
            
            return products
            
        except PyMongoError as e:
            logger.error(f"Error listing products: {e}")
            return []

    def search_products(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search products by text query"""
        try:
            # Use MongoDB text search (requires text index)
            # For now, use regex search on name and description
            search_query = {
                "$or": [
                    {"name": {"$regex": query, "$options": "i"}},
                    {"description": {"$regex": query, "$options": "i"}},
                ]
            }
            
            cursor = self.collection.find(search_query).limit(limit)
            products = []
            
            for doc in cursor:
                product = dict(doc)
                product["id"] = product.pop("product_id", None)
                product.pop("_id", None)
                products.append(product)
            
            return products
            
        except PyMongoError as e:
            logger.error(f"Error searching products: {e}")
            return []


class MongoDBUserBehavior(UserBehaviorInterface):
    """MongoDB user behavior tracking implementation"""

    def __init__(self):
        try:
            self.db = _get_mongodb_db()
            self.interactions_collection = self.db.user_interactions
            self.products_collection = self.db.products
            
            # Create indexes
            self.interactions_collection.create_index([("user_id", 1), ("timestamp", -1)])
            self.interactions_collection.create_index([("product_id", 1), ("timestamp", -1)])
            self.interactions_collection.create_index("interaction_type")
            
            logger.info(f"MongoDB User Behavior initialized: {config.MONGODB_HOST}:{config.MONGODB_PORT}/{config.MONGODB_DB}")
        except Exception as e:
            logger.error(f"Failed to initialize MongoDB User Behavior: {e}")
            raise

    def _track_interaction(
        self, user_id: str, product_id: str, interaction_type: str
    ) -> bool:
        """Internal method to track any interaction"""
        try:
            interaction = {
                "user_id": user_id,
                "product_id": product_id,
                "interaction_type": interaction_type,
                "timestamp": datetime.utcnow(),
            }
            self.interactions_collection.insert_one(interaction)
            logger.debug(f"Tracked {interaction_type} for user {user_id}, product {product_id}")
            return True
        except PyMongoError as e:
            logger.error(f"Error tracking {interaction_type}: {e}")
            return False

    def track_view(self, user_id: str, product_id: str) -> bool:
        """Track a product view by user"""
        return self._track_interaction(user_id, product_id, "view")

    def track_click(self, user_id: str, product_id: str) -> bool:
        """Track a product click by user"""
        return self._track_interaction(user_id, product_id, "click")

    def track_add_to_cart(self, user_id: str, product_id: str) -> bool:
        """Track a product add-to-cart by user"""
        return self._track_interaction(user_id, product_id, "add_to_cart")

    def track_purchase(self, user_id: str, product_id: str) -> bool:
        """Track a product purchase by user"""
        return self._track_interaction(user_id, product_id, "purchase")

    def get_user_history(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get user's recent product interactions"""
        try:
            cursor = (
                self.interactions_collection.find({"user_id": user_id})
                .sort("timestamp", -1)
                .limit(limit)
            )
            
            history = []
            for doc in cursor:
                interaction = dict(doc)
                interaction.pop("_id", None)
                # Convert timestamp to ISO format if needed
                if isinstance(interaction.get("timestamp"), datetime):
                    interaction["timestamp"] = interaction["timestamp"].isoformat()
                history.append(interaction)
            
            return history
            
        except PyMongoError as e:
            logger.error(f"Error getting user history for {user_id}: {e}")
            return []

    def get_popular_products(
        self, category: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get popular products by view count"""
        try:
            # Aggregate to count views per product
            pipeline = [
                {"$match": {"interaction_type": "view"}},
                {
                    "$group": {
                        "_id": "$product_id",
                        "view_count": {"$sum": 1},
                    }
                },
                {"$sort": {"view_count": -1}},
                {"$limit": limit},
            ]
            
            # If category filter, we need to join with products collection
            if category:
                pipeline.insert(
                    -1,
                    {
                        "$lookup": {
                            "from": "products",
                            "localField": "_id",
                            "foreignField": "product_id",
                            "as": "product",
                        }
                    },
                )
                pipeline.insert(-1, {"$match": {"product.category": category}})
                pipeline.insert(-1, {"$unwind": "$product"})
            
            results = list(self.interactions_collection.aggregate(pipeline))
            
            popular = []
            for result in results:
                product_id = result["_id"]
                view_count = result["view_count"]
                
                # Get product details
                product_doc = self.products_collection.find_one({"product_id": product_id})
                if product_doc:
                    product = dict(product_doc)
                    product["id"] = product.pop("product_id", product_id)
                    product.pop("_id", None)
                    product["view_count"] = view_count
                    popular.append(product)
            
            return popular
            
        except PyMongoError as e:
            logger.error(f"Error getting popular products: {e}")
            return []

    def get_recent_interactions(
        self, limit: int = 10000, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Return recent interaction events"""
        try:
            cursor = (
                self.interactions_collection.find()
                .sort("timestamp", -1)
                .skip(offset)
                .limit(limit)
            )
            
            interactions = []
            for doc in cursor:
                interaction = dict(doc)
                interaction.pop("_id", None)
                if isinstance(interaction.get("timestamp"), datetime):
                    interaction["timestamp"] = interaction["timestamp"].isoformat()
                interactions.append(interaction)
            
            return interactions
            
        except PyMongoError as e:
            logger.error(f"Error getting recent interactions: {e}")
            return []

    def get_interaction_counts(
        self, limit: int = 50000
    ) -> List[Dict[str, Any]]:
        """Return aggregated interaction counts for training CF models"""
        try:
            pipeline = [
                {
                    "$group": {
                        "_id": {"user_id": "$user_id", "product_id": "$product_id"},
                        "count": {"$sum": 1},
                    }
                },
                {"$limit": limit},
            ]
            
            results = list(self.interactions_collection.aggregate(pipeline))
            
            counts = []
            for result in results:
                counts.append({
                    "user_id": result["_id"]["user_id"],
                    "product_id": result["_id"]["product_id"],
                    "count": result["count"],
                })
            
            return counts
            
        except PyMongoError as e:
            logger.error(f"Error getting interaction counts: {e}")
            return []


# Factory functions
def get_mongodb_product_store() -> MongoDBProductStore:
    """Get MongoDB product store instance"""
    return MongoDBProductStore()


def get_mongodb_user_behavior() -> MongoDBUserBehavior:
    """Get MongoDB user behavior instance"""
    return MongoDBUserBehavior()


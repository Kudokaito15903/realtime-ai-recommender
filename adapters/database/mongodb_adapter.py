import os
import sys
import json
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError, DuplicateKeyError
from bson import ObjectId

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

import config
from adapters.interfaces import ProductStoreInterface, UserBehaviorInterface


# ==================== CONNECTION MANAGEMENT ====================
_client: Optional[MongoClient] = None
_db = None


def _get_mongodb_client() -> MongoClient:
    """Get MongoDB client connection with connection pooling"""
    global _client

    if _client is not None:
        return _client

    try:
        if config.MONGODB_URI:
            uri = config.MONGODB_URI
        elif config.MONGODB_USER and config.MONGODB_PASSWORD:
            uri = (
                f"mongodb://{config.MONGODB_USER}:{config.MONGODB_PASSWORD}@"
                f"{config.MONGODB_HOST}:{config.MONGODB_PORT}/"
                f"{config.MONGODB_DB}?authSource={config.MONGODB_AUTH_SOURCE}"
            )
        else:
            uri = f"mongodb://{config.MONGODB_HOST}:{config.MONGODB_PORT}/{config.MONGODB_DB}"

        _client = MongoClient(
            uri,
            maxPoolSize=50,
            minPoolSize=10,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
        )

        # Test connection
        _client.admin.command("ping")
        logger.info(
            f"MongoDB client connected: {config.MONGODB_HOST}:{config.MONGODB_PORT}"
        )

        return _client

    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise


def _get_mongodb_db():
    """Get MongoDB database instance"""
    global _db

    if _db is not None:
        return _db

    client = _get_mongodb_client()
    _db = client[config.MONGODB_DB]
    return _db


# ==================== HELPER FUNCTIONS ====================


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert value to float"""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        logger.warning(f"Invalid float value: {value}, using default {default}")
        return default


def _is_valid_objectid(oid: str) -> bool:
    """Check if string is a valid MongoDB ObjectId"""
    try:
        ObjectId(oid)
        return True
    except Exception:
        return False


def _generate_objectid() -> str:
    """Generate a new MongoDB ObjectId as hex string"""
    return str(ObjectId())


def _ensure_product_id(product_data: Dict[str, Any]) -> str:
    """
    Ensure product has a valid ID.
    Priority: id > _id > auto-generate new ObjectId
    """
    # Try 'id' field first
    product_id = product_data.get("id")
    if product_id:
        return str(product_id)

    # Try '_id' field (MongoDB native)
    _id = product_data.get("_id")
    if _id:
        if isinstance(_id, ObjectId):
            return str(_id)
        return str(_id)

    # Generate new ObjectId
    new_id = _generate_objectid()
    logger.info(f"Auto-generated ObjectId for product: {new_id}")
    return new_id


def _ensure_index(collection, *args, **kwargs):
    """Create index if it doesn't exist, with background option"""
    try:
        kwargs.setdefault("background", True)
        collection.create_index(*args, **kwargs)
    except Exception as e:
        # Index might already exist
        logger.debug(f"Index creation skipped or failed: {e}")


# ==================== PRODUCT STORE ====================


class MongoDBProductStore(ProductStoreInterface):
    """MongoDB product data storage implementation with 2-collection design"""

    def __init__(self):
        try:
            self.db = _get_mongodb_db()
            self.products = self.db.product
            self.variants = self.db.product_variants

            # Create indexes (non-blocking)
            self._create_indexes()

            logger.info(
                f"MongoDB Product Store initialized: "
                f"{config.MONGODB_HOST}:{config.MONGODB_PORT}/{config.MONGODB_DB}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize MongoDB Product Store: {e}")
            raise

    def _create_indexes(self):
        """Create all necessary indexes"""
        # Products collection
        _ensure_index(self.products, "_id", unique=True)
        _ensure_index(self.products, "categoryId")
        _ensure_index(self.products, "name_product")
        _ensure_index(self.products, [("name_product", "text"), ("description", "text")])

        # Variants collection
        _ensure_index(self.variants, "_id", unique=True)
        _ensure_index(self.variants, "product_id")
        _ensure_index(
            self.variants, [("product_id", ASCENDING), ("sku", ASCENDING)]
        )

    def store_product(self, product_data: Dict[str, Any]) -> Optional[str]:
        """Store or update a product in MongoDB (split into 2 collections: product and product_variants)"""
        try:
            # Validation
            if not product_data:
                logger.error("Product data is empty")
                return None

            # Ensure product has valid ID (auto-generate if missing)
            product_id = _ensure_product_id(product_data)

            # --- 1. PREPARE DATA ---

            # Extract categoryId
            category_id = product_data.get("categoryId", [])
            if not isinstance(category_id, list):
                if category_id:
                    category_id = [str(category_id)]
                else:
                    category_id = []

            # Extract variants SKUs list
            variants_data = product_data.get("productVariants", [])
            variant_skus = []
            if variants_data:
                for v in variants_data:
                    if isinstance(v, dict):
                        sku = v.get("sku")
                        if sku:
                            variant_skus.append(sku)

            # --- 2. STORE MAIN PRODUCT ---

            # Prepare product document matching the example structure
            product_doc = {
                "name_product": product_data.get("name", product_data.get("name_product", "")),
                "description": product_data.get("description", ""),
                "video_url": product_data.get("videoUrl", product_data.get("video_url", "")),
                "categoryId": category_id,
                "brandName": product_data.get("brandName", ""),
                "variants": variant_skus,
                "specifications": product_data.get("specifications", []),
                "update_at": datetime.utcnow(),
            }

            # Upsert product using _id
            if _is_valid_objectid(product_id):
                product_doc["_id"] = ObjectId(product_id)
            else:
                # If product_id is not a valid ObjectId, generate new one
                product_id = _generate_objectid()
                product_doc["_id"] = ObjectId(product_id)

            self.products.update_one(
                {"_id": ObjectId(product_id)},
                {
                    "$set": product_doc,
                    "$setOnInsert": {"create_at": datetime.utcnow()},
                },
                upsert=True,
            )

            # --- 3. STORE VARIANTS ---

            # Remove old variants for this product (full sync approach)
            self.variants.delete_many({"product_id": product_id})

            # Insert new variants
            if variants_data:
                variant_docs = []

                for v in variants_data:
                    if not isinstance(v, dict):
                        continue

                    # Generate variant ID with ObjectId
                    v_id = v.get("id") or v.get("_id")
                    if v_id:
                        v_id = str(v_id)
                    else:
                        v_id = _generate_objectid()

                    # Prepare variant document matching the example structure
                    variant_doc = {
                        "product_id": product_id,
                        "variant_name": v.get("variantName", v.get("variant_name", "")),
                        "color": v.get("color", ""),
                        "sku": v.get("sku", ""),
                        "price": str(_safe_float(v.get("price"), 0.0)),  # Store as string to match example
                        "best_specifications": v.get("bestSpecifications", v.get("best_specifications", [])),
                        "update_at": datetime.utcnow(),
                    }

                    # Set _id
                    if _is_valid_objectid(v_id):
                        variant_doc["_id"] = ObjectId(v_id)
                    else:
                        v_id = _generate_objectid()
                        variant_doc["_id"] = ObjectId(v_id)

                    variant_docs.append(variant_doc)

                # Bulk insert
                if variant_docs:
                    # Set create_at for new documents
                    for doc in variant_docs:
                        doc["create_at"] = datetime.utcnow()
                    self.variants.insert_many(variant_docs, ordered=False)

            logger.debug(
                f"Stored product {product_id} with {len(variants_data)} variants"
            )
            return str(product_id)


        except DuplicateKeyError as e:
            logger.error(
                f"Duplicate key error storing product {product_data.get('id')}: {e}"
            )
            return None
        except PyMongoError as e:
            logger.error(f"MongoDB error storing product {product_data.get('id')}: {e}")
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error storing product {product_data.get('id')}: {e}"
            )
            return None

    def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a product by ID, reconstructing from 2 collections"""
        try:
            if not product_id:
                return None

            product_id = str(product_id)

            # 1. Get Main Product
            if _is_valid_objectid(product_id):
                product_doc = self.products.find_one({"_id": ObjectId(product_id)})
            else:
                # Fallback: try to find by product_id field if it exists
                product_doc = self.products.find_one({"product_id": product_id})
            
            if not product_doc:
                return None

            product = dict(product_doc)
            # Convert _id to string
            if "_id" in product:
                product["id"] = str(product["_id"])
                product.pop("_id", None)
            else:
                product["id"] = product_id

            # Specifications are already embedded in the document
            if "specifications" not in product:
                product["specifications"] = []

            # 2. Get Variants
            variants_cursor = self.variants.find({"product_id": product_id})
            variants = []

            for v_doc in variants_cursor:
                v = dict(v_doc)
                # Convert _id to string
                if "_id" in v:
                    v_id = str(v["_id"])
                    v.pop("_id", None)
                else:
                    v_id = v.get("variant_id", "")

                # Map fields to match API response format
                variant = {
                    "id": v_id,
                    "sku": v.get("sku", ""),
                    "variantName": v.get("variant_name", ""),
                    "color": v.get("color", ""),
                    "price": float(v.get("price", 0)) if isinstance(v.get("price"), (str, int, float)) else 0.0,
                    "bestSpecifications": v.get("best_specifications", []),
                }
                variants.append(variant)

            product["productVariants"] = variants

            return product

        except PyMongoError as e:
            logger.error(f"Error retrieving product {product_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error retrieving product {product_id}: {e}")
            return None

    def delete_product(self, product_id: str) -> bool:
        """Delete a product and all related data from MongoDB"""
        try:
            if not product_id:
                return False

            product_id = str(product_id)

            # Delete variants
            self.variants.delete_many({"product_id": product_id})

            # Delete product
            if _is_valid_objectid(product_id):
                result = self.products.delete_one({"_id": ObjectId(product_id)})
            else:
                # Fallback: try to delete by product_id field if it exists
                result = self.products.delete_one({"product_id": product_id})

            if result.deleted_count > 0:
                logger.debug(f"Deleted product {product_id} from MongoDB")
                return True

            logger.warning(f"Product {product_id} not found for deletion")
            return False

        except PyMongoError as e:
            logger.error(f"Error deleting product {product_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting product {product_id}: {e}")
            return False

    def list_products(
        self, category: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """List products with optional filtering"""
        try:
            query = {}
            if category:
                # Search in categoryId array
                query["categoryId"] = str(category)

            cursor = self.products.find(query).skip(offset).limit(limit)
            products = []

            for doc in cursor:
                product = dict(doc)
                # Convert _id to string
                if "_id" in product:
                    product["id"] = str(product["_id"])
                    product.pop("_id", None)
                products.append(product)

            return products

        except PyMongoError as e:
            logger.error(f"Error listing products: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error listing products: {e}")
            return []

    def search_products(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search products by text query"""
        try:
            if not query:
                return []

            # Try text search first (requires text index)
            try:
                cursor = (
                    self.products.find(
                        {"$text": {"$search": query}}, {"score": {"$meta": "textScore"}}
                    )
                    .sort([("score", {"$meta": "textScore"})])
                    .limit(limit)
                )

                products = []
                for doc in cursor:
                    product = dict(doc)
                    # Convert _id to string
                    if "_id" in product:
                        product["id"] = str(product["_id"])
                        product.pop("_id", None)
                    product.pop("score", None)
                    products.append(product)

                if products:
                    return products

            except Exception:
                # Text index not available, fallback to regex
                pass

            # Fallback to regex search
            search_query = {
                "$or": [
                    {"name_product": {"$regex": query, "$options": "i"}},
                    {"description": {"$regex": query, "$options": "i"}},
                ]
            }

            cursor = self.products.find(search_query).limit(limit)
            products = []

            for doc in cursor:
                product = dict(doc)
                # Convert _id to string
                if "_id" in product:
                    product["id"] = str(product["_id"])
                    product.pop("_id", None)
                products.append(product)

            return products

        except PyMongoError as e:
            logger.error(f"Error searching products: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error searching products: {e}")
            return []

    def store_products_batch(self, products: List[Dict[str, Any]]) -> int:
        """Bulk insert/update products (bonus method for performance)"""
        success_count = 0

        for product_data in products:
            if self.store_product(product_data):
                success_count += 1

        logger.info(f"Batch stored {success_count}/{len(products)} products")
        return success_count


# ==================== USER BEHAVIOR ====================


class MongoDBUserBehavior(UserBehaviorInterface):
    """MongoDB user behavior tracking implementation"""

    def __init__(self):
        try:
            self.db = _get_mongodb_db()
            self.interactions = self.db.user_interactions
            self.products = self.db.product

            # Create indexes (non-blocking)
            self._create_indexes()

            logger.info(
                f"MongoDB User Behavior initialized: "
                f"{config.MONGODB_HOST}:{config.MONGODB_PORT}/{config.MONGODB_DB}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize MongoDB User Behavior: {e}")
            raise

    def _create_indexes(self):
        """Create all necessary indexes"""
        _ensure_index(
            self.interactions, [("user_id", ASCENDING), ("timestamp", DESCENDING)]
        )
        _ensure_index(
            self.interactions, [("product_id", ASCENDING), ("timestamp", DESCENDING)]
        )
        _ensure_index(self.interactions, "interaction_type")
        _ensure_index(self.interactions, "timestamp")
        _ensure_index(
            self.interactions, [("user_id", ASCENDING), ("product_id", ASCENDING)]
        )

        # Optional: TTL index to auto-delete old interactions (e.g., after 90 days)
        # _ensure_index(self.interactions, "timestamp", expireAfterSeconds=60*60*24*90)

        # Index for session-based queries
        _ensure_index(self.interactions, "session_id")

    def _track_interaction(
        self,
        user_id: str,
        product_id: str,
        interaction_type: str,
        variant_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> bool:
        """Internal method to track any interaction"""
        try:
            if not user_id or not product_id:
                logger.warning("Missing user_id or product_id for interaction tracking")
                return False

            interaction = {
                "user_id": str(user_id),
                "product_id": str(product_id),
                "interaction_type": interaction_type,
                "timestamp": datetime.utcnow(),
            }

            # Add variant_id if provided (important for add_to_cart and purchase)
            if variant_id:
                interaction["variant_id"] = str(variant_id)
                interaction["sku"] = str(variant_id)  # Alias for compatibility

            # Add session_id if provided
            if session_id:
                interaction["session_id"] = str(session_id)

            self.interactions.insert_one(interaction)

            logger.debug(
                f"Tracked {interaction_type}: user={user_id}, "
                f"product={product_id}, variant={variant_id or 'N/A'}, session={session_id or 'N/A'}"
            )
            return True

        except PyMongoError as e:
            logger.error(f"Error tracking {interaction_type}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error tracking {interaction_type}: {e}")
            return False

    def track_view(
        self,
        user_id: str,
        product_id: str,
        variant_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> bool:
        """Track a product view by user"""
        return self._track_interaction(
            user_id, product_id, "view", variant_id, session_id
        )

    def track_click(
        self,
        user_id: str,
        product_id: str,
        variant_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> bool:
        """Track a product click by user"""
        return self._track_interaction(
            user_id, product_id, "click", variant_id, session_id
        )

    def track_add_to_cart(
        self,
        user_id: str,
        product_id: str,
        variant_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> bool:
        """Track a product add-to-cart by user"""
        return self._track_interaction(
            user_id, product_id, "add_to_cart", variant_id, session_id
        )

    def track_purchase(
        self,
        user_id: str,
        product_id: str,
        variant_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> bool:
        """Track a product purchase by user"""
        return self._track_interaction(
            user_id, product_id, "purchase", variant_id, session_id
        )

    def get_user_history(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get user's recent product interactions"""
        try:
            if not user_id:
                return []

            cursor = (
                self.interactions.find({"user_id": str(user_id)})
                .sort("timestamp", DESCENDING)
                .limit(limit)
            )

            history = []
            for doc in cursor:
                interaction = dict(doc)
                interaction.pop("_id", None)

                # Convert timestamp to ISO format
                if isinstance(interaction.get("timestamp"), datetime):
                    interaction["timestamp"] = interaction["timestamp"].isoformat()

                history.append(interaction)

            return history

        except Exception as e:
            logger.error(f"Unexpected error getting user history for {user_id}: {e}")
            return []

    def get_session_interactions(self, session_id: str) -> List[Dict[str, Any]]:
        """Get interactions for a specific session"""
        try:
            if not session_id:
                return []

            cursor = (
                self.interactions.find({"session_id": str(session_id)})
                .sort("timestamp", ASCENDING)
            )

            interactions = []
            for doc in cursor:
                interaction = dict(doc)
                interaction.pop("_id", None)
                
                # Convert timestamp to ISO format
                if isinstance(interaction.get("timestamp"), datetime):
                    interaction["timestamp"] = interaction["timestamp"].isoformat()
                    
                interactions.append(interaction)

            return interactions

        except PyMongoError as e:
            logger.error(f"Error getting session interactions for {session_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error getting session interactions for {session_id}: {e}")
            return []

    def get_popular_products(
        self, category: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get popular products by view count (FIXED aggregation pipeline)"""
        try:
            # Base aggregation pipeline
            pipeline = [
                {"$match": {"interaction_type": "view"}},
                {
                    "$group": {
                        "_id": "$product_id",
                        "view_count": {"$sum": 1},
                    }
                },
                {"$sort": {"view_count": DESCENDING}},
            ]

            # Get more results if we need to filter by category
            fetch_limit = limit * 3 if category else limit
            pipeline.append({"$limit": fetch_limit})

            # Execute aggregation
            results = list(self.interactions.aggregate(pipeline, allowDiskUse=True))

            # Fetch product details and filter
            popular = []
            for result in results:
                product_id = result["_id"]
                view_count = result["view_count"]

                # Get product details
                if _is_valid_objectid(product_id):
                    product_doc = self.products.find_one({"_id": ObjectId(product_id)})
                else:
                    product_doc = self.products.find_one({"product_id": product_id})

                if not product_doc:
                    continue

                # Filter by category if specified
                if category:
                    category_ids = product_doc.get("categoryId", [])
                    if not isinstance(category_ids, list):
                        category_ids = [category_ids] if category_ids else []
                    if str(category) not in [str(c) for c in category_ids]:
                        continue

                # Build product dict
                product = dict(product_doc)
                # Convert _id to string
                if "_id" in product:
                    product["id"] = str(product["_id"])
                    product.pop("_id", None)
                else:
                    product["id"] = product_id
                
                # Ensure product_id key exists for service layer compatibility
                product["product_id"] = product["id"]
                
                product["view_count"] = view_count
                popular.append(product)

                # Stop if we have enough results
                if len(popular) >= limit:
                    break

            return popular
        except Exception as e:
            logger.error(f"Unexpected error getting popular products: {e}")
            return []

    def get_recent_interactions(
        self, limit: int = 10000, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Return recent interaction events"""
        try:
            cursor = (
                self.interactions.find()
                .sort("timestamp", DESCENDING)
                .skip(offset)
                .limit(limit)
            )

            interactions = []
            for doc in cursor:
                interaction = dict(doc)
                interaction.pop("_id", None)

                # Convert timestamp to ISO format
                if isinstance(interaction.get("timestamp"), datetime):
                    interaction["timestamp"] = interaction["timestamp"].isoformat()

                interactions.append(interaction)

            return interactions

        except PyMongoError as e:
            logger.error(f"Error getting recent interactions: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error getting recent interactions: {e}")
            return []

    def get_interaction_counts(self, limit: int = 50000) -> List[Dict[str, Any]]:
        """Return aggregated interaction counts for training CF models"""
        try:
            pipeline = [
                {
                    "$group": {
                        "_id": {"user_id": "$user_id", "product_id": "$product_id"},
                        "count": {"$sum": 1},
                        "last_interaction": {"$max": "$timestamp"},
                    }
                },
                {"$sort": {"count": DESCENDING}},
                {"$limit": limit},
            ]

            results = list(self.interactions.aggregate(pipeline, allowDiskUse=True))

            counts = []
            for result in results:
                interaction_data = {
                    "user_id": result["_id"]["user_id"],
                    "product_id": result["_id"]["product_id"],
                    "count": result["count"],
                }

                # Add last interaction timestamp if available
                if "last_interaction" in result:
                    if isinstance(result["last_interaction"], datetime):
                        interaction_data["timestamp"] = result[
                            "last_interaction"
                        ].isoformat()
                    else:
                        interaction_data["timestamp"] = result["last_interaction"]

                counts.append(interaction_data)

            return counts

        except PyMongoError as e:
            logger.error(f"Error getting interaction counts: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error getting interaction counts: {e}")
            return []


# ==================== FACTORY FUNCTIONS ====================

_product_store_instance: Optional[MongoDBProductStore] = None
_user_behavior_instance: Optional[MongoDBUserBehavior] = None


def get_mongodb_product_store() -> MongoDBProductStore:
    """Get MongoDB product store singleton instance"""
    global _product_store_instance

    if _product_store_instance is None:
        _product_store_instance = MongoDBProductStore()

    return _product_store_instance


def get_mongodb_user_behavior() -> MongoDBUserBehavior:
    """Get MongoDB user behavior singleton instance"""
    global _user_behavior_instance

    if _user_behavior_instance is None:
        _user_behavior_instance = MongoDBUserBehavior()

    return _user_behavior_instance


def reset_connections():
    """Reset all connections (useful for testing or reconnection)"""
    global _client, _db, _product_store_instance, _user_behavior_instance

    if _client:
        _client.close()

    _client = None
    _db = None
    _product_store_instance = None
    _user_behavior_instance = None

    logger.info("MongoDB connections reset")

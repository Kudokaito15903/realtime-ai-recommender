"""
PostgreSQL adapters for event processing and data storage.
This replaces Supabase-specific logic with a self-hosted Postgres database.
"""

import os
import time
import json
import threading
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime

from loguru import logger
import psycopg2
from psycopg2.extras import RealDictCursor

from adapters.interfaces import (
    EventProcessorInterface,
    ProductStoreInterface,
    UserBehaviorInterface,
    ContentStoreInterface,
)


def _get_pg_conn():
    """Create a new PostgreSQL connection using environment variables."""
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    db = os.getenv("POSTGRES_DB", "realtime_ai")
    user = os.getenv("POSTGRES_USER", "realtime_ai")
    password = os.getenv("POSTGRES_PASSWORD", "realtime_ai")

    return psycopg2.connect(
        host=host,
        port=port,
        dbname=db,
        user=user,
        password=password,
        cursor_factory=RealDictCursor,
    )


def _ensure_tables():
    """
    Ensure required tables exist.
    This is a lightweight safety net for development; in production,
    you may want proper migrations instead.
    """
    ddl_statements = [
        # Events table
        """
        CREATE TABLE IF NOT EXISTS product_events (
            id SERIAL PRIMARY KEY,
            event_type VARCHAR(32) NOT NULL,
            product_id VARCHAR(255) NOT NULL,
            data JSONB NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            processed BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            processed_at TIMESTAMPTZ
        );
        """,
        # Products table
        """
        CREATE TABLE IF NOT EXISTS products (
            product_id VARCHAR(255) PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT '',
            price NUMERIC(18, 4) NOT NULL DEFAULT 0,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """,
        # User views / interactions table
        """
        CREATE TABLE IF NOT EXISTS user_views (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            product_id VARCHAR(255) NOT NULL,
            event_type VARCHAR(32) NOT NULL DEFAULT 'view',
            session_id VARCHAR(255),
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """,
        # Category popularity table
        """
        CREATE TABLE IF NOT EXISTS category_popularity (
            category TEXT PRIMARY KEY,
            view_count BIGINT NOT NULL DEFAULT 0,
            last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """,
        # Content table
        """
        CREATE TABLE IF NOT EXISTS content (
            content_id VARCHAR(255) PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT '',
            tags JSONB NOT NULL DEFAULT '[]'::jsonb,
            status VARCHAR(32) NOT NULL DEFAULT 'published',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """,
    ]

    # Additional schema evolution for existing databases
    alter_statements = [
        """
        ALTER TABLE user_views
        ADD COLUMN IF NOT EXISTS event_type VARCHAR(32) NOT NULL DEFAULT 'view';
        """,
        """
        ALTER TABLE user_views
        ADD COLUMN IF NOT EXISTS session_id VARCHAR(255);
        """,
    ]

    try:
        conn = _get_pg_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    for ddl in ddl_statements:
                        cur.execute(ddl)
                    for alter in alter_statements:
                        cur.execute(alter)
            logger.info("Ensured PostgreSQL tables and columns exist")
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error ensuring PostgreSQL tables/columns: {e}")


class PostgresEventProcessor(EventProcessorInterface):
    """PostgreSQL event processor implementation using polling."""

    def __init__(self):
        _ensure_tables()
        self.event_handlers: List[Callable[[Dict[str, Any]], None]] = []
        self.running = False
        self.consumer_thread: Optional[threading.Thread] = None
        logger.info("Postgres Event Processor initialized")

    def publish_product_created(self, product_data: Dict[str, Any]) -> Optional[str]:
        return self._publish_event("create", product_data["id"], product_data)

    def publish_product_updated(
        self, product_id: str, update_data: Dict[str, Any]
    ) -> Optional[str]:
        return self._publish_event("update", product_id, update_data)

    def publish_product_deleted(self, product_id: str) -> Optional[str]:
        return self._publish_event("delete", product_id, {"id": product_id})

    def publish_event(self, event_data: Dict[str, Any]) -> Optional[str]:
        """Publish a generic event"""
        event_type = event_data.get("event_type", "unknown")
        entity_id = (
            event_data.get("content_id") or event_data.get("product_id") or "unknown"
        )
        real_data = event_data.get("data", event_data)

        return self._publish_event(event_type, entity_id, real_data)

    def _publish_event(
        self, event_type: str, product_id: str, data: Dict[str, Any]
    ) -> Optional[str]:
        try:
            conn = _get_pg_conn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO product_events (event_type, product_id, data, timestamp, processed)
                            VALUES (%s, %s, %s, %s, FALSE)
                            RETURNING id;
                            """,
                            (
                                event_type,
                                product_id,
                                json.dumps(data),
                                datetime.utcnow(),
                            ),
                        )
                        row = cur.fetchone()
                        event_id = row["id"]
                        logger.info(
                            f"Published {event_type} event for product {product_id}: {event_id}"
                        )
                        return str(event_id)
            finally:
                conn.close()
        except Exception as e:
            logger.error(
                f"Error publishing {event_type} event for product {product_id}: {e}"
            )
            return None

    def start_consumer(self, consumer_id: Optional[str] = None) -> None:
        if self.running:
            logger.warning("Event consumer is already running")
            return

        self.running = True
        self.consumer_thread = threading.Thread(
            target=self._consume_loop,
            args=(consumer_id,),
            daemon=True,
        )
        self.consumer_thread.start()
        logger.info(f"Started Postgres event consumer: {consumer_id}")

    def stop_consumer(self) -> None:
        if not self.running:
            logger.warning("Event consumer is not running")
            return

        self.running = False
        if self.consumer_thread and self.consumer_thread.is_alive():
            self.consumer_thread.join(timeout=5.0)
        logger.info("Stopped Postgres event consumer")

    def add_event_handler(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        self.event_handlers.append(handler)

    def _consume_loop(self, consumer_id: Optional[str]) -> None:
        try:
            while self.running:
                try:
                    conn = _get_pg_conn()
                    try:
                        with conn:
                            with conn.cursor() as cur:
                                cur.execute(
                                    """
                                    SELECT *
                                    FROM product_events
                                    WHERE processed = FALSE
                                    ORDER BY created_at ASC
                                    LIMIT 10;
                                    """
                                )
                                events = cur.fetchall()

                                if not events:
                                    time.sleep(2)
                                    continue

                                for event in events:
                                    try:
                                        event_data = {
                                            "event_type": event["event_type"],
                                            "product_id": event["product_id"],
                                            "data": event["data"],
                                            "timestamp": event["timestamp"],
                                        }
                                        for handler in self.event_handlers:
                                            try:
                                                handler(event_data)
                                            except Exception as e:
                                                logger.error(f"Error in handler: {e}")

                                        cur.execute(
                                            """
                                            UPDATE product_events
                                            SET processed = TRUE,
                                                processed_at = %s
                                            WHERE id = %s;
                                            """,
                                            (datetime.utcnow(), event["id"]),
                                        )
                                        logger.debug(
                                            f"Processed event {event['id']}: {event['event_type']}"
                                        )
                                    except Exception as e:
                                        logger.error(
                                            f"Error processing event {event['id']}: {e}"
                                        )
                    finally:
                        conn.close()
                except Exception as e:
                    logger.error(f"Error in event consumer loop: {e}")
                    time.sleep(1)
        except Exception as e:
            logger.error(f"Unexpected error in event consumer loop: {e}")
            self.running = False


class PostgresProductStore(ProductStoreInterface):
    """PostgreSQL product data storage implementation."""

    def __init__(self):
        _ensure_tables()
        logger.info("Postgres Product Store initialized")

    def store_product(self, product_data: Dict[str, Any]) -> bool:
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

            product = {
                "product_id": product_data["id"],
                "name": product_data.get("name", ""),
                "description": product_data.get("description", ""),
                "category": category or "",
                "price": float(price or 0),
                "metadata": {
                    k: v
                    for k, v in product_data.items()
                    if k
                    not in [
                        "id",
                        "name",
                        "description",
                        "category",
                        "price",
                        "created_at",
                        "updated_at",
                    ]
                },
            }

            conn = _get_pg_conn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO products (
                                product_id, name, description, category, price, metadata, updated_at
                            )
                            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
                            ON CONFLICT (product_id) DO UPDATE SET
                                name = EXCLUDED.name,
                                description = EXCLUDED.description,
                                category = EXCLUDED.category,
                                price = EXCLUDED.price,
                                metadata = EXCLUDED.metadata,
                                updated_at = EXCLUDED.updated_at;
                            """,
                            (
                                product["product_id"],
                                product["name"],
                                product["description"],
                                product["category"],
                                product["price"],
                                json.dumps(product["metadata"]),
                                datetime.utcnow(),
                            ),
                        )
                logger.debug(f"Stored product {product_data['id']} in Postgres")
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error storing product {product_data.get('id')}: {e}")
            return False

    def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        try:
            conn = _get_pg_conn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT *
                            FROM products
                            WHERE product_id = %s;
                            """,
                            (product_id,),
                        )
                        row = cur.fetchone()
                        if not row:
                            return None

                        metadata = row.get("metadata") or {}
                        return {
                            "id": row["product_id"],
                            "name": row["name"],
                            "description": row["description"],
                            "category": row["category"],
                            "price": float(row["price"] or 0),
                            "created_at": row.get("created_at"),
                            "updated_at": row.get("updated_at"),
                            **metadata,
                        }
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error retrieving product {product_id}: {e}")
            return None

    def delete_product(self, product_id: str) -> bool:
        try:
            conn = _get_pg_conn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "DELETE FROM products WHERE product_id = %s;",
                            (product_id,),
                        )
                logger.debug(f"Deleted product {product_id} from Postgres")
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error deleting product {product_id}: {e}")
            return False

    def list_products(
        self,
        category: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        try:
            conn = _get_pg_conn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        if category:
                            cur.execute(
                                """
                                SELECT *
                                FROM products
                                WHERE category = %s
                                ORDER BY created_at DESC
                                LIMIT %s OFFSET %s;
                                """,
                                (category, limit, offset),
                            )
                        else:
                            cur.execute(
                                """
                                SELECT *
                                FROM products
                                ORDER BY created_at DESC
                                LIMIT %s OFFSET %s;
                                """,
                                (limit, offset),
                            )
                        rows = cur.fetchall()

                products: List[Dict[str, Any]] = []
                for row in rows:
                    metadata = row.get("metadata") or {}
                    products.append(
                        {
                            "id": row["product_id"],
                            "name": row["name"],
                            "description": row["description"],
                            "category": row["category"],
                            "price": float(row["price"] or 0),
                            "created_at": row.get("created_at"),
                            "updated_at": row.get("updated_at"),
                            **metadata,
                        }
                    )
                return products
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error listing products: {e}")
            return []

    def search_products(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Simple text search using ILIKE on name/description.
        For production search, you may want PostgreSQL full-text search.
        """
        try:
            conn = _get_pg_conn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        pattern = f"%{query}%"
                        cur.execute(
                            """
                            SELECT *
                            FROM products
                            WHERE name ILIKE %s OR description ILIKE %s
                            ORDER BY created_at DESC
                            LIMIT %s;
                            """,
                            (pattern, pattern, limit),
                        )
                        rows = cur.fetchall()

                products: List[Dict[str, Any]] = []
                for row in rows:
                    metadata = row.get("metadata") or {}
                    products.append(
                        {
                            "id": row["product_id"],
                            "name": row["name"],
                            "description": row["description"],
                            "category": row["category"],
                            "price": float(row["price"] or 0),
                            "created_at": row.get("created_at"),
                            "updated_at": row.get("updated_at"),
                            **metadata,
                        }
                    )
                return products
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error searching products: {e}")
            return []


class PostgresUserBehavior(UserBehaviorInterface):
    """PostgreSQL user behavior tracking implementation."""

    def __init__(self):
        _ensure_tables()
        logger.info("Postgres User Behavior initialized")

    def _insert_event(
        self,
        user_id: str,
        product_id: str,
        event_type: str,
        session_id: Optional[str] = None,
    ) -> bool:
        try:
            conn = _get_pg_conn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO user_views (user_id, product_id, event_type, session_id, timestamp)
                            VALUES (%s, %s, %s, %s, %s);
                            """,
                            (
                                user_id,
                                product_id,
                                event_type,
                                session_id,
                                datetime.utcnow(),
                            ),
                        )
                # Update category popularity
                self._update_category_popularity(product_id)
                logger.debug(
                    f"Tracked {event_type}: user {user_id} -> product {product_id} (session={session_id})"
                )
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error tracking {event_type}: {e}")
            return False

    def track_view(
        self, user_id: str, product_id: str, session_id: Optional[str] = None
    ) -> bool:
        return self._insert_event(user_id, product_id, "view", session_id)

    def track_click(
        self, user_id: str, product_id: str, session_id: Optional[str] = None
    ) -> bool:
        return self._insert_event(user_id, product_id, "click", session_id)

    def track_add_to_cart(
        self, user_id: str, product_id: str, session_id: Optional[str] = None
    ) -> bool:
        return self._insert_event(user_id, product_id, "add_to_cart", session_id)

    def track_purchase(
        self, user_id: str, product_id: str, session_id: Optional[str] = None
    ) -> bool:
        return self._insert_event(user_id, product_id, "purchase", session_id)

    def get_user_history(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        try:
            conn = _get_pg_conn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT uv.*, p.name, p.category, p.price
                            FROM user_views uv
                            LEFT JOIN products p ON uv.product_id = p.product_id
                            WHERE uv.user_id = %s
                            ORDER BY uv.timestamp DESC
                            LIMIT %s;
                            """,
                            (user_id, limit),
                        )
                        rows = cur.fetchall()
                return list(rows) if rows else []
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error getting user history: {e}")
            return []

    def get_popular_products(
        self, category: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get popular products by view count.
        Uses category_popularity for a simple aggregate.
        """
        try:
            conn = _get_pg_conn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        if category:
                            cur.execute(
                                """
                                SELECT p.*
                                FROM category_popularity cp
                                JOIN products p ON p.category = cp.category
                                WHERE cp.category = %s
                                ORDER BY cp.view_count DESC
                                LIMIT %s;
                                """,
                                (category, limit),
                            )
                        else:
                            cur.execute(
                                """
                                SELECT p.*
                                FROM category_popularity cp
                                JOIN products p ON p.category = cp.category
                                ORDER BY cp.view_count DESC
                                LIMIT %s;
                                """,
                                (limit,),
                            )
                        rows = cur.fetchall()

                products: List[Dict[str, Any]] = []
                for row in rows:
                    metadata = row.get("metadata") or {}
                    products.append(
                        {
                            "id": row["product_id"],
                            "name": row["name"],
                            "description": row["description"],
                            "category": row["category"],
                            "price": float(row["price"] or 0),
                            "created_at": row.get("created_at"),
                            "updated_at": row.get("updated_at"),
                            **metadata,
                        }
                    )
                return products
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error getting popular products: {e}")
            return []

    # Optional methods for advanced recommenders
    def get_recent_interactions(
        self,
        limit: int = 10000,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        try:
            conn = _get_pg_conn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT user_id, product_id, event_type, session_id, timestamp
                            FROM user_views
                            ORDER BY timestamp DESC
                            LIMIT %s OFFSET %s;
                            """,
                            (limit, offset),
                        )
                        rows = cur.fetchall()
                return list(rows) if rows else []
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error getting recent interactions: {e}")
            return []

    def get_session_interactions(
        self, session_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get all interactions for a specific session, ordered by time."""
        try:
            conn = _get_pg_conn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT user_id, product_id, event_type, session_id, timestamp
                            FROM user_views
                            WHERE session_id = %s
                            ORDER BY timestamp ASC
                            LIMIT %s;
                            """,
                            (session_id, limit),
                        )
                        rows = cur.fetchall()
                return list(rows) if rows else []
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error getting session interactions: {e}")
            return []

    def get_interaction_counts(self, limit: int = 50000) -> List[Dict[str, Any]]:
        try:
            conn = _get_pg_conn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT
                                user_id,
                                product_id,
                                SUM(
                                    CASE event_type
                                        WHEN 'view' THEN 1
                                        WHEN 'click' THEN 2
                                        WHEN 'add_to_cart' THEN 3
                                        WHEN 'purchase' THEN 5
                                        ELSE 1
                                    END
                                ) AS count
                            FROM user_views
                            GROUP BY user_id, product_id
                            ORDER BY count DESC
                            LIMIT %s;
                            """,
                            (limit,),
                        )
                        rows = cur.fetchall()
                return list(rows) if rows else []
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error getting interaction counts: {e}")
            return []

    def _update_category_popularity(self, product_id: str) -> None:
        try:
            category = self._get_product_category(product_id)
            if not category:
                return

            conn = _get_pg_conn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO category_popularity (category, view_count, last_updated)
                            VALUES (%s, 1, %s)
                            ON CONFLICT (category) DO UPDATE SET
                                view_count = category_popularity.view_count + 1,
                                last_updated = EXCLUDED.last_updated;
                            """,
                            (category, datetime.utcnow()),
                        )
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error updating category popularity: {e}")

    def _get_product_category(self, product_id: str) -> Optional[str]:
        try:
            conn = _get_pg_conn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT category
                            FROM products
                            WHERE product_id = %s
                            LIMIT 1;
                            """,
                            (product_id,),
                        )
                        row = cur.fetchone()
                        if not row:
                            return None
                        return row.get("category")
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error looking up product category for {product_id}: {e}")
            return None


class PostgresContentStore(ContentStoreInterface):
    """PostgreSQL content storage implementation."""

    def __init__(self):
        _ensure_tables()
        logger.info("Postgres Content Store initialized")

    def store_content(self, content_data: Dict[str, Any]) -> bool:
        try:
            content = {
                "content_id": content_data["id"],
                "title": content_data.get("title", ""),
                "content": content_data.get("content", ""),
                "category": content_data.get("category", ""),
                "tags": json.dumps(content_data.get("tags", [])),
                "status": content_data.get("status", "published"),
                "created_at": (
                    datetime.utcnow()
                    if "created_at" not in content_data
                    else datetime.fromtimestamp(content_data["created_at"])
                ),
                "updated_at": (
                    datetime.utcnow()
                    if "updated_at" not in content_data
                    else datetime.fromtimestamp(content_data["updated_at"])
                ),
            }

            conn = _get_pg_conn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO content (
                                content_id, title, content, category, tags, status, created_at, updated_at
                            )
                            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                            ON CONFLICT (content_id) DO UPDATE SET
                                title = EXCLUDED.title,
                                content = EXCLUDED.content,
                                category = EXCLUDED.category,
                                tags = EXCLUDED.tags,
                                status = EXCLUDED.status,
                                updated_at = EXCLUDED.updated_at;
                            """,
                            (
                                content["content_id"],
                                content["title"],
                                content["content"],
                                content["category"],
                                content["tags"],
                                content["status"],
                                content["created_at"],
                                content["updated_at"],
                            ),
                        )
                logger.debug(f"Stored content {content_data['id']} in Postgres")
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error storing content {content_data.get('id')}: {e}")
            return False

    def get_content(self, content_id: str) -> Optional[Dict[str, Any]]:
        try:
            conn = _get_pg_conn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT *
                            FROM content
                            WHERE content_id = %s;
                            """,
                            (content_id,),
                        )
                        row = cur.fetchone()
                        if not row:
                            return None

                        tags = row.get("tags")
                        if isinstance(tags, str):
                            tags = json.loads(tags)

                        return {
                            "id": row["content_id"],
                            "title": row["title"],
                            "content": row["content"],
                            "category": row["category"],
                            "tags": tags or [],
                            "status": row["status"],
                            "created_at": row.get("created_at"),
                            "updated_at": row.get("updated_at"),
                        }
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error retrieving content {content_id}: {e}")
            return None

    def update_content(self, content_id: str, update_data: Dict[str, Any]) -> bool:
        try:
            fields = []
            values = []

            if "title" in update_data:
                fields.append("title = %s")
                values.append(update_data["title"])
            if "content" in update_data:
                fields.append("content = %s")
                values.append(update_data["content"])
            if "category" in update_data:
                fields.append("category = %s")
                values.append(update_data["category"])
            if "tags" in update_data:
                fields.append("tags = %s::jsonb")
                values.append(json.dumps(update_data["tags"]))
            if "status" in update_data:
                fields.append("status = %s")
                values.append(update_data["status"])

            fields.append("updated_at = %s")
            if "updated_at" in update_data:
                values.append(datetime.fromtimestamp(update_data["updated_at"]))
            else:
                values.append(datetime.utcnow())

            if not fields:
                return True

            values.append(content_id)

            query = f"UPDATE content SET {', '.join(fields)} WHERE content_id = %s"

            conn = _get_pg_conn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(query, tuple(values))
                        return cur.rowcount > 0
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error updating content {content_id}: {e}")
            return False

    def delete_content(self, content_id: str) -> bool:
        try:
            conn = _get_pg_conn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "DELETE FROM content WHERE content_id = %s;",
                            (content_id,),
                        )
                logger.debug(f"Deleted content {content_id} from Postgres")
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error deleting content {content_id}: {e}")
            return False

    def list_content(
        self,
        category: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        try:
            conn = _get_pg_conn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        query = "SELECT * FROM content WHERE 1=1"
                        params = []

                        if category:
                            query += " AND category = %s"
                            params.append(category)

                        if status:
                            query += " AND status = %s"
                            params.append(status)

                        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
                        params.append(limit)
                        params.append(offset)

                        cur.execute(query, tuple(params))
                        rows = cur.fetchall()

                results = []
                for row in rows:
                    tags = row.get("tags")
                    if isinstance(tags, str):
                        tags = json.loads(tags)

                    results.append(
                        {
                            "id": row["content_id"],
                            "title": row["title"],
                            "content": row["content"],
                            "category": row["category"],
                            "tags": tags or [],
                            "status": row["status"],
                            "created_at": row.get("created_at"),
                            "updated_at": row.get("updated_at"),
                        }
                    )
                return results
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error listing content: {e}")
            return []


# Factory functions
def get_postgres_event_processor() -> PostgresEventProcessor:
    return PostgresEventProcessor()


def get_postgres_product_store() -> PostgresProductStore:
    return PostgresProductStore()


def get_postgres_user_behavior() -> PostgresUserBehavior:
    return PostgresUserBehavior()


def get_postgres_content_store() -> PostgresContentStore:
    return PostgresContentStore()

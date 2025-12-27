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
    ]

    # Additional schema evolution for existing databases
    alter_statements = [
        """
        ALTER TABLE user_views
        ADD COLUMN IF NOT EXISTS event_type VARCHAR(32) NOT NULL DEFAULT 'view';
        """
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
        self.event_handler: Optional[Callable[[Dict[str, Any]], None]] = None
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

    def set_event_handler(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        self.event_handler = handler

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
                                        if self.event_handler:
                                            event_data = {
                                                "event_type": event["event_type"],
                                                "product_id": event["product_id"],
                                                "data": event["data"],
                                                "timestamp": event["timestamp"],
                                            }
                                            self.event_handler(event_data)

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
            product = {
                "product_id": product_data["id"],
                "name": product_data.get("name", ""),
                "description": product_data.get("description", ""),
                "category": product_data.get("category", ""),
                "price": float(product_data.get("price", 0) or 0),
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

    def _insert_event(self, user_id: str, product_id: str, event_type: str) -> bool:
        try:
            conn = _get_pg_conn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO user_views (user_id, product_id, event_type, timestamp)
                            VALUES (%s, %s, %s, %s);
                            """,
                            (user_id, product_id, event_type, datetime.utcnow()),
                        )
                # Update category popularity
                self._update_category_popularity(product_id)
                logger.debug(
                    f"Tracked {event_type}: user {user_id} -> product {product_id}"
                )
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error tracking {event_type}: {e}")
            return False

    def track_view(self, user_id: str, product_id: str) -> bool:
        return self._insert_event(user_id, product_id, "view")

    def track_click(self, user_id: str, product_id: str) -> bool:
        return self._insert_event(user_id, product_id, "click")

    def track_add_to_cart(self, user_id: str, product_id: str) -> bool:
        return self._insert_event(user_id, product_id, "add_to_cart")

    def track_purchase(self, user_id: str, product_id: str) -> bool:
        return self._insert_event(user_id, product_id, "purchase")

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
                            SELECT user_id, product_id, event_type, timestamp
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


# Factory functions
def get_postgres_event_processor() -> PostgresEventProcessor:
    return PostgresEventProcessor()


def get_postgres_product_store() -> PostgresProductStore:
    return PostgresProductStore()


def get_postgres_user_behavior() -> PostgresUserBehavior:
    return PostgresUserBehavior()

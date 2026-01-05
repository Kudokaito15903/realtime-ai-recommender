import os
import os
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from loguru import logger

from adapters.interfaces import ContentStoreInterface

def _get_pg_conn():
    dsn = os.getenv("POSTGRES_DSN")
    if not dsn:
        raise ValueError("POSTGRES_DSN is required")
    return psycopg2.connect(dsn, cursor_factory=RealDictCursor)


class PostgresContentStore(ContentStoreInterface):
    """PostgreSQL content storage implementation"""

    def __init__(self):
        self.conn = _get_pg_conn()
        self.conn.autocommit = True
        logger.info("PostgreSQL Content Store initialized")

    # ------------------------------------------------------------------
    def store_content(self, content_data: Dict[str, Any]) -> bool:
        """Insert or update content (UPSERT)"""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO content (
                        content_id, title, content, category,
                        tags, status, created_at, updated_at
                    )
                    VALUES (
                        %(content_id)s, %(title)s, %(content)s, %(category)s,
                        %(tags)s::jsonb, %(status)s, %(created_at)s, %(updated_at)s
                    )
                    ON CONFLICT (content_id)
                    DO UPDATE SET
                        title = EXCLUDED.title,
                        content = EXCLUDED.content,
                        category = EXCLUDED.category,
                        tags = EXCLUDED.tags,
                        status = EXCLUDED.status,
                        updated_at = EXCLUDED.updated_at
                    """,
                    {
                        "content_id": content_data["id"],
                        "title": content_data["title"],
                        "content": content_data["content"],
                        "category": content_data.get("category"),
                        "tags": json.dumps(content_data.get("tags", [])),
                        "status": content_data.get("status", "published"),
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                    },
                )

            logger.debug(f"Stored content {content_data['id']} in PostgreSQL")
            return True

        except Exception as e:
            logger.error(f"Error storing content {content_data.get('id')}: {e}")
            return False

    # ------------------------------------------------------------------
    def get_content(self, content_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve content by ID"""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM content WHERE content_id = %s",
                    (content_id,),
                )
                row = cur.fetchone()

            if not row:
                return None

            return {
                "id": row["content_id"],
                "title": row["title"],
                "content": row["content"],
                "category": row["category"],
                "tags": row["tags"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }

        except Exception as e:
            logger.error(f"Error retrieving content {content_id}: {e}")
            return None

    # ------------------------------------------------------------------
    def update_content(self, content_id: str, update_data: Dict[str, Any]) -> bool:
        """Partial update"""
        try:
            fields = []
            values = {}

            for key in ["title", "content", "category", "status"]:
                if key in update_data:
                    fields.append(f"{key} = %({key})s")
                    values[key] = update_data[key]

            if "tags" in update_data:
                fields.append("tags = %(tags)s::jsonb")
                values["tags"] = json.dumps(update_data["tags"])

            fields.append("updated_at = %(updated_at)s")
            values["updated_at"] = datetime.utcnow()
            values["content_id"] = content_id

            sql = f"""
                UPDATE content
                SET {", ".join(fields)}
                WHERE content_id = %(content_id)s
            """

            with self.conn.cursor() as cur:
                cur.execute(sql, values)

            logger.debug(f"Updated content {content_id}")
            return True

        except Exception as e:
            logger.error(f"Error updating content {content_id}: {e}")
            return False

    # ------------------------------------------------------------------
    def delete_content(self, content_id: str) -> bool:
        """Delete content"""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM content WHERE content_id = %s",
                    (content_id,),
                )

            logger.debug(f"Deleted content {content_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting content {content_id}: {e}")
            return False

    # ------------------------------------------------------------------
    def list_content(
        self,
        category: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List content with filters"""
        try:
            conditions = []
            params = {}

            if category:
                conditions.append("category = %(category)s")
                params["category"] = category

            if status:
                conditions.append("status = %(status)s")
                params["status"] = status

            where_clause = (
                f"WHERE {' AND '.join(conditions)}" if conditions else ""
            )

            sql = f"""
                SELECT *
                FROM content
                {where_clause}
                ORDER BY updated_at DESC
                LIMIT %(limit)s OFFSET %(offset)s
            """

            params.update({"limit": limit, "offset": offset})

            with self.conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

            return [
                {
                    "id": r["content_id"],
                    "title": r["title"],
                    "content": r["content"],
                    "category": r["category"],
                    "tags": r["tags"],
                    "status": r["status"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                }
                for r in rows
            ]

        except Exception as e:
            logger.error(f"Error listing content: {e}")
            return []

def get_postgres_content_store() -> PostgresContentStore:
    return PostgresContentStore()
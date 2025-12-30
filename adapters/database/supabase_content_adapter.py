"""
Content store adapter for CMS (articles, FAQs, policies, guides).
Uses Supabase for storage.
"""

import os
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from loguru import logger
from supabase import create_client, Client

from adapters.interfaces import ContentStoreInterface


class SupabaseContentStore(ContentStoreInterface):
    """Supabase content storage implementation"""

    def __init__(self, url: str, key: str):
        self.url = url
        self.key = key
        self.client: Client = create_client(url, key)
        logger.info(f"Supabase Content Store initialized: {url}")

    def store_content(self, content_data: Dict[str, Any]) -> bool:
        """Store or update content in Supabase"""
        try:
            content = {
                "content_id": content_data["id"],
                "title": content_data["title"],
                "content": content_data["content"],
                "category": content_data["category"],
                "tags": json.dumps(content_data.get("tags", [])),
                "status": content_data.get("status", "published"),
                "created_at": datetime.utcnow().isoformat() if "created_at" not in content_data else datetime.fromtimestamp(content_data["created_at"]).isoformat(),
                "updated_at": datetime.utcnow().isoformat() if "updated_at" not in content_data else datetime.fromtimestamp(content_data["updated_at"]).isoformat(),
            }

            result = (
                self.client.table("content")
                .upsert(content, on_conflict="content_id")
                .execute()
            )

            if result.data:
                logger.debug(f"Stored content {content_data['id']} in Supabase")
                return True
            else:
                logger.error(f"Failed to store content {content_data['id']}")
                return False

        except Exception as e:
            logger.error(f"Error storing content {content_data.get('id')}: {e}")
            return False

    def get_content(self, content_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve content by ID from Supabase"""
        try:
            result = (
                self.client.table("content")
                .select("*")
                .eq("content_id", content_id)
                .single()
                .execute()
            )

            if result.data:
                content = result.data
                return {
                    "id": content["content_id"],
                    "title": content["title"],
                    "content": content["content"],
                    "category": content["category"],
                    "tags": json.loads(content.get("tags", "[]")),
                    "status": content.get("status", "published"),
                    "created_at": content.get("created_at"),
                    "updated_at": content.get("updated_at"),
                }
            else:
                return None

        except Exception as e:
            logger.error(f"Error retrieving content {content_id}: {e}")
            return None

    def update_content(self, content_id: str, update_data: Dict[str, Any]) -> bool:
        """Update content in Supabase"""
        try:
            update_dict = {}
            if "title" in update_data:
                update_dict["title"] = update_data["title"]
            if "content" in update_data:
                update_dict["content"] = update_data["content"]
            if "category" in update_data:
                update_dict["category"] = update_data["category"]
            if "tags" in update_data:
                update_dict["tags"] = json.dumps(update_data["tags"])
            if "status" in update_data:
                update_dict["status"] = update_data["status"]
            if "updated_at" in update_data:
                update_dict["updated_at"] = datetime.fromtimestamp(update_data["updated_at"]).isoformat()

            result = (
                self.client.table("content")
                .update(update_dict)
                .eq("content_id", content_id)
                .execute()
            )

            if result.data:
                logger.debug(f"Updated content {content_id} in Supabase")
                return True
            else:
                return False

        except Exception as e:
            logger.error(f"Error updating content {content_id}: {e}")
            return False

    def delete_content(self, content_id: str) -> bool:
        """Delete content from Supabase"""
        try:
            result = (
                self.client.table("content")
                .delete()
                .eq("content_id", content_id)
                .execute()
            )

            logger.debug(f"Deleted content {content_id} from Supabase")
            return True

        except Exception as e:
            logger.error(f"Error deleting content {content_id}: {e}")
            return False

    def list_content(
        self, 
        category: Optional[str] = None, 
        limit: int = 100, 
        offset: int = 0,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List content with optional filtering"""
        try:
            query = self.client.table("content").select("*")

            if category:
                query = query.eq("category", category)
            
            if status:
                query = query.eq("status", status)

            result = query.range(offset, offset + limit - 1).execute()

            contents = []
            for content in result.data:
                    contents.append(
                    {
                        "id": content["content_id"],
                        "title": content["title"],
                        "content": content["content"],
                        "category": content["category"],
                        "tags": json.loads(content.get("tags", "[]")),
                        "status": content.get("status", "published"),
                        "created_at": content.get("created_at"),
                        "updated_at": content.get("updated_at"),
                    }
                )

            return contents

        except Exception as e:
            logger.error(f"Error listing content: {e}")
            return []


def get_supabase_content_store() -> SupabaseContentStore:
    """Factory function for Supabase content store"""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required")
    return SupabaseContentStore(url, key)
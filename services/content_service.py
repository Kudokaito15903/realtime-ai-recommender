"""
Content management service for admin CMS.
Handles CRUD for articles, FAQs, policies, guides, etc.
"""

import os
import time
import uuid
from typing import List, Dict, Any, Optional
from loguru import logger

from adapters.factory import get_content_event_processor, get_content_store
from domain.embeddings.product_embeddings import get_embedding_model


class ContentService:
    def __init__(self):
        self.event_processor = get_content_event_processor()
        self.content_store = get_content_store()
        self.embedding_model = get_embedding_model()

    def create_content(self, content_data: Dict[str, Any]) -> str:
        content_id = str(uuid.uuid4())
        content_data["id"] = content_id
        content_data["created_at"] = time.time()
        content_data["updated_at"] = time.time()

        ok = self.content_store.store_content(content_data)
        if not ok:
            raise ValueError("Failed to store content")

        # Publish event for embedding update
        if self.event_processor:
            event_data = {
                "event_type": "create",
                'entity_type': 'content',
                "timestamp": time.time(),
                "data": content_data,
            }
            self.event_processor.publish_event(event_data)

        logger.info(f"Created content {content_id}: {content_data.get('title')}")
        return content_id

    def get_content(self, content_id: str) -> Optional[Dict[str, Any]]:
        return self.content_store.get_content(content_id)

    def update_content(self, content_id: str, update_data: Dict[str, Any]) -> bool:
        update_data["updated_at"] = time.time()
        ok = self.content_store.update_content(content_id, update_data)
        update_data["id"] = content_id
        if ok and self.event_processor:
            event_data = {
                "event_type": "update",
                "entity_type": "content",
                "timestamp": time.time(),
                "data": update_data,
            }
            self.event_processor.publish_event(event_data)
        return ok

    def delete_content(self, content_id: str) -> bool:
        ok = self.content_store.delete_content(content_id)
        if ok and self.event_processor:
            event_data = {
                "content_id": content_id,
                "event_type": "delete",
                "timestamp": time.time(),
            }
            self.event_processor.publish_event(event_data)
        return ok

    def list_content(
        self, 
        category: Optional[str] = None, 
        limit: int = 100,
        offset: int = 0,
        search: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List content with filtering, pagination, and search.
        """
        # If search is provided, use vector search
        if search:
            return self.search_content(query=search, category=category, limit=limit)
        
        # Otherwise, use regular list with filters
        results = self.content_store.list_content(
            category=category, 
            limit=limit, 
            offset=offset,
            status=status
        )
        
        # Filter by search term if provided (text search fallback)
        if search:
            search_lower = search.lower()
            results = [
                item for item in results
                if search_lower in item.get("title", "").lower() or 
                   search_lower in item.get("content", "").lower()
            ]
        
        return results

    def search_content(
        self, 
        query: str, 
        category: Optional[str] = None, 
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Semantic search for content using vector similarity.
        """
        try:
            from adapters.factory import get_vector_store
            
            vector_store = get_vector_store()
            if not vector_store:
                # Fallback to text search
                all_content = self.content_store.list_content(category=category, limit=1000)
                query_lower = query.lower()
                results = [
                    item for item in all_content
                    if query_lower in item.get("title", "").lower() or 
                       query_lower in item.get("content", "").lower()
                ]
                return results[:limit]
            
            # Generate query embedding
            query_embedding = self.embedding_model.get_embedding(query)
            
            # Search in vector store
            candidates = vector_store.find_similar_products(
                embedding=query_embedding,
                limit=limit * 2,
                min_score=0.3
            )
            
            # Filter for content type and category
            results = []
            for candidate in candidates:
                metadata = candidate.get("metadata", {}) or {}
                if metadata.get("type") != "content":
                    continue
                
                if category and metadata.get("category") != category:
                    continue
                
                content_id = candidate.get("product_id")  # Reusing product_id field for content_id
                if not content_id:
                    continue
                
                # Get full content details
                content = self.content_store.get_content(content_id)
                if content:
                    content["similarity_score"] = candidate.get("similarity_score", 0.0)
                    results.append(content)
            
            # Sort by similarity score
            results.sort(key=lambda x: x.get("similarity_score", 0.0), reverse=True)
            return results[:limit]
            
        except Exception as e:
            logger.error(f"Error in semantic search: {e}")
            # Fallback to text search
            all_content = self.content_store.list_content(category=category, limit=1000)
            query_lower = query.lower()
            results = [
                item for item in all_content
                if query_lower in item.get("title", "").lower() or 
                   query_lower in item.get("content", "").lower()
            ]
            return results[:limit]

    def get_categories(self) -> List[str]:
        """
        Get list of all available content categories.
        """
        try:
            all_content = self.content_store.list_content(limit=10000)
            categories = set()
            for item in all_content:
                cat = item.get("category")
                if cat:
                    categories.add(cat)
            return sorted(list(categories))
        except Exception as e:
            logger.error(f"Error getting categories: {e}")
            return []
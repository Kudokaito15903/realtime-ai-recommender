"""
Supabase adapters for event processing and data storage.
This replaces Redis Streams with Supabase real-time events and PostgreSQL storage.
"""

import os
import time
import json
import asyncio
import threading
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from loguru import logger
from supabase import create_client, Client

from .interfaces import EventProcessorInterface, ProductStoreInterface, UserBehaviorInterface


class SupabaseEventProcessor(EventProcessorInterface):
    """Supabase real-time event processor implementation"""

    def __init__(self, url: str, key: str):
        self.url = url
        self.key = key
        self.client: Client = create_client(url, key)
        self.event_handler: Optional[Callable[[Dict[str, Any]], None]] = None
        self.running = False
        self.consumer_thread = None

        logger.info(f"Supabase Event Processor initialized: {url}")

    def publish_product_created(self, product_data: Dict[str, Any]) -> Optional[str]:
        """Publish a product created event to Supabase"""
        return self._publish_event("create", product_data['id'], product_data)

    def publish_product_updated(self, product_id: str, update_data: Dict[str, Any]) -> Optional[str]:
        """Publish a product updated event to Supabase"""
        return self._publish_event("update", product_id, update_data)

    def publish_product_deleted(self, product_id: str) -> Optional[str]:
        """Publish a product deleted event to Supabase"""
        return self._publish_event("delete", product_id, {'id': product_id})

    def _publish_event(self, event_type: str, product_id: str, data: Dict[str, Any]) -> Optional[str]:
        """Publish an event to Supabase events table"""
        try:
            event = {
                'event_type': event_type,
                'product_id': product_id,
                'data': json.dumps(data),
                'timestamp': datetime.utcnow().isoformat(),
                'processed': False
            }

            # Insert event into events table
            result = self.client.table('product_events').insert(event).execute()

            if result.data:
                event_id = result.data[0]['id']
                logger.info(f"Published {event_type} event for product {product_id}: {event_id}")
                return str(event_id)
            else:
                logger.error(f"Failed to publish {event_type} event for product {product_id}")
                return None

        except Exception as e:
            logger.error(f"Error publishing {event_type} event for product {product_id}: {e}")
            return None

    def start_consumer(self, consumer_id: Optional[str] = None) -> None:
        """Start consuming events from Supabase"""
        if self.running:
            logger.warning("Event consumer is already running")
            return

        self.running = True
        self.consumer_thread = threading.Thread(
            target=self._consume_loop,
            args=(consumer_id,),
            daemon=True
        )
        self.consumer_thread.start()
        logger.info(f"Started Supabase event consumer: {consumer_id}")

    def stop_consumer(self) -> None:
        """Stop consuming events"""
        if not self.running:
            logger.warning("Event consumer is not running")
            return

        self.running = False
        if self.consumer_thread and self.consumer_thread.is_alive():
            self.consumer_thread.join(timeout=5.0)
        logger.info("Stopped Supabase event consumer")

    def set_event_handler(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Set the function to handle incoming events"""
        self.event_handler = handler

    def _consume_loop(self, consumer_id: Optional[str]) -> None:
        """Main loop for consuming events from Supabase"""
        try:
            while self.running:
                try:
                    # Fetch unprocessed events
                    result = (
                        self.client.table('product_events')
                        .select('*')
                        .eq('processed', False)
                        .order('created_at', desc=False)
                        .limit(10)
                        .execute()
                    )

                    events = result.data
                    if not events:
                        time.sleep(2)  # Wait before checking again
                        continue

                    # Process each event
                    for event in events:
                        try:
                            if self.event_handler:
                                # Parse the event data
                                event_data = {
                                    'event_type': event['event_type'],
                                    'product_id': event['product_id'],
                                    'data': json.loads(event['data']),
                                    'timestamp': event['timestamp']
                                }

                                # Call the event handler
                                self.event_handler(event_data)

                            # Mark event as processed
                            self.client.table('product_events').update({
                                'processed': True,
                                'processed_at': datetime.utcnow().isoformat()
                            }).eq('id', event['id']).execute()

                            logger.debug(f"Processed event {event['id']}: {event['event_type']}")

                        except Exception as e:
                            logger.error(f"Error processing event {event['id']}: {e}")

                except Exception as e:
                    logger.error(f"Error in event consumer loop: {e}")
                    time.sleep(1)  # Avoid tight loop on persistent errors

        except Exception as e:
            logger.error(f"Unexpected error in event consumer loop: {e}")
            self.running = False


class SupabaseProductStore(ProductStoreInterface):
    """Supabase product data storage implementation"""

    def __init__(self, url: str, key: str):
        self.url = url
        self.key = key
        self.client: Client = create_client(url, key)
        logger.info(f"Supabase Product Store initialized: {url}")

    def store_product(self, product_data: Dict[str, Any]) -> bool:
        """Store or update a product in Supabase"""
        try:
            # Prepare product data for storage
            product = {
                'product_id': product_data['id'],
                'name': product_data.get('name', ''),
                'description': product_data.get('description', ''),
                'category': product_data.get('category', ''),
                'price': product_data.get('price', 0),
                'metadata': json.dumps({k: v for k, v in product_data.items()
                                      if k not in ['id', 'name', 'description', 'category', 'price']}),
                'updated_at': datetime.utcnow().isoformat()
            }

            # Upsert (insert or update)
            result = (
                self.client.table('products')
                .upsert(product, on_conflict='product_id')
                .execute()
            )

            if result.data:
                logger.debug(f"Stored product {product_data['id']} in Supabase")
                return True
            else:
                logger.error(f"Failed to store product {product_data['id']}")
                return False

        except Exception as e:
            logger.error(f"Error storing product {product_data['id']}: {e}")
            return False

    def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a product by ID from Supabase"""
        try:
            result = (
                self.client.table('products')
                .select('*')
                .eq('product_id', product_id)
                .single()
                .execute()
            )

            if result.data:
                product = result.data
                # Merge metadata back into the main product dict
                metadata = json.loads(product.get('metadata', '{}'))
                return {
                    'id': product['product_id'],
                    'name': product['name'],
                    'description': product['description'],
                    'category': product['category'],
                    'price': product['price'],
                    'created_at': product.get('created_at'),
                    'updated_at': product.get('updated_at'),
                    **metadata
                }
            else:
                return None

        except Exception as e:
            logger.error(f"Error retrieving product {product_id}: {e}")
            return None

    def delete_product(self, product_id: str) -> bool:
        """Delete a product from Supabase"""
        try:
            result = (
                self.client.table('products')
                .delete()
                .eq('product_id', product_id)
                .execute()
            )

            logger.debug(f"Deleted product {product_id} from Supabase")
            return True

        except Exception as e:
            logger.error(f"Error deleting product {product_id}: {e}")
            return False

    def list_products(self, category: Optional[str] = None,
                      limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """List products with optional filtering"""
        try:
            query = self.client.table('products').select('*')

            if category:
                query = query.eq('category', category)

            result = query.range(offset, offset + limit - 1).execute()

            products = []
            for product in result.data:
                metadata = json.loads(product.get('metadata', '{}'))
                products.append({
                    'id': product['product_id'],
                    'name': product['name'],
                    'description': product['description'],
                    'category': product['category'],
                    'price': product['price'],
                    'created_at': product.get('created_at'),
                    'updated_at': product.get('updated_at'),
                    **metadata
                })

            return products

        except Exception as e:
            logger.error(f"Error listing products: {e}")
            return []

    def search_products(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search products by text query using Supabase full-text search"""
        try:
            # Use Supabase text search (requires full-text search setup)
            result = (
                self.client.table('products')
                .select('*')
                .text_search('name', query)
                .limit(limit)
                .execute()
            )

            products = []
            for product in result.data:
                metadata = json.loads(product.get('metadata', '{}'))
                products.append({
                    'id': product['product_id'],
                    'name': product['name'],
                    'description': product['description'],
                    'category': product['category'],
                    'price': product['price'],
                    'created_at': product.get('created_at'),
                    'updated_at': product.get('updated_at'),
                    **metadata
                })

            return products

        except Exception as e:
            logger.error(f"Error searching products: {e}")
            return []


class SupabaseUserBehavior(UserBehaviorInterface):
    """Supabase user behavior tracking implementation"""

    def __init__(self, url: str, key: str):
        self.url = url
        self.key = key
        self.client: Client = create_client(url, key)
        logger.info(f"Supabase User Behavior initialized: {url}")

    def track_view(self, user_id: str, product_id: str) -> bool:
        """Track a product view by user"""
        try:
            view_data = {
                'user_id': user_id,
                'product_id': product_id,
                'timestamp': datetime.utcnow().isoformat()
            }

            result = self.client.table('user_views').insert(view_data).execute()

            if result.data:
                # Update category popularity
                self._update_category_popularity(product_id)
                logger.debug(f"Tracked view: user {user_id} -> product {product_id}")
                return True
            else:
                return False

        except Exception as e:
            logger.error(f"Error tracking view: {e}")
            return False

    def get_user_history(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get user's recent product views"""
        try:
            result = (
                self.client.table('user_views')
                .select('*, products(name, category, price)')
                .eq('user_id', user_id)
                .order('timestamp', desc=True)
                .limit(limit)
                .execute()
            )

            return result.data or []

        except Exception as e:
            logger.error(f"Error getting user history: {e}")
            return []

    def get_popular_products(self, category: Optional[str] = None,
                            limit: int = 10) -> List[Dict[str, Any]]:
        """Get popular products by view count"""
        try:
            # This would require a more complex query or materialized view
            # For now, return recent products
            query = self.client.table('products').select('*')
            if category:
                query = query.eq('category', category)

            result = query.order('created_at', desc=True).limit(limit).execute()
            return result.data or []

        except Exception as e:
            logger.error(f"Error getting popular products: {e}")
            return []

    def _update_category_popularity(self, product_id: str) -> None:
        """Update category popularity based on product view"""
        try:
            # Get product category
            product = self.get_product(product_id)
            if product and product.get('category'):
                category = product['category']

                # Increment category view count (would need proper implementation)
                # This is a simplified version
                self.client.table('category_popularity').upsert({
                    'category': category,
                    'view_count': 1,  # This should be incremented properly
                    'last_updated': datetime.utcnow().isoformat()
                }, on_conflict='category').execute()

        except Exception as e:
            logger.error(f"Error updating category popularity: {e}")


# Factory functions
def get_supabase_event_processor() -> SupabaseEventProcessor:
    """Factory function to create Supabase event processor"""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables are required")

    return SupabaseEventProcessor(url, key)


def get_supabase_product_store() -> SupabaseProductStore:
    """Factory function to create Supabase product store"""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables are required")

    return SupabaseProductStore(url, key)


def get_supabase_user_behavior() -> SupabaseUserBehavior:
    """Factory function to create Supabase user behavior tracker"""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables are required")

    return SupabaseUserBehavior(url, key)
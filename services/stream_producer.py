 
import os
import json
import redis
from typing import Dict, Any, Optional
from datetime import datetime
from loguru import logger

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_DB, PRODUCT_STREAM_KEY


class ProductEventProducer:
    """Service for publishing product events to Redis Streams"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProductEventProducer, cls).__new__(cls)
            # Initialize Redis client
            cls._instance.redis = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                password=REDIS_PASSWORD,
                db=REDIS_DB,
                decode_responses=True
            )
            logger.info(f"Product Event Producer initialized: {REDIS_HOST}:{REDIS_PORT}")
        return cls._instance
    
    def publish_product_created(self, product_data: Dict[str, Any]) -> Optional[str]:
        """Publish a product created event to the stream"""
        event = {
            'event_type': 'create',
            'timestamp': datetime.utcnow().isoformat(),
            'data': json.dumps(product_data)
        }
        return self._publish_event(product_data['id'], event)
    
    def publish_product_updated(self, product_id: str, update_data: Dict[str, Any]) -> Optional[str]:
        """Publish a product updated event to the stream"""
        event = {
            'event_type': 'update',
            'timestamp': datetime.utcnow().isoformat(),
            'data': json.dumps(update_data)
        }
        return self._publish_event(product_id, event)
    
    def publish_product_deleted(self, product_id: str) -> Optional[str]:
        """Publish a product deleted event to the stream"""
        event = {
            'event_type': 'delete',
            'timestamp': datetime.utcnow().isoformat(),
            'data': json.dumps({'id': product_id})
        }
        return self._publish_event(product_id, event)
    
    def _publish_event(self, product_id: str, event: Dict[str, Any]) -> Optional[str]:
        """Publish an event to the Redis Stream"""
        try:
            # Add the product_id to the event data
            event['product_id'] = product_id
            
            # Publish to Redis Stream
            event_id = self.redis.xadd(PRODUCT_STREAM_KEY, event)
            
            logger.info(f"Published {event['event_type']} event for product {product_id}: {event_id}")
            return event_id
        except Exception as e:
            logger.error(f"Error publishing {event['event_type']} event for product {product_id}: {e}")
            return None


# Convenience function to get the singleton instance
def get_product_event_producer() -> ProductEventProducer:
    return ProductEventProducer()
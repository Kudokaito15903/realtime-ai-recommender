"""
Redis adapter that implements the new interfaces.
This provides backward compatibility while using the new abstraction layer.
"""

import json
import time
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime
from loguru import logger

from .interfaces import EventProcessorInterface
from services.stream_producer import get_product_event_producer


class RedisEventProcessor(EventProcessorInterface):
    """Redis Streams event processor that implements the new interface"""

    def __init__(self):
        self.producer = get_product_event_producer()
        self.event_handler: Optional[Callable[[Dict[str, Any]], None]] = None
        self.consumer = None
        self.running = False

        logger.info("Redis Event Processor initialized (compatibility mode)")

    def publish_product_created(self, product_data: Dict[str, Any]) -> Optional[str]:
        """Publish a product created event using Redis Streams"""
        return self.producer.publish_product_created(product_data)

    def publish_product_updated(self, product_id: str, update_data: Dict[str, Any]) -> Optional[str]:
        """Publish a product updated event using Redis Streams"""
        return self.producer.publish_product_updated(product_id, update_data)

    def publish_product_deleted(self, product_id: str) -> Optional[str]:
        """Publish a product deleted event using Redis Streams"""
        return self.producer.publish_product_deleted(product_id)

    def start_consumer(self, consumer_id: Optional[str] = None) -> None:
        """Start consuming events from Redis Streams"""
        if self.running:
            logger.warning("Redis event consumer is already running")
            return

        try:
            from services.stream_consumer import ProductEventConsumer

            # Create and configure the Redis consumer
            self.consumer = ProductEventConsumer(consumer_id)

            # Set up event handling if a handler is configured
            if self.event_handler:
                # We need to adapt the Redis consumer to use our event handler
                original_process_message = self.consumer._process_message

                def adapted_process_message(message_id: str, message_data: Dict[str, str]):
                    """Adapt Redis consumer messages to our interface"""
                    try:
                        # Convert Redis message format to our standard format
                        event_data = {
                            'event_type': message_data.get('event_type'),
                            'product_id': message_data.get('product_id'),
                            'data': json.loads(message_data.get('data', '{}')),
                            'timestamp': message_data.get('timestamp')
                        }

                        # Call our event handler
                        self.event_handler(event_data)

                    except Exception as e:
                        logger.error(f"Error in adapted event handler: {e}")
                        # Fall back to original processing
                        original_process_message(message_id, message_data)

                # Replace the process message method
                self.consumer._process_message = adapted_process_message

            # Start the Redis consumer
            self.consumer.start()
            self.running = True

            logger.info(f"Started Redis event consumer: {consumer_id}")

        except Exception as e:
            logger.error(f"Error starting Redis event consumer: {e}")
            raise

    def stop_consumer(self) -> None:
        """Stop consuming events"""
        if not self.running:
            logger.warning("Redis event consumer is not running")
            return

        try:
            if self.consumer:
                self.consumer.stop()
            self.running = False
            logger.info("Stopped Redis event consumer")

        except Exception as e:
            logger.error(f"Error stopping Redis event consumer: {e}")

    def set_event_handler(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Set the function to handle incoming events"""
        self.event_handler = handler
        logger.debug("Set event handler for Redis event processor")
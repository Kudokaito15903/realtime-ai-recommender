import os
import json
import time
import redis
import threading
import signal
import sys
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from loguru import logger

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_DB,
    PRODUCT_STREAM_KEY, PRODUCT_STREAM_GROUP, PRODUCT_STREAM_CONSUMER
)
from models.embeddings import get_embedding_model
from services.vector_store import get_vector_store


class ProductEventConsumer:
    """Service for consuming product events from Redis Streams and processing them"""
    
    def __init__(self, consumer_id: Optional[str] = None):
        # Initialize Redis client
        self.redis = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            db=REDIS_DB,
            decode_responses=True
        )
        
        # Set consumer ID
        self.consumer_id = consumer_id or PRODUCT_STREAM_CONSUMER.format(threading.get_ident())
        
        # Initialize services
        self.embedding_model = get_embedding_model()
        self.vector_store = get_vector_store()
        
        # Flag for controlling the consumer loop
        self.running = False
        self.thread = None
        
        logger.info(f"Product Event Consumer initialized: {self.consumer_id}")
        
        # Create consumer group if it doesn't exist
        self._ensure_consumer_group()
    
    def _ensure_consumer_group(self) -> None:
        """Ensure the consumer group exists in Redis"""
        try:
            # Check if stream exists
            stream_info = self.redis.exists(PRODUCT_STREAM_KEY)
            if not stream_info:
                # Create stream with a dummy message that can be deleted later
                self.redis.xadd(PRODUCT_STREAM_KEY, {'init': 'true'})
                logger.info(f"Created stream {PRODUCT_STREAM_KEY}")
            
            # Create consumer group
            self.redis.xgroup_create(PRODUCT_STREAM_KEY, PRODUCT_STREAM_GROUP, id='0', mkstream=True)
            logger.info(f"Created consumer group {PRODUCT_STREAM_GROUP}")
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP Consumer Group name already exists" in str(e):
                logger.info(f"Consumer group {PRODUCT_STREAM_GROUP} already exists")
            else:
                logger.error(f"Error creating consumer group: {e}")
                raise
    
    def start(self, batch_size: int = 10, block_ms: int = 2000) -> None:
        """Start consuming events in a separate thread"""
        if self.running:
            logger.warning("Consumer is already running")
            return
        
        self.running = True
        self.thread = threading.Thread(
            target=self._consume_loop,
            args=(batch_size, block_ms),
            daemon=True
        )
        self.thread.start()
        logger.info(f"Started product event consumer: {self.consumer_id}")
    
    def stop(self) -> None:
        """Stop consuming events"""
        if not self.running:
            logger.warning("Consumer is not running")
            return
        
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5.0)
        logger.info(f"Stopped product event consumer: {self.consumer_id}")
    
    def _consume_loop(self, batch_size: int, block_ms: int) -> None:
        """Main loop for consuming events"""
        try:
            while self.running:
                # Read messages from the stream with our consumer group
                streams = {PRODUCT_STREAM_KEY: '>'}  # Read new messages
                
                try:
                    # Read messages
                    messages = self.redis.xreadgroup(
                        groupname=PRODUCT_STREAM_GROUP,
                        consumername=self.consumer_id,
                        streams=streams,
                        count=batch_size,
                        block=block_ms
                    )
                    
                    if not messages:
                        # No new messages, continue
                        continue
                    
                    # Process messages
                    for stream_name, stream_messages in messages:
                        for message_id, message_data in stream_messages:
                            try:
                                # Process the message
                                self._process_message(message_id, message_data)
                                
                                # Acknowledge successful processing
                                self.redis.xack(PRODUCT_STREAM_KEY, PRODUCT_STREAM_GROUP, message_id)
                            except Exception as e:
                                logger.error(f"Error processing message {message_id}: {e}")
                                # Note: We don't ack the message so it will be reprocessed
                
                except redis.exceptions.ResponseError as e:
                    logger.error(f"Redis error in consumer loop: {e}")
                    time.sleep(1)  # Avoid tight loop in case of persistent errors
                    
        except Exception as e:
            logger.error(f"Unexpected error in consumer loop: {e}")
            self.running = False
    
    def _process_message(self, message_id: str, message_data: Dict[str, str]) -> None:
        """Process a single message from the stream"""
        # Extract message fields
        event_type = message_data.get('event_type')
        product_id = message_data.get('product_id')
        timestamp = message_data.get('timestamp')
        
        logger.debug(f"Processing {event_type} event for product {product_id} from {timestamp}")
        
        if not event_type or not product_id:
            logger.warning(f"Invalid message format, missing fields: {message_data}")
            return
        
        # Process based on event type
        if event_type == 'create' or event_type == 'update':
            # Parse the product data
            try:
                data_str = message_data.get('data', '{}')
                product_data = json.loads(data_str)
                
                # For updates, make sure we have the product ID
                if 'id' not in product_data:
                    product_data['id'] = product_id
                
                # Generate embedding for the product
                start_time = time.time()
                product_embedding = self.embedding_model.get_product_embedding(product_data)
                
                # Store in vector database with metadata
                metadata = {
                    'category': product_data.get('category', 'unknown'),
                    'name': product_data.get('name', 'unknown'),
                    'price': str(product_data.get('price', 0)),
                }
                
                self.vector_store.store_product_embedding(
                    product_id=product_id,
                    embedding=product_embedding,
                    metadata=metadata
                )
                
                logger.info(f"Processed {event_type} for product {product_id} in {time.time() - start_time:.4f}s")
                
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing product data: {e}")
            except Exception as e:
                logger.error(f"Error processing {event_type} event: {e}")
        
        elif event_type == 'delete':
            # Delete embedding from vector store
            self.vector_store.delete_product_embedding(product_id)
            logger.info(f"Deleted embedding for product {product_id}")
        
        else:
            logger.warning(f"Unknown event type: {event_type}")


# Function to start a consumer process
def start_consumer_process(consumer_id: Optional[str] = None) -> None:
    """Start a consumer process that handles shutdown gracefully"""
    consumer = ProductEventConsumer(consumer_id)
    
    # Set up signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        logger.info(f"Received shutdown signal, stopping consumer: {consumer.consumer_id}")
        consumer.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start consuming
    consumer.start()
    
    # Keep the process alive
    while True:
        time.sleep(1)


# Entry point for running as a script
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Product Event Consumer')
    parser.add_argument('--consumer-id', type=str, help='Unique consumer ID')
    args = parser.parse_args()
    
    # Configure logging
    logger.info(f"Starting product event consumer process")
    
    # Start the consumer
    start_consumer_process(args.consumer_id)
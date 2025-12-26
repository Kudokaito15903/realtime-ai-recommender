"""
Modern stream consumer using the new adapter system.
This replaces the Redis-specific consumer with a backend-agnostic implementation.
"""

import os
import time
import signal
import sys
import threading
from loguru import logger

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.factory import get_event_processor, get_vector_store
from models.embeddings import get_embedding_model


class ModernProductEventConsumer:
    """Modern product event consumer using adapter pattern"""

    def __init__(self, consumer_id: str = None):
        self.consumer_id = consumer_id or f"modern-worker-{threading.get_ident()}"

        # Initialize services using the adapter factory
        self.event_processor = get_event_processor()
        self.vector_store = get_vector_store()
        self.embedding_model = get_embedding_model()

        # Set up event handling
        self.event_processor.set_event_handler(self._handle_event)

        logger.info(f"Modern Product Event Consumer initialized: {self.consumer_id}")

    def _handle_event(self, event_data: dict) -> None:
        """Handle incoming product events (backend-agnostic)"""
        event_type = event_data.get('event_type')
        product_id = event_data.get('product_id')
        data = event_data.get('data', {})
        timestamp = event_data.get('timestamp')

        logger.debug(f"Processing {event_type} event for product {product_id} from {timestamp}")

        if not event_type or not product_id:
            logger.warning(f"Invalid event format, missing fields: {event_data}")
            return

        try:
            if event_type in ['create', 'update']:
                self._process_product_upsert(product_id, data)
            elif event_type == 'delete':
                self._process_product_delete(product_id)
            else:
                logger.warning(f"Unknown event type: {event_type}")

        except Exception as e:
            logger.error(f"Error processing {event_type} event for product {product_id}: {e}")

    def _process_product_upsert(self, product_id: str, product_data: dict) -> None:
        """Process product create/update events"""
        try:
            # Ensure product ID is in the data
            if 'id' not in product_data:
                product_data['id'] = product_id

            # Generate embedding for the product
            start_time = time.time()
            product_embedding = self.embedding_model.get_product_embedding(product_data)

            # Prepare metadata for vector storage
            metadata = {
                'category': product_data.get('category', 'unknown'),
                'name': product_data.get('name', 'unknown'),
                'price': str(product_data.get('price', 0)),
                'description': product_data.get('description', ''),
            }

            # Store in vector database
            success = self.vector_store.store_product_embedding(
                product_id=product_id,
                embedding=product_embedding,
                metadata=metadata
            )

            if success:
                processing_time = time.time() - start_time
                logger.info(f"Processed product {product_id} in {processing_time:.4f}s")
            else:
                logger.error(f"Failed to store embedding for product {product_id}")

        except Exception as e:
            logger.error(f"Error processing product upsert for {product_id}: {e}")

    def _process_product_delete(self, product_id: str) -> None:
        """Process product delete events"""
        try:
            success = self.vector_store.delete_product_embedding(product_id)
            if success:
                logger.info(f"Deleted embedding for product {product_id}")
            else:
                logger.error(f"Failed to delete embedding for product {product_id}")

        except Exception as e:
            logger.error(f"Error processing product delete for {product_id}: {e}")

    def start(self) -> None:
        """Start the event consumer"""
        try:
            self.event_processor.start_consumer(self.consumer_id)
            logger.info(f"Modern event consumer started: {self.consumer_id}")
        except Exception as e:
            logger.error(f"Error starting modern event consumer: {e}")
            raise

    def stop(self) -> None:
        """Stop the event consumer"""
        try:
            self.event_processor.stop_consumer()
            logger.info(f"Modern event consumer stopped: {self.consumer_id}")
        except Exception as e:
            logger.error(f"Error stopping modern event consumer: {e}")


def start_modern_consumer_process(consumer_id: str = None) -> None:
    """Start a modern consumer process with graceful shutdown"""
    consumer = ModernProductEventConsumer(consumer_id)

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
    logger.info(f"Modern consumer {consumer.consumer_id} is running. Press Ctrl+C to stop.")
    while True:
        time.sleep(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Modern Product Event Consumer')
    parser.add_argument('--consumer-id', type=str, help='Unique consumer ID')
    args = parser.parse_args()

    # Configure logging
    logger.info("Starting modern product event consumer process")

    # Start the consumer
    start_modern_consumer_process(args.consumer_id)
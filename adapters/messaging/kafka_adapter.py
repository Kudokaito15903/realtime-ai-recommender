"""
Kafka messaging adapter for event processing - FIXED VERSION
"""

import os
import json
import threading
import time
from typing import Dict, Any, Optional, Callable
from loguru import logger
from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError


class KafkaEventProcessor:
    """Kafka event processor implementation"""

    def __init__(self, bootstrap_servers: str, topic: str, group_id: str):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.group_id = group_id

        self.producer = None
        self.consumer = None
        self.running = False  # ✅ FIX: Changed from True to False
        self.consumer_thread = None
        self.event_handlers: List[Callable[[Dict[str, Any]], None]] = []
        
        # ✅ FIX: Add thread lock for safety
        self._lock = threading.Lock()

        self._initialize_producer()

        logger.info(
            f"Kafka Event Processor initialized: {bootstrap_servers}, topic={topic}"
        )

    def _initialize_producer(self):
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                # ✅ FIX: Add retry configuration
                retries=3,
                max_in_flight_requests_per_connection=1,
                acks='all'
            )
            logger.info("Kafka producer initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Kafka producer: {e}")
            raise

    def publish_product_created(self, product_data: Dict[str, Any]) -> Optional[str]:
        return self._publish_event("create", product_data["id"], product_data)

    def publish_product_updated(
        self, product_id: str, update_data: Dict[str, Any]
    ) -> Optional[str]:
        return self._publish_event("update", product_id, update_data)

    def publish_product_deleted(self, product_id: str) -> Optional[str]:
        return self._publish_event("delete", product_id, {"id": product_id})

    def publish_event(self, event_data: Dict[str, Any]) -> Optional[str]:
        """Publish a generic event (for compatibility with other adapters)"""
        event_type = event_data.get("event_type", "unknown")
        product_id = event_data.get("id") or event_data.get("product_id", "unknown")
        data = event_data.get("data", event_data)
        return self._publish_event(event_type, product_id, data)

    def _publish_event(
        self, event_type: str, product_id: str, data: Dict[str, Any]
    ) -> Optional[str]:
        with self._lock:
            if not self.producer:
                logger.warning("Kafka producer not available, skipping event publish")
                return None

        try:
            event = {
                "event_type": event_type,
                "product_id": product_id,
                "data": data,
                "timestamp": time.time(),
            }

            future = self.producer.send(self.topic, event)
            record_metadata = future.get(timeout=10)

            logger.debug(
                f"Published {event_type} event for product {product_id} to partition {record_metadata.partition}"
            )
            return f"{record_metadata.partition}:{record_metadata.offset}"

        except KafkaError as e:
            logger.error(
                f"Kafka error publishing {event_type} event for product {product_id}: {e}"
            )
            return None
        except Exception as e:
            logger.error(
                f"Error publishing {event_type} event for product {product_id}: {e}"
            )
            return None

    def start_consumer(self, consumer_id: Optional[str] = None) -> None:
        # ✅ FIX: Correct logic check
        with self._lock:
            if self.running or (self.consumer_thread and self.consumer_thread.is_alive()):
                logger.warning("Kafka consumer is already running")
                return
            
            self.running = True

        self.consumer_thread = threading.Thread(
            target=self._consume_loop, args=(consumer_id,), daemon=True
        )
        self.consumer_thread.start()
        logger.info(f"Started Kafka consumer: {consumer_id or 'default'}")

    def stop_consumer(self) -> None:
        with self._lock:
            if not self.running:
                return
            self.running = False

        if self.consumer_thread and self.consumer_thread.is_alive():
            self.consumer_thread.join(timeout=5.0)

        # ✅ FIX: Thread-safe consumer cleanup
        with self._lock:
            if self.consumer:
                try:
                    self.consumer.close()
                except Exception as e:
                    logger.error(f"Error closing consumer: {e}")
                finally:
                    self.consumer = None

        logger.info("Stopped Kafka consumer")

    def add_event_handler(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Add the callback handler for processing events"""
        with self._lock:
            self.event_handlers.append(handler)

    def _consume_loop(self, consumer_id: Optional[str]) -> None:
        try:
            logger.info(
            f"Initializing Kafka consumer | "
            f"bootstrap={self.bootstrap_servers} | "
            f"topic={self.topic} | "
            f"group_id={self.group_id}"
        )

            self.consumer = KafkaConsumer(
                self.topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                value_deserializer=lambda x: json.loads(x.decode("utf-8")),
                auto_offset_reset="earliest",
                enable_auto_commit=False,  # ✅ FIX: Manual commit for reliability
                session_timeout_ms=30000,
                max_poll_records=100
            )

            logger.info("Kafka consumer connected and listening...")
            logger.info(f"Consumer ID: {consumer_id or 'default'}")
            logger.info(f"Subscribed to topic: {self.topic}")
            logger.info(f"Group ID: {self.group_id}")
            while self.running:
                # Poll for messages
                message_batch = self.consumer.poll(timeout_ms=1000)

                for partition, messages in message_batch.items():
                    for message in messages:
                        if not self.running:
                            break

                        try:
                            event_data = message.value
                            logger.debug(
                                f"Received Kafka message: {event_data.get('event_type')}"
                            )

                            # ✅ FIX: Thread-safe handler access
                            with self._lock:
                                handlers = list(self.event_handlers)

                            for handler in handlers:
                                try:
                                    handler(event_data)
                                except Exception as e:
                                    logger.error(f"Error in Kafka handler: {e}")

                        except Exception as e:
                            logger.error(f"Error processing Kafka message: {e}")

                try:
                    if message_batch:
                        self.consumer.commit()
                except Exception as e:
                    logger.error(f"Error committing offsets: {e}")

        except Exception as e:
            logger.error(f"Kafka consumer error: {e}")
        finally:
            logger.info("Kafka consumer loop exited")


    def close(self):
        logger.info("Closing Kafka Event Processor...")
        self.stop_consumer()
        
        with self._lock:
            if self.producer:
                try:
                    self.producer.flush(timeout=5)
                    self.producer.close()
                except Exception as e:
                    logger.error(f"Error closing producer: {e}")
                finally:
                    self.producer = None
        
        logger.info("Kafka Event Processor closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def is_healthy(self) -> bool:
        """Check if the processor is healthy"""
        with self._lock:
            producer_ok = self.producer is not None
            consumer_ok = not self.running or (
                self.consumer is not None and 
                self.consumer_thread and 
                self.consumer_thread.is_alive()
            )
        return producer_ok and consumer_ok
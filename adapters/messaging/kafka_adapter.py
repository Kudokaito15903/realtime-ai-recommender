"""
Kafka messaging adapter for event processing.
"""

import os
import json
import threading
import time
from typing import Dict, Any, Optional, Callable
from loguru import logger
from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError

from adapters.interfaces import EventProcessorInterface


class KafkaEventProcessor(EventProcessorInterface):
    """Kafka event processor implementation"""

    def __init__(self, bootstrap_servers: str, topic: str, group_id: str):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.group_id = group_id

        self.producer = None
        self.consumer = None
        self.running = False
        self.consumer_thread = None
        self.event_handler = None

        self._initialize_producer()

        logger.info(
            f"Kafka Event Processor initialized: {bootstrap_servers}, topic={topic}"
        )

    def _initialize_producer(self):
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
        except Exception as e:
            logger.error(f"Failed to initialize Kafka producer: {e}")

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

        except Exception as e:
            logger.error(
                f"Error publishing {event_type} event for product {product_id}: {e}"
            )
            return None

    def start_consumer(self, consumer_id: Optional[str] = None) -> None:
        if self.running:
            logger.warning("Kafka consumer is already running")
            return

        self.running = True
        self.consumer_thread = threading.Thread(
            target=self._consume_loop, args=(consumer_id,), daemon=True
        )
        self.consumer_thread.start()
        logger.info(f"Started Kafka consumer: {consumer_id}")

    def stop_consumer(self) -> None:
        if not self.running:
            return

        self.running = False
        if self.consumer_thread and self.consumer_thread.is_alive():
            self.consumer_thread.join(timeout=5.0)

        if self.consumer:
            self.consumer.close()

        logger.info("Stopped Kafka consumer")

    def set_event_handler(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        self.event_handler = handler

    def _consume_loop(self, consumer_id: Optional[str]) -> None:
        try:
            self.consumer = KafkaConsumer(
                self.topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                value_deserializer=lambda x: json.loads(x.decode("utf-8")),
                auto_offset_reset="earliest",
            )

            logger.info("Kafka consumer connected and listening...")

            while self.running:
                # Poll for messages (non-blocking way, or use iteration)
                # Using poll for better control
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

                            if self.event_handler:
                                self.event_handler(event_data)

                        except Exception as e:
                            logger.error(f"Error processing Kafka message: {e}")

        except Exception as e:
            logger.error(f"Kafka consumer error: {e}")
            self.running = False

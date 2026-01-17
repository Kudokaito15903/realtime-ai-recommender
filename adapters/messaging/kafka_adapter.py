"""
Kafka messaging adapter for product-events and content-events
"""

import json
import threading
import time
from typing import Dict, Any, Optional, Callable, List
from loguru import logger
from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError


class KafkaEventProcessor:
    """Kafka event processor implementation (generic for product & content)"""

    def __init__(
        self,
        bootstrap_servers: str,
        topic: str,
        group_id: str,
        entity_type: str,  # "product" | "content"
    ):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.group_id = group_id
        self.entity_type = entity_type

        self.producer: Optional[KafkaProducer] = None
        self.consumer: Optional[KafkaConsumer] = None
        self.running = False
        self.consumer_thread: Optional[threading.Thread] = None
        self.event_handlers: List[Callable[[Dict[str, Any]], None]] = []

        self._lock = threading.Lock()
        self._initialize_producer()

        logger.info(
            f"KafkaEventProcessor initialized | "
            f"topic={topic} | group={group_id} | entity={entity_type}"
        )

    # ------------------------------------------------------------------
    # Producer
    # ------------------------------------------------------------------

    def _initialize_producer(self):
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8"),
                retries=3,
                acks="all",
                max_in_flight_requests_per_connection=1,
            )
            logger.info("Kafka producer initialized successfully")
        except Exception as e:
            logger.exception("Failed to initialize Kafka producer")
            raise

    def publish_create(self, data: Dict[str, Any]) -> Optional[str]:
        return self._publish_event("create", data)

    def publish_update(self, data: Dict[str, Any]) -> Optional[str]:
        return self._publish_event("update", data)

    def publish_delete(self, entity_id: str) -> Optional[str]:
        return self._publish_event("delete", {"id": entity_id})

    def publish_event(self, event_data: Dict[str, Any]) -> Optional[str]:
        """Generic publish (adapter compatibility)"""
        event_type = event_data.get("event_type", "unknown")
        data = event_data.get("data", event_data)

        entity_id = event_data.get("entity_id") or data.get("id") or event_data.get("product_id") or event_data.get("content_id")
        
        return self._publish_event(event_type, data, entity_id=entity_id)

    def _publish_event(
        self, event_type: str, data: Dict[str, Any], entity_id: Optional[str] = None
    ) -> Optional[str]:
        with self._lock:
            if not self.producer:
                logger.warning("Kafka producer not available")
                return None


        event = {
            "eventType": event_type,
            "entityId": entity_id, 
            "data": data,
            "timestamp": time.time(),
        }

        try:
            future = self.producer.send(
                self.topic,
                key=entity_id or "unknown",  # ✅ ensure ordering per entity
                value=event,
            )
            metadata = future.get(timeout=10)

            logger.debug(
                f"Published {event_type} | {self.entity_type}:{entity_id} | "
                f"partition={metadata.partition} offset={metadata.offset}"
            )
            return f"{metadata.partition}:{metadata.offset}"

        except KafkaError as e:
            logger.error(f"Kafka publish error: {e}")
            return None
        except Exception as e:
            logger.exception("Unexpected publish error")
            return None

    # ------------------------------------------------------------------
    # Consumer
    # ------------------------------------------------------------------

    def add_event_handler(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        with self._lock:
            self.event_handlers.append(handler)

    def start_consumer(self, consumer_id: Optional[str] = None) -> None:
        with self._lock:
            if self.running:
                logger.warning("Kafka consumer already running")
                return
            self.running = True

        self.consumer_thread = threading.Thread(
            target=self._consume_loop,
            args=(consumer_id,),
            daemon=True,
        )
        self.consumer_thread.start()

        logger.info(
            f"Kafka consumer started | topic={self.topic} | group={self.group_id}"
        )

    def stop_consumer(self) -> None:
        with self._lock:
            self.running = False

        if self.consumer_thread:
            self.consumer_thread.join(timeout=5)

        with self._lock:
            if self.consumer:
                try:
                    self.consumer.close()
                except Exception:
                    logger.exception("Error closing Kafka consumer")
                finally:
                    self.consumer = None

        logger.info("Kafka consumer stopped")

    def _consume_loop(self, consumer_id: Optional[str]) -> None:
        try:
            self.consumer = KafkaConsumer(
                self.topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                auto_offset_reset="earliest",
                enable_auto_commit=False,
                session_timeout_ms=30000,
                max_poll_records=100,
            )

            logger.info(
                f"Kafka consumer connected | "
                f"topic={self.topic} | group={self.group_id} | "
                f"consumer_id={consumer_id or 'default'}"
            )

            while self.running:
                records = self.consumer.poll(timeout_ms=1000)
                if not records:
                    continue

                for _, messages in records.items():
                    for message in messages:
                        if not self.running:
                            break

                        event = message.value
                        success = True

                        with self._lock:
                            handlers = list(self.event_handlers)

                        for handler in handlers:
                            try:
                                handler(event)
                            except Exception:
                                logger.exception(
                                    f"Handler error for event {event.get('event_type', 'unknown')}"
                                )
                                success = False
                                break

                        if success:
                            try:
                                self.consumer.commit()
                            except Exception:
                                logger.exception("Commit offset failed")

        except Exception:
            logger.exception("Kafka consumer fatal error")
        finally:
            logger.info("Kafka consumer loop exited")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        logger.info("Closing KafkaEventProcessor...")
        self.stop_consumer()

        with self._lock:
            if self.producer:
                try:
                    self.producer.flush(timeout=5)
                    self.producer.close()
                except Exception:
                    logger.exception("Error closing Kafka producer")
                finally:
                    self.producer = None

        logger.info("KafkaEventProcessor closed")

    def is_healthy(self) -> bool:
        with self._lock:
            producer_ok = self.producer is not None
            consumer_ok = not self.running or (
                self.consumer_thread and self.consumer_thread.is_alive()
            )
        return producer_ok and consumer_ok

import os
import time
import signal
import sys
import uuid
from typing import Dict, Any
from loguru import logger

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.factory import (
    get_content_event_processor,
    get_vector_store,
    get_content_store,
)
from domain.embeddings.product_embeddings import get_embedding_model


class ContentEventHandler:
    """
    Kafka Content Event Consumer
    - Consume content events
    - Build content embeddings
    - Upsert / delete vector store
    """

    def __init__(self, worker_name: str = "content-vector"):
        self.worker_name = worker_name

        self.event_processor = get_content_event_processor()
        self.vector_store = get_vector_store()
        self.content_store = get_content_store()
        self.embedding_model = get_embedding_model()

        self._started = False

    # ------------------------------------------------------------------
    # Event handler (CRITICAL)
    # ------------------------------------------------------------------
    def _handle_event(self, event: Dict[str, Any]) -> None:

        data = event.get("data")
        if event.get("entity_type") != "content":
            return

        event_type = event.get("event_type")
        content_id = data.get("id") or data.get("content_id")
        timestamp = event.get("timestamp")
        logger.info(f"Processing content event: {event_type} for content_id: {content_id}")
        logger.debug(f"Content event data: {data}")
        if not event_type or not content_id:
                raise ValueError(f"Invalid content event schema: {event}")

        logger.debug(
            f"[{self.worker_name}] event={event_type} content={content_id} ts={timestamp}"
        )

        try:
            if event_type in ("create", "update"):
                self._process_upsert(content_id, data)

            elif event_type == "delete":
                self._process_delete(content_id)

            else:
                logger.warning(f"Unsupported content event type: {event_type}")

        except Exception:
            logger.exception(
                f"Content event FAILED | type={event_type} content={content_id}"
            )
            raise

    # ------------------------------------------------------------------
    # Business logic
    # ------------------------------------------------------------------
    def _process_upsert(self, content_id: str, data: dict) -> None:
        start_time = time.time()

        # Build text for embedding
        text = f"{data.get('title', '')} {data.get('content', '')} {' '.join(data.get('tags', []))}".strip()
        if not text:
            raise ValueError(f"Empty content text for {content_id}")

        embedding = self.embedding_model.embed_text(text)
        metadata = self._build_metadata(data)

        success = self.vector_store.store_content_embedding(
            content_id=content_id,
            embedding=embedding,
            metadata=metadata,
        )

        if not success:
            raise RuntimeError(f"Vector upsert failed for content {content_id}")

        logger.info(
            f"Vector upsert OK | content={content_id} "
            f"time={time.time() - start_time:.3f}s"
        )

    def _process_delete(self, content_id: str) -> None:
        success = self.vector_store.delete_content_embedding(content_id)

        if not success:
            raise RuntimeError(f"Vector delete failed for content {content_id}")

        logger.info(f"Vector deleted | content={content_id}")

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------
    def _build_metadata(self, content: dict) -> dict:
        return {
            "entity_type": "content",
            "title": content.get("title", ""),
            "category": content.get("category", "unknown"),
            "content": content.get("content", ""),
            "tags": content.get("tags", []),
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._started:
            return

        self.event_processor.add_event_handler(self._handle_event)
        self.event_processor.start_consumer(consumer_id=self.worker_name)

        self._started = True
        logger.info(f"Content vector consumer started | worker={self.worker_name}")

    def stop(self) -> None:
        self.event_processor.stop_consumer()
        logger.info(f"Content vector consumer stopped | worker={self.worker_name}")

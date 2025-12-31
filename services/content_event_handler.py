import os
import time
import threading
from typing import Dict, Any
from loguru import logger

from adapters.factory import get_event_processor, get_vector_store, get_content_store
from domain.embeddings.product_embeddings import get_embedding_model


class ContentEventHandler:
    def __init__(self):
        self.event_processor = get_event_processor()
        self.vector_store = get_vector_store()
        self.content_store = get_content_store()
        self.embedding_model = get_embedding_model()
        self._started = False

    def _handle_event(self, event: Dict[str, Any]):
        try:
            event_type = event.get("event_type") or event.get("type")
            content_id = event.get("content_id") or event.get("id") or event.get("product_id") or (event.get("data") or {}).get("id")
            logger.debug(f"Content event received: {event_type} - {content_id}")

            if not content_id:
                logger.warning("Content event without content id; ignoring")
                return

            if event_type in ("create", "update"):
                # fetch content and upsert embedding
                try:
                    content = self.content_store.get_content(content_id)
                    if not content:
                        logger.warning(f"Content {content_id} not found in content store")
                        return
                    # Create embedding from title + content
                    text = f"{content.get('title', '')} {content.get('content', '')}"
                    emb = self.embedding_model.embed_text(text)
                    metadata = {
                        "type": "content",
                        "category": content.get("category"),
                        "tags": content.get("tags", []),
                        "title": content.get("title"),
                    }
                    self.vector_store.store_product_embedding(content_id, emb, metadata=metadata)
                    logger.info(f"Upserted embedding for content {content_id} from event {event_type}")
                except Exception as e:
                    logger.exception(f"Failed to upsert embedding for content {content_id}: {e}")

            elif event_type == "delete":
                try:
                    self.vector_store.delete_product_embedding(content_id)
                    logger.info(f"Deleted embedding for content {content_id} from vector store")
                except Exception as e:
                    logger.exception(f"Failed to delete embedding for content {content_id}: {e}")

            else:
                logger.debug(f"Unhandled event type: {event_type}")

        except Exception:
            logger.exception("Error in content event handler")

    def start(self):
        if self._started:
            return
        try:
            self.event_processor.add_event_handler(self._handle_event)
            self.event_processor.start_consumer(consumer_id="content-handler")
            self._started = True
            logger.info("ContentEventHandler started and listening to events")
        except Exception as e:
            logger.exception(f"Failed to start ContentEventHandler: {e}")

    def stop(self):
        try:
            # Note: stopping consumer might affect product handler too if same processor
            # In production, use separate topics or group ids
            pass
        except Exception:
            logger.exception("Error stopping event processor")


# Provide a singleton instance
_content_handler_instance: ContentEventHandler | None = None


def get_content_event_handler() -> ContentEventHandler:
    global _content_handler_instance
    if _content_handler_instance is None:
        _content_handler_instance = ContentEventHandler()
    return _content_handler_instance
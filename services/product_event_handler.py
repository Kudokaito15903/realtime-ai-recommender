import os
import time
import threading
from typing import Dict, Any
from loguru import logger

from adapters.factory import get_event_processor, get_vector_store, get_product_store
from domain.embeddings.product_embeddings import get_embedding_model


class ProductEventHandler:
    def __init__(self):
        self.event_processor = get_event_processor()
        self.vector_store = get_vector_store()
        self.product_store = get_product_store()
        self.embedding_model = get_embedding_model()
        self._started = False

    def _handle_event(self, event: Dict[str, Any]):
        try:
            event_type = event.get("event_type") or event.get("type")
            product_id = event.get("product_id") or event.get("id") or (event.get("data") or {}).get("id")
            logger.debug(f"Product event received: {event_type} - {product_id}")

            if not product_id:
                logger.warning("Product event without product id; ignoring")
                return

            if event_type in ("create", "update"):
                # fetch product details and upsert embedding
                try:
                    product = self.product_store.get_product(product_id)
                    if not product:
                        logger.warning(f"Product {product_id} not found in product store")
                        return
                    emb = self.embedding_model.get_product_embedding(product)
                    self.vector_store.store_product_embedding(product_id, emb, metadata={"source": "product_event"})
                    logger.info(f"Upserted embedding for product {product_id} from event {event_type}")
                except Exception as e:
                    logger.exception(f"Failed to upsert embedding for product {product_id}: {e}")

            elif event_type == "delete":
                try:
                    self.vector_store.delete_product_embedding(product_id)
                    logger.info(f"Deleted embedding for product {product_id} from vector store")
                except Exception as e:
                    logger.exception(f"Failed to delete embedding for product {product_id}: {e}")

            else:
                logger.debug(f"Unhandled event type: {event_type}")

        except Exception:
            logger.exception("Error in product event handler")

    def start(self):
        if self._started:
            return
        # register handler and start consumer
        try:
            self.event_processor.add_event_handler(self._handle_event)
            self.event_processor.start_consumer()
            self._started = True
            logger.info("ProductEventHandler started and listening to events")
        except Exception as e:
            logger.exception(f"Failed to start ProductEventHandler: {e}")

    def stop(self):
        try:
            self.event_processor.stop_consumer()
        except Exception:
            logger.exception("Error stopping event processor")


# Provide a singleton instance
_handler_instance: ProductEventHandler | None = None


def get_product_event_handler() -> ProductEventHandler:
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = ProductEventHandler()
    return _handler_instance

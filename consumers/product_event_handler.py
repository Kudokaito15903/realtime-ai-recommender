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
    get_event_processor,
    get_vector_store,
    get_product_store,
)
from domain.embeddings.product_embeddings import get_embedding_model


class ProductEventHandler:
    """
    Kafka Product Event Consumer
    - Consume product events
    - Build product embeddings
    - Upsert / delete vector store
    """

    def __init__(self, worker_name: str | None = None):
        self.worker_name = worker_name or f"vector-worker-{uuid.uuid4()}"

        # Adapters
        self.event_processor = get_event_processor()
        self.vector_store = get_vector_store()
        self.product_store = get_product_store()
        self.embedding_model = get_embedding_model()

        self._started = False

        logger.info(f"ProductEventHandler initialized | worker={self.worker_name}")

    # ------------------------------------------------------------------
    # Event handler (CRITICAL)
    # ------------------------------------------------------------------
    def _handle_event(self, event: Dict[str, Any]) -> None:
        if event.get("entity_type") != "product":
            return

        event_type = event.get("event_type")
        product_id = event.get("entity_id")
        timestamp = event.get("timestamp")
        data = event.get("data")

        if not event_type or not product_id:
            # Try to recover from data (backwards compatibility)
            if data and isinstance(data, dict):
                product_id = data.get("id") or data.get("product_id")

            if not product_id:
                logger.error(f"Invalid product event schema (missing ID), skipping: {event}")
                return

        logger.debug(
            f"[{self.worker_name}] event={event_type} product={product_id} ts={timestamp}"
        )

        try:
            if event_type in ("create", "update"):
                self._process_upsert(product_id, data)

            elif event_type == "delete":
                self._process_delete(product_id)

            else:
                logger.warning(f"Unsupported product event type: {event_type}")

        except Exception:
            logger.exception(
                f"Product event FAILED | type={event_type} product={product_id}"
            )
            raise

    # ------------------------------------------------------------------
    # Business logic
    # ------------------------------------------------------------------
    def _process_upsert(self, product_id: str, data: dict) -> None:
        start_time = time.time()

        embedding = self.embedding_model.get_product_embedding(data)
        metadata = self._build_metadata(data)

        success = self.vector_store.store_product_embedding(
            product_id=product_id,
            embedding=embedding,
            metadata=metadata,
        )

        if not success:
            raise RuntimeError(f"Vector upsert failed for product {product_id}")

        logger.info(
            f"Vector upsert OK | product={product_id} "
            f"time={time.time() - start_time:.3f}s"
        )

    def _process_delete(self, product_id: str) -> None:
        success = self.vector_store.delete_product_embedding(product_id)

        if not success:
            raise RuntimeError(f"Vector delete failed for product {product_id}")

        logger.info(f"Vector deleted | product={product_id}")

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------
    def _build_metadata(self, product: dict) -> dict:
        category = product.get("category")
        if not category and product.get("categoryId"):
            cid = product["categoryId"]
            category = cid[0] if isinstance(cid, list) and cid else cid

        # Handle product variants
        variants = product.get("productVariants")
        if variants and isinstance(variants, list) and len(variants) > 0:
            # Aggregate prices, brands, and descriptions from variants
            prices = [v.get("price") for v in variants if v.get("price") is not None]
            brands = [v.get("brandName") for v in variants if v.get("brandName")]
            descriptions = [v.get("description") for v in variants if v.get("description")]
            price = prices[0] if prices else product.get("price", 0)
            brand = brands[0] if brands else product.get("brandName", "")
            description = descriptions[0] if descriptions else product.get("description", "")
        else:
            price = product.get("price", 0)
            brand = product.get("brandName", "")
            description = product.get("description", "")

        return {
            "entity_type": "product",
            "name": product.get("name", ""),
            "category": category or "unknown",
            "price": str(price or 0),
            "brand": brand,
            "description": description,
        }

    # ------------------------------------------------------------------
    # Lifecycle (MATCH ContentEventHandler)
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._started:
            return

        self.event_processor.add_event_handler(self._handle_event)
        self.event_processor.start_consumer(consumer_id=self.worker_name)

        self._started = True
        logger.info(f"Product vector consumer started | worker={self.worker_name}")

    def stop(self) -> None:
        self.event_processor.stop_consumer()
        self._started = False
        logger.info(f"Product vector consumer stopped | worker={self.worker_name}")

# ----------------------------------------------------------------------
# Process bootstrap
# ----------------------------------------------------------------------
def start_vector_consumer_process(worker_name: str | None = None) -> None:
    consumer = ProductEventHandler(worker_name)

    def shutdown_handler(sig, frame):
        logger.info("Shutdown signal received")
        consumer.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    consumer.start()

    logger.info("Product vector consumer running...")
    while True:
        time.sleep(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Product Vector Kafka Consumer")
    parser.add_argument("--worker-name", type=str)
    args = parser.parse_args()

    start_vector_consumer_process(args.worker_name)

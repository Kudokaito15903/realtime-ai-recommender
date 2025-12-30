
import os
import time
import signal
import sys
import threading
import uuid
from loguru import logger

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.factory import get_event_processor, get_vector_store
from domain.embeddings.product_embeddings import get_embedding_model


class ModernProductEventConsumer:
    def __init__(self, consumer_id: str | None = None):
        self.consumer_id = consumer_id or f"vector-worker-{uuid.uuid4()}"

        # Adapters (NO DATABASE)
        self.event_processor = get_event_processor()
        self.vector_store = get_vector_store()
        self.embedding_model = get_embedding_model()

        # Register handler
        self.event_processor.set_event_handler(self._handle_event)

        logger.info(f"Vector Product Consumer initialized: {self.consumer_id}")

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------
    def _handle_event(self, event_data: dict) -> None:
        event_type = event_data.get("event_type")
        product_id = (
            event_data.get("product_id")
            or event_data.get("id")
            or event_data.get("data", {}).get("id")
        )
        product_data = event_data.get("data", {})
        timestamp = event_data.get("timestamp")

        if not event_type or not product_id:
            logger.warning(f"Invalid event format: {event_data}")
            return

        logger.debug(
            f"[{self.consumer_id}] {event_type} product={product_id} ts={timestamp}"
        )

        try:
            if event_type in ("create", "update"):
                self._process_upsert(product_id, product_data)
            elif event_type == "delete":
                self._process_delete(product_id)
            else:
                logger.warning(f"Unsupported event type: {event_type}")

        except Exception as e:
            logger.exception(
                f"Failed processing {event_type} for product {product_id}: {e}"
            )

    def _process_upsert(self, product_id: str, product_data: dict) -> None:
        start_time = time.time()

        if "id" not in product_data:
            product_data["id"] = product_id

        embedding = self.embedding_model.get_product_embedding(product_data)

        metadata = self._build_metadata(product_data)

        success = self.vector_store.store_product_embedding(
            product_id=product_id,
            embedding=embedding,
            metadata=metadata,
        )

        if success:
            logger.info(
                f"Vector upsert OK product={product_id} "
                f"time={time.time() - start_time:.3f}s"
            )
        else:
            logger.error(f"Vector upsert FAILED product={product_id}")
    def _process_delete(self, product_id: str) -> None:
        success = self.vector_store.delete_product_embedding(product_id)

        if success:
            logger.info(f"Vector deleted product={product_id}")
        else:
            logger.error(f"Vector delete FAILED product={product_id}")

    # ------------------------------------------------------------------
    # Metadata builder
    # ------------------------------------------------------------------
    def _build_metadata(self, product_data: dict) -> dict:
        # Category
        category = product_data.get("category")
        if not category and product_data.get("categoryId"):
            cid = product_data["categoryId"]
            category = cid[0] if isinstance(cid, list) and cid else cid

        # Price
        price = product_data.get("price")
        if price is None and product_data.get("productVariants"):
            variants = product_data["productVariants"]
            if variants and isinstance(variants[0], dict):
                price = variants[0].get("price")

        return {
            "name": product_data.get("name", ""),
            "category": category or "unknown",
            "price": str(price or 0),
            "brand": product_data.get("brandName", ""),
            "description": product_data.get("description", ""),
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        self.event_processor.start_consumer(self.consumer_id)
        logger.info(f"Vector consumer started: {self.consumer_id}")

    def stop(self) -> None:
        self.event_processor.stop_consumer()
        logger.info(f"Vector consumer stopped: {self.consumer_id}")


# ----------------------------------------------------------------------
# Process bootstrap
# ----------------------------------------------------------------------
def start_vector_consumer_process(consumer_id: str | None = None) -> None:
    consumer = ModernProductEventConsumer(consumer_id)

    def shutdown_handler(sig, frame):
        logger.info("Shutdown signal received")
        consumer.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    consumer.start()

    logger.info("Vector consumer running...")
    while True:
        time.sleep(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Vector Product Event Consumer")
    parser.add_argument("--consumer-id", type=str)
    args = parser.parse_args()

    start_vector_consumer_process(args.consumer_id)

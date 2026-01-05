import os
import time
import signal
import sys
import uuid
import json
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

        logger.info(
            f"ProductEventHandler initialized | worker={self.worker_name}")

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
                logger.error(
                    f"Invalid product event schema (missing ID), skipping: {event}"
                )
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
            raise RuntimeError(
                f"Vector upsert failed for product {product_id}")

        logger.info(f"Vector upsert OK | product={product_id} "
                    f"time={time.time() - start_time:.3f}s")

    def _process_delete(self, product_id: str) -> None:
        success = self.vector_store.delete_product_embedding(product_id)

        if not success:
            raise RuntimeError(
                f"Vector delete failed for product {product_id}")

        logger.info(f"Vector deleted | product={product_id}")

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def _build_metadata(self, data: dict) -> dict:
        identity = {
            "product_id": data.get("sku"),
            "name": data.get("name"),
            "brand": data.get("brandName"),
            "sku": data.get("sku"),
            "type": "product",
        }

        # -----------------------------
        # 2. Commercial
        # -----------------------------
        commercial = {
            "price": data.get("price"),
            "list_price": data.get("listPrice"),
            "currency": "USD",
            "has_video": bool(data.get("videoUrl")),
            "in_stock": True,
        }

        # -----------------------------
        # 3. Taxonomy
        # -----------------------------
        taxonomy = {
            "category": data.get("category"),
            "category_ids": data.get("categoryId", []),
            "tags": self._build_tags(data),
        }

        # -----------------------------
        # 4. Attributes (structured)
        # -----------------------------
        attributes = {}
        specs_text_chunks = []

        for spec in data.get("specifications", []):
            group = spec.get("group", "general").lower()
            key = spec.get("key", "").lower().replace(" ", "_")
            value = spec.get("value")

            if not group or not key or value is None:
                continue

            attributes.setdefault(group, {})[key] = value
            specs_text_chunks.append(f"{spec.get('key')}: {value}")

        # -----------------------------
        # 5. Variants
        # -----------------------------
        variants = []
        variant_colors = []

        for v in data.get("productVariants", []):
            variants.append({
                "sku": v.get("sku"),
                "name": v.get("variantName"),
                "color": v.get("color"),
                "price": v.get("price"),
            })

            if v.get("color"):
                variant_colors.append(v.get("color"))

            for bs in v.get("bestSpecifications", []):
                specs_text_chunks.append(f"{bs.get('key')}: {bs.get('value')}")

        # -----------------------------
        # 6. AI Embedding Text
        # -----------------------------
        embedding_text = self._build_embedding_text(
            name=data.get("name"),
            brand=data.get("brandName"),
            category=data.get("category"),
            price=data.get("price"),
            description=data.get("description"),
            specs_text=specs_text_chunks,
            colors=variant_colors,
            rating=data.get("avgRating"),
        )

        # -----------------------------
        # 7. AI Metadata
        # -----------------------------
        ai = {
            "embedding_text":
            embedding_text,
            "intents": [
                "product_info",
                "price_check",
                "compare_products",
                "variant_selection",
                "technical_specs",
            ],
        }

        # -----------------------------
        # 8. Final Metadata
        # -----------------------------
        return {
            "entity_type": "product",
            # Flatten key fields for easy filtering in Pinecone
            "product_id": data.get("sku"),
            "name": data.get("name"),
            "category": data.get("category", "unknown"),
            "brand": data.get("brandName", ""),
            "price": float(data.get("price", 0) or 0),
            "avg_rating": float(data.get("avgRating", 0) or 0),
            "has_video": bool(data.get("videoUrl")),
            
            # Serialize complex structures to JSON strings
            "identity": json.dumps(identity),
            "commercial": json.dumps(commercial),
            "taxonomy": json.dumps(taxonomy),
            "attributes": json.dumps(attributes),
            "variants": json.dumps(variants),
            "ai": json.dumps(ai),
        }

    def _build_tags(self, data: dict) -> list:
        tags = set()

        if data.get("category"):
            tags.add(data["category"].lower())

        for cid in data.get("categoryId", []):
            tags.add(cid.lower())

        if data.get("brandName"):
            tags.add(data["brandName"].lower())

        if data.get("color"):
            tags.add(data["color"].lower())

        return list(tags)

    def _build_embedding_text(
        self,
        name: str,
        brand: str,
        category: str,
        price: float,
        description: str,
        specs_text: list,
        colors: list,
        rating: float,
    ) -> str:
        parts = []

        if name:
            parts.append(f"Product name: {name}.")
        if brand:
            parts.append(f"Brand: {brand}.")
        if category:
            parts.append(f"Category: {category}.")
        if price is not None:
            parts.append(f"Price: {price}.")
        if rating:
            parts.append(f"Average rating: {rating} stars.")
        if description:
            parts.append(description)
        if specs_text:
            parts.append("Specifications: " + ", ".join(specs_text))
        if colors:
            parts.append("Available colors: " + ", ".join(set(colors)))

        return " ".join(parts)

    # ------------------------------------------------------------------
    # Lifecycle (MATCH ContentEventHandler)
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._started:
            return

        self.event_processor.add_event_handler(self._handle_event)
        self.event_processor.start_consumer(consumer_id=self.worker_name)

        self._started = True
        logger.info(
            f"Product vector consumer started | worker={self.worker_name}")

    def stop(self) -> None:
        self.event_processor.stop_consumer()
        self._started = False
        logger.info(
            f"Product vector consumer stopped | worker={self.worker_name}")


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

    parser = argparse.ArgumentParser(
        description="Product Vector Kafka Consumer")
    parser.add_argument("--worker-name", type=str)
    args = parser.parse_args()

    start_vector_consumer_process(args.worker_name)

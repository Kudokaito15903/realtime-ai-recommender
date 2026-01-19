import os
import time
import signal
import sys
import uuid
import json
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, asdict
from loguru import logger

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.factory import (
    get_event_processor,
    get_vector_store,
    get_product_store,
)
from domain.embeddings.product_embeddings import get_embedding_model


# ==================== DATA VALIDATION ====================


@dataclass
class ProductMetadata:
    """Structured metadata for vector store"""

    # Core fields (filterable)
    entity_type: str = "product"
    product_id: str = ""
    sku: str = ""
    name: str = ""
    brand: str = ""
    category: str = ""

    # Commercial (filterable)
    price: float = 0.0
    list_price: float = 0.0
    currency: str = "VND"
    in_stock: bool = True
    has_discount: bool = False
    discount_percentage: float = 0.0

    # Quality metrics (filterable)
    avg_rating: float = 0.0
    review_count: int = 0

    # Media (filterable)
    has_video: bool = False
    image_count: int = 0

    # Taxonomy (filterable)
    category_ids: List[str] = None
    tags: List[str] = None

    # Variants (for filtering)
    variant_count: int = 0
    available_colors: List[str] = None
    available_sizes: List[str] = None

    # Rich data (JSON - not filterable but queryable)
    attributes: str = "{}"  # JSON string
    variants: str = "[]"  # JSON string

    # AI metadata
    embedding_version: str = "v1"
    indexed_at: float = 0.0

    def __post_init__(self):
        if self.category_ids is None:
            self.category_ids = []
        if self.tags is None:
            self.tags = []
        if self.available_colors is None:
            self.available_colors = []
        if self.available_sizes is None:
            self.available_sizes = []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for vector store"""
        data = asdict(self)
        # Ensure lists are not None
        for key, value in data.items():
            if value is None:
                if key in [
                    "category_ids",
                    "tags",
                    "available_colors",
                    "available_sizes",
                ]:
                    data[key] = []
                elif key in ["attributes", "variants"]:
                    data[key] = "{}" if key == "attributes" else "[]"
        return data


class DataValidator:
    """Validate and sanitize product data"""

    @staticmethod
    def validate_product_id(data: Dict) -> Optional[str]:
        """Extract and validate product ID"""
        product_id = (
            data.get("id")
            or data.get("product_id")
            or data.get("sku")
            or data.get("entityId")
            or data.get("entity_id")
        )

        if not product_id:
            return None

        # Sanitize
        product_id = str(product_id).strip()

        if not product_id or len(product_id) > 100:
            return None

        return product_id

    @staticmethod
    def safe_float(value: Any, default: float = 0.0) -> float:
        """Safely convert to float"""
        if value is None:
            return default

        try:
            return float(value)
        except (ValueError, TypeError):
            logger.warning(f"Invalid float value: {value}")
            return default

    @staticmethod
    def safe_int(value: Any, default: int = 0) -> int:
        """Safely convert to int"""
        if value is None:
            return default

        try:
            return int(value)
        except (ValueError, TypeError):
            logger.warning(f"Invalid int value: {value}")
            return default

    @staticmethod
    def safe_list(value: Any, default: Optional[List] = None) -> List:
        """Safely convert to list"""
        if default is None:
            default = []

        if value is None:
            return default

        if isinstance(value, list):
            return value

        if isinstance(value, str):
            return [value]

        return default


# ==================== MAIN HANDLER ====================


class ProductEventHandler:
    """
    Kafka Product Event Consumer - IMPROVED
    - Better metadata schema
    - Validation
    - Performance optimization
    """

    # Important specs for semantic search
    IMPORTANT_SPECS = {
        "battery life",
        "screen size",
        "ram",
        "storage",
        "weight",
        "dimensions",
        "processor",
        "cpu",
        "gpu",
        "display",
        "camera",
        "connectivity",
        "material",
    }

    def __init__(self, worker_name: Optional[str] = None):
        self.worker_name = worker_name or f"vector-worker-{uuid.uuid4()}"

        # Adapters
        self.event_processor = get_event_processor()
        self.vector_store = get_vector_store()
        self.product_store = get_product_store()
        self.embedding_model = get_embedding_model()

        self._started = False

        # Statistics
        self._stats = {"processed": 0, "upserted": 0, "deleted": 0, "failed": 0}

        logger.info(f"ProductEventHandler initialized | worker={self.worker_name}")

    # ==================== EVENT HANDLING ====================

    def _handle_event(self, event: Dict[str, Any]) -> None:
        """Handle product event (with validation)"""
        logger.debug(f"Processing product event: {event.get('eventType')}")
        event_type = event.get("eventType") or event.get("event_type")
        data = event

        # Validate product ID
        product_id = DataValidator.validate_product_id(data)

        if not product_id:
            logger.error(f"Invalid product event (missing/invalid ID): {event}")
            return

        if not event_type:
            logger.error(f"Invalid product event (missing eventType): {event}")
            return

        timestamp = event.get("timestamp", time.time())

        logger.debug(
            f"[{self.worker_name}] event={event_type} product={product_id} ts={timestamp}"
        )

        try:
            # Normalize event type
            norm_type = str(event_type).upper()

            if norm_type in ("CREATED", "UPDATED", "UPSERT", "CREATE", "UPDATE"):
                self._process_upsert(product_id, data)
                self._stats["upserted"] += 1

            elif norm_type in ("DELETED", "DELETE"):
                self._process_delete(product_id)
                self._stats["deleted"] += 1

            else:
                logger.warning(f"Unsupported event type: {event_type}")
                return

            self._stats["processed"] += 1

        except Exception as e:
            logger.exception(
                f"Product event FAILED | type={event_type} product={product_id} error={e}"
            )
            self._stats["failed"] += 1
            raise

    # ==================== BUSINESS LOGIC ====================

    def _process_upsert(self, product_id: str, data: Dict) -> None:
        """Process upsert event (Dual Strategy)"""
        start_time = time.time()

        # 1. Recommendation Embedding (Namespace: "products")
        # Used for "Similar Products" and content-based recommendation
        payload = data.get("data", data)
        if not payload.get("id"):
            payload["id"] = product_id

        rec_embedding = self.embedding_model.get_product_recommendation_embedding(
            payload
        )

        # Build metadata (using new Builder)
        from consumers.product_metadata_builder import ProductMetadataBuilder

        raw_metadata = ProductMetadataBuilder.build(payload)

        # Flatten for Pinecone
        rec_metadata = {
            "product_id": str(raw_metadata["product"].get("product_id")),
            "name": str(raw_metadata["product"].get("name", "")),
            "brand": str(raw_metadata["product"].get("brand", "")),
            "categories": raw_metadata["product"].get("categories", []),
            "warranty": str(raw_metadata["product"].get("warranty", "")),
            "created_at": str(raw_metadata["product"].get("created_at") or ""),
            "updated_at": str(raw_metadata["product"].get("updated_at") or ""),
            "min_price": float(raw_metadata["stats"].get("min_price", 0)),
            "max_price": float(raw_metadata["stats"].get("max_price", 0)),
            "vector_type": "recommendation",
            # Serialized JSON for complex structs
            "variants_json": json.dumps(raw_metadata["variants"]),
            "stats_json": json.dumps(raw_metadata["stats"]),
        }

        # Store in vector DB (products namespace)
        success = self.vector_store.store_product_embedding(
            product_id=product_id,
            embedding=rec_embedding,
            metadata=rec_metadata,
            namespace="products",
        )

        if not success:
            raise RuntimeError(f"Vector upsert failed for product {product_id}")

        # 2. RAG Chatbot Embeddings (Namespace: "rag_chunks")
        # Used for Chatbot Q&A
        chunks = self.embedding_model.embed_product_chunks(payload)
        chunk_count = 0

        for embedding, chunk_info in chunks:
            chunk_metadata = chunk_info["metadata"]
            chunk_metadata["text"] = chunk_info["text"]
            chunk_metadata["vector_type"] = "rag_chunk"
            chunk_id = chunk_metadata["chunk_id"]

            # Store chunk (rag_chunks namespace)
            self.vector_store.store_product_embedding(
                product_id=chunk_id,
                embedding=embedding,
                metadata=chunk_metadata,
                namespace="rag_chunks",
            )
            chunk_count += 1

        elapsed = time.time() - start_time
        logger.info(
            f"Vector upsert OK | product={product_id} chunks={chunk_count} time={elapsed:.3f}s"
        )

    def _process_delete(self, product_id: str) -> None:
        """Process delete event"""
        # 1. Delete main recommendation embedding
        success = self.vector_store.delete_product_embedding(
            product_id, namespace="products"
        )

        if not success:
            logger.warning(
                f"Vector delete failed or not found for product {product_id}"
            )

        chunk_types = [
            "overview",
            "technical",
            "design",
            "camera",
            "battery_connectivity",
            "warranty",
        ]

        for c_type in chunk_types:
            chunk_id = f"{product_id}_{c_type}"
            self.vector_store.delete_product_embedding(chunk_id, namespace="rag_chunks")

        logger.info(f"Vector deleted | product={product_id} (and associated chunks)")

    # ==================== LIFECYCLE ====================

    def start(self) -> None:
        """Start consumer"""
        if self._started:
            return

        self.event_processor.add_event_handler(self._handle_event)
        self.event_processor.start_consumer(consumer_id=self.worker_name)

        self._started = True
        logger.info(f"Product vector consumer started | worker={self.worker_name}")

    def stop(self) -> None:
        """Stop consumer"""
        self.event_processor.stop_consumer()
        self._started = False
        logger.info(
            f"Product vector consumer stopped | worker={self.worker_name} | "
            f"stats={self._stats}"
        )

    def get_stats(self) -> Dict[str, int]:
        """Get processing statistics"""
        return self._stats.copy()


# ==================== PROCESS BOOTSTRAP ====================


def start_vector_consumer_process(worker_name: Optional[str] = None) -> None:
    """Start consumer process with signal handling"""
    consumer = ProductEventHandler(worker_name)

    def shutdown_handler(sig, frame):
        logger.info("Shutdown signal received")
        stats = consumer.get_stats()
        logger.info(f"Final stats: {stats}")
        consumer.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    consumer.start()

    logger.info("Product vector consumer running... (Press Ctrl+C to stop)")

    # Periodic stats logging
    last_log = time.time()
    while True:
        time.sleep(1)

        # Log stats every 60 seconds
        if time.time() - last_log > 60:
            stats = consumer.get_stats()
            logger.info(f"Stats: {stats}")
            last_log = time.time()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Product Vector Kafka Consumer")
    parser.add_argument("--worker-name", type=str, help="Worker name/ID")
    args = parser.parse_args()

    start_vector_consumer_process(args.worker_name)

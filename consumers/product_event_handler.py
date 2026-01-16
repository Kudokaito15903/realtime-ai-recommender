"""
Product Event Handler - IMPROVED VERSION
Fixes: Metadata schema, validation, performance, consistency
"""

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
    variants: str = "[]"    # JSON string
    
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
                if key in ['category_ids', 'tags', 'available_colors', 'available_sizes']:
                    data[key] = []
                elif key in ['attributes', 'variants']:
                    data[key] = "{}" if key == "attributes" else "[]"
        return data


class DataValidator:
    """Validate and sanitize product data"""
    
    @staticmethod
    def validate_product_id(data: Dict) -> Optional[str]:
        """Extract and validate product ID"""
        product_id = data.get("id") or data.get("product_id") or data.get("sku")
        
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
        'battery life', 'screen size', 'ram', 'storage', 
        'weight', 'dimensions', 'processor', 'cpu', 'gpu',
        'display', 'camera', 'connectivity', 'material'
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
        self._stats = {
            'processed': 0,
            'upserted': 0,
            'deleted': 0,
            'failed': 0
        }
        
        logger.info(f"ProductEventHandler initialized | worker={self.worker_name}")
    
    # ==================== EVENT HANDLING ====================
    
    def _handle_event(self, event: Dict[str, Any]) -> None:
        """Handle product event (with validation)"""
        
        if event.get("entityType") != "PRODUCT":
            return
        
        event_type = event.get("eventType")
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
            if event_type in ("CREATED", "UPDATED", "upsert"):
                self._process_upsert(product_id, data)
                self._stats['upserted'] += 1
            
            elif event_type == "DELETED":
                self._process_delete(product_id)
                self._stats['deleted'] += 1
            
            else:
                logger.warning(f"Unsupported event type: {event_type}")
                return
            
            self._stats['processed'] += 1
        
        except Exception as e:
            logger.exception(
                f"Product event FAILED | type={event_type} product={product_id} error={e}"
            )
            self._stats['failed'] += 1
            raise
    
    # ==================== BUSINESS LOGIC ====================
    
    def _process_upsert(self, product_id: str, data: Dict) -> None:
        """Process upsert event (OPTIMIZED)"""
        start_time = time.time()
        
        # Generate embedding
        embedding = self.embedding_model.get_product_embedding(data)
        
        # Build metadata (improved schema)
        metadata = self._build_metadata_v2(data)
        
        # Store in vector DB
        success = self.vector_store.store_product_embedding(
            product_id=product_id,
            embedding=embedding,
            metadata=metadata,
        )
        
        if not success:
            raise RuntimeError(f"Vector upsert failed for product {product_id}")
        
        elapsed = time.time() - start_time
        logger.info(f"Vector upsert OK | product={product_id} time={elapsed:.3f}s")
    
    def _process_delete(self, product_id: str) -> None:
        """Process delete event"""
        success = self.vector_store.delete_product_embedding(product_id)
        
        if not success:
            raise RuntimeError(f"Vector delete failed for product {product_id}")
        
        logger.info(f"Vector deleted | product={product_id}")
    
    # ==================== METADATA BUILDING (V2) ====================
    
    def _build_metadata_v2(self, data: Dict) -> Dict[str, Any]:
        """
        Build metadata with improved schema
        
        Key improvements:
        1. All filterable fields are primitives (not JSON strings)
        2. Proper validation and type conversion
        3. Calculate derived fields (discount, stock status)
        4. Rich data in JSON only when necessary
        """
        
        # Extract and validate core fields
        product_id = DataValidator.validate_product_id(data) or "unknown"
        sku = str(data.get("sku", product_id))
        name = str(data.get("name", ""))[:200]  # Limit length
        brand = str(data.get("brandName") or data.get("brand") or "")[:100]
        category = str(data.get("category", ""))[:100]
        
        # Commercial data (with validation)
        price = DataValidator.safe_float(data.get("price"), 0.0)
        list_price = DataValidator.safe_float(data.get("listPrice"), price)
        
        # Calculate discount
        has_discount = list_price > price and price > 0
        discount_percentage = (
            ((list_price - price) / list_price * 100)
            if has_discount
            else 0.0
        )
        
        # Stock status (try to infer from data)
        in_stock = data.get("inStock", True)
        if isinstance(in_stock, str):
            in_stock = in_stock.lower() not in ['false', '0', 'out of stock']
        
        # Quality metrics
        avg_rating = DataValidator.safe_float(data.get("avgRating"), 0.0)
        review_count = DataValidator.safe_int(data.get("reviewCount"), 0)
        
        # Media
        has_video = bool(data.get("videoUrl"))
        images = DataValidator.safe_list(data.get("images"))
        image_count = len(images)
        
        # Taxonomy
        category_ids = DataValidator.safe_list(data.get("categoryId"))
        tags = self._extract_tags(data)
        
        # Process variants (optimized)
        variants_data = DataValidator.safe_list(data.get("productVariants"))
        variant_info = self._process_variants(variants_data)
        
        # Process attributes (optimized)
        specs_data = DataValidator.safe_list(data.get("specifications"))
        attributes = self._process_attributes(specs_data)
        
        # Create metadata object
        metadata = ProductMetadata(
            entity_type="product",
            product_id=product_id,
            sku=sku,
            name=name,
            brand=brand,
            category=category,
            
            price=price,
            list_price=list_price,
            currency=data.get("currency", "VND"),
            in_stock=in_stock,
            has_discount=has_discount,
            discount_percentage=round(discount_percentage, 2),
            
            avg_rating=avg_rating,
            review_count=review_count,
            
            has_video=has_video,
            image_count=image_count,
            
            category_ids=category_ids,
            tags=tags,
            
            variant_count=variant_info['count'],
            available_colors=variant_info['colors'],
            available_sizes=variant_info['sizes'],
            
            attributes=json.dumps(attributes, ensure_ascii=False),
            variants=json.dumps(variant_info['variants'], ensure_ascii=False),
            
            embedding_version="v2",
            indexed_at=time.time(),
        )
        
        return metadata.to_dict()
    
    def _process_variants(self, variants_data: List[Dict]) -> Dict:
        """Process variants efficiently"""
        colors = set()
        sizes = set()
        variants = []
        
        for v in variants_data:
            if not isinstance(v, dict):
                continue
            
            # Extract color
            color = v.get("color", "").strip()
            if color:
                colors.add(color)
            
            # Extract size
            size = v.get("size", "").strip()
            if size:
                sizes.add(size)
            
            # Store variant summary
            variants.append({
                "sku": v.get("sku", ""),
                "name": v.get("variantName", ""),
                "color": color,
                "size": size,
                "price": DataValidator.safe_float(v.get("price")),
                "in_stock": v.get("inStock", True),
            })
        
        return {
            'count': len(variants),
            'colors': sorted(list(colors)),
            'sizes': sorted(list(sizes)),
            'variants': variants,
        }
    
    def _process_attributes(self, specs_data: List[Dict]) -> Dict:
        """Process specifications into structured attributes"""
        attributes = {}
        
        for spec in specs_data:
            if not isinstance(spec, dict):
                continue
            
            group = spec.get("group", "general").lower().strip()
            key = spec.get("key", "").lower().strip().replace(" ", "_")
            value = spec.get("value")
            
            if not key or value is None:
                continue
            
            # Group by category
            if group not in attributes:
                attributes[group] = {}
            
            attributes[group][key] = value
        
        return attributes
    
    def _extract_tags(self, data: Dict) -> List[str]:
        """Extract searchable tags"""
        tags = set()
        
        # Category
        category = data.get("category", "").strip()
        if category:
            tags.add(category.lower())
        
        # Category IDs
        for cid in DataValidator.safe_list(data.get("categoryId")):
            if cid:
                tags.add(str(cid).lower())
        
        # Brand
        brand = (data.get("brandName") or data.get("brand") or "").strip()
        if brand:
            tags.add(brand.lower())
        
        # Color (main product)
        color = data.get("color", "").strip()
        if color:
            tags.add(color.lower())
        
        return sorted(list(tags))
    
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
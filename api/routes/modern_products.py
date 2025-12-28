"""
Modern products API using the new adapter system.
This provides the same functionality but works with any backend (Redis, Pinecone+Supabase, etc.)
"""

import os
import sys
import time
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Path
from loguru import logger

# Add project root to path
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from data.schemas import BackendInfoResponse, ProductCreate
from adapters.factory import (
    get_event_processor,
    get_vector_store,
    get_product_store,
    get_backend_info,
)
from domain.embeddings.product_embeddings import get_embedding_model

# Initialize router
router = APIRouter()

# Initialize services using the modern adapter pattern
event_processor = get_event_processor()
vector_store = get_vector_store()
embedding_model = get_embedding_model()

# Product store will be available if configured
try:
    product_store = get_product_store()
    PRODUCT_STORE_AVAILABLE = True
except Exception as e:
    logger.warning(f"Product store not available: {e}")
    product_store = None
    PRODUCT_STORE_AVAILABLE = False


@router.get("/backend-info", response_model=BackendInfoResponse)
async def get_backend_information():
    try:
        backend_info = get_backend_info()

        backend_info["runtime_status"] = {
            "vector_store_ready": vector_store is not None,
            "event_processor_ready": event_processor is not None,
            "product_store_ready": PRODUCT_STORE_AVAILABLE,
            "embedding_model_ready": embedding_model is not None,
        }

        if hasattr(vector_store, "get_index_stats"):
            try:
                backend_info["vector_store_stats"] = True
            except Exception as e:
                backend_info["vector_store_stats"] = {"error": str(e)}

        return backend_info

    except Exception as e:
        logger.error(f"Error getting backend info: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get backend info: {str(e)}"
        )


@router.get("/{product_id}", response_model=Dict[str, Any])
async def get_product(
    product_id: str = Path(..., description="The ID of the product to retrieve"),
    include_similar: bool = Query(False, description="Include similar products"),
):
    """Get a product by ID using the modern system"""
    try:
        product_data = None

        # Try to get from product store if available
        if PRODUCT_STORE_AVAILABLE:
            product_data = product_store.get_product(product_id)
            if not product_data:
                raise HTTPException(
                    status_code=404, detail=f"Product {product_id} not found"
                )

        # If no product store, we can still check if vector embedding exists
        elif vector_store:
            embedding = vector_store.get_product_embedding(product_id)
            if embedding is None:
                raise HTTPException(
                    status_code=404, detail=f"Product {product_id} not found"
                )

            # Create minimal product data
            product_data = {
                "id": product_id,
                "name": f"Product {product_id}",
                "description": "Product data available in vector store only",
            }

        result = {"product": product_data}

        # Include similar products if requested
        if include_similar and vector_store:
            try:
                # Get product embedding
                product_embedding = vector_store.get_product_embedding(product_id)
                if product_embedding is not None:
                    # Find similar products
                    similar_products = vector_store.find_similar_products(
                        embedding=product_embedding, limit=6, min_score=0.7
                    )
                    result["similar_products"] = similar_products
                else:
                    result["similar_products"] = []
            except Exception as e:
                logger.error(f"Error finding similar products: {e}")
                result["similar_products"] = []

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving product: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve product: {str(e)}"
        )


@router.get("/similar/{product_id}", response_model=List[Dict[str, Any]])
async def get_similar_products(
    product_id: str = Path(
        ..., description="The ID of the product to find similar items for"
    ),
    limit: int = Query(6, description="Maximum number of similar products to return"),
    threshold: float = Query(0.7, description="Minimum similarity threshold"),
):
    """Find products similar to the given product ID using the modern system"""
    try:
        # Get product embedding
        product_embedding = vector_store.get_product_embedding(product_id)
        if product_embedding is None:
            raise HTTPException(
                status_code=404,
                detail=f"Product {product_id} not found in vector store",
            )

        # Find similar products
        similar_products = vector_store.find_similar_products(
            embedding=product_embedding, limit=limit, min_score=threshold
        )

        return similar_products

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error finding similar products: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to find similar products: {str(e)}"
        )


@router.get("/search/text", response_model=List[Dict[str, Any]])
async def search_products_by_text(
    query: str = Query(..., description="Text query to search for"),
    limit: int = Query(10, description="Maximum number of results"),
    category: Optional[str] = Query(None, description="Filter by category"),
):
    """Search for products using text similarity via the modern system"""
    try:
        # Generate embedding for the search query
        query_embedding = embedding_model.embed_text(query)

        # Search for similar products
        similar_products = vector_store.find_similar_products(
            embedding=query_embedding,
            limit=limit,
            min_score=0.3,  # Lower threshold for text search
        )

        # Filter by category if specified
        if category:
            similar_products = [
                product
                for product in similar_products
                if product.get("metadata", {}).get("category", "").lower()
                == category.lower()
            ]

        return similar_products

    except Exception as e:
        logger.error(f"Error searching products by text: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to search products: {str(e)}"
        )


@router.post("/", response_model=Dict[str, Any], status_code=201)
async def create_product(product: ProductCreate):
    """Create a new product using the modern system"""
    try:
        # Convert Pydantic model to dict
        product_data = product.dict()
        product_id = product_data.get("id")

        if not product_id:
            raise HTTPException(status_code=400, detail="Product ID is required")

        # Store product in product store if available
        if PRODUCT_STORE_AVAILABLE:
            try:
                product_store.store_product(product_data)
                logger.info(f"Stored product {product_id} in product store")
            except Exception as e:
                logger.error(
                    f"Failed to store product {product_id} in product store: {e}"
                )
                # Continue even if product store fails

        # Generate embedding for the product
        try:
            start_time = time.time()
            product_embedding = embedding_model.get_product_embedding(product_data)

            # Prepare metadata for vector storage
            # Extract category from categoryId if available
            category = product_data.get("category")
            if not category and product_data.get("categoryId"):
                category_id = product_data.get("categoryId")
                if isinstance(category_id, list) and len(category_id) > 0:
                    category = category_id[0]
                elif isinstance(category_id, str):
                    category = category_id

            # Get price from first variant if not at product level
            price = product_data.get("price")
            if price is None and product_data.get("productVariants"):
                variants = product_data.get("productVariants")
                if variants and len(variants) > 0:
                    price = (
                        variants[0].get("price")
                        if isinstance(variants[0], dict)
                        else None
                    )

            metadata = {
                "category": category or "unknown",
                "name": product_data.get("name", "unknown"),
                "price": str(price or 0),
                "description": product_data.get("description", ""),
                "brandName": product_data.get("brandName", ""),
            }

            # Store in vector database
            success = vector_store.store_product_embedding(
                product_id=product_id, embedding=product_embedding, metadata=metadata
            )

            if success:
                processing_time = time.time() - start_time
                logger.info(f"Created product {product_id} in {processing_time:.4f}s")
            else:
                logger.error(f"Failed to store embedding for product {product_id}")
        except Exception as e:
            logger.error(f"Error generating embedding for product {product_id}: {e}")
            # Continue even if embedding generation fails

        # Publish event if event processor is available
        if event_processor:
            try:
                event_data = {
                    "id": product_id,
                    "event_type": "create",
                    "timestamp": time.time(),
                    "data": product_data,
                }
                event_processor.publish_event(event_data)
                logger.info(f"Published create event for product {product_id}")
            except Exception as e:
                logger.error(f"Failed to publish event for product {product_id}: {e}")

        return {
            "id": product_id,
            "status": "created",
            "product": product_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating product: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create product: {str(e)}"
        )


@router.get("/", response_model=List[Dict[str, Any]])
async def list_products(
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(100, description="Maximum number of products"),
    offset: int = Query(0, description="Number of products to skip"),
):
    """List products using the modern system"""
    if not PRODUCT_STORE_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="Product listing not available. Product store backend not configured.",
        )

    try:
        products = product_store.list_products(
            category=category, limit=limit, offset=offset
        )

        return products

    except Exception as e:
        logger.error(f"Error listing products: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to list products: {str(e)}"
        )

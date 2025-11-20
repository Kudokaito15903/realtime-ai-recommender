"""
Modern products API using the new adapter system.
This provides the same functionality but works with any backend (Redis, Pinecone+Supabase, etc.)
"""

import os
import sys
import time
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Path, BackgroundTasks
from pydantic import BaseModel
from loguru import logger

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from data.schemas import ProductCreate, ProductUpdate, Product, SimilarProductResult
from adapters.factory import get_event_processor, get_vector_store, get_product_store, get_backend_info
from models.embeddings import get_embedding_model

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


@router.get("/backend-info", response_model=Dict[str, Any])
async def get_backend_information():
    """Get information about the current backend configuration"""
    try:
        backend_info = get_backend_info()

        # Add runtime status
        backend_info["runtime_status"] = {
            "vector_store_ready": vector_store is not None,
            "event_processor_ready": event_processor is not None,
            "product_store_ready": PRODUCT_STORE_AVAILABLE,
            "embedding_model_ready": embedding_model is not None
        }

        # Add vector store stats if available
        if hasattr(vector_store, 'get_index_stats'):
            try:
                backend_info["vector_store_stats"] = vector_store.get_index_stats()
            except Exception as e:
                backend_info["vector_store_stats"] = {"error": str(e)}

        return backend_info

    except Exception as e:
        logger.error(f"Error getting backend info: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get backend info: {str(e)}")


@router.post("/", response_model=Dict[str, Any])
async def create_product(product: ProductCreate, background_tasks: BackgroundTasks):
    """Create a new product using the modern backend-agnostic system"""
    # Ensure product has an ID
    if not product.id:
        raise HTTPException(status_code=400, detail="Product ID is required")

    start_time = time.time()

    # Convert to dict for easier handling
    product_dict = product.model_dump()

    # Add creation timestamp
    product_dict["created_at"] = time.time()
    product_dict["updated_at"] = time.time()

    try:
        # Store in product store if available
        if PRODUCT_STORE_AVAILABLE:
            success = product_store.store_product(product_dict)
            if not success:
                logger.warning(f"Failed to store product {product.id} in product store")

        # Publish event for real-time processing (vector embeddings, etc.)
        event_id = event_processor.publish_product_created(product_dict)

        # Return success response
        return {
            "status": "success",
            "message": "Product created successfully",
            "product_id": product.id,
            "event_id": event_id,
            "backend_type": get_backend_info()["backend_type"],
            "processing_time": time.time() - start_time
        }

    except Exception as e:
        logger.error(f"Error creating product: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create product: {str(e)}")


@router.put("/{product_id}", response_model=Dict[str, Any])
async def update_product(
    product_id: str = Path(..., description="The ID of the product to update"),
    update_data: ProductUpdate = None,
    background_tasks: BackgroundTasks = None
):
    """Update an existing product using the modern system"""
    if not update_data:
        raise HTTPException(status_code=400, detail="Update data is required")

    start_time = time.time()

    try:
        # Check if product exists (if product store is available)
        if PRODUCT_STORE_AVAILABLE:
            existing_product = product_store.get_product(product_id)
            if not existing_product:
                raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

        # Convert to dict for easier handling
        update_dict = update_data.model_dump(exclude_unset=True)

        # Add updated timestamp
        update_dict["updated_at"] = time.time()
        update_dict["id"] = product_id  # Ensure ID is included

        # Update in product store if available
        if PRODUCT_STORE_AVAILABLE:
            # Merge with existing data
            merged_data = {**existing_product, **update_dict}
            success = product_store.store_product(merged_data)
            if not success:
                logger.warning(f"Failed to update product {product_id} in product store")

        # Publish event for real-time processing
        event_id = event_processor.publish_product_updated(product_id, update_dict)

        # Return success response
        return {
            "status": "success",
            "message": "Product updated successfully",
            "product_id": product_id,
            "event_id": event_id,
            "backend_type": get_backend_info()["backend_type"],
            "processing_time": time.time() - start_time
        }

    except Exception as e:
        logger.error(f"Error updating product: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update product: {str(e)}")


@router.delete("/{product_id}", response_model=Dict[str, Any])
async def delete_product(
    product_id: str = Path(..., description="The ID of the product to delete"),
    background_tasks: BackgroundTasks = None
):
    """Delete a product using the modern system"""
    start_time = time.time()

    try:
        # Check if product exists and delete from product store if available
        if PRODUCT_STORE_AVAILABLE:
            existing_product = product_store.get_product(product_id)
            if not existing_product:
                raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

            success = product_store.delete_product(product_id)
            if not success:
                logger.warning(f"Failed to delete product {product_id} from product store")

        # Publish event for real-time processing (will delete vector embedding)
        event_id = event_processor.publish_product_deleted(product_id)

        # Return success response
        return {
            "status": "success",
            "message": "Product deleted successfully",
            "product_id": product_id,
            "event_id": event_id,
            "backend_type": get_backend_info()["backend_type"],
            "processing_time": time.time() - start_time
        }

    except Exception as e:
        logger.error(f"Error deleting product: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete product: {str(e)}")


@router.get("/{product_id}", response_model=Dict[str, Any])
async def get_product(
    product_id: str = Path(..., description="The ID of the product to retrieve"),
    include_similar: bool = Query(False, description="Include similar products")
):
    """Get a product by ID using the modern system"""
    try:
        product_data = None

        # Try to get from product store if available
        if PRODUCT_STORE_AVAILABLE:
            product_data = product_store.get_product(product_id)
            if not product_data:
                raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

        # If no product store, we can still check if vector embedding exists
        elif vector_store:
            embedding = vector_store.get_product_embedding(product_id)
            if embedding is None:
                raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

            # Create minimal product data
            product_data = {
                "id": product_id,
                "name": f"Product {product_id}",
                "description": "Product data available in vector store only"
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
                        embedding=product_embedding,
                        limit=6,
                        min_score=0.7
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
        raise HTTPException(status_code=500, detail=f"Failed to retrieve product: {str(e)}")


@router.get("/similar/{product_id}", response_model=List[Dict[str, Any]])
async def get_similar_products(
    product_id: str = Path(..., description="The ID of the product to find similar items for"),
    limit: int = Query(6, description="Maximum number of similar products to return"),
    threshold: float = Query(0.7, description="Minimum similarity threshold")
):
    """Find products similar to the given product ID using the modern system"""
    try:
        # Get product embedding
        product_embedding = vector_store.get_product_embedding(product_id)
        if product_embedding is None:
            raise HTTPException(status_code=404, detail=f"Product {product_id} not found in vector store")

        # Find similar products
        similar_products = vector_store.find_similar_products(
            embedding=product_embedding,
            limit=limit,
            min_score=threshold
        )

        return similar_products

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error finding similar products: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to find similar products: {str(e)}")


@router.get("/search/text", response_model=List[Dict[str, Any]])
async def search_products_by_text(
    query: str = Query(..., description="Text query to search for"),
    limit: int = Query(10, description="Maximum number of results"),
    category: Optional[str] = Query(None, description="Filter by category")
):
    """Search for products using text similarity via the modern system"""
    try:
        # Generate embedding for the search query
        query_embedding = embedding_model.get_text_embedding(query)

        # Search for similar products
        similar_products = vector_store.find_similar_products(
            embedding=query_embedding,
            limit=limit,
            min_score=0.3  # Lower threshold for text search
        )

        # Filter by category if specified
        if category:
            similar_products = [
                product for product in similar_products
                if product.get('metadata', {}).get('category', '').lower() == category.lower()
            ]

        return similar_products

    except Exception as e:
        logger.error(f"Error searching products by text: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search products: {str(e)}")


@router.get("/", response_model=List[Dict[str, Any]])
async def list_products(
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(100, description="Maximum number of products"),
    offset: int = Query(0, description="Number of products to skip")
):
    """List products using the modern system"""
    if not PRODUCT_STORE_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="Product listing not available. Product store backend not configured."
        )

    try:
        products = product_store.list_products(
            category=category,
            limit=limit,
            offset=offset
        )

        return products

    except Exception as e:
        logger.error(f"Error listing products: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list products: {str(e)}")
 
import os
import sys
import json
import time
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Path, Depends, BackgroundTasks
from pydantic import BaseModel
import redis
from loguru import logger

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_DB
from data.schemas import ProductCreate, ProductUpdate, Product, SimilarProductResult
from services.stream_producer import get_product_event_producer
from models.similarity import get_similarity_search
from models.recommendations import get_product_recommender


# Initialize router
router = APIRouter()

# Initialize services
product_event_producer = get_product_event_producer()
similarity_search = get_similarity_search()
product_recommender = get_product_recommender()

# Initialize Redis client
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    db=REDIS_DB,
    decode_responses=True
)


@router.post("/", response_model=Dict[str, Any])
async def create_product(product: ProductCreate, background_tasks: BackgroundTasks):
    """Create a new product and process it in real-time"""
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
        # Store basic product data in Redis
        redis_key = f"product:{product.id}"
        
        # Convert dictionary values to strings for Redis
        redis_data = {}
        for key, value in product_dict.items():
            if isinstance(value, dict):
                # Convert nested dictionaries to JSON strings
                redis_data[key] = json.dumps(value)
            else:
                # Convert other values to strings
                redis_data[key] = str(value)
        
        # Store in Redis
        redis_client.hset(redis_key, mapping=redis_data)
        
        # Publish event to stream for real-time processing
        event_id = product_event_producer.publish_product_created(product_dict)
        
        # Return success response
        return {
            "status": "success",
            "message": "Product created successfully",
            "product_id": product.id,
            "event_id": event_id,
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
    """Update an existing product"""
    if not update_data:
        raise HTTPException(status_code=400, detail="Update data is required")
    
    # Check if product exists
    if not redis_client.exists(f"product:{product_id}"):
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
    
    start_time = time.time()
    
    try:
        # Convert to dict for easier handling
        update_dict = update_data.model_dump(exclude_unset=True)
        
        # Add updated timestamp
        update_dict["updated_at"] = time.time()
        
        # Convert dictionary values to strings
        redis_data = {}
        for key, value in update_dict.items():
            if isinstance(value, dict):
                # Convert nested dictionaries to JSON strings
                redis_data[key] = json.dumps(value)
            else:
                # Convert other values to strings
                redis_data[key] = str(value)
        
        # Update in Redis
        redis_client.hset(f"product:{product_id}", mapping=redis_data)
        
        # Publish event to stream for real-time processing
        event_id = product_event_producer.publish_product_updated(product_id, update_dict)
        
        # Return success response
        return {
            "status": "success",
            "message": "Product updated successfully",
            "product_id": product_id,
            "event_id": event_id,
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
    """Delete a product"""
    # Check if product exists
    if not redis_client.exists(f"product:{product_id}"):
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
    
    start_time = time.time()
    
    try:
        # Delete from Redis
        redis_client.delete(f"product:{product_id}")
        
        # Publish event to stream for real-time processing
        event_id = product_event_producer.publish_product_deleted(product_id)
        
        # Return success response
        return {
            "status": "success",
            "message": "Product deleted successfully",
            "product_id": product_id,
            "event_id": event_id,
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
    """Get a product by ID with option to include similar products"""
    # Check if product exists
    if not redis_client.exists(f"product:{product_id}"):
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
    
    try:
        # Get product data from Redis
        product_data = redis_client.hgetall(f"product:{product_id}")
        
        # Parse attributes if needed
        if 'attributes' in product_data and isinstance(product_data['attributes'], str):
            try:
                product_data['attributes'] = json.loads(product_data['attributes'])
            except json.JSONDecodeError:
                product_data['attributes'] = {}
        
        # Convert timestamps
        for field in ['created_at', 'updated_at']:
            if field in product_data and product_data[field]:
                try:
                    product_data[field] = float(product_data[field])
                except (ValueError, TypeError):
                    pass
        
        result = {"product": product_data}
        
        # Include similar products if requested
        if include_similar:
            similar_products = similarity_search.search_by_product_id(
                product_id=product_id,
                limit=6,
                threshold=0.7
            )
            result["similar_products"] = similar_products
        
        return result
    
    except Exception as e:
        logger.error(f"Error retrieving product: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve product: {str(e)}")


@router.get("/similar/{product_id}", response_model=List[SimilarProductResult])
async def get_similar_products(
    product_id: str = Path(..., description="The ID of the product to find similar items for"),
    limit: int = Query(6, description="Maximum number of similar products to return"),
    threshold: float = Query(0.7, description="Minimum similarity threshold")
):
    """Find products similar to the given product ID"""
    # Check if product exists
    if not redis_client.exists(f"product:{product_id}"):
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
    
    try:
        # Track view for recommendations (if needed)
        # product_recommender.track_product_view(None, product_id)
        
        # Find similar products
        similar_products = similarity_search.search_by_product_id(
            product_id=product_id,
            limit=limit,
            threshold=threshold
        )
        
        return similar_products
    
    except Exception as e:
        logger.error(f"Error finding similar products: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to find similar products: {str(e)}")


@router.get("/search/text", response_model=List[Dict[str, Any]])
async def search_products_by_text(
    query: str = Query(..., description="Text query to search for"),
    limit: int = Query(10, description="Maximum number of results"),
    category: Optional[str] = Query(None, description="Filter by category")
):
    """Search for products using text similarity"""
    try:
        # Set up category filter
        categories = [category] if category else None
        
        # Perform text search
        results = similarity_search.search_by_text(
            query_text=query,
            limit=limit,
            categories=categories
        )
        
        return results
    
    except Exception as e:
        logger.error(f"Error searching products: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search products: {str(e)}")
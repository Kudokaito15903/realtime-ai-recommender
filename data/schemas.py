 
from typing import Dict, List, Optional, Union, Any
from datetime import datetime
from pydantic import BaseModel, Field, validator
import uuid


class ProductBase(BaseModel):
    """Base model for product data"""
    name: str
    description: str
    category: str
    price: float
    sku: str
    attributes: Dict[str, Any] = Field(default_factory=dict)


class ProductCreate(ProductBase):
    """Model for creating a new product"""
    id: Optional[str] = None

    @validator('id', pre=True, always=True)
    def default_id(cls, v):
        """Generate a UUID if id is not provided"""
        return v or str(uuid.uuid4())


class ProductUpdate(BaseModel):
    """Model for updating an existing product"""
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    sku: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None


class Product(ProductBase):
    """Model for a product with metadata"""
    id: str
    created_at: datetime
    updated_at: datetime
    embedding_updated_at: Optional[datetime] = None


class ProductEvent(BaseModel):
    """Model for product event in the stream"""
    id: str
    event_type: str  # "create", "update", "delete"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: Union[ProductCreate, ProductUpdate, Dict[str, Any]]


class SimilarProductResult(BaseModel):
    """Model for similar product search result"""
    product_id: str
    similarity_score: float


class ProductRecommendation(BaseModel):
    """Model for product recommendation"""
    product_id: str
    score: float
    recommendation_type: str  # "similar", "frequently_bought_together", "popular_in_category"


class RecommendationResponse(BaseModel):
    """Model for recommendation API response"""
    recommendations: List[ProductRecommendation]
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    generated_at: datetime = Field(default_factory=datetime.utcnow)
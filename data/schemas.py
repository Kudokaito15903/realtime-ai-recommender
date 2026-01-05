from typing import Dict, List, Optional, Union, Any
from datetime import datetime
from pydantic import BaseModel, Field, validator
import uuid


class CloudServicesInfo(BaseModel):
    pinecone_configured: bool
    supabase_configured: bool


class RuntimeStatus(BaseModel):
    vector_store_ready: bool
    event_processor_ready: bool
    product_store_ready: bool
    embedding_model_ready: bool


class BackendInfoResponse(BaseModel):
    vector_store: str
    event_processor: str
    product_store: str
    user_behavior: str
    backend_type: str
    cloud_services: CloudServicesInfo
    runtime_status: RuntimeStatus
    vector_store_stats: bool = None


class Specification(BaseModel):
    """Model for product specification"""

    key: str
    value: Union[str, int, float]
    type: str  # "TEXT", "NUMBER", etc.
    group: str  # "TECHNICAL", "DISPLAY", etc.


class ProductVariant(BaseModel):
    """Model for product variant"""

    sku: str
    variantName: str
    color: Optional[str] = None
    price: float
    bestSpecifications: Optional[List["Specification"]] = None


class ProductBase(BaseModel):
    """Base model for product data"""

    name: str
    description: str
    category: Optional[str] = None  # Made optional for variant-based products
    price: Optional[float] = None  # Made optional, can be in variants
    sku: Optional[str] = None  # Made optional, can be in variants

    # New fields from the JSON structure
    brandName: Optional[str] = None
    videoUrl: Optional[str] = None
    avgRating: Optional[float] = 0.0
    categoryId: Optional[List[str]] = None  # Changed to list
    specifications: Optional[List[Specification]] = (
        None  # Changed to list of Specification
    )
    productVariants: Optional[List[ProductVariant]] = None

    # Legacy/optional fields for backward compatibility
    color: Optional[str] = None
    listPrice: Optional[float] = None
    sold: Optional[int] = None
    thumbnail: Optional[str] = None
    imageList: Optional[List[str]] = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    """Model for updating an existing product"""

    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    sku: Optional[str] = None
    color: Optional[str] = None
    listPrice: Optional[float] = None
    sold: Optional[int] = None
    avgRating: Optional[float] = None
    videoUrl: Optional[str] = None
    categoryId: Optional[Union[str, List[str]]] = None  # Support both string and list
    specifications: Optional[Union[Dict[str, Any], List[Specification]]] = (
        None  # Support both formats
    )
    thumbnail: Optional[str] = None
    imageList: Optional[List[str]] = None
    brandName: Optional[str] = None
    productVariants: Optional[List[ProductVariant]] = None


class Product(ProductBase):
    """Model for a product with metadata"""

    product_id: str = Field(alias="_id")
    created_at: datetime
    updated_at: datetime
    embedding_updated_at: Optional[datetime] = None
    
class SimilarProductResult(BaseModel):
    """Model for similar product search result"""

    product_id: str
    similarity_score: float
    sold: Optional[int] = None
    avgRating: Optional[float] = None
    price: Optional[float] = None
    listPrice: Optional[float] = None
    category: Optional[str] = None
    thumbnail: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class RecommendedVariant(BaseModel):
    """Model for recommended variant"""

    sku: str
    variantName: str
    color: Optional[str] = None
    price: float


class ProductRecommendation(BaseModel):
    """Model for product recommendation"""

    product_id: str
    score: float
    recommendation_type: (
        str  # "similar", "frequently_bought_together", "popular_in_category"
    )
    recommended_variant: Optional[RecommendedVariant] = (
        None  # Selected variant for this product
    )


class ContentCreate(BaseModel):
    title: str
    content: str
    category: str  # e.g., 'faq', 'policy', 'guide', 'blog', 'cskh'
    tags: Optional[List[str]] = []
    status: Optional[str] = "published"  # 'draft', 'published', 'archived'


class ContentUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None

class ContentResponse(BaseModel):
    content_id: str = Field(alias="id")
    title: str
    content: str
    category: Optional[str]
    status: str


class ContentStatusResponse(BaseModel):
    content_id: str
    status: str


class ContentListResponse(BaseModel):
    items: List[ContentResponse]
    total: int
    limit: int
    offset: int
    has_more: bool


class ContentSearchResponse(BaseModel):
    query: str
    results: List[ContentResponse]
    count: int
 
class RecommendationResponse(BaseModel):
    """Model for recommendation API response"""

    recommendations: List[ProductRecommendation]
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# Update forward references
ProductVariant.update_forward_refs()

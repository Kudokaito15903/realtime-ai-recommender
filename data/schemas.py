from typing import Dict, List, Optional, Union, Any
from datetime import datetime
from pydantic import BaseModel, Field, validator
import uuid

# ==================== CLOUD SERVICES INFO ====================
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
    vector_store_stats: Optional[dict] = None  # Changed from bool to dict


# ==================== PRODUCT MODELS ====================

class Specification(BaseModel):
    """Model for product specification"""
    key: str
    value: str  # ✅ FIXED: Always string (e.g., "231 g", "12 GB")
    type: str = "TECH"
    group: str = "General"
class Category(BaseModel):
    """Model for product category"""
    id: str
    name: str
class ProductVariant(BaseModel):
    """Model for product variant"""
    id: Optional[str] = None  # ✅ ADDED: Variant ID (auto-generated if not provided)
    sku: Optional[str] = None  # ✅ Auto-generated if not provided
    variantName: str
    color: Optional[str] = None
    price: float
    inStock: bool = True

class ProductBase(BaseModel):
    """Base model for product data"""
    name: str
    brand: str
    description: str
    listPrice: float  # ✅ REQUIRED (not optional)
    currency: str = "VND"
    inStock: bool = True
    warranty: Optional[str] = None  # ✅ FIXED: No default, user provides
    categories: List[Category] = []
    images: List[str] = []
    videoUrl: Optional[str] = ""
    specifications: List[Specification] = []
    productVariants: List[ProductVariant] = []

    @validator('listPrice')
    def validate_price(cls, v):
        if v < 0:
            raise ValueError('listPrice must be non-negative')
        return v

    @validator('productVariants')
    def validate_variants(cls, v):
        if not v:
            raise ValueError('At least one product variant is required')
        return v
class ProductCreate(ProductBase):
    """Model for creating a new product"""
    pass

class ProductUpdate(BaseModel):
    """Model for updating an existing product (all fields optional)"""
    name: Optional[str] = None
    brand: Optional[str] = None
    description: Optional[str] = None
    listPrice: Optional[float] = None
    currency: Optional[str] = None
    inStock: Optional[bool] = None
    warranty: Optional[str] = None
    categories: Optional[List[Category]] = None
    images: Optional[List[str]] = None
    videoUrl: Optional[str] = None
    specifications: Optional[List[Specification]] = None
    productVariants: Optional[List[ProductVariant]] = None

    @validator('listPrice')
    def validate_price(cls, v):
        if v is not None and v < 0:
            raise ValueError('listPrice must be non-negative')
        return v


class Product(BaseModel):
    """Model for product response (from database)"""
    id: str  # ✅ FIXED: MongoDB _id converted to string
    name: str
    brand: str
    description: str
    listPrice: float
    currency: str = "VND"
    inStock: bool = True
    warranty: Optional[str] = None
    categories: List[Category] = []
    categoryId: List[str] = []
    images: List[str] = []
    videoUrl: Optional[str] = ""
    specifications: List[Specification] = []
    productVariants: List[ProductVariant] = []
    
    variants: List[str] = []  # Array of SKUs
    created_at: Optional[datetime] = Field(None, alias="create_at")
    updated_at: Optional[datetime] = Field(None, alias="update_at")
class ProductListResponse(BaseModel):
    """Model for paginated product list response"""
    products: List[Product]
    total: int
    limit: int
    offset: int
    has_more: bool


class ProductSearchResponse(BaseModel):
    """Model for product search results"""
    results: List[Product]
    query: str
    total: int
    
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
    category: Optional[str] = None
    brandName: Optional[str] = None
    recommendation_type: str  # "similar", "frequently_bought_together", "popular_in_category"
    recommended_variant: Optional[RecommendedVariant] = None

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
    page: int
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
# ProductVariant.update_forward_refs() # Not strictly needed with Python 3.9+ typing if ordered correctly

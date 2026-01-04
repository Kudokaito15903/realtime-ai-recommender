import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ================================
# BACKEND SELECTION CONFIGURATION
# ================================

# Backend type selection: 'redis', 'cloud', 'hybrid'
# Default to hybrid stack: Pinecone (vector store) + Postgres (events/data) + Redis (legacy/caching)
BACKEND_TYPE = os.getenv("BACKEND_TYPE", "hybrid")

# Component-specific backend selection
VECTOR_STORE_TYPE = os.getenv(
    "VECTOR_STORE_TYPE", "pinecone"
)  # redis, pinecone, qdrant, chroma, elasticsearch
EVENT_PROCESSOR_TYPE = os.getenv(
    "EVENT_PROCESSOR_TYPE", "postgres"
)  # redis, supabase, nats, memory, postgres
DATA_STORE_TYPE = os.getenv(
    "DATA_STORE_TYPE", "postgres"
)  # redis, supabase, postgresql, sqlite
BEHAVIOR_STORE_TYPE = os.getenv("BEHAVIOR_STORE_TYPE", "postgres")

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "product-events")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "recommender-group")

# ================================
# CLOUD SERVICES CONFIGURATION
# ================================

# Pinecone Configuration
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT", "us-east-1")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "product-recommendations")

# Elasticsearch Configuration
ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
ELASTICSEARCH_API_KEY = os.getenv("ELASTICSEARCH_API_KEY")
ELASTICSEARCH_INDEX_NAME = os.getenv("ELASTICSEARCH_INDEX_NAME", "product-recommendations")

# Supabase Configuration (optional, kept for backward compatibility)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# PostgreSQL Configuration (self-hosted)
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_DB = os.getenv("POSTGRES_DB", "realtime_ai")
POSTGRES_USER = os.getenv("POSTGRES_USER", "realtime_ai")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "realtime_ai")

# MongoDB Configuration
MONGODB_HOST = os.getenv("MONGODB_HOST", "localhost")
MONGODB_PORT = int(os.getenv("MONGODB_PORT", 27017))
MONGODB_DB = os.getenv("MONGODB_DB", "realtime_ai")
MONGODB_USER = os.getenv("MONGODB_USER", None)
MONGODB_PASSWORD = os.getenv("MONGODB_PASSWORD", None)
MONGODB_AUTH_SOURCE = os.getenv("MONGODB_AUTH_SOURCE", "admin")
MONGODB_URI = os.getenv(
    "MONGODB_URI", None
)  # Full connection string (overrides individual settings)

# ================================
# LEGACY REDIS CONFIGURATION
# ================================

# Redis Configuration (for fallback or hybrid mode)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# Stream Configuration (Redis Streams)
PRODUCT_STREAM_KEY = os.getenv("PRODUCT_STREAM_KEY", "product:updates")
PRODUCT_STREAM_GROUP = os.getenv("PRODUCT_STREAM_GROUP", "product-processors")
PRODUCT_STREAM_CONSUMER = os.getenv("PRODUCT_STREAM_CONSUMER", "worker-{}")

# Vector Store Configuration (Redis)
VECTOR_INDEX_NAME = os.getenv("VECTOR_INDEX_NAME", "product:vectors")

# ================================
# SHARED CONFIGURATION
# ================================

# Vector Configuration
VECTOR_DIMENSION = int(
    os.getenv("VECTOR_DIMENSION", 384)
)  # Dimension from all-MiniLM-L6-v2
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", 0.75))

# Model Configuration
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
MODEL_CACHE_DIR = os.getenv("MODEL_CACHE_DIR", "./model_cache")

# ================================
# RECOMMENDER CONFIGURATION (ALS / Session)
# ================================

# ALS (implicit feedback) settings
ALS_MODEL_PATH = os.getenv(
    "ALS_MODEL_PATH", os.path.join(MODEL_CACHE_DIR, "als_model.npz")
)
ALS_FACTORS = int(os.getenv("ALS_FACTORS", 64))
ALS_ITERATIONS = int(os.getenv("ALS_ITERATIONS", 15))
ALS_REGULARIZATION = float(os.getenv("ALS_REGULARIZATION", 0.1))
ALS_ALPHA = float(os.getenv("ALS_ALPHA", 40.0))
ALS_TRAINING_INTERACTIONS_LIMIT = int(
    os.getenv("ALS_TRAINING_INTERACTIONS_LIMIT", 50000)
)
ALS_REFRESH_SECONDS = int(os.getenv("ALS_REFRESH_SECONDS", 24 * 3600))  # 24h

# ALS Data Quality Settings
ALS_DATA_QUALITY_ENABLED = (
    os.getenv("ALS_DATA_QUALITY_ENABLED", "True").lower() == "true"
)
ALS_REMOVE_DUPLICATES = os.getenv("ALS_REMOVE_DUPLICATES", "True").lower() == "true"
ALS_REMOVE_OUTLIERS = os.getenv("ALS_REMOVE_OUTLIERS", "True").lower() == "true"
ALS_OUTLIER_THRESHOLD_STD = float(os.getenv("ALS_OUTLIER_THRESHOLD_STD", "3.0"))
ALS_REMOVE_STALE = os.getenv("ALS_REMOVE_STALE", "True").lower() == "true"
ALS_MAX_AGE_DAYS = int(os.getenv("ALS_MAX_AGE_DAYS", "90"))
ALS_REMOVE_COLD_START = os.getenv("ALS_REMOVE_COLD_START", "True").lower() == "true"
ALS_MIN_USER_INTERACTIONS = int(os.getenv("ALS_MIN_USER_INTERACTIONS", "2"))
ALS_MIN_PRODUCT_INTERACTIONS = int(os.getenv("ALS_MIN_PRODUCT_INTERACTIONS", "2"))

# ALS Normalization Settings
ALS_NORMALIZATION_METHOD = os.getenv(
    "ALS_NORMALIZATION_METHOD", "none"
)  # none, log, minmax, zscore, sqrt

# ALS Feature Engineering Settings
ALS_TEMPORAL_WEIGHTING_ENABLED = (
    os.getenv("ALS_TEMPORAL_WEIGHTING_ENABLED", "False").lower() == "true"
)
ALS_RECENCY_HALF_LIFE_DAYS = float(os.getenv("ALS_RECENCY_HALF_LIFE_DAYS", "30.0"))

# Session-based recommendations
SESSION_GAP_SECONDS = int(os.getenv("SESSION_GAP_SECONDS", 30 * 60))  # 30 minutes
SESSION_TRANSITIONS_LIMIT = int(os.getenv("SESSION_TRANSITIONS_LIMIT", 20000))
SESSION_TRANSITIONS_REFRESH_SECONDS = int(
    os.getenv("SESSION_TRANSITIONS_REFRESH_SECONDS", 5 * 60)
)  # 5m
SESSION_RECENT_K = int(os.getenv("SESSION_RECENT_K", 5))
# Enhanced session recommendation parameters
SESSION_TIME_DECAY_HALF_LIFE_DAYS = float(
    os.getenv("SESSION_TIME_DECAY_HALF_LIFE_DAYS", 7.0)
)  # 7 days (was 30) - faster decay for trends
SESSION_HISTORY_DECAY = float(
    os.getenv("SESSION_HISTORY_DECAY", 0.7)
)  # Weight decay for position in history (recency)
SESSION_DIVERSITY_LAMBDA = float(
    os.getenv("SESSION_DIVERSITY_LAMBDA", 0.3)
)  # Diversity penalty weight
SESSION_POPULARITY_NORMALIZATION = (
    os.getenv("SESSION_POPULARITY_NORMALIZATION", "True").lower() == "true"
)

# API Configuration
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", 8000))
DEBUG_MODE = os.getenv("DEBUG_MODE", "False").lower() == "true"

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4")
OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1")

# ================================
# HYBRID RECOMMENDER WEIGHTS
# ================================
HYBRID_WEIGHT_ALS = float(os.getenv("HYBRID_WEIGHT_ALS", 1.0))
HYBRID_WEIGHT_SESSION = float(os.getenv("HYBRID_WEIGHT_SESSION", 1.0))
HYBRID_WEIGHT_VECTOR = float(os.getenv("HYBRID_WEIGHT_VECTOR", 1.0))

#Chatbot 
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", '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')
OPENAI_MODEL= os.getenv("OPENAI_MODEL", 'google/gemma-3-27b-it:free')
OPENAI_API_URL = os.getenv("OPENAI_API_URL", 'https://openrouter.ai/api/v1')

# Brand & Fine-tuning
BRAND_PERSONALITY = os.getenv(
    "BRAND_PERSONALITY", 
    "Bạn là một trợ lý ảo nhiệt tình, am hiểu công nghệ và luôn sẵn sàng giúp đỡ. "
    "Hãy sử dụng ngôn ngữ trẻ trung, năng động nhưng vẫn giữ sự chuyên nghiệp. "
    "Luôn xưng hô là 'mình' hoặc 'Chatbot' và gọi khách hàng là 'bạn'."
)
COLLECT_FINE_TUNING_DATA = os.getenv("COLLECT_FINE_TUNING_DATA", "True").lower() == "true"

class Config:
    """Configuration class for easy access to settings."""

    def __init__(self):
        # Load environment variables
        load_dotenv()

        # Backend configuration (mirror module-level defaults)
        self.BACKEND_TYPE = os.getenv("BACKEND_TYPE", BACKEND_TYPE)
        self.VECTOR_STORE_TYPE = os.getenv("VECTOR_STORE_TYPE", VECTOR_STORE_TYPE)
        self.EVENT_PROCESSOR_TYPE = os.getenv(
            "EVENT_PROCESSOR_TYPE", EVENT_PROCESSOR_TYPE
        )
        self.DATA_STORE_TYPE = os.getenv("DATA_STORE_TYPE", DATA_STORE_TYPE)
        self.BEHAVIOR_STORE_TYPE = os.getenv("BEHAVIOR_STORE_TYPE", BEHAVIOR_STORE_TYPE)

        # Redis configuration
        self.REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
        self.REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
        self.REDIS_DB = int(os.getenv("REDIS_DB", 0))
        self.REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

        # API configuration
        self.API_HOST = os.getenv("API_HOST", "0.0.0.0")
        self.API_PORT = int(os.getenv("API_PORT", 8000))

        # Vector configuration
        self.VECTOR_DIMENSIONS = int(os.getenv("VECTOR_DIMENSION", 384))
        self.SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", 0.75))

        # Model configuration
        self.EMBEDDING_MODEL_NAME = os.getenv(
            "EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2"
        )
        self.MODEL_CACHE_DIR = os.getenv("MODEL_CACHE_DIR", "./model_cache")

        #Chatbot
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
        self.OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4")
        self.OPENAI_API_URL = os.getenv(
            "OPENAI_API_URL", "https://api.openai.com/v1"
        )
        # Logging
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.DEBUG_MODE = os.getenv("DEBUG_MODE", "False").lower() == "true"

        # Chatbot Configuration
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", OPENAI_API_KEY)
        self.OPENAI_MODEL = os.getenv("OPENAI_MODEL", OPENAI_MODEL) 
        self.OPENAI_API_URL = os.getenv("OPENAI_API_URL", OPENAI_API_URL)

        # Brand & Fine-tuning
        self.BRAND_PERSONALITY = os.getenv(
            "BRAND_PERSONALITY", 
            "Bạn là một trợ lý ảo nhiệt tình, am hiểu công nghệ và luôn sẵn sàng giúp đỡ. "
            "Hãy sử dụng ngôn ngữ trẻ trung, năng động nhưng vẫn giữ sự chuyên nghiệp. "
            "Luôn xưng hô là 'mình' hoặc 'Chatbot' và gọi khách hàng là 'bạn'."
        )
        self.COLLECT_FINE_TUNING_DATA = os.getenv("COLLECT_FINE_TUNING_DATA", "True").lower() == "true"

    def get_redis_url(self) -> str:
        """Get Redis connection URL."""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

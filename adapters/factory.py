"""
Factory functions to create the appropriate adapters based on configuration.
This provides a unified interface to switch between different backends.
"""

import os
from typing import Union
from loguru import logger

from .interfaces import VectorStoreInterface, EventProcessorInterface, ProductStoreInterface
import config


def create_vector_store() -> VectorStoreInterface:
    """Create vector store adapter based on configuration"""
    store_type = config.VECTOR_STORE_TYPE.lower()

    logger.info(f"Creating vector store: {store_type}")

    if store_type == "pinecone":
        from .pinecone_adapter import get_pinecone_vector_store
        return get_pinecone_vector_store()

    elif store_type == "redis":
        from services.vector_store import get_vector_store
        return get_vector_store()

    elif store_type == "qdrant":
        # Future implementation
        raise NotImplementedError("Qdrant adapter not implemented yet")

    elif store_type == "chroma":
        # Future implementation
        raise NotImplementedError("Chroma adapter not implemented yet")

    else:
        raise ValueError(f"Unknown vector store type: {store_type}")


def create_event_processor() -> EventProcessorInterface:
    """Create event processor adapter based on configuration"""
    processor_type = config.EVENT_PROCESSOR_TYPE.lower()

    logger.info(f"Creating event processor: {processor_type}")

    if processor_type == "supabase":
        from .supabase_adapter import get_supabase_event_processor
        return get_supabase_event_processor()

    elif processor_type == "redis":
        # We need to create a Redis adapter that implements the interface
        from .redis_adapter import RedisEventProcessor
        return RedisEventProcessor()

    elif processor_type == "nats":
        # Future implementation
        raise NotImplementedError("NATS adapter not implemented yet")

    elif processor_type == "memory":
        # Future implementation for in-memory event processing
        raise NotImplementedError("Memory adapter not implemented yet")

    else:
        raise ValueError(f"Unknown event processor type: {processor_type}")


def create_product_store() -> ProductStoreInterface:
    """Create product store adapter based on configuration"""
    store_type = config.DATA_STORE_TYPE.lower()

    logger.info(f"Creating product store: {store_type}")

    if store_type == "supabase":
        from .supabase_adapter import get_supabase_product_store
        return get_supabase_product_store()

    elif store_type == "postgresql":
        # Future implementation for direct PostgreSQL
        raise NotImplementedError("PostgreSQL adapter not implemented yet")

    elif store_type == "sqlite":
        # Future implementation for SQLite
        raise NotImplementedError("SQLite adapter not implemented yet")

    elif store_type == "redis":
        # Future implementation for Redis hash storage
        raise NotImplementedError("Redis product store adapter not implemented yet")

    else:
        raise ValueError(f"Unknown product store type: {store_type}")


# Singleton instances for performance
_vector_store_instance = None
_event_processor_instance = None
_product_store_instance = None


def get_vector_store() -> VectorStoreInterface:
    """Get singleton vector store instance"""
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = create_vector_store()
    return _vector_store_instance


def get_event_processor() -> EventProcessorInterface:
    """Get singleton event processor instance"""
    global _event_processor_instance
    if _event_processor_instance is None:
        _event_processor_instance = create_event_processor()
    return _event_processor_instance


def get_product_store() -> ProductStoreInterface:
    """Get singleton product store instance"""
    global _product_store_instance
    if _product_store_instance is None:
        _product_store_instance = create_product_store()
    return _product_store_instance


def reset_instances():
    """Reset all singleton instances (useful for testing or configuration changes)"""
    global _vector_store_instance, _event_processor_instance, _product_store_instance
    _vector_store_instance = None
    _event_processor_instance = None
    _product_store_instance = None
    logger.info("Reset all adapter instances")


def get_backend_info() -> dict:
    """Get information about current backend configuration"""
    return {
        "backend_type": config.BACKEND_TYPE,
        "vector_store": config.VECTOR_STORE_TYPE,
        "event_processor": config.EVENT_PROCESSOR_TYPE,
        "data_store": config.DATA_STORE_TYPE,
        "cloud_services": {
            "pinecone_configured": bool(config.PINECONE_API_KEY),
            "supabase_configured": bool(config.SUPABASE_URL and config.SUPABASE_SERVICE_ROLE_KEY)
        }
    }
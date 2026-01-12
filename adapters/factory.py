import os
from loguru import logger
from typing import Dict

import config
from .interfaces import (
    VectorStoreInterface,
    EventProcessorInterface,
    ProductStoreInterface,
    UserBehaviorInterface,
    ContentStoreInterface,
)


def create_vector_store() -> VectorStoreInterface:
    store_type = config.VECTOR_STORE_TYPE.lower()
    logger.info(f"Creating vector store: {store_type}")

    if store_type == "pinecone":
        from adapters.vector_store.pinecone_adapter import get_pinecone_vector_store

        return get_pinecone_vector_store()

    if store_type == "elasticsearch":
        from adapters.vector_store.elasticsearch_adapter import get_elasticsearch_vector_store

        return get_elasticsearch_vector_store()

    raise ValueError(f"Unknown vector store type: {store_type}")


def create_event_processor() -> EventProcessorInterface:
    processor_type = config.EVENT_PROCESSOR_TYPE.lower()
    logger.info(f"Creating event processor: {processor_type}")

    if processor_type == "supabase":
        from adapters.database.supabase_adapter import get_supabase_event_processor

        return get_supabase_event_processor()

    if processor_type in ("postgres", "postgresql"):
        from adapters.database.postgres_adapter import get_postgres_event_processor

        return get_postgres_event_processor()

    if processor_type == "kafka":
        from adapters.messaging.kafka_adapter import KafkaEventProcessor

        return KafkaEventProcessor(
            bootstrap_servers=config.KAFKA_BOOTSTRAP_SERVERS,
            topic=config.KAFKA_TOPIC,
            group_id=config.KAFKA_GROUP_ID,
        )

    raise ValueError(f"Unknown event processor type: {processor_type}")


def create_product_store() -> ProductStoreInterface:
    store_type = config.DATA_STORE_TYPE.lower()
    logger.info(f"Creating product store: {store_type}")

    if store_type == "supabase":
        from adapters.database.supabase_adapter import get_supabase_product_store

        return get_supabase_product_store()

    if store_type in ("postgres", "postgresql"):
        from adapters.database.postgres_adapter import get_postgres_product_store

        return get_postgres_product_store()

    if store_type == "mongodb":
        from adapters.database.mongodb_adapter import get_mongodb_product_store

        return get_mongodb_product_store()

    raise ValueError(f"Unknown product store type: {store_type}")


def create_user_behavior() -> UserBehaviorInterface:
    behavior_type = config.BEHAVIOR_STORE_TYPE.lower()
    logger.info(f"Creating user behavior store: {behavior_type}")

    if behavior_type == "supabase":
        from adapters.database.supabase_adapter import get_supabase_user_behavior

        return get_supabase_user_behavior()

    if behavior_type in ("postgres", "postgresql"):
        from adapters.database.postgres_adapter import get_postgres_user_behavior

        return get_postgres_user_behavior()

    if behavior_type == "mongodb":
        from adapters.database.mongodb_adapter import get_mongodb_user_behavior

        return get_mongodb_user_behavior()

    raise ValueError(f"Unknown user behavior store type: {behavior_type}")


def create_content_store() -> ContentStoreInterface:
    store_type = config.DATA_STORE_TYPE.lower()  # Reuse DATA_STORE_TYPE or add CONTENT_STORE_TYPE
    logger.info(f"Creating content store: {store_type}")

    if store_type == "supabase":
        from adapters.database.supabase_content_adapter import get_supabase_content_store

        return get_supabase_content_store()

    # Add other implementations if needed
    raise ValueError(f"Unknown content store type: {store_type}")


_vector_store_instance: VectorStoreInterface | None = None
_event_processor_instance: EventProcessorInterface | None = None
_product_store_instance: ProductStoreInterface | None = None
_user_behavior_instance: UserBehaviorInterface | None = None
_content_store_instance: ContentStoreInterface | None = None


def get_vector_store() -> VectorStoreInterface:
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = create_vector_store()
    return _vector_store_instance


def get_event_processor() -> EventProcessorInterface:
    global _event_processor_instance
    if _event_processor_instance is None:
        _event_processor_instance = create_event_processor()
    return _event_processor_instance


def get_product_store() -> ProductStoreInterface:
    global _product_store_instance
    if _product_store_instance is None:
        _product_store_instance = create_product_store()
    return _product_store_instance


def get_user_behavior() -> UserBehaviorInterface:
    global _user_behavior_instance
    if _user_behavior_instance is None:
        _user_behavior_instance = create_user_behavior()
    return _user_behavior_instance


def get_content_store() -> ContentStoreInterface:
    global _content_store_instance
    if _content_store_instance is None:
        _content_store_instance = create_content_store()
    return _content_store_instance


def reset_instances() -> None:
    global _vector_store_instance, _event_processor_instance, _product_store_instance, _user_behavior_instance, _content_store_instance

    _vector_store_instance = None
    _event_processor_instance = None
    _product_store_instance = None
    _user_behavior_instance = None
    _content_store_instance = None

    logger.info("All adapter instances have been reset")


def get_backend_info() -> Dict:
    """Get information about current backend configuration"""
    return {
        "vector_store": config.VECTOR_STORE_TYPE,
        "event_processor": config.EVENT_PROCESSOR_TYPE,
        "product_store": config.DATA_STORE_TYPE,
        "user_behavior": config.BEHAVIOR_STORE_TYPE,
        "backend_type": config.BACKEND_TYPE,
        "cloud_services": {
            "pinecone_configured": bool(config.PINECONE_API_KEY),
            "elasticsearch_configured": bool(config.ELASTICSEARCH_URL),
            "supabase_configured": bool(
                config.SUPABASE_URL and config.SUPABASE_SERVICE_ROLE_KEY
            ),
        },
    }

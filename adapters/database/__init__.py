"""
Database adapters.
"""
from adapters.database.postgres_adapter import (
    PostgresEventProcessor,
    PostgresProductStore,
    PostgresUserBehavior,
    get_postgres_event_processor,
    get_postgres_product_store,
    get_postgres_user_behavior,
)
from adapters.database.supabase_adapter import (
    SupabaseEventProcessor,
    SupabaseProductStore,
    SupabaseUserBehavior,
    get_supabase_event_processor,
    get_supabase_product_store,
    get_supabase_user_behavior,
)

__all__ = [
    "PostgresEventProcessor",
    "PostgresProductStore",
    "PostgresUserBehavior",
    "get_postgres_event_processor",
    "get_postgres_product_store",
    "get_postgres_user_behavior",
    "SupabaseEventProcessor",
    "SupabaseProductStore",
    "SupabaseUserBehavior",
    "get_supabase_event_processor",
    "get_supabase_product_store",
    "get_supabase_user_behavior",
]


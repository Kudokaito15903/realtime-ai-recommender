import redis
import json
import logging
import hashlib
from typing import Any, Optional, List, Dict, Union
from functools import wraps

logger = logging.getLogger(__name__)

from datetime import datetime
import numpy as np


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


class RedisCache:
    """
    Redis Cache Wrapper for Chatbot Service
    Handles JSON serialization automatically.
    """

    PREFIXES = {
        "product": "prod",
        "embedding": "emb",
        "query_result": "qr",
        "conversation": "conv",
        "intent": "int",
    }

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        socket_timeout: int = 2,
    ):
        self.enabled = False
        try:
            self.redis = redis.Redis(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=True,
                socket_timeout=socket_timeout,
            )
            # Fast check
            self.redis.ping()
            self.enabled = True
            logger.info(f"✅ Connected to Redis at {host}:{port}/{db}")
        except Exception as e:
            logger.warning(
                f"⚠️ Could not connect to Redis: {e}. Caching will be disabled."
            )
            self.redis = None

    def _make_key(self, key: str, prefix: str = "") -> str:
        """Construct namespaced key"""
        mapped_prefix = self.PREFIXES.get(prefix, prefix)
        if mapped_prefix:
            return f"{mapped_prefix}:{key}"
        return key

    def get(self, key: str, prefix: str = "") -> Optional[Any]:
        """Get value from cache and deserialize JSON"""
        if not self.enabled or not self.redis:
            return None

        full_key = self._make_key(key, prefix)
        try:
            data = self.redis.get(full_key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.debug(f"Cache get failed for {full_key}: {e}")
        return None

    def set(self, key: str, value: Any, prefix: str = "", ttl: int = 300) -> bool:
        """Serialize value to JSON and set in cache with TTL"""
        if not self.enabled or not self.redis:
            return False

        full_key = self._make_key(key, prefix)
        try:
            json_data = json.dumps(value, cls=CustomJSONEncoder, ensure_ascii=False)
            return self.redis.setex(full_key, ttl, json_data)
        except Exception as e:
            logger.warning(f"Cache set failed for {full_key}: {e}")
            return False

    def get_list(self, key: str, prefix: str = "") -> List[Any]:
        """Get list from cache (stored as JSON array)"""
        data = self.get(key, prefix)
        if isinstance(data, list):
            return data
        return []

    def set_list(self, key: str, value: List[Any], prefix: str = "", ttl: int = 300):
        """Set list to cache"""
        self.set(key, value, prefix, ttl)

    def delete(self, key: str, prefix: str = ""):
        """Delete key from cache"""
        if not self.enabled or not self.redis:
            return

        full_key = self._make_key(key, prefix)
        try:
            self.redis.delete(full_key)
        except Exception as e:
            logger.warning(f"Cache delete failed: {e}")

    def invalidate_pattern(self, pattern: str):
        """Delete all keys matching pattern"""
        if not self.enabled or not self.redis:
            return

        try:
            keys = self.redis.keys(pattern)
            if keys:
                self.redis.delete(*keys)
                logger.info(f"Invalidated {len(keys)} keys matching '{pattern}'")
        except Exception as e:
            logger.error(f"Pattern invalidation failed: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get Redis stats"""
        if not self.enabled or not self.redis:
            return {"status": "disabled"}
        try:
            info = self.redis.info()
            return {
                "used_memory": info.get("used_memory_human"),
                "connected_clients": info.get("connected_clients"),
                "uptime_days": info.get("uptime_in_days"),
                "total_keys": self.redis.dbsize(),
            }
        except Exception:
            return {"status": "error"}


def cache_result(ttl=300, prefix=""):
    """Decorator to cache method results"""

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Try to find cache instance
            cache = getattr(self, "cache", None)
            if not cache or not isinstance(cache, RedisCache) or not cache.enabled:
                return func(self, *args, **kwargs)

            # Generate key from args (simplified)
            # Assuming first arg is self, rest are arguments
            key_parts = [func.__name__]
            key_parts.extend([str(a) for a in args])
            key_parts.extend([f"{k}={v}" for k, v in sorted(kwargs.items())])

            key_str = "|".join(key_parts)
            key_hash = hashlib.md5(key_str.encode()).hexdigest()

            cached = cache.get(key_hash, prefix=prefix)
            if cached is not None:
                return cached

            result = func(self, *args, **kwargs)
            cache.set(key_hash, result, prefix=prefix, ttl=ttl)
            return result

        return wrapper

    return decorator

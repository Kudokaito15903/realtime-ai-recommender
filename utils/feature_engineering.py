"""
Feature Engineering for ALS Training Pipeline.

Provides temporal weighting, frequency features, and category features.
"""

import math
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger


def apply_temporal_weighting(
    interactions: List[Dict[str, Any]],
    half_life_days: float = 30.0,
    timestamp_key: Optional[str] = None,
    count_key: str = "count",
) -> List[Dict[str, Any]]:
    """
    Apply recency weighting to interaction counts.

    Recent interactions are weighted more heavily than old ones.
    Uses exponential decay: weight = 2^(-age / half_life)

    Args:
        interactions: List of interaction dicts
        half_life_days: Half-life in days (interactions older than this have weight < 0.5)
        timestamp_key: Key for timestamp in interaction dict
        count_key: Key for count in interaction dict

    Returns:
        List of interactions with temporally weighted counts
    """
    if not interactions or not timestamp_key:
        return interactions

    current_time = time.time()
    half_life_seconds = half_life_days * 24 * 3600

    result = []
    for x in interactions:
        new_x = x.copy()
        ts = x.get(timestamp_key)

        if ts is None:
            # No timestamp, keep original count
            result.append(new_x)
            continue

        # Parse timestamp
        try:
            if isinstance(ts, str):
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                ts_float = dt.timestamp()
            elif isinstance(ts, (int, float)):
                ts_float = float(ts)
            else:
                result.append(new_x)
                continue

            # Calculate age in seconds
            age_seconds = current_time - ts_float

            # Exponential decay: weight = 2^(-age / half_life)
            # Recent interactions (age=0) have weight=1.0
            # Interactions at half_life have weight=0.5
            decay_weight = math.pow(2.0, -age_seconds / half_life_seconds)

            # Apply weight to count
            original_count = x.get(count_key, 0.0)
            weighted_count = original_count * decay_weight

            new_x[count_key] = weighted_count
            result.append(new_x)

        except Exception as e:
            logger.warning(f"Error applying temporal weighting: {e}, keeping original count")
            result.append(new_x)

    logger.debug(f"Applied temporal weighting (half_life={half_life_days} days) to {len(result)} interactions")
    return result


def add_frequency_features(
    interactions: List[Dict[str, Any]],
    window_days: int = 7,
    timestamp_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Add frequency features to interactions.

    Calculates number of interactions per user/product in a time window.

    Args:
        interactions: List of interaction dicts
        window_days: Time window in days for frequency calculation
        timestamp_key: Key for timestamp in interaction dict

    Returns:
        List of interactions with frequency features added
    """
    if not interactions or not timestamp_key:
        return interactions

    current_time = time.time()
    window_seconds = window_days * 24 * 3600

    # Count interactions per user/product in window
    user_freq: Dict[str, int] = {}
    product_freq: Dict[str, int] = {}

    for x in interactions:
        ts = x.get(timestamp_key)
        if ts is None:
            continue

        try:
            if isinstance(ts, str):
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                ts_float = dt.timestamp()
            elif isinstance(ts, (int, float)):
                ts_float = float(ts)
            else:
                continue

            age_seconds = current_time - ts_float
            if age_seconds <= window_seconds:
                uid = str(x.get("user_id", ""))
                pid = str(x.get("product_id", ""))

                if uid:
                    user_freq[uid] = user_freq.get(uid, 0) + 1
                if pid:
                    product_freq[pid] = product_freq.get(pid, 0) + 1

        except Exception:
            continue

    # Add frequency features to interactions
    result = []
    for x in interactions:
        new_x = x.copy()
        uid = str(x.get("user_id", ""))
        pid = str(x.get("product_id", ""))

        new_x["user_frequency"] = user_freq.get(uid, 0)
        new_x["product_frequency"] = product_freq.get(pid, 0)

        result.append(new_x)

    logger.debug(f"Added frequency features (window={window_days} days) to {len(result)} interactions")
    return result


def add_category_features(
    interactions: List[Dict[str, Any]],
    product_store: Optional[Any] = None,
    category_key: str = "category",
) -> List[Dict[str, Any]]:
    """
    Add category information to interactions.

    Fetches product category from product store and adds as feature.

    Args:
        interactions: List of interaction dicts
        product_store: Product store instance with get_product() method
        category_key: Key to store category in interaction dict

    Returns:
        List of interactions with category features added
    """
    if not interactions or not product_store:
        return interactions

    if not hasattr(product_store, "get_product"):
        logger.warning("Product store does not have get_product method, skipping category features")
        return interactions

    result = []
    category_cache: Dict[str, Optional[str]] = {}

    for x in interactions:
        new_x = x.copy()
        pid = str(x.get("product_id", ""))

        if pid in category_cache:
            category = category_cache[pid]
        else:
            try:
                product = product_store.get_product(pid)
                category = product.get("category") if product else None
                category_cache[pid] = category
            except Exception as e:
                logger.debug(f"Error fetching category for product {pid}: {e}")
                category = None
                category_cache[pid] = None

        new_x[category_key] = category
        result.append(new_x)

    logger.debug(f"Added category features to {len(result)} interactions")
    return result


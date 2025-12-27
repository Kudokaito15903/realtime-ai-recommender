"""
Interaction Features - Offline ML Pipeline
Feature engineering for ALS training data.
"""

import math
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
from loguru import logger


def apply_temporal_weighting(
    interactions: List[Dict[str, Any]],
    half_life_days: float = 30.0,
    timestamp_key: str = "timestamp",
    count_key: str = "count",
) -> List[Dict[str, Any]]:
    """
    Apply temporal decay weighting to interaction counts.
    More recent interactions get higher weights.

    Args:
        interactions: List of interaction dicts
        half_life_days: Half-life in days for exponential decay
        timestamp_key: Key for timestamp in interaction dict
        count_key: Key for count in interaction dict

    Returns:
        List of interactions with temporally weighted counts
    """
    if not interactions:
        return []

    now = time.time()
    half_life_seconds = half_life_days * 24 * 3600

    def parse_timestamp(ts_val: Any) -> float:
        """Parse timestamp from various formats."""
        if ts_val is None:
            return now  # Default to current time if missing
        if isinstance(ts_val, (int, float)):
            return float(ts_val)
        try:
            # Try ISO format
            return datetime.fromisoformat(
                str(ts_val).replace("Z", "+00:00")
            ).timestamp()
        except Exception:
            return now

    weighted = []
    for interaction in interactions:
        new_interaction = interaction.copy()

        timestamp = parse_timestamp(interaction.get(timestamp_key))
        age_seconds = max(now - timestamp, 0.0)

        # Exponential decay: weight = 2^(-age / half_life)
        if half_life_seconds > 0:
            decay = math.exp(-age_seconds * math.log(2) / half_life_seconds)
        else:
            decay = 1.0

        original_count = float(interaction.get(count_key, 0) or 0)
        weighted_count = original_count * decay

        new_interaction[count_key] = weighted_count
        weighted.append(new_interaction)

    logger.info(
        f"Applied temporal weighting (half_life={half_life_days}d) to {len(weighted)} interactions"
    )
    return weighted


def add_frequency_features(
    interactions: List[Dict[str, Any]],
    count_key: str = "count",
) -> List[Dict[str, Any]]:
    """
    Add frequency-based features to interactions.

    Args:
        interactions: List of interaction dicts
        count_key: Key for count in interaction dict

    Returns:
        List of interactions with frequency features added
    """
    if not interactions:
        return []

    # Calculate user and product frequencies
    user_counts: Dict[str, float] = {}
    product_counts: Dict[str, float] = {}

    for interaction in interactions:
        user_id = str(interaction.get("user_id", ""))
        product_id = str(interaction.get("product_id", ""))
        count = float(interaction.get(count_key, 0) or 0)

        user_counts[user_id] = user_counts.get(user_id, 0.0) + count
        product_counts[product_id] = product_counts.get(product_id, 0.0) + count

    # Add frequency features
    enhanced = []
    for interaction in interactions:
        new_interaction = interaction.copy()
        user_id = str(interaction.get("user_id", ""))
        product_id = str(interaction.get("product_id", ""))

        new_interaction["user_frequency"] = user_counts.get(user_id, 0.0)
        new_interaction["product_frequency"] = product_counts.get(product_id, 0.0)

        enhanced.append(new_interaction)

    logger.debug(f"Added frequency features to {len(enhanced)} interactions")
    return enhanced


def add_category_features(
    interactions: List[Dict[str, Any]],
    product_store: Optional[Any] = None,
    count_key: str = "count",
) -> List[Dict[str, Any]]:
    """
    Add category features to interactions from product store.

    Args:
        interactions: List of interaction dicts
        product_store: Product store adapter (optional)
        count_key: Key for count in interaction dict

    Returns:
        List of interactions with category features added
    """
    if not interactions or product_store is None:
        return interactions

    if not hasattr(product_store, "get_product"):
        logger.warning(
            "Product store does not support get_product; skipping category features"
        )
        return interactions

    enhanced = []
    category_cache: Dict[str, str] = {}

    for interaction in interactions:
        new_interaction = interaction.copy()
        product_id = str(interaction.get("product_id", ""))

        # Try to get category from cache or product store
        if product_id in category_cache:
            category = category_cache[product_id]
        else:
            try:
                product = product_store.get_product(product_id)
                category = product.get("category", "unknown") if product else "unknown"
                category_cache[product_id] = category
            except Exception as e:
                logger.debug(f"Could not get category for product {product_id}: {e}")
                category = "unknown"
                category_cache[product_id] = category

        new_interaction["category"] = category
        enhanced.append(new_interaction)

    logger.info(f"Added category features to {len(enhanced)} interactions")
    return enhanced


def apply_interaction_type_weighting(
    interactions: List[Dict[str, Any]],
    weights: Optional[Dict[str, float]] = None,
    type_key: str = "interaction_type",
    count_key: str = "count",
) -> List[Dict[str, Any]]:
    """
    Apply different weights to different interaction types.

    Args:
        interactions: List of interaction dicts
        weights: Dictionary mapping interaction types to weights
        type_key: Key for interaction type in interaction dict
        count_key: Key for count in interaction dict

    Returns:
        List of interactions with type-weighted counts
    """
    if not interactions:
        return []

    if weights is None:
        # Default weights: purchase > add_to_cart > click > view
        weights = {
            "purchase": 5.0,
            "add_to_cart": 3.0,
            "click": 2.0,
            "view": 1.0,
        }

    weighted = []
    for interaction in interactions:
        new_interaction = interaction.copy()
        interaction_type = str(interaction.get(type_key, "view")).lower()
        weight = weights.get(interaction_type, 1.0)

        original_count = float(interaction.get(count_key, 0) or 0)
        weighted_count = original_count * weight

        new_interaction[count_key] = weighted_count
        weighted.append(new_interaction)

    logger.debug(f"Applied interaction type weighting to {len(weighted)} interactions")
    return weighted

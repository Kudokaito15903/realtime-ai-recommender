import math
import time
from typing import List, Dict, Any, Tuple
from collections import defaultdict
from loguru import logger


def calculate_popularity_scores(
    interactions: List[Dict[str, Any]],
    half_life_days: float = 3.0,
    now_ts: float = None,
) -> Dict[str, float]:
    """
    Calculate popularity scores with time decay.
    Score = Sum( 1.0 * 2^(-age_days / half_life) )

    Args:
        interactions: List of interaction dicts. Must have 'product_id' and 'timestamp'.
        half_life_days: Time in days for weight to decay by half.
                        Smaller = more focus on "Trending".
                        Larger = more focus on "All-time".
        now_ts: Current timestamp (seconds). Defaults to time.time().

    Returns:
        Dict of {product_id: score}
    """
    if not interactions:
        return {}

    if now_ts is None:
        now_ts = time.time()

    scores = defaultdict(float)

    for x in interactions:
        pid = x.get("product_id")
        ts_val = x.get("timestamp")

        if not pid or not ts_val:
            continue

        # Parse timestamp
        # DB might return ISO string or float/int
        try:
            if isinstance(ts_val, (int, float)):
                ts = float(ts_val)
            else:
                # ISO String
                # Simple parse, assuming roughly ISO format
                # For robust parsing, datetime.fromisoformat is better but needs imports
                # Here we assume adapter gives ISO strings like "2023-01-01T00:00:00"
                # Doing a lazy conversion or assuming the adapter standardizes this is better.
                # Let's import datetime
                from datetime import datetime

                if ts_val.endswith("Z"):
                    ts_val = ts_val[:-1]
                dt = datetime.fromisoformat(ts_val)
                ts = dt.timestamp()
        except Exception:
            # Fallback
            continue

        age_seconds = now_ts - ts
        if age_seconds < 0:
            age_seconds = 0

        age_days = age_seconds / 86400.0

        # Decay formula
        weight = math.pow(2, -age_days / half_life_days)

        scores[str(pid)] += weight

    return scores


def get_popular_recommendations(
    interactions: List[Dict[str, Any]],
    limit: int = 10,
    half_life_days: float = 7.0,
    category_filter: str = None,
    product_store_func=None,
) -> List[Tuple[str, float]]:
    """
    Get ranked list of popular items.

    Args:
        interactions: Recent interactions to derive trends from.
        limit: Number of items to return.
        half_life_days: Decay factor.
        category_filter: Optional category ID to filter results.
        product_store_func: Optional callable (pid -> product_dict) to check category.
                            Required if category_filter is set.

    Returns:
        List of (product_id, score) tuples.
    """
    scores = calculate_popularity_scores(interactions, half_life_days=half_life_days)

    # Sort
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    # Filter
    final_recs = []
    for pid, score in ranked:
        if category_filter and product_store_func:
            # Check category
            try:
                prod = product_store_func(pid)
                if not prod:
                    continue
                cats = prod.get("categoryId", [])
                if isinstance(cats, str):
                    cats = [cats]
                if str(category_filter) not in [str(c) for c in cats]:
                    continue
            except Exception:
                continue

        final_recs.append((pid, score))
        if len(final_recs) >= limit:
            break

    return final_recs

import math
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


def parse_timestamp(ts_val: Any) -> float:
    """Parse various timestamp formats into UNIX timestamp (seconds)."""
    if ts_val is None:
        return 0.0
    if isinstance(ts_val, (int, float)):
        return float(ts_val)
    try:
        return datetime.fromisoformat(str(ts_val).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def compute_interaction_weight(
    item: Dict[str, Any],
    now_ts: Optional[float] = None,
    recency_half_life_seconds: int = 60 * 60 * 24 * 3,
    base_weights: Optional[Dict[str, float]] = None,
) -> float:
    """
    Compute a weight for a single interaction combining:
    - Event type (view/click/add_to_cart/purchase)
    - Optional pre-computed score
    - Recency decay with configurable half-life
    """
    if now_ts is None:
        now_ts = time.time()

    if base_weights is None:
        base_weights = {
            "view": 1.0,
            "click": 2.0,
            "add_to_cart": 3.0,
            "purchase": 5.0,
        }

    event_type = (item.get("event_type") or "view").lower()

    # If caller already provided a score, use it as base; otherwise use event-type weight.
    base = item.get("score")
    if base is None:
        base = base_weights.get(event_type, 1.0)

    try:
        base_f = float(base)
    except Exception:
        base_f = 1.0

    ts = parse_timestamp(item.get("timestamp"))
    age = max(now_ts - ts, 0.0)
    if recency_half_life_seconds <= 0:
        decay = 1.0
    else:
        decay = math.exp(-age * math.log(2) / recency_half_life_seconds)

    return base_f * decay


def build_recency_weighted_user_vector(
    history: List[Dict[str, Any]],
    embedding_dimension: int,
    vector_store,
    embedding_model,
    product_store=None,
    top_k_interactions: int = 20,
    recency_half_life_seconds: int = 60 * 60 * 24 * 3,
) -> Tuple[np.ndarray, List[Dict[str, Any]], float]:
    """
    Build a recency-weighted user embedding vector from interaction history.

    Returns:
        user_vector (np.ndarray)
        top_history (List[Dict]) - interactions kept after weighting/sorting
        target_price (float) - mean price of top interactions (for price distance)
    """
    if not history:
        return np.zeros(embedding_dimension, dtype=np.float32), [], 0.0

    now_ts = time.time()

    weighted_history: List[Dict[str, Any]] = []
    for item in history:
        pid = item.get("product_id")
        if not pid:
            continue
        w = compute_interaction_weight(
            item,
            now_ts=now_ts,
            recency_half_life_seconds=recency_half_life_seconds,
        )
        weighted_history.append(
            {
                "product_id": str(pid),
                "weight": w,
                "price": item.get("price"),
            }
        )

    weighted_history.sort(key=lambda x: x["weight"], reverse=True)
    top_history = weighted_history[:top_k_interactions]
    if not top_history:
        return np.zeros(embedding_dimension, dtype=np.float32), [], 0.0

    prices = [float(h["price"]) for h in top_history if h.get("price") is not None]
    target_price = float(np.mean(prices)) if prices else 0.0

    accumulator = np.zeros(embedding_dimension, dtype=np.float32)
    total_w = 0.0

    for item in top_history:
        pid = item["product_id"]
        emb = vector_store.get_product_embedding(pid)
        if emb is None and product_store is not None:
            try:
                product = product_store.get_product(pid)
                if product:
                    emb = embedding_model.get_product_embedding(product)
            except Exception:
                emb = None
        if emb is None:
            continue
        accumulator += emb * item["weight"]
        total_w += item["weight"]

    if total_w <= 0:
        return (
            np.zeros(embedding_dimension, dtype=np.float32),
            top_history,
            target_price,
        )

    user_vec = accumulator / total_w
    norm = np.linalg.norm(user_vec)
    if norm > 0:
        user_vec /= norm

    return user_vec.astype(np.float32), top_history, target_price

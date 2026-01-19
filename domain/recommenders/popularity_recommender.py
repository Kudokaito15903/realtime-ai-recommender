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
        try:
            if isinstance(ts_val, (int, float)):
                ts = float(ts_val)
            else:
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
    scores = calculate_popularity_scores(interactions, half_life_days=half_life_days)

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    final_recs = []
    for pid, score in ranked:
        if category_filter and product_store_func:
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

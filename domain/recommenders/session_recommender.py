"""
Pure Session-Based Recommender

This module provides session-level recommendations based purely on:
- Item → Next-item transitions (Markov chain)
- Time-aware transitions (recent transitions weighted higher)
- Popularity fallbacks (global → category → brand)

Key design principles:
- NO embeddings or vector similarity
- NO personalization (that's for other recommenders)
- Session_id is critical for grouping short-term intent
"""

import time
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


def _parse_ts_to_epoch(ts: Any) -> Optional[float]:
    """Convert various timestamp formats to epoch seconds."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return float(ts)
    if isinstance(ts, datetime):
        return ts.timestamp()
    if isinstance(ts, str):
        s = ts.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(s).timestamp()
        except Exception:
            return None
    return None


EVENT_WEIGHTS = {
    "view": 1.0,
    "click": 2.0,
    "add_to_cart": 3.0,
    "purchase": 5.0,
}


@dataclass
class SessionTransitionStats:
    """
    Pure session-level transition statistics.

    Attributes:
        transitions: item_id -> {next_item_id: (count, latest_timestamp)}
        totals: item_id -> total outgoing transition count
        popularity_global: Global item popularity counter
        popularity_by_category: Category -> item popularity counter
        popularity_by_brand: Brand -> item popularity counter
        created_at: When these stats were built
    """

    created_at: float
    transitions: Dict[str, Dict[str, Tuple[int, float]]] = field(default_factory=dict)
    totals: Dict[str, int] = field(default_factory=dict)
    popularity_global: Counter = field(default_factory=Counter)
    popularity_by_category: Dict[str, Counter] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    popularity_by_brand: Dict[str, Counter] = field(
        default_factory=lambda: defaultdict(Counter)
    )


def build_session_transitions(
    interactions: List[Dict[str, Any]],
    session_gap_seconds: int = 1800,
    product_store=None,
) -> SessionTransitionStats:
    """
    Build item→next-item transition stats from interactions.

    Args:
        interactions: List of dicts with keys: user_id, product_id, timestamp,
                      and optionally session_id, event_type, category, brand
        session_gap_seconds: If session_id is missing, infer sessions using this gap
        product_store: Optional store to fetch category/brand metadata

    Returns:
        SessionTransitionStats with transition counts and popularity data
    """
    # Group by session (use session_id if available, else infer from user_id + time gap)

    sessions: Dict[str, List[Tuple[float, str, float]]] = defaultdict(list)
    popularity_global: Counter = Counter()
    popularity_by_category: Dict[str, Counter] = defaultdict(Counter)
    popularity_by_brand: Dict[str, Counter] = defaultdict(Counter)

    # Track product metadata
    product_meta_cache: Dict[str, Tuple[Optional[str], Optional[str]]] = {}

    def get_product_meta(pid: str) -> Tuple[Optional[str], Optional[str]]:
        """Get (category, brand) for a product."""
        if pid in product_meta_cache:
            return product_meta_cache[pid]
        category, brand = None, None
        if product_store:
            try:
                product = product_store.get_product(pid)
                if product:
                    category = product.get("category")
                    brand = product.get("brand") or product.get("brandName")
            except Exception:
                pass
        product_meta_cache[pid] = (category, brand)
        return category, brand

    # First pass: group interactions by session
    for row in interactions:
        pid = row.get("product_id")
        ts = _parse_ts_to_epoch(row.get("timestamp"))
        if pid is None or ts is None:
            continue

        pid_s = str(pid)
        session_id = row.get("session_id")

        if session_id:
            # Explicit session_id provided
            session_key = str(session_id)
        else:
            # Infer session from user_id (will be split by time gap later)
            user_id = row.get("user_id")
            if user_id is None:
                continue
            session_key = f"inferred_{user_id}"

        event_type = row.get("event_type", "view")
        event_weight = EVENT_WEIGHTS.get(event_type, 1.0)

        sessions[session_key].append((ts, pid_s, event_weight))

        # Update popularity
        popularity_global[pid_s] += 1
        category, brand = get_product_meta(pid_s)
        if category:
            popularity_by_category[category][pid_s] += 1
        if brand:
            popularity_by_brand[brand][pid_s] += 1

    # Second pass: build transitions within sessions
    transitions: Dict[str, Dict[str, Tuple[int, float]]] = defaultdict(dict)
    totals: Dict[str, int] = defaultdict(int)

    for session_key, items in sessions.items():
        if len(items) < 2:
            continue

        # Sort by timestamp
        items.sort(key=lambda x: x[0])

        # If inferred session, split by time gap
        if session_key.startswith("inferred_"):
            sub_sessions = []
            current_sub = [items[0]]
            for i in range(1, len(items)):
                gap = items[i][0] - items[i - 1][0]
                if gap > session_gap_seconds:
                    sub_sessions.append(current_sub)
                    current_sub = [items[i]]
                else:
                    current_sub.append(items[i])
            sub_sessions.append(current_sub)
        else:
            sub_sessions = [items]

        # Build transitions for each sub-session
        for sub in sub_sessions:
            if len(sub) < 2:
                continue
            for i in range(len(sub) - 1):
                ts_from, pid_from, w_from = sub[i]
                ts_to, pid_to, _ = sub[i + 1]

                if pid_from == pid_to:
                    continue  # Skip self-transitions

                # Update transition count and timestamp
                if pid_to in transitions[pid_from]:
                    old_count, old_ts = transitions[pid_from][pid_to]
                    transitions[pid_from][pid_to] = (
                        old_count + w_from,
                        max(old_ts, ts_to),
                    )
                else:
                    transitions[pid_from][pid_to] = (w_from, ts_to)

                totals[pid_from] += w_from

    logger.info(
        f"Built session transitions: {len(transitions)} source items, "
        f"{sum(len(v) for v in transitions.values())} transitions, "
        f"{len(sessions)} sessions"
    )

    return SessionTransitionStats(
        created_at=time.time(),
        transitions=dict(transitions),
        totals=dict(totals),
        popularity_global=popularity_global,
        popularity_by_category=dict(popularity_by_category),
        popularity_by_brand=dict(popularity_by_brand),
    )


def recommend_next_items(
    stats: SessionTransitionStats,
    current_session_items: List[str],
    limit: int = 10,
    time_decay_half_life_days: float = 7.0,
    recency_decay: float = 0.7,
    category_hint: Optional[str] = None,
    brand_hint: Optional[str] = None,
) -> List[Tuple[str, float]]:
    """
    Recommend next items based on current session context.

    Pure session logic:
    1. Look up transitions from items in current session
    2. Weight by recency in session (recent items matter more)
    3. Apply time decay (recent transitions matter more)
    4. Fallback to popularity (category → brand → global)

    Args:
        stats: SessionTransitionStats from build_session_transitions
        current_session_items: List of product_ids in current session (most recent LAST)
        limit: Max recommendations to return
        time_decay_half_life_days: Half-life for transition time decay
        recency_decay: Weight decay for position in session (0.7 means each older item gets 0.7x weight)
        category_hint: Optional category for popularity fallback
        brand_hint: Optional brand for popularity fallback

    Returns:
        List of (product_id, score) tuples, sorted by score descending
    """
    if not stats or not current_session_items or limit <= 0:
        return []

    seen = set(current_session_items)
    scores: Dict[str, float] = defaultdict(float)
    now = time.time()

    # Time decay factor
    time_decay_factor = (
        math.log(2) / (time_decay_half_life_days * 24 * 3600)
        if time_decay_half_life_days > 0
        else 0
    )

    # Process items in reverse order (most recent first gets highest weight)
    n_items = len(current_session_items)
    for i, pid in enumerate(reversed(current_session_items)):
        pid_s = str(pid)

        # Position weight: most recent item = 1.0, older items decay
        position_weight = recency_decay**i

        trans = stats.transitions.get(pid_s, {})
        total = stats.totals.get(pid_s, 0)

        if not trans or total <= 0:
            continue

        for next_pid, (count, latest_ts) in trans.items():
            if next_pid in seen:
                continue

            # Base transition probability
            base_prob = count / total

            # Apply time decay
            if time_decay_factor > 0:
                age_seconds = now - latest_ts
                time_weight = math.exp(-time_decay_factor * age_seconds)
            else:
                time_weight = 1.0

            # Combined score
            score = position_weight * base_prob * time_weight
            scores[next_pid] += score

    # If we have scores, return top items
    if scores:
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:limit]

    # Fallback to popularity
    return _popularity_fallback(
        stats=stats,
        seen=seen,
        limit=limit,
        category_hint=category_hint,
        brand_hint=brand_hint,
    )


def _popularity_fallback(
    stats: SessionTransitionStats,
    seen: set,
    limit: int,
    category_hint: Optional[str] = None,
    brand_hint: Optional[str] = None,
) -> List[Tuple[str, float]]:
    """
    Fallback to popularity when no transitions are available.
    Priority: category → brand → global
    """
    results: List[Tuple[str, float]] = []

    # Try category first
    if category_hint and category_hint in stats.popularity_by_category:
        for pid, count in stats.popularity_by_category[category_hint].most_common():
            if pid not in seen:
                results.append((pid, float(count)))
                if len(results) >= limit:
                    return results

    # Try brand
    if brand_hint and brand_hint in stats.popularity_by_brand:
        for pid, count in stats.popularity_by_brand[brand_hint].most_common():
            if pid not in seen and pid not in {r[0] for r in results}:
                results.append((pid, float(count)))
                if len(results) >= limit:
                    return results

    # Global popularity
    for pid, count in stats.popularity_global.most_common():
        if pid not in seen and pid not in {r[0] for r in results}:
            results.append((pid, float(count)))
            if len(results) >= limit:
                return results

    return results

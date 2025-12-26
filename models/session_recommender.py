import time
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, DefaultDict, Dict, Iterable, List, Optional, Tuple

from loguru import logger


def _parse_ts_to_epoch(ts: Any) -> Optional[float]:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return float(ts)
    if isinstance(ts, datetime):
        return ts.timestamp()
    if isinstance(ts, str):
        s = ts.strip()
        # Handle trailing Z
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(s).timestamp()
        except Exception:
            return None
    return None


@dataclass
class TransitionStats:
    created_at: float
    session_gap_seconds: int
    transitions: Dict[str, Counter]
    totals: Dict[str, int]
    popularity: Counter
    # Time-aware transitions: store (count, latest_timestamp) for each transition
    transition_timestamps: Dict[str, Dict[str, Tuple[float, float]]] = field(default_factory=lambda: defaultdict(dict))
    # Category and brand popularity for cold-start handling
    popularity_by_category: Dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    popularity_by_brand: Dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    # Product metadata cache: product_id -> (category, brand)
    product_metadata: Dict[str, Tuple[Optional[str], Optional[str]]] = field(default_factory=dict)


def build_transition_stats(
    interactions: Iterable[Dict[str, Any]],
    session_gap_seconds: int = 1800,
    event_weights: Optional[Dict[str, float]] = None,
    product_store=None,
) -> TransitionStats:
    """
    Build item->next-item transition counts from raw interaction events.
    Each interaction should include: user_id, product_id, timestamp, event_type.
    
    Args:
        interactions: Iterable of interaction dicts
        session_gap_seconds: Maximum gap between interactions to consider same session
        event_weights: Dict mapping event_type to weight (default: view=1, click=2, add_to_cart=3, purchase=5)
        product_store: Optional product store to fetch category/brand metadata
    """
    if event_weights is None:
        event_weights = {
            "view": 1.0,
            "click": 2.0,
            "add_to_cart": 3.0,
            "purchase": 5.0,
        }
    
    by_user: DefaultDict[str, List[Tuple[float, str, float]]] = defaultdict(list)
    popularity: Counter = Counter()
    popularity_by_category: Dict[str, Counter] = defaultdict(Counter)
    popularity_by_brand: Dict[str, Counter] = defaultdict(Counter)
    product_metadata: Dict[str, Tuple[Optional[str], Optional[str]]] = {}

    # First pass: collect interactions with event weights
    for row in interactions:
        uid = row.get("user_id")
        pid = row.get("product_id")
        ts = _parse_ts_to_epoch(row.get("timestamp"))
        if uid is None or pid is None or ts is None:
            continue
        
        event_type = (row.get("event_type") or "view").lower()
        weight = event_weights.get(event_type, 1.0)
        
        uid_s = str(uid)
        pid_s = str(pid)
        by_user[uid_s].append((ts, pid_s, weight))
        popularity[pid_s] += weight
        
        # Try to get category/brand from product store if available
        if pid_s not in product_metadata and product_store is not None:
            try:
                product = product_store.get_product(pid_s)
                if product:
                    category = product.get("category")
                    brand = product.get("brand") or product.get("attributes", {}).get("brand")
                    product_metadata[pid_s] = (category, brand)
                    if category:
                        popularity_by_category[category][pid_s] += weight
                    if brand:
                        popularity_by_brand[brand][pid_s] += weight
            except Exception as e:
                logger.debug(f"Could not fetch metadata for product {pid_s}: {e}")
                product_metadata[pid_s] = (None, None)

    transitions: Dict[str, Counter] = defaultdict(Counter)
    totals: Dict[str, float] = defaultdict(float)
    transition_timestamps: Dict[str, Dict[str, Tuple[float, float]]] = defaultdict(dict)

    # Second pass: build transitions with weighted counts and timestamps
    for _, seq in by_user.items():
        if len(seq) < 2:
            continue
        seq.sort(key=lambda x: x[0])  # time ascending
        prev_ts, prev_pid, prev_weight = seq[0]
        for ts, pid, weight in seq[1:]:
            gap = ts - prev_ts
            if gap <= session_gap_seconds and prev_pid != pid:
                # Weighted transition count
                transition_weight = (prev_weight + weight) / 2.0  # Average of both event weights
                transitions[prev_pid][pid] += transition_weight
                totals[prev_pid] += transition_weight
                
                # Store timestamp (keep latest)
                if pid in transition_timestamps[prev_pid]:
                    old_count, old_ts = transition_timestamps[prev_pid][pid]
                    transition_timestamps[prev_pid][pid] = (old_count + transition_weight, max(old_ts, ts))
                else:
                    transition_timestamps[prev_pid][pid] = (transition_weight, ts)
            prev_ts, prev_pid, prev_weight = ts, pid, weight

    logger.info(
        f"Built session transitions: items={len(transitions)}, users={len(by_user)}, "
        f"events={sum(popularity.values()):.1f}, categories={len(popularity_by_category)}"
    )
    return TransitionStats(
        created_at=time.time(),
        session_gap_seconds=session_gap_seconds,
        transitions=dict(transitions),
        totals=dict(totals),
        popularity=popularity,
        transition_timestamps=dict(transition_timestamps),
        popularity_by_category=dict(popularity_by_category),
        popularity_by_brand=dict(popularity_by_brand),
        product_metadata=product_metadata,
    )


def recommend_from_history(
    stats: TransitionStats,
    recent_product_ids: List[str],
    limit: int = 10,
    decay: float = 0.7,
    time_decay_half_life_days: float = 30.0,
    diversity_lambda: float = 0.3,
    popularity_normalization: bool = True,
    vector_store=None,
    embedding_model=None,
) -> List[Tuple[str, float]]:
    """
    Enhanced session-based recommendations with:
    - Event-weighted transitions
    - Time decay for transitions
    - Category/brand-aware fallback
    - Diversity penalty (MMR-lite)
    - Popularity normalization
    
    Args:
        stats: TransitionStats with transitions and metadata
        recent_product_ids: List of recent product IDs (most recent first)
        limit: Maximum number of recommendations
        decay: Recency decay factor for position in history
        time_decay_half_life_days: Half-life in days for transition time decay
        diversity_lambda: Weight for diversity penalty (0 = no penalty, 1 = max penalty)
        popularity_normalization: Whether to normalize by log(1 + popularity)
        vector_store: Optional vector store for similarity computation (for diversity)
        embedding_model: Optional embedding model for similarity computation
    """
    if not stats or not recent_product_ids or limit <= 0:
        return []

    seen = {str(pid) for pid in recent_product_ids}
    scores: DefaultDict[str, float] = defaultdict(float)
    now = time.time()
    time_decay_factor = math.log(2) / (time_decay_half_life_days * 24 * 3600) if time_decay_half_life_days > 0 else 0

    # Extract categories/brands from recent products for fallback
    recent_categories = set()
    recent_brands = set()
    for pid in recent_product_ids:
        pid_s = str(pid)
        if pid_s in stats.product_metadata:
            cat, brand = stats.product_metadata[pid_s]
            if cat:
                recent_categories.add(cat)
            if brand:
                recent_brands.add(brand)

    # Build scores from transitions with time decay
    for i, pid in enumerate(recent_product_ids):
        pid_s = str(pid)
        trans = stats.transitions.get(pid_s)
        total = float(stats.totals.get(pid_s, 0) or 0)
        if not trans or total <= 0:
            continue
        
        position_weight = (decay ** i)
        trans_timestamps = stats.transition_timestamps.get(pid_s, {})
        
        for nxt, cnt in trans.items():
            if nxt in seen:
                continue
            
            # Base transition probability
            base_score = float(cnt) / total if total > 0 else 0.0
            
            # Apply time decay if timestamp available
            if nxt in trans_timestamps:
                _, latest_ts = trans_timestamps[nxt]
                age_seconds = now - latest_ts
                if time_decay_factor > 0:
                    time_decay = math.exp(-time_decay_factor * age_seconds)
                else:
                    time_decay = 1.0
                base_score *= time_decay
            
            scores[nxt] += position_weight * base_score

    # Fallback strategy: category -> brand -> global popularity
    if not scores:
        # Try category-based popularity first
        for cat in recent_categories:
            if cat in stats.popularity_by_category:
                for pid, cnt in stats.popularity_by_category[cat].most_common(limit * 2):
                    if pid not in seen:
                        scores[pid] = float(cnt)
                        if len(scores) >= limit:
                            break
                if len(scores) >= limit:
                    break
        
        # Then try brand-based popularity
        if len(scores) < limit:
            for brand in recent_brands:
                if brand in stats.popularity_by_brand:
                    for pid, cnt in stats.popularity_by_brand[brand].most_common(limit * 2):
                        if pid not in seen and pid not in scores:
                            scores[pid] = float(cnt)
                            if len(scores) >= limit:
                                break
                    if len(scores) >= limit:
                        break
        
        # Finally, global popularity
        if len(scores) < limit:
            for pid, cnt in stats.popularity.most_common(limit * 3):
                if pid not in seen and pid not in scores:
                    scores[pid] = float(cnt)
                    if len(scores) >= limit:
                        break

    if not scores:
        return []

    # Apply popularity normalization
    if popularity_normalization:
        for pid in list(scores.keys()):
            pop = stats.popularity.get(pid, 0)
            if pop > 0:
                scores[pid] /= math.log1p(float(pop))

    # Apply diversity penalty (MMR-lite) if similarity available
    if diversity_lambda > 0 and vector_store is not None and embedding_model is not None:
        selected = []
        remaining = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        # Get embeddings for recent products
        recent_embeddings = {}
        for pid in recent_product_ids[:5]:  # Limit to avoid too many lookups
            pid_s = str(pid)
            emb = vector_store.get_product_embedding(pid_s)
            if emb is not None:
                recent_embeddings[pid_s] = emb
        
        while len(selected) < limit and remaining:
            best_pid, best_score = remaining[0]
            remaining = remaining[1:]
            
            # Compute diversity penalty
            diversity_penalty = 0.0
            if recent_embeddings:
                # Check similarity to recent products
                best_emb = vector_store.get_product_embedding(best_pid)
                if best_emb is not None:
                    for recent_pid, recent_emb in recent_embeddings.items():
                        # Cosine similarity
                        dot = sum(a * b for a, b in zip(best_emb, recent_emb))
                        norm_a = math.sqrt(sum(a * a for a in best_emb))
                        norm_b = math.sqrt(sum(b * b for b in recent_emb))
                        if norm_a > 0 and norm_b > 0:
                            similarity = dot / (norm_a * norm_b)
                            diversity_penalty = max(diversity_penalty, similarity)
            
            # Also check similarity to already selected items
            for sel_pid, _ in selected:
                sel_emb = vector_store.get_product_embedding(sel_pid)
                best_emb = vector_store.get_product_embedding(best_pid)
                if sel_emb is not None and best_emb is not None:
                    dot = sum(a * b for a, b in zip(best_emb, sel_emb))
                    norm_a = math.sqrt(sum(a * a for a in best_emb))
                    norm_b = math.sqrt(sum(b * b for b in sel_emb))
                    if norm_a > 0 and norm_b > 0:
                        similarity = dot / (norm_a * norm_b)
                        diversity_penalty = max(diversity_penalty, similarity)
            
            # Apply penalty
            adjusted_score = best_score * (1.0 - diversity_lambda * diversity_penalty)
            selected.append((best_pid, adjusted_score))
        
        ranked = selected
    else:
        # Simple ranking without diversity
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    return ranked[:limit]


import time
from collections import Counter, defaultdict
from dataclasses import dataclass
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


def build_transition_stats(
    interactions: Iterable[Dict[str, Any]],
    session_gap_seconds: int = 1800,
) -> TransitionStats:
    """
    Build item->next-item transition counts from raw interaction events.
    Each interaction should include: user_id, product_id, timestamp.
    """
    by_user: DefaultDict[str, List[Tuple[float, str]]] = defaultdict(list)
    popularity: Counter = Counter()

    for row in interactions:
        uid = row.get("user_id")
        pid = row.get("product_id")
        ts = _parse_ts_to_epoch(row.get("timestamp"))
        if uid is None or pid is None or ts is None:
            continue
        uid_s = str(uid)
        pid_s = str(pid)
        by_user[uid_s].append((ts, pid_s))
        popularity[pid_s] += 1

    transitions: Dict[str, Counter] = defaultdict(Counter)
    totals: Dict[str, int] = defaultdict(int)

    for _, seq in by_user.items():
        if len(seq) < 2:
            continue
        seq.sort(key=lambda x: x[0])  # time ascending
        prev_ts, prev_pid = seq[0]
        for ts, pid in seq[1:]:
            gap = ts - prev_ts
            if gap <= session_gap_seconds and prev_pid != pid:
                transitions[prev_pid][pid] += 1
                totals[prev_pid] += 1
            prev_ts, prev_pid = ts, pid

    logger.info(
        f"Built session transitions: items={len(transitions)}, users={len(by_user)}, events={sum(popularity.values())}"
    )
    return TransitionStats(
        created_at=time.time(),
        session_gap_seconds=session_gap_seconds,
        transitions=dict(transitions),
        totals=dict(totals),
        popularity=popularity,
    )


def recommend_from_history(
    stats: TransitionStats,
    recent_product_ids: List[str],
    limit: int = 10,
    decay: float = 0.7,
) -> List[Tuple[str, float]]:
    """
    Session-based recommendations using a simple multi-step transition blend:
    score(cand) = sum_i (decay^i) * P(cand | item_i)
    where item_0 is most recent.
    """
    if not stats or not recent_product_ids or limit <= 0:
        return []

    seen = {str(pid) for pid in recent_product_ids}
    scores: DefaultDict[str, float] = defaultdict(float)

    for i, pid in enumerate(recent_product_ids):
        pid_s = str(pid)
        trans = stats.transitions.get(pid_s)
        total = float(stats.totals.get(pid_s, 0) or 0)
        if not trans or total <= 0:
            continue
        w = (decay ** i)
        for nxt, cnt in trans.items():
            if nxt in seen:
                continue
            scores[nxt] += w * (float(cnt) / total)

    if not scores:
        # Fallback to popular (excluding already seen)
        for pid, cnt in stats.popularity.most_common(limit * 3):
            if pid not in seen:
                scores[pid] = float(cnt)
                if len(scores) >= limit:
                    break

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return ranked[:limit]


import hashlib
from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class ABVariant:
    name: str
    traffic_share: float  # 0.0–1.0


def _hash_to_float(value: str) -> float:
    """Deterministic hash → [0,1) for user bucketing."""
    h = hashlib.sha256(value.encode("utf-8")).hexdigest()
    # Use first 8 hex chars → 32 bits
    bucket = int(h[:8], 16)
    return (bucket % 10_000_000) / 10_000_000.0


def assign_variant(
    user_id: str, experiments: Dict[str, Dict[str, ABVariant]]
) -> Dict[str, str]:
    """
    Assign a user to variants for multiple experiments in a deterministic way.

    experiments format:
        {
            "exp_name": {
                "A": ABVariant(name="A", traffic_share=0.5),
                "B": ABVariant(name="B", traffic_share=0.5),
            },
            ...
        }

    Returns:
        Dict[experiment_name] = variant_name
    """
    assignments: Dict[str, str] = {}
    if not user_id:
        return assignments

    for exp_name, variants in experiments.items():
        key = f"{exp_name}:{user_id}"
        r = _hash_to_float(key)

        cumulative = 0.0
        chosen = None
        for v_name, v in sorted(variants.items(), key=lambda x: x[0]):
            cumulative += max(0.0, min(1.0, v.traffic_share))
            if r < cumulative:
                chosen = v_name
                break
        if chosen is None:
            # Fallback to last variant by name if shares don't sum to 1
            chosen = sorted(variants.keys())[-1]

        assignments[exp_name] = chosen

    return assignments

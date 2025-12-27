"""
Normalization methods for interaction counts in ALS training.

Provides various normalization techniques to improve model performance.
"""

import math
from typing import List, Literal

import numpy as np
from loguru import logger


def normalize_counts(
    counts: List[float],
    method: Literal["none", "log", "minmax", "zscore", "sqrt"] = "none",
) -> List[float]:
    """
    Normalize interaction counts using various methods.

    Args:
        counts: List of raw interaction counts
        method: Normalization method:
            - "none": No normalization (return as-is)
            - "log": Log transformation log(1 + x)
            - "minmax": Min-max scaling to [0, 1]
            - "zscore": Z-score normalization (mean=0, std=1)
            - "sqrt": Square root transformation sqrt(x)

    Returns:
        List of normalized counts
    """
    if not counts:
        return []

    if method == "none":
        return counts

    counts_array = np.array(counts, dtype=np.float32)

    if method == "log":
        # Log transformation: log(1 + x)
        # Reduces impact of power users
        normalized = np.log1p(counts_array)
        logger.debug(
            f"Applied log normalization: min={normalized.min():.4f}, max={normalized.max():.4f}"
        )
        return normalized.tolist()

    elif method == "sqrt":
        # Square root transformation: sqrt(x)
        # Less aggressive than log
        normalized = np.sqrt(counts_array)
        logger.debug(
            f"Applied sqrt normalization: min={normalized.min():.4f}, max={normalized.max():.4f}"
        )
        return normalized.tolist()

    elif method == "minmax":
        # Min-max scaling to [0, 1]
        min_val = counts_array.min()
        max_val = counts_array.max()
        if max_val > min_val:
            normalized = (counts_array - min_val) / (max_val - min_val)
        else:
            normalized = np.zeros_like(counts_array)
        logger.debug(
            f"Applied min-max normalization: min={normalized.min():.4f}, max={normalized.max():.4f}"
        )
        return normalized.tolist()

    elif method == "zscore":
        # Z-score normalization: (x - mean) / std
        mean_val = counts_array.mean()
        std_val = counts_array.std()
        if std_val > 0:
            normalized = (counts_array - mean_val) / std_val
        else:
            normalized = np.zeros_like(counts_array)
        logger.debug(
            f"Applied z-score normalization: mean={normalized.mean():.4f}, std={normalized.std():.4f}"
        )
        return normalized.tolist()

    else:
        logger.warning(f"Unknown normalization method: {method}, using 'none'")
        return counts


def apply_normalization_to_interactions(
    interactions: List[dict],
    method: Literal["none", "log", "minmax", "zscore", "sqrt"] = "none",
    count_key: str = "count",
) -> List[dict]:
    """
    Apply normalization to interaction counts in a list of interaction dicts.

    Args:
        interactions: List of interaction dicts with count field
        method: Normalization method
        count_key: Key for count in interaction dict

    Returns:
        List of interactions with normalized counts
    """
    if not interactions or method == "none":
        return interactions

    counts = [x.get(count_key, 0.0) for x in interactions]
    normalized_counts = normalize_counts(counts, method=method)

    result = []
    for i, x in enumerate(interactions):
        new_x = x.copy()
        new_x[count_key] = float(normalized_counts[i])
        result.append(new_x)

    return result

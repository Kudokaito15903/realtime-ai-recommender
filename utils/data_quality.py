"""
Data Quality Checks for ALS Training Pipeline.

Provides validation, cleaning, and quality metrics for interaction data.
"""

import math
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


class DataQualityStats:
    """Statistics about data quality checks."""

    def __init__(self):
        self.total_records = 0
        self.removed_invalid = 0
        self.removed_duplicates = 0
        self.removed_outliers = 0
        self.removed_stale = 0
        self.removed_cold_start_users = 0
        self.removed_cold_start_products = 0
        self.final_records = 0
        self.unique_users = 0
        self.unique_products = 0
        self.count_stats = {
            "min": float("inf"),
            "max": float("-inf"),
            "mean": 0.0,
            "median": 0.0,
            "std": 0.0,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            "total_records": self.total_records,
            "removed": {
                "invalid": self.removed_invalid,
                "duplicates": self.removed_duplicates,
                "outliers": self.removed_outliers,
                "stale": self.removed_stale,
                "cold_start_users": self.removed_cold_start_users,
                "cold_start_products": self.removed_cold_start_products,
            },
            "final_records": self.final_records,
            "unique_users": self.unique_users,
            "unique_products": self.unique_products,
            "count_stats": self.count_stats,
        }

    def log_summary(self) -> None:
        """Log summary of data quality checks."""
        logger.info("=" * 60)
        logger.info("Data Quality Check Summary")
        logger.info("=" * 60)
        logger.info(f"Total records: {self.total_records}")
        logger.info(f"Removed - Invalid: {self.removed_invalid}")
        logger.info(f"Removed - Duplicates: {self.removed_duplicates}")
        logger.info(f"Removed - Outliers: {self.removed_outliers}")
        logger.info(f"Removed - Stale data: {self.removed_stale}")
        logger.info(f"Removed - Cold-start users: {self.removed_cold_start_users}")
        logger.info(
            f"Removed - Cold-start products: {self.removed_cold_start_products}"
        )
        logger.info(f"Final records: {self.final_records}")
        logger.info(f"Unique users: {self.unique_users}")
        logger.info(f"Unique products: {self.unique_products}")
        logger.info(
            f"Count stats - Min: {self.count_stats['min']:.2f}, "
            f"Max: {self.count_stats['max']:.2f}, "
            f"Mean: {self.count_stats['mean']:.2f}, "
            f"Median: {self.count_stats['median']:.2f}"
        )
        logger.info("=" * 60)


def validate_interactions(
    interactions: List[Dict[str, Any]],
    remove_duplicates: bool = True,
    remove_outliers: bool = True,
    outlier_threshold_std: float = 3.0,
    remove_stale: bool = True,
    max_age_days: int = 90,
    remove_cold_start: bool = True,
    min_user_interactions: int = 2,
    min_product_interactions: int = 2,
    timestamp_key: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], DataQualityStats]:
    """
    Validate and clean interactions data.

    Args:
        interactions: List of interaction dicts with user_id, product_id, count
        remove_duplicates: Remove duplicate user-product pairs (keep max count)
        remove_outliers: Remove interactions with count > mean + threshold_std * std
        outlier_threshold_std: Number of standard deviations for outlier detection
        remove_stale: Remove interactions older than max_age_days
        max_age_days: Maximum age of interactions in days
        remove_cold_start: Remove users/products with too few interactions
        min_user_interactions: Minimum interactions per user
        min_product_interactions: Minimum interactions per product
        timestamp_key: Key for timestamp in interaction dict (optional)

    Returns:
        Tuple of (cleaned_interactions, stats)
    """
    stats = DataQualityStats()
    stats.total_records = len(interactions)

    if not interactions:
        logger.warning("No interactions provided for validation")
        return [], stats

    # Step 1: Basic validation (None, non-numeric, <= 0)
    cleaned = []
    for x in interactions:
        uid = x.get("user_id")
        pid = x.get("product_id")
        cnt = x.get("count", 0)

        if uid is None or pid is None:
            stats.removed_invalid += 1
            continue

        try:
            cnt_f = float(cnt)
        except (ValueError, TypeError):
            stats.removed_invalid += 1
            continue

        if cnt_f <= 0 or not math.isfinite(cnt_f):
            stats.removed_invalid += 1
            continue

        cleaned.append(
            {
                "user_id": str(uid),
                "product_id": str(pid),
                "count": cnt_f,
                "timestamp": x.get(timestamp_key) if timestamp_key else None,
            }
        )

    # Step 2: Remove stale data (if timestamp available)
    if remove_stale and timestamp_key:
        current_time = time.time()
        max_age_seconds = max_age_days * 24 * 3600
        fresh = []
        for x in cleaned:
            ts = x.get("timestamp")
            if ts is None:
                fresh.append(x)  # Keep if no timestamp
                continue

            # Try to parse timestamp
            try:
                if isinstance(ts, str):
                    # Try ISO format
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    ts_float = dt.timestamp()
                elif isinstance(ts, (int, float)):
                    ts_float = float(ts)
                else:
                    fresh.append(x)  # Keep if can't parse
                    continue

                age_seconds = current_time - ts_float
                if age_seconds <= max_age_seconds:
                    fresh.append(x)
                else:
                    stats.removed_stale += 1
            except Exception:
                fresh.append(x)  # Keep if parsing fails
        cleaned = fresh

    # Step 3: Remove duplicates (keep max count per user-product pair)
    if remove_duplicates:
        pair_counts: Dict[Tuple[str, str], float] = {}
        for x in cleaned:
            key = (x["user_id"], x["product_id"])
            current_count = pair_counts.get(key, 0.0)
            pair_counts[key] = max(current_count, x["count"])

        duplicate_count = len(cleaned) - len(pair_counts)
        stats.removed_duplicates = duplicate_count

        cleaned = [
            {"user_id": uid, "product_id": pid, "count": cnt, "timestamp": None}
            for (uid, pid), cnt in pair_counts.items()
        ]

    # Step 4: Calculate statistics for outlier detection
    if remove_outliers and cleaned:
        counts = [x["count"] for x in cleaned]
        if len(counts) > 1:
            mean_count = sum(counts) / len(counts)
            variance = sum((c - mean_count) ** 2 for c in counts) / len(counts)
            std_count = math.sqrt(variance) if variance > 0 else 0.0

            threshold = mean_count + outlier_threshold_std * std_count

            filtered = []
            for x in cleaned:
                if x["count"] <= threshold:
                    filtered.append(x)
                else:
                    stats.removed_outliers += 1
            cleaned = filtered

    # Step 5: Remove cold-start users/products
    if remove_cold_start and cleaned:
        # Count interactions per user and product
        user_counts: Dict[str, int] = {}
        product_counts: Dict[str, int] = {}

        for x in cleaned:
            uid = x["user_id"]
            pid = x["product_id"]
            user_counts[uid] = user_counts.get(uid, 0) + 1
            product_counts[pid] = product_counts.get(pid, 0) + 1

        # Filter out cold-start
        filtered = []
        for x in cleaned:
            uid = x["user_id"]
            pid = x["product_id"]

            if user_counts[uid] < min_user_interactions:
                stats.removed_cold_start_users += 1
                continue

            if product_counts[pid] < min_product_interactions:
                stats.removed_cold_start_products += 1
                continue

            filtered.append(x)

        cleaned = filtered

    # Calculate final statistics
    stats.final_records = len(cleaned)
    if cleaned:
        counts = [x["count"] for x in cleaned]
        stats.count_stats["min"] = min(counts)
        stats.count_stats["max"] = max(counts)
        stats.count_stats["mean"] = sum(counts) / len(counts)

        sorted_counts = sorted(counts)
        n = len(sorted_counts)
        if n % 2 == 0:
            stats.count_stats["median"] = (
                sorted_counts[n // 2 - 1] + sorted_counts[n // 2]
            ) / 2
        else:
            stats.count_stats["median"] = sorted_counts[n // 2]

        # Calculate std
        mean = stats.count_stats["mean"]
        variance = sum((c - mean) ** 2 for c in counts) / len(counts)
        stats.count_stats["std"] = math.sqrt(variance) if variance > 0 else 0.0

        # Count unique users and products
        unique_users = {x["user_id"] for x in cleaned}
        unique_products = {x["product_id"] for x in cleaned}
        stats.unique_users = len(unique_users)
        stats.unique_products = len(unique_products)

    return cleaned, stats

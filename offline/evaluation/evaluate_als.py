import sys
import os
import time
import numpy as np
from typing import List, Dict, Any, Set
from collections import defaultdict

# Add project root to path
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from loguru import logger
from adapters.factory import get_user_behavior
from offline.evaluation.data_split import split_data_by_time
from offline.evaluation.offline_metrics import evaluate_recommendations
from domain.recommenders.als_recommender import (
    ALSSettings,
    train_implicit_als,
    recommend_for_user,
    ALSModel,
)
from config import ALS_FACTORS, ALS_ITERATIONS, ALS_REGULARIZATION, ALS_ALPHA


def evaluate_als_model(limit: int = 50000):
    logger.info("Starting Offline ALS Evaluation...")

    # 1. Fetch Data
    behavior = get_user_behavior()
    if not hasattr(behavior, "get_recent_interactions"):
        logger.error("Backend does not support fetching recent interactions.")
        return

    # Use raw interactions instead of counts for splitting
    interactions = behavior.get_recent_interactions(limit=limit)
    logger.info(f"Fetched {len(interactions)} interactions.")

    if not interactions:
        logger.warning("No data found.")
        return

    # 2. Split Data
    train_data, test_data = split_data_by_time(interactions, test_ratio=0.2)

    if not train_data or not test_data:
        logger.error("Data split resulted in empty sets.")
        return

    # 3. Prepare Training Data for ALS (Group by user/item -> count)
    # ALS expects 'count' field
    train_counts = defaultdict(float)
    for x in train_data:
        uid = x.get("user_id")
        pid = x.get("product_id")
        if uid and pid:
            train_counts[(str(uid), str(pid))] += 1.0

    train_interactions_agg = [
        {"user_id": uid, "product_id": pid, "count": cnt}
        for (uid, pid), cnt in train_counts.items()
    ]

    # 4. Train ALS
    settings = ALSSettings(
        factors=ALS_FACTORS,
        iterations=ALS_ITERATIONS,
        regularization=ALS_REGULARIZATION,
        alpha=ALS_ALPHA,
    )

    logger.info("Training ALS on Train Set...")
    model, cui = train_implicit_als(
        train_interactions_agg,
        settings=settings,
        apply_data_quality=False,  # Already filtered/split
        apply_normalization=True,
        normalization_method="log",  # Good default
    )

    # 5. Evaluate on Test Set
    # Group test data by user -> set of product_ids (Ground Truth)
    test_ground_truth: Dict[str, Set[str]] = defaultdict(set)
    for x in test_data:
        uid = x.get("user_id")
        pid = x.get("product_id")
        if uid and pid:
            test_ground_truth[str(uid)].add(str(pid))

    logger.info(f"Evaluating on {len(test_ground_truth)} test users...")

    all_metrics = defaultdict(list)
    k_values = [5, 10, 20]

    for user_id, ground_truth in test_ground_truth.items():
        # Get recommendations
        # Note: recommend_for_user returns (pid, score)
        # Cui contains training data, passed to filter out seen items
        recs_tuples = recommend_for_user(model, user_id, Cui=cui, limit=20)
        rec_ids = [r[0] for r in recs_tuples]

        metrics = evaluate_recommendations(rec_ids, ground_truth, k_values)

        for k, v in metrics.items():
            all_metrics[k].append(v)

    # 6. Report Results
    print("\n" + "=" * 50)
    print(f"ALS MODEL EVALUATION RESULTS")
    print(f"Train Interactions: {len(train_data)}")
    print(f"Test Interactions:  {len(test_data)}")
    print(f"Test Users:         {len(test_ground_truth)}")
    print("=" * 50)

    results = {}
    for k in sorted(all_metrics.keys()):
        avg_score = np.mean(all_metrics[k])
        results[k] = avg_score
        print(f"{k:<15}: {avg_score:.4f}")

    print("=" * 50 + "\n")


if __name__ == "__main__":
    evaluate_als_model()

import os
import sys
import time
from typing import Optional

from loguru import logger

# Ensure project root is on sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.factory import get_user_behavior, get_product_store
from models.als_recommender import ALSSettings, train_implicit_als, save_als_model
from utils.feature_engineering import (
    apply_temporal_weighting,
    add_frequency_features,
    add_category_features,
)
from config import (
    ALS_MODEL_PATH,
    ALS_FACTORS,
    ALS_ITERATIONS,
    ALS_REGULARIZATION,
    ALS_ALPHA,
    ALS_TRAINING_INTERACTIONS_LIMIT,
    ALS_DATA_QUALITY_ENABLED,
    ALS_REMOVE_DUPLICATES,
    ALS_REMOVE_OUTLIERS,
    ALS_OUTLIER_THRESHOLD_STD,
    ALS_REMOVE_STALE,
    ALS_MAX_AGE_DAYS,
    ALS_REMOVE_COLD_START,
    ALS_MIN_USER_INTERACTIONS,
    ALS_MIN_PRODUCT_INTERACTIONS,
    ALS_NORMALIZATION_METHOD,
    ALS_TEMPORAL_WEIGHTING_ENABLED,
    ALS_RECENCY_HALF_LIFE_DAYS,
)


def train_als_offline(
    interactions_limit: Optional[int] = None,
) -> None:
    """
    Offline training entrypoint for the implicit ALS model.

    Typical usage:
    - Run once per day (e.g. 2AM) from a scheduler/cron.
    - Reads aggregated interaction counts from the behavior store.
    - Trains ALS and saves the model artifact to ALS_MODEL_PATH.
    """
    behavior = get_user_behavior()

    if not hasattr(behavior, "get_interaction_counts"):
        logger.warning(
            "User behavior backend does not implement get_interaction_counts; "
            "offline ALS training is unavailable."
        )
        return

    limit = interactions_limit or ALS_TRAINING_INTERACTIONS_LIMIT
    logger.info(f"Starting offline ALS training (limit={limit})")

    interactions = behavior.get_interaction_counts(limit=limit)
    if not interactions:
        logger.warning("No interactions returned for ALS training; skipping.")
        return

    # Apply feature engineering (temporal weighting, frequency, category)
    if ALS_TEMPORAL_WEIGHTING_ENABLED:
        # Try to get timestamps from interactions
        # Note: get_interaction_counts may not include timestamps by default
        # This would require adapter changes to include timestamp in aggregation
        logger.info("Temporal weighting enabled, but timestamps may not be available in aggregated counts")
        # For now, skip temporal weighting if timestamps not available
        # interactions = apply_temporal_weighting(
        #     interactions,
        #     half_life_days=ALS_RECENCY_HALF_LIFE_DAYS,
        #     timestamp_key="timestamp",
        # )

    # Add category features if product store available
    try:
        product_store = get_product_store()
        interactions = add_category_features(interactions, product_store=product_store)
    except Exception as e:
        logger.debug(f"Could not add category features: {e}")

    # Prepare data quality config
    data_quality_config = {
        "remove_duplicates": ALS_REMOVE_DUPLICATES,
        "remove_outliers": ALS_REMOVE_OUTLIERS,
        "outlier_threshold_std": ALS_OUTLIER_THRESHOLD_STD,
        "remove_stale": ALS_REMOVE_STALE,
        "max_age_days": ALS_MAX_AGE_DAYS,
        "remove_cold_start": ALS_REMOVE_COLD_START,
        "min_user_interactions": ALS_MIN_USER_INTERACTIONS,
        "min_product_interactions": ALS_MIN_PRODUCT_INTERACTIONS,
        "timestamp_key": None,  # May not be available in aggregated counts
    }

    settings = ALSSettings(
        factors=ALS_FACTORS,
        iterations=ALS_ITERATIONS,
        regularization=ALS_REGULARIZATION,
        alpha=ALS_ALPHA,
    )

    start_time = time.time()
    model, _ = train_implicit_als(
        interactions,
        settings=settings,
        apply_data_quality=ALS_DATA_QUALITY_ENABLED,
        apply_normalization=True,
        normalization_method=ALS_NORMALIZATION_METHOD,
        data_quality_config=data_quality_config,
    )
    save_als_model(model, ALS_MODEL_PATH)

    logger.info(
        f"Offline ALS training completed in {time.time() - start_time:.2f}s. "
        f"Model saved to {ALS_MODEL_PATH} (trained_at={model.trained_at:.0f})."
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Offline ALS model trainer")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Maximum number of aggregated interactions to use for training. "
            "Defaults to ALS_TRAINING_INTERACTIONS_LIMIT from config."
        ),
    )
    args = parser.parse_args()

    train_als_offline(interactions_limit=args.limit)

    # Example scheduler (cron) usage on Linux:
    #   0 2 * * * /usr/bin/python -m services.model_trainer >> /var/log/als_trainer.log 2>&1
    #
    # On Windows Task Scheduler, configure a daily task at 2AM that runs:
    #   python -m services.model_trainer



"""
Train ALS - Offline ML Pipeline
Offline training script for ALS model.
"""

import os
import sys
import time
import argparse
from typing import Optional

from loguru import logger

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from adapters.factory import get_user_behavior, get_product_store
from domain.recommenders.als_recommender import ALSSettings, train_implicit_als, save_als_model
from offline.als.interaction_features import (
    apply_temporal_weighting,
    add_category_features,
    add_frequency_features,
    apply_interaction_type_weighting,
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
    output_path: Optional[str] = None,
    enable_feature_engineering: bool = True,
) -> None:
    """
    Offline training entrypoint for the implicit ALS model.
    
    Typical usage:
    - Run once per day (e.g. 2AM) from a scheduler/cron.
    - Reads aggregated interaction counts from the behavior store.
    - Trains ALS and saves the model artifact.
    
    Args:
        interactions_limit: Maximum number of interactions to use
        output_path: Optional custom output path for model
        enable_feature_engineering: Whether to apply feature engineering
    """
    behavior = get_user_behavior()
    
    if not hasattr(behavior, "get_interaction_counts"):
        logger.error(
            "User behavior backend does not implement get_interaction_counts; "
            "offline ALS training is unavailable."
        )
        return
    
    limit = interactions_limit or ALS_TRAINING_INTERACTIONS_LIMIT
    logger.info(f"Starting offline ALS training (limit={limit})")
    
    # Fetch interactions
    interactions = behavior.get_interaction_counts(limit=limit)
    if not interactions:
        logger.warning("No interactions returned for ALS training; skipping.")
        return
    
    logger.info(f"Retrieved {len(interactions)} interactions for training")
    
    # Feature engineering
    if enable_feature_engineering:
        # Temporal weighting
        if ALS_TEMPORAL_WEIGHTING_ENABLED:
            try:
                interactions = apply_temporal_weighting(
                    interactions,
                    half_life_days=ALS_RECENCY_HALF_LIFE_DAYS,
                    timestamp_key="timestamp",
                )
            except Exception as e:
                logger.warning(f"Temporal weighting failed: {e}")
        
        # Frequency features
        try:
            interactions = add_frequency_features(interactions)
        except Exception as e:
            logger.warning(f"Frequency features failed: {e}")
        
        # Category features
        try:
            product_store = get_product_store()
            interactions = add_category_features(interactions, product_store=product_store)
        except Exception as e:
            logger.debug(f"Category features not available: {e}")
        
        # Interaction type weighting (if available)
        try:
            interactions = apply_interaction_type_weighting(interactions)
        except Exception as e:
            logger.debug(f"Interaction type weighting not available: {e}")
    
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
        "timestamp_key": "timestamp" if ALS_TEMPORAL_WEIGHTING_ENABLED else None,
    }
    
    # ALS settings
    settings = ALSSettings(
        factors=ALS_FACTORS,
        iterations=ALS_ITERATIONS,
        regularization=ALS_REGULARIZATION,
        alpha=ALS_ALPHA,
    )
    
    # Train model
    start_time = time.time()
    logger.info("Starting ALS training...")
    
    model, cui = train_implicit_als(
        interactions,
        settings=settings,
        apply_data_quality=ALS_DATA_QUALITY_ENABLED,
        apply_normalization=True,
        normalization_method=ALS_NORMALIZATION_METHOD,
        data_quality_config=data_quality_config,
    )
    
    # Save model
    model_path = output_path or ALS_MODEL_PATH
    save_als_model(model, model_path)
    
    elapsed = time.time() - start_time
    logger.info(
        f"Offline ALS training completed in {elapsed:.2f}s. "
        f"Model saved to {model_path} (trained_at={model.trained_at:.0f}). "
        f"Model stats: {model.n_users} users, {model.n_items} items, {model.k} factors"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Offline ALS model trainer")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of interactions to use for training",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Custom output path for model file",
    )
    parser.add_argument(
        "--no-features",
        action="store_true",
        help="Disable feature engineering",
    )
    
    args = parser.parse_args()
    
    train_als_offline(
        interactions_limit=args.limit,
        output_path=args.output,
        enable_feature_engineering=not args.no_features,
    )
    
    # Example scheduler (cron) usage on Linux:
    #   0 2 * * * /usr/bin/python -m offline.als.train_als >> /var/log/als_trainer.log 2>&1
    #
    # On Windows Task Scheduler, configure a daily task at 2AM that runs:
    #   python -m offline.als.train_als


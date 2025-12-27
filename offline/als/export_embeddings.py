"""
Export Embeddings - Offline ML Pipeline
Export user and item embeddings from trained ALS model to vector store.
"""

import os
import sys
import time
import argparse
from typing import List, Dict, Any, Optional

import numpy as np
from loguru import logger

# Add project root to path
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from domain.recommenders.als_recommender import load_als_model
from adapters.factory import get_vector_store
from config import ALS_MODEL_PATH, VECTOR_DIMENSION


def export_user_embeddings(
    model_path: str,
    vector_store: Optional[Any] = None,
    batch_size: int = 100,
) -> int:
    """
    Export user embeddings from ALS model to vector store.

    Args:
        model_path: Path to ALS model file
        vector_store: Vector store adapter (optional, will get from factory if None)
        batch_size: Batch size for bulk operations

    Returns:
        Number of embeddings exported
    """
    model = load_als_model(model_path)
    if model is None:
        logger.error(f"Could not load ALS model from {model_path}")
        return 0

    if vector_store is None:
        vector_store = get_vector_store()

    logger.info(f"Exporting {model.n_users} user embeddings from ALS model")

    exported = 0
    for i in range(0, model.n_users, batch_size):
        batch_end = min(i + batch_size, model.n_users)
        user_ids_batch = model.user_ids[i:batch_end]
        embeddings_batch = model.user_factors[i:batch_end]

        for user_id, embedding in zip(user_ids_batch, embeddings_batch):
            try:
                # Store user embedding
                # Note: Vector store may need to support user embeddings separately
                # For now, we'll store with a prefix
                user_id_str = str(user_id)
                embedding_array = np.array(embedding, dtype=np.float32)

                # Normalize embedding
                norm = np.linalg.norm(embedding_array)
                if norm > 0:
                    embedding_array = embedding_array / norm

                metadata = {
                    "type": "user_embedding",
                    "source": "als",
                    "model_trained_at": model.trained_at,
                }

                # Store with prefix "user:embedding:"
                success = vector_store.store_product_embedding(
                    product_id=f"user:embedding:{user_id_str}",
                    embedding=embedding_array,
                    metadata=metadata,
                )

                if success:
                    exported += 1
            except Exception as e:
                logger.warning(f"Failed to export embedding for user {user_id}: {e}")

        if (i + batch_size) % 1000 == 0:
            logger.info(f"Exported {exported} user embeddings...")

    logger.info(f"Exported {exported} user embeddings to vector store")
    return exported


def export_item_embeddings(
    model_path: str,
    vector_store: Optional[Any] = None,
    batch_size: int = 100,
) -> int:
    """
    Export item (product) embeddings from ALS model to vector store.

    Args:
        model_path: Path to ALS model file
        vector_store: Vector store adapter (optional)
        batch_size: Batch size for bulk operations

    Returns:
        Number of embeddings exported
    """
    model = load_als_model(model_path)
    if model is None:
        logger.error(f"Could not load ALS model from {model_path}")
        return 0

    if vector_store is None:
        vector_store = get_vector_store()

    logger.info(f"Exporting {model.n_items} item embeddings from ALS model")

    exported = 0
    for i in range(0, model.n_items, batch_size):
        batch_end = min(i + batch_size, model.n_items)
        product_ids_batch = model.product_ids[i:batch_end]
        embeddings_batch = model.item_factors[i:batch_end]

        for product_id, embedding in zip(product_ids_batch, embeddings_batch):
            try:
                product_id_str = str(product_id)
                embedding_array = np.array(embedding, dtype=np.float32)

                # Normalize embedding
                norm = np.linalg.norm(embedding_array)
                if norm > 0:
                    embedding_array = embedding_array / norm

                metadata = {
                    "type": "item_embedding",
                    "source": "als",
                    "model_trained_at": model.trained_at,
                }

                success = vector_store.store_product_embedding(
                    product_id=f"als:item:{product_id_str}",
                    embedding=embedding_array,
                    metadata=metadata,
                )

                if success:
                    exported += 1
            except Exception as e:
                logger.warning(
                    f"Failed to export embedding for product {product_id}: {e}"
                )

        if (i + batch_size) % 1000 == 0:
            logger.info(f"Exported {exported} item embeddings...")

    logger.info(f"Exported {exported} item embeddings to vector store")
    return exported


def export_all_embeddings(
    model_path: Optional[str] = None,
    export_users: bool = True,
    export_items: bool = True,
    batch_size: int = 100,
) -> Dict[str, int]:
    """
    Export all embeddings from ALS model.

    Args:
        model_path: Path to ALS model file
        export_users: Whether to export user embeddings
        export_items: Whether to export item embeddings
        batch_size: Batch size for bulk operations

    Returns:
        Dictionary with export counts
    """
    model_path = model_path or ALS_MODEL_PATH
    vector_store = get_vector_store()

    results = {
        "users": 0,
        "items": 0,
    }

    start_time = time.time()

    if export_users:
        results["users"] = export_user_embeddings(
            model_path,
            vector_store=vector_store,
            batch_size=batch_size,
        )

    if export_items:
        results["items"] = export_item_embeddings(
            model_path,
            vector_store=vector_store,
            batch_size=batch_size,
        )

    elapsed = time.time() - start_time
    logger.info(
        f"Export completed in {elapsed:.2f}s: "
        f"{results['users']} user embeddings, {results['items']} item embeddings"
    )

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export ALS embeddings to vector store"
    )
    parser.add_argument(
        "--model-path",
        type=str,
        default=None,
        help="Path to ALS model file",
    )
    parser.add_argument(
        "--users-only",
        action="store_true",
        help="Export only user embeddings",
    )
    parser.add_argument(
        "--items-only",
        action="store_true",
        help="Export only item embeddings",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for bulk operations",
    )

    args = parser.parse_args()

    export_users = not args.items_only
    export_items = not args.users_only

    export_all_embeddings(
        model_path=args.model_path,
        export_users=export_users,
        export_items=export_items,
        batch_size=args.batch_size,
    )

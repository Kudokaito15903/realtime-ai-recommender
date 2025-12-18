import os
import time
import threading
import numpy as np
from typing import List, Dict, Any, Optional
from loguru import logger

from models.embeddings import get_embedding_model
from adapters.factory  import (
    get_vector_store,
    get_user_behavior,
    get_product_store,
)
from config import (
    SIMILARITY_THRESHOLD,
    ALS_MODEL_PATH,
    ALS_FACTORS,
    ALS_ITERATIONS,
    ALS_REGULARIZATION,
    ALS_ALPHA,
    ALS_TRAINING_INTERACTIONS_LIMIT,
    ALS_REFRESH_SECONDS,
    SESSION_GAP_SECONDS,
    SESSION_TRANSITIONS_LIMIT,
    SESSION_TRANSITIONS_REFRESH_SECONDS,
    SESSION_RECENT_K,
)

from models.als_recommender import (
    ALSSettings,
    load_als_model,
    save_als_model,
    train_implicit_als,
    recommend_for_user as als_recommend_for_user,
)
from models.session_recommender import (
    TransitionStats,
    build_transition_stats,
    recommend_from_history as session_recommend_from_history,
)


class ProductRecommender:
    """Service for generating real-time product recommendations (Supabase-based)"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProductRecommender, cls).__new__(cls)

            cls._instance.vector_store = get_vector_store()
            cls._instance.embedding_model = get_embedding_model()
            cls._instance.user_behavior = get_user_behavior()
            cls._instance.product_store = get_product_store()

            # ALS cache
            cls._instance._als_lock = threading.Lock()
            cls._instance._als_model = None
            cls._instance._als_cui = None
            cls._instance._als_loaded_at = 0.0

            # Session-transition cache
            cls._instance._session_lock = threading.Lock()
            cls._instance._session_stats: Optional[TransitionStats] = None
            cls._instance._session_loaded_at = 0.0

            logger.info("Product Recommender (Supabase) initialized")

        return cls._instance

    # ---------------------------------------------------------
    # Similar products (vector-based)
    # ---------------------------------------------------------
    def get_similar_products(self, product_id: str, limit: int = 6) -> List[Dict[str, Any]]:
        start_time = time.time()

        embedding = self.vector_store.get_product_embedding(product_id)
        if embedding is None:
            logger.warning(f"No embedding found for product {product_id}")
            return []

        similar_products = self.vector_store.find_similar_products(
            embedding=embedding,
            limit=limit + 1,
            min_score=SIMILARITY_THRESHOLD
        )

        results = [
            {
                "product_id": p["product_id"],
                "score": p["similarity_score"],
                "recommendation_type": "similar"
            }
            for p in similar_products
            if p["product_id"] != product_id
        ][:limit]

        logger.debug(
            f"Found {len(results)} similar products in {time.time() - start_time:.4f}s"
        )
        return results

    # ---------------------------------------------------------
    # Text-based search (semantic)
    # ---------------------------------------------------------
    def get_similar_products_by_text(self, query_text: str, limit: int = 6) -> List[Dict[str, Any]]:
        start_time = time.time()

        query_embedding = self.embedding_model.get_embedding(query_text)

        similar_products = self.vector_store.find_similar_products(
            embedding=query_embedding,
            limit=limit,
            min_score=SIMILARITY_THRESHOLD * 0.8
        )

        results = [
            {
                "product_id": p["product_id"],
                "score": p["similarity_score"],
                "recommendation_type": "search"
            }
            for p in similar_products
        ][:limit]

        logger.debug(
            f"Found {len(results)} products for text query in {time.time() - start_time:.4f}s"
        )
        return results

    # ---------------------------------------------------------
    # Popular products (Supabase-based)
    # ---------------------------------------------------------
    def get_popular_in_category(self, category: str, limit: int = 6) -> List[Dict[str, Any]]:
        products = self.user_behavior.get_popular_products(
            category=category,
            limit=limit
        )

        return [
            {
                "product_id": p["product_id"],
                "score": 1.0,  # popularity score placeholder
                "recommendation_type": "popular_in_category"
            }
            for p in products
        ]

    # ---------------------------------------------------------
    # Personalized recommendations
    # ---------------------------------------------------------
    def get_personalized_recommendations(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:

        history = self.user_behavior.get_user_history(user_id, limit=5)

        if not history:
            logger.debug(f"No history for user {user_id}, fallback to popular")
            return self.get_popular_in_category(category=None, limit=limit)

        all_recommendations = []

        for item in history:
            product_id = item["product_id"]
            similar = self.get_similar_products(product_id, limit=3)
            all_recommendations.extend(similar)

        # Deduplicate
        seen = set()
        unique = []

        for rec in sorted(all_recommendations, key=lambda x: x["score"], reverse=True):
            if rec["product_id"] not in seen:
                seen.add(rec["product_id"])
                unique.append(rec)

        # Remove already viewed products
        viewed_ids = {item["product_id"] for item in history}
        filtered = [rec for rec in unique if rec["product_id"] not in viewed_ids]

        logger.debug(
            f"Generated {len(filtered)} personalized recommendations for user {user_id}"
        )
        return filtered[:limit]

    # ---------------------------------------------------------
    # ALS recommendations (collaborative filtering)
    # ---------------------------------------------------------
    def _als_model_is_fresh(self) -> bool:
        try:
            if not ALS_MODEL_PATH or not os.path.exists(ALS_MODEL_PATH):
                return False
            age = time.time() - os.path.getmtime(ALS_MODEL_PATH)
            return age <= ALS_REFRESH_SECONDS
        except Exception:
            return False

    def _try_load_als_model(self) -> None:
        """Load ALS model from disk if available."""
        with self._als_lock:
            if self._als_model is not None:
                return
            model = load_als_model(ALS_MODEL_PATH)
            if model is not None:
                self._als_model = model
                self._als_cui = None  # matrix not persisted
                self._als_loaded_at = time.time()
                logger.info(f"Loaded ALS model from {ALS_MODEL_PATH} (trained_at={model.trained_at:.0f})")

    def _train_and_save_als_model(self) -> None:
        """Train ALS model from behavior store and persist it."""
        if not hasattr(self.user_behavior, "get_interaction_counts"):
            logger.warning("Behavior store does not support interaction counts; ALS unavailable")
            return

        interactions = self.user_behavior.get_interaction_counts(limit=ALS_TRAINING_INTERACTIONS_LIMIT)
        if not interactions:
            logger.warning("No interactions available for ALS training")
            return

        settings = ALSSettings(
            factors=ALS_FACTORS,
            iterations=ALS_ITERATIONS,
            regularization=ALS_REGULARIZATION,
            alpha=ALS_ALPHA,
        )
        model, cui = train_implicit_als(interactions, settings=settings)
        save_als_model(model, ALS_MODEL_PATH)

        with self._als_lock:
            self._als_model = model
            self._als_cui = cui
            self._als_loaded_at = time.time()

    def get_als_recommendations(self, user_id: str, limit: int = 10, train_if_missing: bool = True) -> List[Dict[str, Any]]:
        """Personalized recommendations via implicit ALS."""
        if not user_id:
            return []

        # Load model if exists
        self._try_load_als_model()

        # Train if requested and missing/stale
        if train_if_missing:
            should_train = False
            with self._als_lock:
                should_train = self._als_model is None or not self._als_model_is_fresh()
            if should_train:
                logger.info("ALS model missing/stale; training...")
                self._train_and_save_als_model()

        with self._als_lock:
            model = self._als_model
            cui = self._als_cui

        if model is None:
            return self.get_popular_in_category(category=None, limit=limit)

        ranked = als_recommend_for_user(model, user_id=user_id, Cui=cui, limit=limit)
        if not ranked:
            return self.get_popular_in_category(category=None, limit=limit)

        return [
            {"product_id": pid, "score": float(score), "recommendation_type": "als"}
            for pid, score in ranked
        ]

    # ---------------------------------------------------------
    # Session-based recommendations (recent interactions)
    # ---------------------------------------------------------
    def _ensure_session_stats(self) -> None:
        with self._session_lock:
            # TTL
            if self._session_stats is not None and (time.time() - self._session_loaded_at) <= SESSION_TRANSITIONS_REFRESH_SECONDS:
                return

        if not hasattr(self.user_behavior, "get_recent_interactions"):
            logger.warning("Behavior store does not support recent interactions; session recommender unavailable")
            return

        interactions = self.user_behavior.get_recent_interactions(limit=SESSION_TRANSITIONS_LIMIT, offset=0)
        if not interactions:
            return

        stats = build_transition_stats(interactions, session_gap_seconds=SESSION_GAP_SECONDS)
        with self._session_lock:
            self._session_stats = stats
            self._session_loaded_at = time.time()

    def get_session_based_recommendations(
        self,
        user_id: str,
        limit: int = 10,
        recent_k: int = SESSION_RECENT_K,
    ) -> List[Dict[str, Any]]:
        """
        Recommend based on the user's most recent interactions in the current session.
        This uses global item->next-item transition statistics + recency weighting.
        """
        if not user_id:
            return []

        history = self.user_behavior.get_user_history(user_id, limit=max(2, recent_k))
        if not history:
            return self.get_popular_in_category(category=None, limit=limit)

        recent_ids = [str(x.get("product_id")) for x in history if x.get("product_id") is not None][:recent_k]
        if not recent_ids:
            return self.get_popular_in_category(category=None, limit=limit)

        self._ensure_session_stats()
        with self._session_lock:
            stats = self._session_stats

        if stats is None:
            # fallback: vector-based from last viewed item
            return self.get_similar_products(product_id=recent_ids[0], limit=limit)

        ranked = session_recommend_from_history(stats, recent_product_ids=recent_ids, limit=limit)
        if not ranked:
            return self.get_similar_products(product_id=recent_ids[0], limit=limit)

        return [
            {"product_id": pid, "score": float(score), "recommendation_type": "session"}
            for pid, score in ranked
        ]

    # ---------------------------------------------------------
    # Hybrid: combine multiple strategies
    # ---------------------------------------------------------
    def get_hybrid_recommendations(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Hybrid ranking: session + ALS (if available) + vector-based history as a fallback.
        """
        if not user_id:
            return []

        candidates: List[Dict[str, Any]] = []

        # Session-based (fast, no training)
        try:
            candidates.extend(self.get_session_based_recommendations(user_id=user_id, limit=max(limit, 20)))
        except Exception as e:
            logger.warning(f"Session recommendations failed: {e}")

        # ALS (do NOT force-train here; use if already available)
        try:
            candidates.extend(self.get_als_recommendations(user_id=user_id, limit=max(limit, 20), train_if_missing=False))
        except Exception as e:
            logger.warning(f"ALS recommendations failed: {e}")

        # Vector-history (existing)
        try:
            candidates.extend(self.get_personalized_recommendations(user_id=user_id, limit=max(limit, 20)))
        except Exception as e:
            logger.warning(f"Vector-history recommendations failed: {e}")

        # Deduplicate and keep best score per product (within each method scale)
        best: Dict[str, Dict[str, Any]] = {}
        for rec in candidates:
            pid = rec.get("product_id")
            if not pid:
                continue
            prev = best.get(pid)
            if prev is None or float(rec.get("score", 0.0)) > float(prev.get("score", 0.0)):
                best[pid] = rec

        ranked = sorted(best.values(), key=lambda x: float(x.get("score", 0.0)), reverse=True)
        return ranked[:limit]

    # ---------------------------------------------------------
    # Track user behavior (Supabase)
    # ---------------------------------------------------------
    def track_product_view(self, user_id: str, product_id: str) -> None:
        if not user_id or not product_id:
            return

        self.user_behavior.track_view(user_id, product_id)
        logger.debug(f"Tracked product view: user={user_id}, product={product_id}")


# Singleton accessor
def get_product_recommender() -> ProductRecommender:
    return ProductRecommender()

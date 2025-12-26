import os
import time
import threading
import numpy as np
from typing import List, Dict, Any, Optional
import math
from datetime import datetime
from loguru import logger

from domain.embeddings.product_embeddings import get_embedding_model
from adapters.factory import (
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
    SESSION_TIME_DECAY_HALF_LIFE_DAYS,
    SESSION_DIVERSITY_LAMBDA,
    SESSION_POPULARITY_NORMALIZATION,
)

from domain.recommenders.als_recommender import (
    ALSSettings,
    load_als_model,
    save_als_model,
    train_implicit_als,
    recommend_for_user as als_recommend_for_user,
)
from domain.recommenders.session_recommender import (
    TransitionStats,
    build_transition_stats,
    recommend_from_history as session_recommend_from_history,
)


class RecommendationService:
    """Service for generating real-time product recommendations"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RecommendationService, cls).__new__(cls)

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

            logger.info("Recommendation Service initialized")

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
    # Interaction-weighted semantic recommendations
    # ---------------------------------------------------------
    def get_recency_weighted_recommendations(
        self,
        user_id: str,
        top_k_interactions: int = 20,
        search_limit: int = 40,
        result_limit: int = 10,
        recency_half_life_seconds: int = 60 * 60 * 24 * 3,  # 3 days
        similarity_threshold: float = SIMILARITY_THRESHOLD * 0.8,
        sim_weight: float = 0.6,
        sold_weight: float = 0.15,
        rating_weight: float = 0.15,
        price_penalty_weight: float = 0.1,
    ) -> List[Dict[str, Any]]:
        """
        Pipeline:
        1) Lấy top-K tương tác có trọng số cao (interaction_score * recency_decay).
        2) User vector = weighted mean embedding các sản phẩm đã tương tác.
        3) Vector search (cosine) để lấy candidates.
        4) Loại bỏ sản phẩm đã xem.
        5) Re-rank theo similarity + sold + avgRating - price_distance.
        """
        if not user_id:
            return []

        history = self.user_behavior.get_user_history(user_id, limit=top_k_interactions * 2)
        if not history:
            logger.debug(f"No history for user {user_id}; returning empty list")
            return []

        now = time.time()

        def parse_ts(ts_val: Any) -> float:
            if ts_val is None:
                return 0.0
            if isinstance(ts_val, (int, float)):
                return float(ts_val)
            try:
                return datetime.fromisoformat(str(ts_val).replace("Z", "+00:00")).timestamp()
            except Exception:
                return 0.0

        def interaction_weight(item: Dict[str, Any]) -> float:
            base = float(item.get("score", 1.0) or 1.0)
            ts = parse_ts(item.get("timestamp"))
            age = max(now - ts, 0.0)
            if recency_half_life_seconds <= 0:
                decay = 1.0
            else:
                decay = math.exp(-age * math.log(2) / recency_half_life_seconds)
            return base * decay

        # Rank interactions by weight and keep top-K
        weighted_history = []
        for item in history:
            pid = item.get("product_id")
            if not pid:
                continue
            w = interaction_weight(item)
            weighted_history.append({
                "product_id": str(pid),
                "weight": w,
                "price": item.get("price"),
            })

        weighted_history.sort(key=lambda x: x["weight"], reverse=True)
        top_history = weighted_history[:top_k_interactions]

        if not top_history:
            return []

        # Mean price for price distance
        prices = [float(h["price"]) for h in top_history if h.get("price") is not None]
        target_price = float(np.mean(prices)) if prices else 0.0

        # Build user vector
        accumulator = np.zeros(self.embedding_model.embedding_dimension, dtype=np.float32)
        total_w = 0.0

        viewed_ids = set()
        for item in top_history:
            pid = item["product_id"]
            viewed_ids.add(pid)
            emb = self.vector_store.get_product_embedding(pid)
            if emb is None and self.product_store is not None:
                try:
                    product = self.product_store.get_product(pid)
                    if product:
                        emb = self.embedding_model.get_product_embedding(product)
                except Exception:
                    emb = None
            if emb is None:
                continue
            accumulator += emb * item["weight"]
            total_w += item["weight"]

        if total_w == 0:
            return []

        user_vec = accumulator / total_w
        norm = np.linalg.norm(user_vec)
        if norm > 0:
            user_vec /= norm

        # Vector search
        candidates = self.vector_store.find_similar_products(
            embedding=user_vec,
            limit=search_limit,
            min_score=similarity_threshold,
        )

        if not candidates:
            return []

        # Filter out already viewed
        candidates = [c for c in candidates if str(c.get("product_id")) not in viewed_ids]

        if not candidates:
            return []

        def get_meta(item: Dict[str, Any], key: str, default: float = 0.0) -> float:
            if key in item and item[key] is not None:
                try:
                    return float(item[key])
                except Exception:
                    pass
            meta = item.get("metadata", {}) or {}
            if key in meta and meta[key] is not None:
                try:
                    return float(meta[key])
                except Exception:
                    pass
            return default

        def price_distance(p: float) -> float:
            if target_price <= 0 or p <= 0:
                return 0.0
            return abs(p - target_price) / max(target_price, 1e-6)

        ranked = []
        for c in candidates:
            sim = float(c.get("similarity_score", c.get("score", 0.0)))
            sold = get_meta(c, "sold", 0.0)
            rating = get_meta(c, "avgRating", 0.0)
            price = get_meta(c, "price", 0.0)

            # Simple normalizations
            sold_norm = math.log1p(max(sold, 0.0)) / 10.0  # cap scale
            rating_norm = min(max(rating / 5.0, 0.0), 1.0)
            price_penalty = price_distance(price)

            final_score = (
                sim_weight * sim
                + sold_weight * sold_norm
                + rating_weight * rating_norm
                - price_penalty_weight * price_penalty
            )

            ranked.append({
                "product_id": c.get("product_id"),
                "similarity_score": sim,
                "sold": sold,
                "avgRating": rating,
                "price": price,
                "price_distance": price_penalty,
                "final_score": final_score,
            })

        ranked.sort(key=lambda x: x["final_score"], reverse=True)
        return ranked[:result_limit]

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

        stats = build_transition_stats(
            interactions, 
            session_gap_seconds=SESSION_GAP_SECONDS,
            product_store=self.product_store
        )
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

        ranked = session_recommend_from_history(
            stats, 
            recent_product_ids=recent_ids, 
            limit=limit,
            time_decay_half_life_days=SESSION_TIME_DECAY_HALF_LIFE_DAYS,
            diversity_lambda=SESSION_DIVERSITY_LAMBDA,
            popularity_normalization=SESSION_POPULARITY_NORMALIZATION,
            vector_store=self.vector_store,
            embedding_model=self.embedding_model
        )
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
    # Track user behavior
    # ---------------------------------------------------------
    def track_product_view(self, user_id: str, product_id: str) -> None:
        if not user_id or not product_id:
            return

        self.user_behavior.track_view(user_id, product_id)
        logger.debug(f"Tracked product view: user={user_id}, product={product_id}")

    def track_product_click(self, user_id: str, product_id: str) -> None:
        if not user_id or not product_id:
            return
        self.user_behavior.track_click(user_id, product_id)
        logger.debug(f"Tracked product click: user={user_id}, product={product_id}")

    def track_add_to_cart(self, user_id: str, product_id: str) -> None:
        if not user_id or not product_id:
            return
        self.user_behavior.track_add_to_cart(user_id, product_id)
        logger.debug(f"Tracked add to cart: user={user_id}, product={product_id}")

    def track_purchase(self, user_id: str, product_id: str) -> None:
        if not user_id or not product_id:
            return
        self.user_behavior.track_purchase(user_id, product_id)
        logger.debug(f"Tracked purchase: user={user_id}, product={product_id}")

    def get_als_model_info(self) -> Dict[str, Any]:
        """Get information about the ALS model."""
        with self._als_lock:
            if self._als_model is None:
                return {"status": "not_loaded", "model_path": ALS_MODEL_PATH}
            
            return {
                "status": "loaded",
                "model_path": ALS_MODEL_PATH,
                "trained_at": self._als_model.trained_at,
                "n_users": self._als_model.n_users,
                "n_items": self._als_model.n_items,
                "loaded_at": self._als_loaded_at,
            }


# Singleton accessor
def get_recommendation_service() -> RecommendationService:
    return RecommendationService()


# Alias for backward compatibility
def get_product_recommender() -> RecommendationService:
    return get_recommendation_service()


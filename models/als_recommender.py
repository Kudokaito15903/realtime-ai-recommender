import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from loguru import logger
from scipy import sparse
from implicit.als import AlternatingLeastSquares
from sklearn.preprocessing import MinMaxScaler, StandardScaler


@dataclass(frozen=True)
class ALSSettings:
    factors: int = 64
    iterations: int = 15
    regularization: float = 0.1
    alpha: float = 40.0
    use_gpu: bool = False  # Bật nếu có CUDA


class ALSModel:
    def __init__(
        self,
        user_ids: np.ndarray,
        product_ids: np.ndarray,
        user_factors: np.ndarray,
        item_factors: np.ndarray,
        trained_at: float,
    ):
        self.user_ids = user_ids
        self.product_ids = product_ids
        self.user_factors = user_factors
        self.item_factors = item_factors
        self.trained_at = trained_at

        # Derived mappings
        self.user_id_to_index = {str(uid): int(i) for i, uid in enumerate(self.user_ids)}
        self.product_id_to_index = {str(pid): int(i) for i, pid in enumerate(self.product_ids)}

    @property
    def n_users(self) -> int:
        return int(self.user_factors.shape[0])

    @property
    def n_items(self) -> int:
        return int(self.item_factors.shape[0])

    @property
    def k(self) -> int:
        return int(self.user_factors.shape[1])


def _ensure_dir_for_file(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def save_als_model(model: ALSModel, path: str) -> None:
    _ensure_dir_for_file(path)
    np.savez_compressed(
        path,
        user_ids=model.user_ids.astype(object),
        product_ids=model.product_ids.astype(object),
        user_factors=model.user_factors.astype(np.float32),
        item_factors=model.item_factors.astype(np.float32),
        trained_at=np.array([model.trained_at], dtype=np.float64),
    )


def load_als_model(path: str) -> Optional[ALSModel]:
    try:
        if not os.path.exists(path):
            return None
        data = np.load(path, allow_pickle=True)
        trained_at = float(data["trained_at"][0]) if "trained_at" in data else 0.0
        return ALSModel(
            user_ids=data["user_ids"],
            product_ids=data["product_ids"],
            user_factors=data["user_factors"],
            item_factors=data["item_factors"],
            trained_at=trained_at,
        )
    except Exception as e:
        logger.error(f"Failed to load ALS model from {path}: {e}")
        return None


def train_implicit_als(
    interactions: List[Dict[str, Any]],
    settings: ALSSettings,
    seed: int = 42,
    apply_data_quality: bool = True,
    apply_normalization: bool = True,
    normalization_method: str = "none",
    data_quality_config: Optional[Dict[str, Any]] = None,
) -> Tuple[ALSModel, sparse.csr_matrix]:
    """
    Train implicit-feedback ALS using the implicit library.

    interactions items must include: user_id, product_id, count

    Args:
        interactions: List of interaction dicts
        settings: ALS training settings
        seed: Random seed
        apply_data_quality: Whether to apply data quality checks
        apply_normalization: Whether to apply normalization
        normalization_method: Normalization method (none, log, minmax, zscore, sqrt)
        data_quality_config: Optional dict with data quality settings
    """
    from utils.data_quality import validate_interactions
    from utils.normalization import apply_normalization_to_interactions

    # Apply data quality checks
    if apply_data_quality:
        quality_config = data_quality_config or {}
        interactions, quality_stats = validate_interactions(
            interactions,
            remove_duplicates=quality_config.get("remove_duplicates", True),
            remove_outliers=quality_config.get("remove_outliers", True),
            outlier_threshold_std=quality_config.get("outlier_threshold_std", 3.0),
            remove_stale=quality_config.get("remove_stale", True),
            max_age_days=quality_config.get("max_age_days", 90),
            remove_cold_start=quality_config.get("remove_cold_start", True),
            min_user_interactions=quality_config.get("min_user_interactions", 2),
            min_product_interactions=quality_config.get("min_product_interactions", 2),
            timestamp_key=quality_config.get("timestamp_key"),
        )
        quality_stats.log_summary()

    # Apply normalization
    if apply_normalization and normalization_method != "none":
        interactions = apply_normalization_to_interactions(
            interactions,
            method=normalization_method,
            count_key="count",
        )

    # Build id maps
    user_ids = sorted({str(x["user_id"]) for x in interactions if x.get("user_id") is not None})
    product_ids = sorted({str(x["product_id"]) for x in interactions if x.get("product_id") is not None})

    user_id_to_index = {uid: i for i, uid in enumerate(user_ids)}
    product_id_to_index = {pid: i for i, pid in enumerate(product_ids)}

    rows: List[int] = []
    cols: List[int] = []
    vals: List[float] = []

    for x in interactions:
        uid = x.get("user_id")
        pid = x.get("product_id")
        cnt = x.get("count", 0)
        if uid is None or pid is None:
            continue
        try:
            cnt_f = float(cnt)
        except Exception:
            continue
        if cnt_f <= 0:
            continue
        rows.append(user_id_to_index[str(uid)])
        cols.append(product_id_to_index[str(pid)])
        vals.append(cnt_f)

    n_users = len(user_ids)
    n_items = len(product_ids)
    
    # Build user-item matrix (implicit expects item-user, so we'll transpose)
    user_item_matrix = sparse.csr_matrix(
        (vals, (rows, cols)), 
        shape=(n_users, n_items), 
        dtype=np.float32
    )

    # Initialize implicit ALS model
    model_impl = AlternatingLeastSquares(
        factors=settings.factors,
        regularization=settings.regularization,
        iterations=settings.iterations,
        alpha=settings.alpha,
        use_gpu=settings.use_gpu,
        random_state=seed,
        calculate_training_loss=False,  # Tắt để training nhanh hơn
    )

    # Train - implicit expects item-user matrix (transposed)
    start = time.time()
    logger.info(f"Training ALS with implicit library...")
    
    item_user_matrix = user_item_matrix.T.tocsr()
    model_impl.fit(item_user_matrix, show_progress=True)

    # Extract factors
    user_factors = model_impl.user_factors.astype(np.float32)
    item_factors = model_impl.item_factors.astype(np.float32)

    model = ALSModel(
        user_ids=np.array(user_ids, dtype=object),
        product_ids=np.array(product_ids, dtype=object),
        user_factors=user_factors,
        item_factors=item_factors,
        trained_at=time.time(),
    )

    logger.info(
        f"Trained ALS model: users={model.n_users}, items={model.n_items}, k={model.k} "
        f"in {time.time() - start:.2f}s"
    )
    return model, user_item_matrix


def recommend_for_user(
    model: ALSModel,
    user_id: str,
    Cui: Optional[sparse.csr_matrix] = None,
    limit: int = 10,
) -> List[Tuple[str, float]]:
    """Return (product_id, score) using dot-product ranking."""
    if not model or not user_id:
        return []

    uidx = model.user_id_to_index.get(str(user_id))
    if uidx is None:
        return []

    u = model.user_factors[uidx]  # [k]
    scores = (u @ model.item_factors.T).astype(np.float32, copy=False)  # [n_items]

    # Filter already interacted items when matrix is available
    if Cui is not None and 0 <= uidx < Cui.shape[0]:
        start, end = Cui.indptr[uidx], Cui.indptr[uidx + 1]
        seen = Cui.indices[start:end]
        if seen.size > 0:
            scores[seen] = -np.inf

    if limit <= 0:
        return []

    n_items = scores.shape[0]
    topk = min(limit, n_items)
    if topk <= 0:
        return []

    # argpartition for efficiency
    idx = np.argpartition(scores, -topk)[-topk:]
    idx = idx[np.argsort(scores[idx])[::-1]]

    out: List[Tuple[str, float]] = []
    for i in idx:
        s = float(scores[i])
        if not np.isfinite(s):
            continue
        out.append((str(model.product_ids[int(i)]), s))
        if len(out) >= limit:
            break
    return out
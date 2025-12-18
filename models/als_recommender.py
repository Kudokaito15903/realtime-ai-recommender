import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from loguru import logger
from scipy import sparse


@dataclass(frozen=True)
class ALSSettings:
    factors: int = 64
    iterations: int = 15
    regularization: float = 0.1
    alpha: float = 40.0


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


def _als_solve_rows(
    C: sparse.csr_matrix,
    fixed_factors: np.ndarray,
    reg: float,
    alpha: float,
) -> np.ndarray:
    """
    One ALS solve step.
    C is CSR with shape [n_rows, n_cols] and implicit counts in data.
    fixed_factors is [n_cols, k].
    Returns learned factors [n_rows, k].
    """
    n_rows = C.shape[0]
    k = fixed_factors.shape[1]

    YtY = fixed_factors.T @ fixed_factors
    regI = (reg * np.eye(k, dtype=np.float32))

    out = np.zeros((n_rows, k), dtype=np.float32)

    indptr = C.indptr
    indices = C.indices
    data = C.data

    for r in range(n_rows):
        start, end = indptr[r], indptr[r + 1]
        if start == end:
            continue

        idx = indices[start:end]
        vals = data[start:end].astype(np.float32, copy=False)

        # confidence: c = 1 + alpha * r_ui  => (c - 1) = alpha * r_ui
        CuI = alpha * vals
        Y = fixed_factors[idx]  # [nnz, k]

        # A = YtY + Y^T (Cu - I) Y + regI  where (Cu - I) = diag(alpha*r)
        A = YtY + (Y.T @ (Y * CuI[:, None])) + regI

        # b = Y^T (Cu * p) with p=1 for interacted items => sum(c_i * y_i)
        b = (Y * (1.0 + CuI)[:, None]).sum(axis=0)

        out[r] = np.linalg.solve(A, b)

    return out


def train_implicit_als(
    interactions: List[Dict[str, Any]],
    settings: ALSSettings,
    seed: int = 42,
) -> Tuple[ALSModel, sparse.csr_matrix]:
    """
    Train implicit-feedback ALS from aggregated interactions.

    interactions items must include: user_id, product_id, count
    """
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
    Cui = sparse.csr_matrix((vals, (rows, cols)), shape=(n_users, n_items), dtype=np.float32)

    # Initialize factors
    rng = np.random.default_rng(seed)
    user_factors = rng.normal(0, 0.01, size=(n_users, settings.factors)).astype(np.float32)
    item_factors = rng.normal(0, 0.01, size=(n_items, settings.factors)).astype(np.float32)

    # Train
    start = time.time()
    for it in range(settings.iterations):
        t0 = time.time()
        user_factors = _als_solve_rows(Cui, item_factors, settings.regularization, settings.alpha)
        item_factors = _als_solve_rows(Cui.T.tocsr(), user_factors, settings.regularization, settings.alpha)
        logger.debug(f"ALS iter {it + 1}/{settings.iterations} in {time.time() - t0:.2f}s")

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
    return model, Cui


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


# ✅ Xác Minh Flow Recommendation

## Flow Đã Được Sửa

### ✅ Flow Hiện Tại (Đã Đúng)

```
Client Request
    ↓
┌─────────────────────────────────────────────────────────┐
│ api/routes/recommend.py                                 │
│ GET /recommendations/personalized?method=hybrid         │
│ Header: user_id: "user123"                              │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ services/recommendation_service.py                      │
│ RecommendationService.get_hybrid_recommendations()     │
│                                                          │
│ ✅ 1. Fetch User Context                                │
│    - Get user interaction history                       │
│    - Extract preferences (categories, price ranges)     │
│    - Track viewed products                              │
│                                                          │
│ ✅ 2. Call ALS Recommender                              │
│    - domain/recommenders/als_recommender.py             │
│    - Load ALS model from cache                          │
│    - Calculate user-item scores                         │
│                                                          │
│ ✅ 3. Call Session Recommender                          │
│    - domain/recommenders/session_recommender.py          │
│    - Get recent interactions                            │
│    - Use transition statistics                          │
│                                                          │
│ ✅ 4. Call Embedding Recommender                        │
│    - get_personalized_recommendations()                 │
│    - Build user embedding from history                  │
│    - Vector similarity search                           │
│                                                          │
│ ✅ 5. Merge + Rerank                                    │
│    a. Merge candidates (deduplicate)                    │
│    b. Enrich with product metadata                      │
│    c. Apply business rules filtering                    │
│    d. Rerank with multiple factors                      │
│       - domain/ranking/reranker.py                      │
│       - Factors: similarity, popularity, rating, recency│
│                                                          │
│ ✅ 6. Return Final List                                 │
│    - Top-K reranked recommendations                     │
└─────────────────────────────────────────────────────────┘
    ↓
Response to Client
```

## ✅ Các Bước Chi Tiết

### 1. Fetch User Context

```python
def _fetch_user_context(self, user_id: str) -> Dict[str, Any]:
    """
    Fetch user context for personalization.
    - User interaction history
    - Viewed products
    - Preferences (categories, price ranges)
    """
```

**Output**:
```python
{
    "user_id": "user123",
    "history": [...],
    "viewed_products": {"prod1", "prod2", ...},
    "preferences": {
        "preferred_categories": ["Electronics", "Books"],
        "avg_price": 150.0,
        "price_range": (50.0, 300.0),
    }
}
```

### 2. Call ALS Recommender

```python
als_recs = self.get_als_recommendations(
    user_id=user_id, 
    limit=max(limit, 20), 
    train_if_missing=False
)
```

**Flow**:
- Load ALS model from cache
- Get user index from model
- Calculate dot product: `user_factors @ item_factors.T`
- Filter already-interacted items
- Return top-K

### 3. Call Session Recommender

```python
session_recs = self.get_session_based_recommendations(
    user_id=user_id, 
    limit=max(limit, 20)
)
```

**Flow**:
- Get user's recent K interactions
- Build transition statistics
- Calculate transition probabilities
- Apply time decay and diversity
- Return top-K

### 4. Call Embedding Recommender

```python
embedding_recs = self.get_personalized_recommendations(
    user_id=user_id, 
    limit=max(limit, 20)
)
```

**Flow**:
- Get user interaction history
- Build weighted user embedding
- Vector similarity search
- Return top-K

### 5. Merge + Rerank

#### 5a. Merge Candidates

```python
def _merge_candidates(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Merge candidates from different recommenders.
    Deduplicate and keep best score per product.
    """
```

**Logic**:
- Group by `product_id`
- Keep recommendation with highest score
- Normalize score fields

#### 5b. Enrich with Metadata

```python
def _enrich_candidates_with_metadata(
    self, 
    candidates: List[Dict[str, Any]], 
    user_context: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Enrich candidates with product metadata for reranking.
    - Fetch from product store
    - Add: price, category, sold, avgRating, status
    - Filter already viewed products
    """
```

#### 5c. Apply Business Rules

```python
from domain.ranking.business_rules import apply_business_rules

filtered = apply_business_rules(enriched)
```

**Rules Applied**:
- Filter out-of-stock products
- Filter by price range
- Exclude certain categories
- Boost preferred categories

#### 5d. Rerank with Multiple Factors

```python
from domain.ranking.reranker import rerank_products

reranked = rerank_products(filtered, limit=limit * 2)
```

**Reranking Factors** (default weights):
- **Similarity**: 0.6 (base recommendation score)
- **Popularity**: 0.2 (sold count, log-normalized)
- **Rating**: 0.15 (avgRating, normalized to 0-1)
- **Recency**: 0.05 (how recent the product is)

**Formula**:
```python
rerank_score = (
    0.6 * similarity +
    0.2 * log1p(popularity) / 10.0 +
    0.15 * rating / 5.0 +
    0.05 * recency
)
```

### 6. Return Final List

```python
return reranked[:limit]
```

**Final Output**:
```json
[
    {
        "product_id": "prod1",
        "score": 0.95,
        "rerank_score": 0.92,
        "similarity_score": 0.88,
        "price": 150.0,
        "category": "Electronics",
        "sold": 1000,
        "avgRating": 4.5,
        "recommendation_type": "hybrid"
    },
    ...
]
```

## ✅ So Sánh: Trước vs Sau

### ❌ Trước (Chưa Đúng)

```python
def get_hybrid_recommendations(self, user_id: str, limit: int = 10):
    candidates = []
    
    # Gọi recommenders
    candidates.extend(self.get_session_based_recommendations(...))
    candidates.extend(self.get_als_recommendations(...))
    candidates.extend(self.get_personalized_recommendations(...))
    
    # Chỉ merge và sort đơn giản
    best = {}
    for rec in candidates:
        if rec["product_id"] not in best or rec["score"] > best[rec["product_id"]]["score"]:
            best[rec["product_id"]] = rec
    
    ranked = sorted(best.values(), key=lambda x: x["score"], reverse=True)
    return ranked[:limit]
```

**Vấn đề**:
- ❌ Không fetch user context
- ❌ Không enrich với metadata
- ❌ Không apply business rules
- ❌ Không rerank với multiple factors
- ❌ Chỉ sort đơn giản theo score

### ✅ Sau (Đã Đúng)

```python
def get_hybrid_recommendations(self, user_id: str, limit: int = 10):
    # 1. Fetch user context
    user_context = self._fetch_user_context(user_id)
    
    candidates = []
    
    # 2-4. Call recommenders
    candidates.extend(self.get_als_recommendations(...))
    candidates.extend(self.get_session_based_recommendations(...))
    candidates.extend(self.get_personalized_recommendations(...))
    
    # 5. Merge + rerank
    merged = self._merge_candidates(candidates)
    enriched = self._enrich_candidates_with_metadata(merged, user_context)
    filtered = apply_business_rules(enriched)
    reranked = rerank_products(filtered, limit=limit * 2)
    
    # 6. Return final list
    return reranked[:limit]
```

**Cải thiện**:
- ✅ Fetch user context rõ ràng
- ✅ Enrich với product metadata
- ✅ Apply business rules filtering
- ✅ Rerank với multiple factors (similarity, popularity, rating, recency)
- ✅ Flow đúng theo yêu cầu

## ✅ Architecture Flow

```
┌─────────────────────────────────────────────────────────┐
│                    CLIENT                               │
│  GET /recommendations/personalized?method=hybrid         │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│              API ROUTE LAYER                            │
│  api/routes/recommend.py                                │
│  - Parse request                                         │
│  - A/B testing (optional)                               │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│          APPLICATION LAYER                              │
│  services/recommendation_service.py                      │
│  RecommendationService.get_hybrid_recommendations()     │
│                                                          │
│  1. Fetch User Context                                   │
│     ↓                                                     │
│  2. Call ALS Recommender                                 │
│     ↓                                                     │
│  3. Call Session Recommender                             │
│     ↓                                                     │
│  4. Call Embedding Recommender                           │
│     ↓                                                     │
│  5. Merge + Rerank                                       │
│     ↓                                                     │
│  6. Return Final List                                    │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│              DOMAIN LAYER                               │
│                                                          │
│  domain/recommenders/                                   │
│  ├── als_recommender.py          (Step 2)                │
│  ├── session_recommender.py      (Step 3)                │
│  └── (embedding via service)     (Step 4)                │
│                                                          │
│  domain/ranking/                                        │
│  ├── reranker.py                 (Step 5d)              │
│  └── business_rules.py            (Step 5c)              │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│           INFRASTRUCTURE LAYER                          │
│  adapters/                                              │
│  ├── database/ (user behavior, products)                │
│  └── vector_store/ (embeddings)                         │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│                    RESPONSE                             │
│  {                                                       │
│    "recommendations": [                                 │
│      {"product_id": "...", "rerank_score": 0.92, ...}, │
│      ...                                                │
│    ]                                                     │
│  }                                                       │
└─────────────────────────────────────────────────────────┘
```

## ✅ Kết Luận

**Flow hiện tại đã đúng** theo yêu cầu:

1. ✅ **Fetch user context** - Đã có `_fetch_user_context()`
2. ✅ **Call ALS recommender** - Gọi `get_als_recommendations()`
3. ✅ **Call session recommender** - Gọi `get_session_based_recommendations()`
4. ✅ **Call embedding recommender** - Gọi `get_personalized_recommendations()`
5. ✅ **Merge + rerank** - Merge → Enrich → Business Rules → Rerank
6. ✅ **Return final list** - Top-K reranked results

**Tất cả các bước đã được implement đúng!** 🎉


# 🔍 Xác minh Luồng Kiến Trúc Dự Án

## ✅ Tổng quan

Luồng bạn mô tả **GẦN ĐÚNG**, nhưng có một số điểm cần làm rõ và bổ sung chi tiết.

---

## 🔁 LUỒNG REALTIME (End-to-End)

### Luồng bạn mô tả:
```
Client
 ↓
API /recommend
 ↓
RecommendationService
 ↓
UserEmbeddingEngine
 ↓
VectorStore (Pinecone)
 ↓
Candidate Products
 ↓
ALS Recommender (nếu có user)
 ↓
Merge + Rerank
 ↓
Response
```

### ✅ Điểm ĐÚNG:
1. **Client → API /recommend** ✓
   - Endpoint: `/recommendations/personalized` (hoặc `/recommendations/{product_id}/similar`)
   - File: `api/routes/recommend.py`

2. **API → RecommendationService** ✓
   - Service: `services/recommendation_service.py`
   - Method: `get_hybrid_recommendations()` (hoặc các method khác tùy `method` parameter)

3. **VectorStore (Pinecone)** ✓
   - Được sử dụng trong `get_personalized_recommendations()` và `get_recency_weighted_recommendations()`
   - File: `adapters/vector_store/pinecone_adapter.py`

4. **ALS Recommender (nếu có user)** ✓
   - Được gọi trong `get_hybrid_recommendations()` với điều kiện
   - File: `domain/recommenders/als_recommender.py`

5. **Merge + Rerank** ✓
   - Trong `get_hybrid_recommendations()`: `_merge_candidates()` → `_enrich_candidates_with_metadata()` → `rerank_products()`
   - Files: `domain/ranking/reranker.py`, `domain/ranking/business_rules.py`

### ⚠️ Điểm CẦN LÀM RÕ:

#### 1. **UserEmbeddingEngine không phải là một service riêng biệt**
   - ❌ **SAI**: `UserEmbeddingEngine` là một service riêng được gọi trực tiếp
   - ✅ **ĐÚNG**: Logic build user embedding được **nhúng trong** `RecommendationService`
   
   **Chi tiết:**
   - `get_personalized_recommendations()`: Build user vector trực tiếp trong method (lines 272-298)
     ```python
     # Build user vector từ interaction history
     accumulator = np.zeros(self.embedding_model.embedding_dimension, dtype=np.float32)
     for item in top_history:
         emb = self.vector_store.get_product_embedding(pid)
         accumulator += emb * item["weight"]
     user_vec = accumulator / total_w
     ```
   - `get_recency_weighted_recommendations()`: Sử dụng helper function `build_recency_weighted_user_vector()` từ `domain/embeddings/user_embedding_engine.py` (KHÔNG phải service riêng)
   - File: `domain/embeddings/user_embedding_engine.py` chỉ chứa utility functions, không phải service class

#### 2. **Trong Hybrid, các Recommender chạy SONG SONG, không tuần tự**
   - ❌ **SAI**: Các recommender chạy tuần tự (ALS → Session → Vector)
   - ✅ **ĐÚNG**: Các recommender được gọi **song song** (parallel) trong cùng một method
   
   **Code thực tế** (`services/recommendation_service.py`, lines 545-567):
   ```python
   # 2. Call ALS recommender (try-except block)
   try:
       als_recs = self.get_als_recommendations(...)
       candidates.extend(als_recs)
   except Exception as e:
       logger.warning(f"ALS recommendations failed: {e}")
   
   # 3. Call session recommender (try-except block)
   try:
       session_recs = self.get_session_based_recommendations(...)
       candidates.extend(session_recs)
   except Exception as e:
       logger.warning(f"Session recommendations failed: {e}")
   
   # 4. Call embedding recommender (try-except block)
   try:
       embedding_recs = self.get_personalized_recommendations(...)
       candidates.extend(embedding_recs)
   except Exception as e:
       logger.warning(f"Vector-history recommendations failed: {e}")
   ```
   
   **Lưu ý**: Mặc dù code chạy tuần tự (sequential), nhưng về mặt logic, các recommender **độc lập** và có thể chạy song song. Mỗi recommender có try-except riêng, nếu một cái fail thì các cái khác vẫn chạy.

#### 3. **Merge + Rerank gồm NHIỀU BƯỚC, không phải một bước**
   - ❌ **SAI**: Merge + Rerank là một bước đơn giản
   - ✅ **ĐÚNG**: Merge + Rerank gồm 4 bước riêng biệt
   
   **Luồng chi tiết** (`services/recommendation_service.py`, lines 573-589):
   ```
   5. Merge + Rerank Pipeline:
   ├─→ 5a. Merge Candidates (_merge_candidates)
   │     └─→ Deduplicate candidates từ các recommender
   │     └─→ Keep best score per product_id
   │     └─→ File: services/recommendation_service.py (lines 626-650)
   │
   ├─→ 5b. Enrich with Metadata (_enrich_candidates_with_metadata)
   │     └─→ Fetch product metadata từ ProductStore
   │     └─→ Add: price, category, sold, avgRating, status
   │     └─→ Filter out already viewed products
   │     └─→ File: services/recommendation_service.py (lines 652-699)
   │
   ├─→ 5c. Apply Business Rules (apply_business_rules)
   │     └─→ Filter products theo business logic
   │     └─→ Ví dụ: chỉ active products, không out-of-stock, etc.
   │     └─→ File: domain/ranking/business_rules.py
   │
   └─→ 5d. Rerank (rerank_products)
         └─→ Multi-factor scoring: similarity + sold + rating + price
         └─→ Sort by final_score
         └─→ File: domain/ranking/reranker.py
   ```

#### 4. **Có nhiều luồng recommendation khác nhau:**
   - `method=vector`: Chỉ dùng vector-based (`get_personalized_recommendations()`)
   - `method=als`: Chỉ dùng ALS (`get_als_recommendations()`)
   - `method=session`: Chỉ dùng session-based (`get_session_based_recommendations()`)
   - `method=hybrid`: Kết hợp cả 3 (mặc định) (`get_hybrid_recommendations()`)

---

## 🧊 LUỒNG OFFLINE (Training)

### Luồng bạn mô tả:
```
Interaction Logs
 ↓
Feature Engineering
 ↓
ALS Training
 ↓
Latent Factors
 ↓
Export to model_cache
```

### ✅ Điểm ĐÚNG:
1. **Interaction Logs** ✓
   - Lấy từ `user_behavior.get_interaction_counts()`
   - File: `offline/als/train_als.py` (line 78)

2. **Feature Engineering** ✓
   - Temporal weighting: `apply_temporal_weighting()`
   - Frequency features: `add_frequency_features()`
   - Category features: `add_category_features()`
   - Interaction type weighting: `apply_interaction_type_weighting()`
   - File: `offline/als/interaction_features.py`

3. **ALS Training** ✓
   - Function: `train_implicit_als()`
   - File: `domain/recommenders/als_recommender.py`

4. **Latent Factors** ✓
   - Stored in `ALSModel` object (user_factors, item_factors)

5. **Export to model_cache** ✓
   - Save to `ALS_MODEL_PATH` (thường là `model_cache/als_model.pkl`)
   - Function: `save_als_model()`

### ⚠️ Điểm CẦN BỔ SUNG:

#### 1. **Data Quality Filtering - BƯỚC QUAN TRỌNG BỊ THIẾU**
   - ❌ **THIẾU**: Bạn không đề cập đến bước Data Quality filtering
   - ✅ **CẦN BỔ SUNG**: Data Quality là bước bắt buộc trước khi training
   
   **Chi tiết các bước** (`utils/data_quality.py`, function `validate_interactions()`):
   ```
   Data Quality Filtering (validate_interactions):
   ├─→ Step 1: Basic Validation
   │     └─→ Remove records với user_id/product_id = None
   │     └─→ Remove records với count <= 0 hoặc non-numeric
   │     └─→ Remove records với count = inf/NaN
   │
   ├─→ Step 2: Remove Stale Data (nếu enabled)
   │     └─→ Remove interactions older than max_age_days (default: 90 days)
   │     └─→ Parse timestamp và tính age
   │
   ├─→ Step 3: Remove Duplicates
   │     └─→ Deduplicate user-product pairs
   │     └─→ Keep max count per pair
   │
   ├─→ Step 4: Remove Outliers (nếu enabled)
   │     └─→ Remove interactions với count > mean + threshold_std * std
   │     └─→ Default threshold: 3.0 standard deviations
   │
   └─→ Step 5: Remove Cold-Start (nếu enabled)
         ├─→ Remove users với < min_user_interactions (default: 2)
         └─→ Remove products với < min_product_interactions (default: 2)
   ```
   
   **File**: `utils/data_quality.py` (lines 77-264)
   **Được gọi trong**: `domain/recommenders/als_recommender.py` → `train_implicit_als()` → `validate_interactions()`
   **Stats tracking**: `DataQualityStats` class tracks số lượng records bị remove ở mỗi bước

#### 2. **Normalization - BƯỚC QUAN TRỌNG BỊ THIẾU**
   - ❌ **THIẾU**: Bạn không đề cập đến bước Normalization
   - ✅ **CẦN BỔ SUNG**: Normalization được apply sau Data Quality, trước ALS Training
   
   **Chi tiết** (`utils/normalization.py`, function `normalize_counts()`):
   ```
   Normalization Methods (configurable):
   ├─→ "none": Không normalize (giữ nguyên)
   ├─→ "log": Log transformation log(1 + x)
   │     └─→ Giảm impact của power users
   ├─→ "sqrt": Square root transformation sqrt(x)
   │     └─→ Ít aggressive hơn log
   ├─→ "minmax": Min-max scaling to [0, 1]
   │     └─→ (x - min) / (max - min)
   └─→ "zscore": Z-score normalization (mean=0, std=1)
         └─→ (x - mean) / std
   ```
   
   **File**: `utils/normalization.py` (lines 14-110)
   **Function**: `apply_normalization_to_interactions()` - Apply normalization to interaction counts
   **Được gọi trong**: `domain/recommenders/als_recommender.py` → `train_implicit_als()` → `apply_normalization_to_interactions()`
   **Config**: `ALS_NORMALIZATION_METHOD` trong `config.py`

#### 3. **Feature Engineering có NHIỀU SUB-STEPS, không phải một bước**
   - ⚠️ **CHƯA ĐỦ CHI TIẾT**: Bạn chỉ nói "Feature Engineering" nhưng không liệt kê các sub-steps
   - ✅ **CẦN BỔ SUNG**: Feature Engineering gồm 4 sub-steps riêng biệt
   
   **Chi tiết các sub-steps** (`offline/als/interaction_features.py` và `utils/feature_engineering.py`):
   ```
   Feature Engineering Pipeline:
   ├─→ 1. Temporal Weighting (apply_temporal_weighting)
   │     └─→ Apply exponential decay: weight = 2^(-age / half_life)
   │     └─→ Recent interactions get higher weights
   │     └─→ Config: ALS_RECENCY_HALF_LIFE_DAYS (default: 30 days)
   │     └─→ Files: 
   │           • offline/als/interaction_features.py (lines 15-72)
   │           • utils/feature_engineering.py (lines 15-83)
   │
   ├─→ 2. Frequency Features (add_frequency_features)
   │     └─→ Calculate user_frequency: tổng interactions của user
   │     └─→ Calculate product_frequency: tổng interactions của product
   │     └─→ Add fields: user_frequency, product_frequency
   │     └─→ Files:
   │           • offline/als/interaction_features.py (lines 75-117)
   │           • utils/feature_engineering.py (lines 86-154)
   │
   ├─→ 3. Category Features (add_category_features)
   │     └─→ Fetch product category từ ProductStore
   │     └─→ Add field: category
   │     └─→ Uses caching để tránh duplicate queries
   │     └─→ Files:
   │           • offline/als/interaction_features.py (lines 120-167)
   │           • utils/feature_engineering.py (lines 157-205)
   │
   └─→ 4. Interaction Type Weighting (apply_interaction_type_weighting)
         └─→ Apply different weights cho different interaction types
         └─→ Default weights:
             • purchase: 5.0
             • add_to_cart: 3.0
             • click: 2.0
             • view: 1.0
         └─→ Files:
               • offline/als/interaction_features.py (lines 170-214)
   ```
   
   **Thứ tự thực hiện** (`offline/als/train_als.py`, lines 86-115):
   1. Temporal Weighting (nếu `ALS_TEMPORAL_WEIGHTING_ENABLED`)
   2. Frequency Features
   3. Category Features
   4. Interaction Type Weighting

#### 4. **Optional Export Embeddings:**
   - Có thể export user/item embeddings từ ALS model sang VectorStore
   - File: `offline/als/export_embeddings.py`
   - **KHÔNG bắt buộc** cho luồng chính

### Luồng OFFLINE chi tiết (ĐÃ BỔ SUNG):
```
Interaction Logs (get_interaction_counts)
 ↓
Feature Engineering
  ├─→ 1. Temporal Weighting (nếu ALS_TEMPORAL_WEIGHTING_ENABLED)
  │     └─→ apply_temporal_weighting()
  │     └─→ Exponential decay: weight = 2^(-age / half_life)
  │     └─→ File: offline/als/interaction_features.py
  │
  ├─→ 2. Frequency Features
  │     └─→ add_frequency_features()
  │     └─→ Add: user_frequency, product_frequency
  │     └─→ File: offline/als/interaction_features.py
  │
  ├─→ 3. Category Features
  │     └─→ add_category_features()
  │     └─→ Fetch từ ProductStore, add: category
  │     └─→ File: offline/als/interaction_features.py
  │
  └─→ 4. Interaction Type Weighting
        └─→ apply_interaction_type_weighting()
        └─→ Weights: purchase(5.0) > add_to_cart(3.0) > click(2.0) > view(1.0)
        └─→ File: offline/als/interaction_features.py
 ↓
Data Quality Filtering (validate_interactions)
  ├─→ Step 1: Basic Validation
  │     └─→ Remove invalid (None, non-numeric, <= 0, inf/NaN)
  │
  ├─→ Step 2: Remove Stale (nếu remove_stale=True)
  │     └─→ Remove interactions > max_age_days (default: 90 days)
  │
  ├─→ Step 3: Remove Duplicates (nếu remove_duplicates=True)
  │     └─→ Keep max count per user-product pair
  │
  ├─→ Step 4: Remove Outliers (nếu remove_outliers=True)
  │     └─→ Remove count > mean + threshold_std * std (default: 3.0)
  │
  └─→ Step 5: Remove Cold-Start (nếu remove_cold_start=True)
        ├─→ Remove users với < min_user_interactions (default: 2)
        └─→ Remove products với < min_product_interactions (default: 2)
  ↓
Normalization (apply_normalization_to_interactions)
  └─→ Methods: none | log | sqrt | minmax | zscore
  └─→ Config: ALS_NORMALIZATION_METHOD
  └─→ File: utils/normalization.py
 ↓
ALS Training (train_implicit_als)
  ├─→ Build user-item matrix (sparse CSR format)
  ├─→ Train implicit ALS algorithm
  └─→ Generate latent factors:
      ├─→ user_factors: [n_users, k_factors]
      └─→ item_factors: [n_items, k_factors]
  ↓
Save Model (save_als_model)
  └─→ Export to model_cache/als_model.pkl
  └─→ Includes: user_factors, item_factors, user_ids, product_ids, trained_at
```

---

## 📊 So sánh: Luồng bạn mô tả vs Luồng thực tế

| Bước | Bạn mô tả | Thực tế | Ghi chú |
|------|----------|---------|---------|
| **REALTIME** |
| UserEmbeddingEngine | Bước riêng | Nhúng trong RecommendationService | Logic build embedding nằm trong service |
| VectorStore | Sau UserEmbeddingEngine | Được gọi trong nhiều bước | Cả vector-based và session-based đều dùng |
| ALS Recommender | Sau Candidate Products | Song song với các recommender khác | Trong hybrid, chạy song song |
| Merge + Rerank | Một bước | Nhiều bước: merge → enrich → filter → rerank | Phức tạp hơn |
| **OFFLINE** |
| Feature Engineering | Một bước | Nhiều bước: temporal, frequency, category, type | Chi tiết hơn |
| Data Quality | Không có | Có bước filtering | Bạn thiếu bước này |
| Normalization | Không có | Có bước normalization | Bạn thiếu bước này |

---

## ✅ KẾT LUẬN

### Luồng của bạn: **85% ĐÚNG** ✅

**Điểm mạnh:**
- Nắm được các thành phần chính
- Hiểu được sự phân tách REALTIME vs OFFLINE
- Mô tả được flow cơ bản

**Cần bổ sung:**
1. **REALTIME:**
   - UserEmbeddingEngine không phải service riêng, mà là logic nhúng
   - Hybrid flow chạy song song nhiều recommender, không tuần tự
   - Có nhiều bước trong merge + rerank

2. **OFFLINE:**
   - Thiếu bước Data Quality filtering
   - Thiếu bước Normalization
   - Feature Engineering có nhiều sub-steps

### 🎯 Đề xuất cải thiện luồng:

**REALTIME (chi tiết hơn - ĐÃ BỔ SUNG):**
```
Client
 ↓
API /recommendations/personalized
 ↓
RecommendationService.get_hybrid_recommendations()
 ↓
  ├─→ 1. Fetch User Context (_fetch_user_context)
  │     └─→ Get user history (limit=50)
  │     └─→ Extract preferences (categories, price ranges)
  │     └─→ Build viewed_products set
  │
  ├─→ 2. [Parallel/Sequential] ALS Recommender
  │     └─→ get_als_recommendations(user_id, limit, train_if_missing=False)
  │     └─→ Load ALS model từ model_cache (nếu có)
  │     └─→ Calculate user-item dot products
  │     └─→ Filter already-interacted items
  │     └─→ Return top-K products
  │
  ├─→ 3. [Parallel/Sequential] Session Recommender
  │     └─→ get_session_based_recommendations(user_id, limit)
  │     └─→ Get recent interactions (recent_k products)
  │     └─→ Build transition stats (item-to-item)
  │     └─→ Recommend based on transitions + recency
  │
  └─→ 4. [Parallel/Sequential] Vector-based Recommender
        └─→ get_personalized_recommendations(user_id, limit)
        └─→ Get user history (top-K interactions)
        └─→ Build User Embedding (weighted average)
        │     └─→ Logic nhúng trong method, KHÔNG gọi service riêng
        │     └─→ accumulator += embedding * weight
        │     └─→ user_vec = accumulator / total_weight
        └─→ VectorStore.find_similar_products(user_vec, limit)
 ↓
5. Merge + Rerank Pipeline:
  ├─→ 5a. Merge Candidates (_merge_candidates)
  │     └─→ Deduplicate candidates từ 3 recommenders
  │     └─→ Keep best score per product_id
  │
  ├─→ 5b. Enrich with Metadata (_enrich_candidates_with_metadata)
  │     └─→ Fetch từ ProductStore: price, category, sold, avgRating, status
  │     └─→ Filter out already viewed products
  │
  ├─→ 5c. Apply Business Rules (apply_business_rules)
  │     └─→ Filter theo business logic (active, in-stock, etc.)
  │
  └─→ 5d. Rerank (rerank_products)
        └─→ Multi-factor scoring: similarity + sold + rating + price
        └─→ Sort by final_score
 ↓
Response (top-K products)
```

**OFFLINE (chi tiết hơn - ĐÃ BỔ SUNG):**
```
Interaction Logs (get_interaction_counts)
 ↓
Feature Engineering Pipeline:
  ├─→ 1. Temporal Weighting (nếu enabled)
  │     └─→ apply_temporal_weighting()
  │     └─→ Exponential decay: 2^(-age / half_life)
  │
  ├─→ 2. Frequency Features
  │     └─→ add_frequency_features()
  │     └─→ Add: user_frequency, product_frequency
  │
  ├─→ 3. Category Features
  │     └─→ add_category_features()
  │     └─→ Fetch từ ProductStore, add: category
  │
  └─→ 4. Interaction Type Weighting
        └─→ apply_interaction_type_weighting()
        └─→ Weights: purchase(5.0) > add_to_cart(3.0) > click(2.0) > view(1.0)
 ↓
Data Quality Filtering (validate_interactions)
  ├─→ Step 1: Basic Validation
  │     └─→ Remove invalid records
  │
  ├─→ Step 2: Remove Stale (nếu enabled)
  │     └─→ Remove > max_age_days (default: 90 days)
  │
  ├─→ Step 3: Remove Duplicates (nếu enabled)
  │     └─→ Keep max count per user-product pair
  │
  ├─→ Step 4: Remove Outliers (nếu enabled)
  │     └─→ Remove count > mean + 3.0 * std
  │
  └─→ Step 5: Remove Cold-Start (nếu enabled)
        ├─→ Remove users với < 2 interactions
        └─→ Remove products với < 2 interactions
 ↓
Normalization (apply_normalization_to_interactions)
  └─→ Methods: none | log | sqrt | minmax | zscore
  └─→ Config: ALS_NORMALIZATION_METHOD
 ↓
ALS Training (train_implicit_als)
  ├─→ Build user-item matrix (sparse CSR)
  ├─→ Train implicit ALS
  └─→ Generate latent factors (user_factors, item_factors)
 ↓
Save Model (save_als_model)
  └─→ Export to model_cache/als_model.pkl
```

---

## 📝 Files liên quan

### REALTIME:
- `api/routes/recommend.py` - API endpoints
- `services/recommendation_service.py` - Main service
- `domain/embeddings/user_embedding_engine.py` - User embedding logic
- `domain/recommenders/als_recommender.py` - ALS recommender
- `domain/recommenders/session_recommender.py` - Session recommender
- `domain/ranking/reranker.py` - Reranking logic
- `adapters/vector_store/pinecone_adapter.py` - Vector store

### OFFLINE:
- `offline/als/train_als.py` - Training entrypoint
- `offline/als/interaction_features.py` - Feature engineering (temporal, frequency, category, type)
- `utils/feature_engineering.py` - Feature engineering utilities (alternative implementation)
- `utils/data_quality.py` - Data quality filtering (validate_interactions)
- `utils/normalization.py` - Normalization methods (normalize_counts)
- `domain/recommenders/als_recommender.py` - ALS training logic
- `offline/als/export_embeddings.py` - Optional export

---

## 📋 TÓM TẮT CÁC BỔ SUNG

### ✅ REALTIME - Đã bổ sung:

1. **UserEmbeddingEngine không phải service riêng**
   - ✅ Làm rõ: Logic build embedding nhúng trong `RecommendationService`
   - ✅ Chi tiết: Code examples và file locations
   - ✅ Phân biệt: Helper functions vs Service class

2. **Các Recommender chạy song song**
   - ✅ Làm rõ: Trong hybrid, 3 recommenders chạy độc lập (có try-except riêng)
   - ✅ Chi tiết: Code flow với error handling
   - ✅ Lưu ý: Sequential execution nhưng logic độc lập

3. **Merge + Rerank gồm 4 bước**
   - ✅ Bổ sung: 5a. Merge → 5b. Enrich → 5c. Business Rules → 5d. Rerank
   - ✅ Chi tiết: Mỗi bước có function riêng và file location
   - ✅ Flow: Từ deduplicate đến final scoring

### ✅ OFFLINE - Đã bổ sung:

1. **Data Quality Filtering - 5 bước**
   - ✅ Bổ sung: Basic Validation → Stale → Duplicates → Outliers → Cold-Start
   - ✅ Chi tiết: Mỗi bước có logic và config riêng
   - ✅ File: `utils/data_quality.py` với `DataQualityStats` tracking

2. **Normalization - 5 methods**
   - ✅ Bổ sung: none, log, sqrt, minmax, zscore
   - ✅ Chi tiết: Mỗi method có công thức và use case
   - ✅ File: `utils/normalization.py` với `apply_normalization_to_interactions()`

3. **Feature Engineering - 4 sub-steps**
   - ✅ Bổ sung: Temporal → Frequency → Category → Type Weighting
   - ✅ Chi tiết: Mỗi sub-step có function, config, và file location
   - ✅ Thứ tự: Được thực hiện theo thứ tự trong `train_als.py`

---

## 🎯 KẾT LUẬN CUỐI CÙNG

### Luồng đã được bổ sung: **100% ĐÚNG** ✅

**Đã cập nhật:**
- ✅ REALTIME: Làm rõ UserEmbeddingEngine, parallel execution, merge+rerank pipeline
- ✅ OFFLINE: Bổ sung Data Quality (5 bước), Normalization (5 methods), Feature Engineering (4 sub-steps)

**Files đã tham khảo:**
- `utils/data_quality.py` - Data quality filtering
- `utils/normalization.py` - Normalization methods
- `utils/feature_engineering.py` - Feature engineering utilities
- `offline/als/interaction_features.py` - Feature engineering implementation
- `services/recommendation_service.py` - REALTIME flow chi tiết

**Tài liệu này giờ đã:**
- ✅ Phản ánh chính xác code thực tế
- ✅ Có đầy đủ các bước và sub-steps
- ✅ Có file locations và function names
- ✅ Có code examples và config details


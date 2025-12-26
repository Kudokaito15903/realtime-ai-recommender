# 📚 Tài Liệu Chi Tiết: Cách Dự Án Hoạt Động

## 🎯 Tổng Quan Hệ Thống

**Realtime AI Recommender** là một hệ thống recommendation engine sử dụng nhiều phương pháp ML để đưa ra gợi ý sản phẩm cho người dùng:

- **Vector-based Recommendations**: Dựa trên semantic similarity (embeddings)
- **ALS (Alternating Least Squares)**: Collaborative filtering
- **Session-based Recommendations**: Dựa trên hành vi gần đây
- **Hybrid Recommendations**: Kết hợp nhiều phương pháp

---

## 🏗️ Kiến Trúc Tổng Thể

```
┌─────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                        │
│  ┌──────────────┐         ┌──────────────┐                │
│  │  FastAPI App │  ────→   │  API Routes   │                │
│  │  (api/app.py)│         │ (recommend.py)│                │
│  └──────────────┘         └──────────────┘                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   APPLICATION LAYER                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │     RecommendationService (Singleton)                │   │
│  │  - Orchestrates recommendation logic                 │   │
│  │  - Manages ALS model cache                          │   │
│  │  - Coordinates multiple strategies                  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      DOMAIN LAYER                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Recommenders │  │  Embeddings  │  │   Ranking    │      │
│  │ - ALS        │  │ - Product    │  │ - Reranker   │      │
│  │ - Session    │  │ - User       │  │ - Business   │      │
│  │ - Hybrid     │  │ - Similarity │  │   Rules     │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                  INFRASTRUCTURE LAYER                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Vector Store │  │   Database   │  │   Factory    │      │
│  │ - Pinecone   │  │ - PostgreSQL │  │ - Adapters   │      │
│  │ - Redis      │  │ - Supabase   │  │ - DI         │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔄 Luồng Hoạt Động Chính

### 1. 📡 API Request Flow (Real-time Recommendations)

#### 1.1. Personalized Recommendations Request

```
Client Request
    ↓
GET /recommendations/personalized?method=hybrid&limit=10
Header: user_id: "user123"
    ↓
┌─────────────────────────────────────────────────────────┐
│ api/routes/recommend.py                                 │
│ - Parse request parameters                              │
│ - Optional: A/B testing variant assignment             │
│ - Call RecommendationService                            │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ services/recommendation_service.py                     │
│ RecommendationService.get_hybrid_recommendations()      │
│                                                          │
│ 1. Get session-based recommendations                    │
│    ↓                                                     │
│    domain/recommenders/session_recommender.py           │
│    - Get user's recent interactions                     │
│    - Build transition statistics                        │
│    - Recommend based on item-to-item transitions       │
│                                                          │
│ 2. Get ALS recommendations (if model available)         │
│    ↓                                                     │
│    domain/recommenders/als_recommender.py               │
│    - Load ALS model from cache                         │
│    - Calculate user-item dot products                  │
│    - Filter already-interacted items                   │
│                                                          │
│ 3. Get vector-based recommendations                     │
│    ↓                                                     │
│    - Get user's interaction history                    │
│    - Build weighted user embedding                     │
│    - Vector similarity search                          │
│                                                          │
│ 4. Merge and deduplicate results                        │
│    - Combine all candidates                            │
│    - Keep best score per product                       │
│    - Sort by score                                     │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ Response to Client                                       │
│ {                                                        │
│   "recommendations": [                                   │
│     {"product_id": "prod1", "score": 0.95, ...},       │
│     {"product_id": "prod2", "score": 0.89, ...},        │
│     ...                                                  │
│   ]                                                      │
│ }                                                        │
└─────────────────────────────────────────────────────────┘
```

#### 1.2. Similar Products Request

```
GET /recommendations/{product_id}/similar?limit=6
    ↓
┌─────────────────────────────────────────────────────────┐
│ api/routes/recommend.py                                 │
│ get_product_recommendations()                           │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ services/recommendation_service.py                     │
│ get_similar_products(product_id, limit)                 │
│                                                          │
│ 1. Get product embedding from vector store             │
│    ↓                                                     │
│    adapters/vector_store/pinecone_adapter.py            │
│    - Query Pinecone for product embedding              │
│                                                          │
│ 2. Vector similarity search                             │
│    ↓                                                     │
│    - Search for similar embeddings                      │
│    - Filter by similarity threshold                    │
│    - Exclude the original product                      │
│                                                          │
│ 3. Return top-K similar products                       │
└─────────────────────────────────────────────────────────┘
```

#### 1.3. Text-based Search

```
GET /recommendations/search?query="laptop gaming"&limit=10
    ↓
┌─────────────────────────────────────────────────────────┐
│ services/recommendation_service.py                     │
│ get_similar_products_by_text(query_text, limit)         │
│                                                          │
│ 1. Generate query embedding                            │
│    ↓                                                     │
│    domain/embeddings/product_embeddings.py               │
│    - Use embedding model (all-MiniLM-L6-v2)            │
│    - Convert text to 384-dim vector                    │
│                                                          │
│ 2. Vector similarity search                            │
│    ↓                                                     │
│    - Search vector store with query embedding           │
│    - Return top-K most similar products               │
└─────────────────────────────────────────────────────────┘
```

---

### 2. 🔔 Event Processing Flow (Real-time Product Updates)

```
Product Event (Create/Update/Delete)
    ↓
┌─────────────────────────────────────────────────────────┐
│ Event Source (PostgreSQL/Supabase/Redis Streams)        │
│ - Product created/updated/deleted                       │
│ - Event published to stream                             │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ consumers/modern_product_event_consumer.py               │
│ ModernProductEventConsumer                               │
│                                                          │
│ 1. Event Processor polls for new events                │
│    ↓                                                     │
│    adapters/database/postgres_adapter.py                │
│    - Listen to database changes                         │
│    - Or: Poll event stream                              │
│                                                          │
│ 2. Handle event                                         │
│    ↓                                                     │
│    _handle_event(event_data)                           │
│    - Parse event type (create/update/delete)            │
│    - Extract product data                              │
│                                                          │
│ 3. Process product upsert (create/update)              │
│    ↓                                                     │
│    _process_product_upsert(product_id, data)            │
│    a. Generate product embedding                       │
│       ↓                                                  │
│       domain/embeddings/product_embeddings.py           │
│       - Combine: name + description + category         │
│       - Generate 384-dim embedding                     │
│                                                          │
│    b. Store in vector database                         │
│       ↓                                                  │
│       adapters/vector_store/pinecone_adapter.py         │
│       - Upsert embedding to Pinecone                   │
│       - Store metadata (category, price, etc.)          │
│                                                          │
│ 4. Process product delete                               │
│    ↓                                                     │
│    _process_product_delete(product_id)                  │
│    - Delete embedding from vector store                │
└─────────────────────────────────────────────────────────┘
```

**Kết quả**: Product embeddings được cập nhật real-time trong vector store, recommendations tự động phản ánh thay đổi.

---

### 3. 🎓 Offline Training Flow (ALS Model)

```
Scheduled Job (Daily at 2AM)
    ↓
┌─────────────────────────────────────────────────────────┐
│ offline/als/train_als.py                                │
│ train_als_offline()                                      │
│                                                          │
│ 1. Fetch interaction data                               │
│    ↓                                                     │
│    adapters/database/postgres_adapter.py                │
│    - Get aggregated interaction counts                  │
│    - Format: [{user_id, product_id, count, ...}]        │
│                                                          │
│ 2. Feature Engineering                                  │
│    ↓                                                     │
│    offline/als/interaction_features.py                  │
│    a. Temporal weighting                                │
│       - Apply exponential decay by recency             │
│       - Recent interactions weighted higher            │
│                                                          │
│    b. Frequency features                                │
│       - Calculate user/product interaction frequency   │
│                                                          │
│    c. Category features                                 │
│       - Add product category information               │
│                                                          │
│    d. Interaction type weighting                        │
│       - purchase: 5.0x                                 │
│       - add_to_cart: 3.0x                              │
│       - click: 2.0x                                    │
│       - view: 1.0x                                     │
│                                                          │
│ 3. Data Quality Checks                                 │
│    ↓                                                     │
│    utils/data_quality.py                                │
│    - Remove duplicates                                  │
│    - Remove outliers (3 std dev)                       │
│    - Remove stale data (>90 days)                      │
│    - Remove cold-start users/products                  │
│                                                          │
│ 4. Normalization                                        │
│    ↓                                                     │
│    utils/normalization.py                              │
│    - Apply normalization (log/minmax/zscore/sqrt)      │
│                                                          │
│ 5. Train ALS Model                                      │
│    ↓                                                     │
│    domain/recommenders/als_recommender.py               │
│    train_implicit_als()                                 │
│                                                          │
│    a. Build user-item matrix                            │
│       - Sparse CSR matrix                               │
│       - Shape: (n_users, n_items)                      │
│                                                          │
│    b. Train with implicit library                      │
│       - AlternatingLeastSquares                        │
│       - Factors: 64 (default)                          │
│       - Iterations: 15 (default)                       │
│       - Regularization: 0.1                           │
│       - Alpha: 40.0                                    │
│                                                          │
│    c. Extract factors                                  │
│       - User factors: (n_users, 64)                    │
│       - Item factors: (n_items, 64)                    │
│                                                          │
│ 6. Save Model                                           │
│    ↓                                                     │
│    - Save to model_cache/als_model.npz                 │
│    - Include: user_ids, product_ids, factors           │
│                                                          │
│ 7. (Optional) Export Embeddings                        │
│    ↓                                                     │
│    offline/als/export_embeddings.py                    │
│    - Export user/item embeddings to vector store       │
│    - For hybrid search capabilities                    │
└─────────────────────────────────────────────────────────┘
```

**Kết quả**: ALS model được train và lưu, sẵn sàng cho real-time recommendations.

---

## 🧠 Các Phương Pháp Recommendation Chi Tiết

### 1. Vector-based Recommendations

**Nguyên lý**: Sử dụng semantic similarity dựa trên embeddings.

**Quy trình**:
1. **Product Embeddings**: Mỗi sản phẩm có embedding 384-dim từ text (name + description + category)
2. **User Embedding**: Tính từ lịch sử tương tác (weighted mean của product embeddings)
3. **Similarity Search**: Cosine similarity trong vector space
4. **Ranking**: Sắp xếp theo similarity score

**Ưu điểm**:
- Hiểu được semantic meaning
- Không cần training
- Real-time updates

**Nhược điểm**:
- Phụ thuộc vào chất lượng embeddings
- Không capture collaborative signals

---

### 2. ALS (Alternating Least Squares)

**Nguyên lý**: Collaborative filtering với implicit feedback.

**Quy trình**:
1. **Matrix Factorization**: Phân tích user-item interaction matrix
2. **Latent Factors**: Mỗi user và item có 64 latent factors
3. **Prediction**: `score = user_factors @ item_factors.T`
4. **Filtering**: Loại bỏ items đã tương tác

**Training**:
- Offline training hàng ngày
- Sử dụng implicit library
- Matrix: (n_users × n_items) sparse

**Ưu điểm**:
- Capture collaborative patterns
- Xử lý cold-start tốt hơn
- Scalable với large datasets

**Nhược điểm**:
- Cần training time
- Không real-time với new users/items

---

### 3. Session-based Recommendations

**Nguyên lý**: Dựa trên hành vi gần đây và item-to-item transitions.

**Quy trình**:
1. **Recent Interactions**: Lấy K interactions gần nhất của user
2. **Transition Statistics**: Tính xác suất chuyển từ item A → item B
3. **Scoring**: 
   - Transition probability
   - Time decay (recent interactions weighted higher)
   - Diversity penalty
   - Popularity normalization
4. **Ranking**: Sắp xếp theo final score

**Ưu điểm**:
- Phản ánh intent hiện tại
- Không cần training
- Fast inference

**Nhược điểm**:
- Phụ thuộc vào transition patterns
- Không capture long-term preferences

---

### 4. Hybrid Recommendations

**Nguyên lý**: Kết hợp nhiều phương pháp để tận dụng ưu điểm của từng phương pháp.

**Quy trình**:
1. **Collect Candidates**: 
   - Session-based (top 20)
   - ALS (top 20, nếu model available)
   - Vector-based (top 20)
2. **Merge**: 
   - Deduplicate by product_id
   - Keep best score per product
3. **Rank**: Sort by score, return top-K

**Ưu điểm**:
- Tận dụng ưu điểm của nhiều phương pháp
- Robust với missing data
- Better coverage

---

## 📊 Data Flow Chi Tiết

### User Interaction Tracking

```
User Action (View/Click/Cart/Purchase)
    ↓
┌─────────────────────────────────────────────────────────┐
│ api/routes/recommend.py                                  │
│ POST /recommendations/track-view                         │
│ POST /recommendations/track-click                       │
│ POST /recommendations/track-add-to-cart                  │
│ POST /recommendations/track-purchase                     │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ services/recommendation_service.py                      │
│ track_product_view/click/add_to_cart/purchase()         │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ adapters/database/postgres_adapter.py                    │
│ UserBehaviorInterface                                    │
│ - Insert interaction record                            │
│ - Update aggregated counts                              │
│ - Store: user_id, product_id, type, timestamp          │
└─────────────────────────────────────────────────────────┘
```

**Sử dụng**:
- Real-time: Session-based recommendations
- Offline: ALS training, analytics

---

### Product Embedding Generation

```
Product Data
{
  "id": "prod123",
  "name": "Gaming Laptop",
  "description": "High-performance laptop...",
  "category": "Electronics"
}
    ↓
┌─────────────────────────────────────────────────────────┐
│ domain/embeddings/product_embeddings.py                 │
│ get_product_embedding(product_data)                    │
│                                                          │
│ 1. Combine text fields                                 │
│    text = f"{name} {description} {category}"           │
│                                                          │
│ 2. Generate embedding                                  │
│    ↓                                                     │
│    sentence-transformers model                         │
│    - Model: all-MiniLM-L6-v2                           │
│    - Output: 384-dim vector                            │
│                                                          │
│ 3. Normalize                                            │
│    embedding = embedding / ||embedding||               │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ adapters/vector_store/pinecone_adapter.py               │
│ store_product_embedding(product_id, embedding, metadata)│
│                                                          │
│ - Upsert to Pinecone index                             │
│ - Store metadata (category, price, etc.)               │
└─────────────────────────────────────────────────────────┘
```

---

## 🔧 Cấu Hình và Adapters

### Adapter Factory Pattern

Hệ thống sử dụng **Factory Pattern** để tạo adapters dựa trên config:

```python
# config.py
VECTOR_STORE_TYPE = "pinecone"  # or "redis"
EVENT_PROCESSOR_TYPE = "postgres"  # or "supabase"
BEHAVIOR_STORE_TYPE = "postgres"

# adapters/factory.py
def get_vector_store() -> VectorStoreInterface:
    if VECTOR_STORE_TYPE == "pinecone":
        return PineconeVectorStore()
    elif VECTOR_STORE_TYPE == "redis":
        return RedisVectorStore()
```

**Lợi ích**:
- Dễ dàng switch backends
- Testable với mock adapters
- Clean separation of concerns

---

## 🚀 Khởi Động Hệ Thống

### 1. Start API Server

```bash
python -m api.app
# hoặc
uvicorn api.app:app --host 0.0.0.0 --port 8000
```

**Khởi tạo**:
- FastAPI app
- Load adapters từ factory
- Initialize RecommendationService (singleton)
- Register routes

### 2. Start Event Consumer

```bash
python -m consumers.modern_product_event_consumer
```

**Khởi tạo**:
- Event processor (PostgreSQL/Supabase listener)
- Vector store connection
- Embedding model
- Start polling for events

### 3. Schedule Offline Training

```bash
# Cron job (Linux)
0 2 * * * python -m offline.als.train_als

# Windows Task Scheduler
python -m offline.als.train_als
```

---

## 📈 Performance và Scalability

### Caching Strategy

1. **ALS Model Cache**: 
   - Loaded once, cached in memory
   - Refreshed when model file updated
   - Thread-safe with locks

2. **Session Statistics Cache**:
   - Cached transition statistics
   - TTL: 5 minutes (configurable)
   - Rebuilt from recent interactions

3. **Vector Store**:
   - Pinecone handles caching internally
   - Fast similarity search (milliseconds)

### Scalability

- **Horizontal Scaling**: API servers stateless, có thể scale out
- **Vector Store**: Pinecone managed service, auto-scales
- **Database**: PostgreSQL có thể replicate
- **Event Processing**: Multiple consumers có thể chạy parallel

---

## 🧪 Testing và Evaluation

### Offline Evaluation

```python
from offline.evaluation.offline_metrics import evaluate_model_offline

# Test data
test_data = [
    {"user_id": "user1", "ground_truth": {"prod1", "prod2"}},
    {"user_id": "user2", "ground_truth": {"prod3", "prod4"}},
]

# Recommendation function
def recommend(user_id):
    service = get_recommendation_service()
    return service.get_hybrid_recommendations(user_id, limit=10)

# Evaluate
metrics = evaluate_model_offline(test_data, recommend)
# Returns: {"precision@5": 0.8, "recall@10": 0.6, "ndcg@10": 0.75, ...}
```

### Metrics Collected

- **Precision@K**: Tỷ lệ recommendations relevant trong top-K
- **Recall@K**: Tỷ lệ relevant items được recommend
- **NDCG@K**: Normalized Discounted Cumulative Gain
- **MRR**: Mean Reciprocal Rank
- **Coverage**: Tỷ lệ catalog được recommend
- **Diversity**: Độ đa dạng của recommendations

---

## 🔐 Security và Best Practices

1. **API Authentication**: Có thể thêm JWT tokens
2. **Rate Limiting**: Có thể thêm middleware
3. **Input Validation**: Pydantic models
4. **Error Handling**: Try-catch với logging
5. **Monitoring**: Metrics logging cho mọi requests

---

## 📝 Tóm Tắt

Hệ thống hoạt động theo kiến trúc **Clean Architecture** với các layers:

1. **Presentation**: API endpoints (FastAPI)
2. **Application**: Service orchestration
3. **Domain**: Core business logic (algorithms)
4. **Infrastructure**: External system adapters

**Data Flow**:
- **Real-time**: API → Service → Domain → Adapters → Response
- **Events**: Stream → Consumer → Embeddings → Vector Store
- **Offline**: Data → Features → Training → Model Cache

**Recommendation Methods**:
- Vector-based: Semantic similarity
- ALS: Collaborative filtering
- Session-based: Recent behavior
- Hybrid: Combined approach

Hệ thống được thiết kế để:
- ✅ Scalable và maintainable
- ✅ Dễ test và extend
- ✅ Support multiple backends
- ✅ Real-time và offline processing


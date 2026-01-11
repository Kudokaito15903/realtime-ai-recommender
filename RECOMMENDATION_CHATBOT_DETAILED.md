# 📘 Hệ Thống Recommendation và Chatbot - Tài Liệu Chi Tiết

## 📋 Mục Lục

1. [Tổng Quan](#1-tổng-quan)
2. [Hệ Thống Recommendation Chi Tiết](#2-hệ-thống-recommendation-chi-tiết)
3. [Hệ Thống Chatbot Chi Tiết](#3-hệ-thống-chatbot-chi-tiết)
4. [Tích Hợp Recommendation và Chatbot](#4-tích-hợp-recommendation-và-chatbot)
5. [API Endpoints](#5-api-endpoints)
6. [Implementation Guide](#6-implementation-guide)

---

## 1. Tổng Quan

### 1.1. Kiến Trúc Hệ Thống

```
┌─────────────────────────────────────────────────────────────┐
│                    E-COMMERCE PLATFORM                       │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┴───────────────────┐
        │                                       │
        ▼                                       ▼
┌────────────────────┐              ┌────────────────────┐
│  RECOMMENDATION    │              │     CHATBOT        │
│     SYSTEM         │◄────────────►│     SYSTEM         │
│                    │   Shared     │                    │
│  - ALS             │   Vector     │  - RAG             │
│  - Vector Search   │   Store      │  - Intent Detection│
│  - Session-based   │   (Pinecone) │  - GPT-4o-mini     │
│  - Hybrid          │              │  - 5 Intent Types  │
└────────────────────┘              └────────────────────┘
        │                                       │
        └───────────────────┬───────────────────┘
                            ▼
                ┌───────────────────────┐
                │   Shared Backend      │
                │  - Product Store      │
                │  - Vector Store       │
                │  - User Behavior      │
                │  - Content Store      │
                └───────────────────────┘
```

### 1.2. So Sánh 2 Hệ Thống

| Aspect       | Recommendation                     | Chatbot                  |
| ------------ | ---------------------------------- | ------------------------ |
| **Mục đích** | Tự động gợi ý sản phẩm             | Trả lời câu hỏi tự nhiên |
| **Input**    | user_id, product_id                | Natural language query   |
| **Output**   | List products + variants           | Natural language answer  |
| **ML/AI**    | ALS + Vector similarity            | RAG + GPT-4o-mini        |
| **Training** | Offline ALS (daily)                | No training (zero-shot)  |
| **Latency**  | 50-200ms                           | 500-2000ms               |
| **Use Case** | Product discovery, personalization | Customer support, Q&A    |

---

## 2. Hệ Thống Recommendation Chi Tiết

### 2.1. Kiến Trúc 2-Layer

#### Layer 1: Candidate Generation (PRODUCT Level)

**Mục đích**: Tìm top N products phù hợp với user

```
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│   ALS    │  │  Vector  │  │ Session  │  │  Hybrid  │
│  (CF)    │  │(Semantic)│  │ (Recent) │  │(Combined)│
└────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘
     │             │             │             │
     └─────────────┴─────────────┴─────────────┘
                        │
                        ▼
              Top 100 Product IDs
```

**Lý do dùng PRODUCT level**:

- ✅ Giảm sparsity (users tương tác với products, không phải từng variant)
- ✅ Model học tốt hơn (nhiều data points)
- ✅ Performance cao hơn
- ✅ Dễ scale

#### Layer 2: Variant Selection (VARIANT Level)

**Mục đích**: Chọn variant tốt nhất cho mỗi product

**Scoring Formula**:

```python
variant_score = (
    0.20 * color_match_score +      # Màu user thích
    0.20 * storage_match_score +    # Dung lượng user chọn
    0.30 * price_similarity_score + # Giá trong range user mua
    0.10 * stock_score +            # Còn hàng
    0.20 * popularity_score         # Variant phổ biến
)
```

**User Preferences**:

- Học từ lịch sử purchases (strong signal)
- Học từ cart adds (medium signal)
- Học từ views (weak signal)

### 2.2. ALS (Collaborative Filtering)

#### Training Pipeline

```
1. DATA COLLECTION
   ↓
   Get interactions (user_id × product_id × count)

2. FEATURE ENGINEERING
   ↓
   a) Temporal Weighting
      weight = 2^(-age_days / half_life)
      Recent interactions = higher weight

   b) Interaction Type Weighting
      purchase: 5.0x
      add_to_cart: 3.0x
      click: 2.0x
      view: 1.0x

   c) Category Features
      Add product category info

3. DATA QUALITY
   ↓
   a) Remove Duplicates
   b) Remove Outliers (count > mean + 3*std)
   c) Remove Stale (> 90 days)
   d) Remove Cold-start (< 2 interactions)

4. NORMALIZATION
   ↓
   log / minmax / zscore / sqrt
   Default: log(1 + x)

5. MATRIX BUILDING
   ↓
   Sparse CSR matrix (n_users × n_items)

6. TRAINING
   ↓
   AlternatingLeastSquares
   - Factors: 64
   - Iterations: 15
   - Regularization: 0.1
   - Alpha: 40.0

7. MODEL SAVE
   ↓
   Save to model_cache/als_model.npz
```

#### Hyperparameters

| Parameter          | Default | Range    | Impact               |
| ------------------ | ------- | -------- | -------------------- |
| **factors**        | 64      | 32-128   | Latent dimensions    |
| **iterations**     | 15      | 10-20    | Convergence quality  |
| **regularization** | 0.1     | 0.01-0.5 | Overfitting control  |
| **alpha**          | 40.0    | 1-100    | Confidence weighting |

#### Data Quality Configuration

```env
ALS_DATA_QUALITY_ENABLED=True
ALS_REMOVE_DUPLICATES=True
ALS_REMOVE_OUTLIERS=True
ALS_OUTLIER_THRESHOLD_STD=3.0
ALS_REMOVE_STALE=True
ALS_MAX_AGE_DAYS=90
ALS_REMOVE_COLD_START=True
ALS_MIN_USER_INTERACTIONS=2
ALS_MIN_PRODUCT_INTERACTIONS=2
```

#### Normalization Methods

**Log** (Recommended):

```python
log(1 + count)
```

- Best for: Power users
- Effect: Giảm ảnh hưởng outliers

**MinMax**:

```python
(count - min) / (max - min)
```

- Best for: Scale to [0, 1]

**Z-Score**:

```python
(count - mean) / std
```

- Best for: Standardize distribution

### 2.3. Vector Similarity

#### Embedding Generation

**Model**: SentenceTransformer `all-MiniLM-L6-v2`

- Dimension: 384
- Language: Multilingual (Vietnamese supported)
- Speed: ~10-20ms/product

**Text Combination**:

```python
text = f"{name} {description} {category} {attributes}"
```

**Example**:

```
"iPhone 15 Pro High-performance smartphone Electronics brand:Apple storage:256GB"
→ [384-dim vector] → Pinecone
```

#### Query Types

**1. Product-to-Product** (Similar):

```http
GET /recommendations/{product_id}/similar?limit=6
```

**2. Text-to-Product** (Search):

```http
GET /recommendations/search?query=laptop gaming&limit=10
```

**3. User-to-Product** (Personalized):

```http
GET /recommendations/personalized?method=vector
Header: user-id: user123
```

User embedding = Weighted average of viewed products:

```python
user_emb = Σ(weight_i * product_emb_i) / Σ(weight_i)
```

### 2.4. Session-based

#### Transition Statistics

**Build Transitions**:

```
Session: [A, B, C, D]

Transitions:
A → B (count++)
B → C (count++)
C → D (count++)

Probability:
P(B|A) = count(A→B) / count(A→*)
```

#### Scoring

```python
score = (
    0.40 * transition_prob +
    0.30 * time_decay +
    0.20 * diversity_bonus +
    0.10 * popularity
)
```

#### Session Definition

**Gap**: 30 minutes (configurable)

```env
SESSION_GAP_SECONDS=1800
```

### 2.5. Hybrid

**Strategy**:

```
Collect candidates:
├── Session-based (top 20)
├── ALS (top 20)
└── Vector (top 20)

Merge & Deduplicate:
├── Keep best score per product
└── Sort by final score

Return: Top 10
```

### 2.6. Tracking Rules

#### View → product_id

```javascript
// Trang chủ, danh mục, product detail
POST /recommendations/track-view?product_id=IP15-PRO
Header: user-id: user123
// variant_id = null (không cần)
```

#### Cart/Purchase → variant_id REQUIRED

```javascript
// Add to cart
POST /recommendations/track-add-to-cart
  ?product_id=IP15-PRO&variant_id=IP15P-256-BL
Header: user-id: user123

// Purchase
POST /recommendations/track-purchase
  ?product_id=IP15-PRO&variant_id=IP15P-256-BL
Header: user-id: user123
```

---

## 3. Hệ Thống Chatbot Chi Tiết

### 3.1. Kiến Trúc RAG

```
User Query
    ↓
┌─────────────────┐
│Intent Detection │ ← Rule-based keywords
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  RAG Pipeline   │
└─────────────────┘
    │
    ├─► RETRIEVAL (R)
    │   └─► Vector Search (Pinecone)
    │       Top K similar docs
    │
    ├─► AUGMENTATION (A)
    │   ├─► Enrich product data
    │   ├─► Get fresh prices/stock
    │   └─► Format for LLM
    │
    └─► GENERATION (G)
        └─► OpenAI GPT-4o-mini
            Natural language answer
```

### 3.2. 5 Intent Types

| Intent           | Keywords                            | Data Source            | Output             |
| ---------------- | ----------------------------------- | ---------------------- | ------------------ |
| **product_info** | `thông tin`, `giá`, `spec`          | Product + Vector Store | Product details    |
| **compare**      | `so sánh`, `khác nhau`, `nên mua`   | Product + Vector Store | Comparison table   |
| **policy**       | `chính sách`, `đổi trả`, `bảo hành` | Content + Vector Store | Policy explanation |
| **cskh**         | `hỗ trợ`, `tư vấn`, `liên hệ`       | Content Store (FAQ)    | Support guidance   |
| **realtime**     | `còn hàng`, `tồn kho`, `giá mới`    | Product Store (fresh)  | Real-time status   |

### 3.3. Intent Detection

```python
def _detect_intent(query: str) -> str:
    q = query.lower()

    # Priority order
    if any(kw in q for kw in ["so sánh", "khác nhau"]):
        return "compare"
    elif any(kw in q for kw in ["còn hàng", "tồn kho"]):
        return "realtime"
    elif any(kw in q for kw in ["chính sách", "đổi trả"]):
        return "policy"
    elif any(kw in q for kw in ["hỗ trợ", "tư vấn"]):
        return "cskh"
    else:
        return "product_info"  # Default
```

### 3.4. Chi Tiết Intent Handlers

#### 3.4.1. Product Information

**Flow**:

```
Query: "Thông tin iPhone 15 Pro"
    ↓
1. Vector Search
   ├─► Embed query
   ├─► Search Pinecone
   └─► Top 3 products
    ↓
2. Enrich Data
   ├─► Get from Product Store
   ├─► Extract: name, price, variants
   └─► Get specifications
    ↓
3. Build Prompt
   ├─► System: "Bạn là trợ lý mua sắm"
   ├─► Context: Formatted product info
   └─► User query
    ↓
4. Generate (GPT-4o-mini)
   └─► Natural Vietnamese answer
```

**Prompt Template**:

```
System: Bạn là trợ lý mua sắm thông minh.

Context:
[Product 1]
Name: iPhone 15 Pro
Price: 28,990,000 - 41,990,000 VNĐ
Variants:
- 128GB Titan Tự Nhiên: 28,990,000 VNĐ
- 256GB Titan Xanh: 33,990,000 VNĐ
Specs:
- Chip: A17 Pro
- Camera: 48MP
- Display: 6.1" Super Retina XDR

User: Thông tin iPhone 15 Pro
```

#### 3.4.2. Product Comparison

**Flow**:

```
Query: "So sánh iPhone 15 và Samsung S24"
    ↓
1. Retrieve Products
   ├─► Search "iPhone 15"
   ├─► Search "Samsung S24"
   └─► Top 5 candidates total
    ↓
2. Extract Comparison Data
   For each product:
   ├─► Price (min/max)
   ├─► Rating & sold count
   ├─► Specifications
   └─► Description
    ↓
3. Build Comparison Table
   ├─► Format side-by-side
   └─► Highlight differences
    ↓
4. Generate Comparison
   └─► GPT analyzes & suggests
```

**Prompt Template**:

```
System: So sánh các sản phẩm một cách khách quan.

Context:
[iPhone 15]
- Giá: 20,990,000 VNĐ
- Chip: A15 Bionic
- Camera: 48MP
- Display: 6.1"

[Samsung S24]
- Giá: 19,990,000 VNĐ
- Chip: Snapdragon 8 Gen 3
- Camera: 50MP
- Display: 6.2"

User: So sánh iPhone 15 và Samsung S24
```

#### 3.4.3. Policy Information

**Flow**:

```
Query: "Chính sách đổi trả"
    ↓
1. Search Policy Content
   ├─► Vector search
   ├─► Filter category="policy"
   └─► Get relevant policies
    ↓
2. Fallback Content Store
   If no vector results:
   └─► Query Content Store directly
    ↓
3. Build Policy Prompt
   ├─► Include policy titles
   └─► Include policy content
    ↓
4. Generate Explanation
   └─► GPT explains clearly
```

#### 3.4.4. Customer Service (CSKH)

**Flow**:

```
Query: "Tôi cần hỗ trợ về đơn hàng"
    ↓
1. Search CSKH Content
   ├─► Vector search FAQ
   ├─► Filter category="cskh"
   └─► Get help articles
    ↓
2. Build Response
   ├─► Include FAQ
   ├─► Step-by-step guidance
   └─► Contact info if needed
    ↓
3. Generate Friendly Response
   └─► GPT with friendly tone
```

#### 3.4.5. Realtime Data

**Flow**:

```
Query: "iPhone 15 còn hàng không?"
    ↓
1. Find Product
   ├─► Vector search
   └─► Get product IDs
    ↓
2. Fetch Fresh Data
   For each product:
   ├─► Query Product Store (fresh)
   ├─► Current price
   ├─► Current rating
   └─► Variants with stock status
    ↓
3. Build Realtime Info
   ├─► Format stock per variant
   ├─► Show current prices
   └─► Last updated time
    ↓
4. Generate Response
   └─► GPT with realtime data
```

### 3.5. Content Management (Admin)

**Upload Content Flow**:

```
Admin uploads content
    ↓
┌─────────────────┐
│ ContentService  │
│ - Generate ID   │
│ - Store to DB   │
│ - Publish event │
└────────┬────────┘
         ↓
┌─────────────────┐
│ Event Processor │
│ - Poll events   │
└────────┬────────┘
         ↓
┌─────────────────┐
│ Event Handler   │
│ - Generate emb  │
│ - Upsert vector │
│ with metadata:  │
│   type: content │
│   category: ... │
└─────────────────┘
```

**Content Types**:

- `policy`: Chính sách
- `faq`: FAQ
- `cskh`: Support docs
- `tutorial`: Hướng dẫn

---

## 4. Tích Hợp Recommendation và Chatbot

### 4.1. Shared Infrastructure

```
┌─────────────────────────────────────┐
│       Pinecone Vector Store         │
│                                     │
│  Namespaces:                        │
│  ├─► products (384-dim)             │
│  │   Used by: Both systems         │
│  │                                  │
│  └─► content (384-dim)              │
│      Used by: Chatbot only         │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│     Supabase (PostgreSQL)           │
│                                     │
│  Tables:                            │
│  ├─► products                       │
│  ├─► product_events                 │
│  ├─► user_views (behavior)          │
│  └─► content                        │
└─────────────────────────────────────┘
```

### 4.2. Integration Scenarios

#### Scenario 1: Chatbot Triggers Recommendation

```
User: "Gợi ý laptop gaming cho tôi"
    ↓
Chatbot:
├─► Detect intent: product_info
├─► Get user preferences from history
├─► Call Recommendation API
│   GET /recommendations/personalized
│   ?category=laptop&limit=5
└─► Format response with GPT
    "Dựa trên lịch sử của bạn, tôi gợi ý:"
```

#### Scenario 2: Recommendation with Chat Context

```
User viewing product page
    ↓
GET /recommendations/{product_id}/similar
    ↓
If user has chat history:
├─► Use chat context for personalization
├─► Extract preferences from chat
└─► Boost relevant products
```

#### Scenario 3: Chatbot Answers About Recommendations

```
User: "Tại sao bạn gợi ý sản phẩm này?"
    ↓
Chatbot:
├─► Get recommendation metadata
├─► Extract: method, score, reason
└─► Explain with GPT
    "Tôi gợi ý sản phẩm này vì bạn đã xem..."
```

---

## 5. API Endpoints

### 5.1. Recommendation Endpoints

#### Personalized Recommendations

```http
GET /recommendations/personalized
  ?limit=10
  &method=hybrid|als|vector|session
  &recent_k=5
Header: user-id: user123

Response:
{
  "recommendations": [
    {
      "product_id": "IP15-PRO",
      "score": 0.95,
      "recommendation_type": "hybrid",
      "recommended_variant": {
        "sku": "IP15P-256-BL",
        "variantName": "256GB Blue",
        "price": 31990000
      }
    }
  ]
}
```

#### Similar Products

```http
GET /recommendations/{product_id}/similar
  ?limit=6
  &threshold=0.75

Response:
{
  "recommendations": [
    {
      "product_id": "IP15",
      "similarity_score": 0.89,
      "name": "iPhone 15"
    }
  ]
}
```

#### Track Interactions

```http
POST /recommendations/track-view
  ?product_id=IP15-PRO
Header: user-id: user123

POST /recommendations/track-add-to-cart
  ?product_id=IP15-PRO&variant_id=IP15P-256-BL
Header: user-id: user123

POST /recommendations/track-purchase
  ?product_id=IP15-PRO&variant_id=IP15P-256-BL
Header: user-id: user123
```

### 5.2. Chatbot Endpoints

#### Chat

```http
POST /chatbot/chat
Content-Type: application/json

{
  "query": "So sánh iPhone 15 và Samsung S24",
  "top_k": 5,
  "user_id": "user123"
}

Response:
{
  "answer": "Dựa trên so sánh...",
  "contexts": [
    {
      "id": "prod_123",
      "type": "product",
      "score": 0.95,
      "data": {...}
    }
  ],
  "intent": "compare",
  "capabilities": {
    "product_info": "Trả lời thông tin sản phẩm",
    "compare": "So sánh sản phẩm",
    "policy": "Thông tin chính sách",
    "cskh": "Hỗ trợ khách hàng",
    "realtime": "Dữ liệu realtime"
  }
}
```

#### Content Management (Admin)

```http
POST /content
Content-Type: application/json

{
  "title": "Chính sách đổi trả",
  "content": "Khách hàng được đổi trả trong 30 ngày...",
  "category": "policy",
  "tags": ["return", "refund"]
}

GET /content
  ?category=policy
  &limit=10
  &offset=0

GET /content/search
  ?q=đổi trả
  &category=policy
```

---

## 6. Implementation Guide

### 6.1. Setup Recommendation System

**1. Environment Variables**:

```env
# ALS Configuration
ALS_FACTORS=64
ALS_ITERATIONS=15
ALS_REGULARIZATION=0.1
ALS_ALPHA=40.0
ALS_NORMALIZATION_METHOD=log

# Data Quality
ALS_DATA_QUALITY_ENABLED=True
ALS_REMOVE_OUTLIERS=True
ALS_MAX_AGE_DAYS=90

# Session
SESSION_GAP_SECONDS=1800
SESSION_RECENT_K=10
```

**2. Train ALS Model**:

```bash
# Manual training
python -m offline.als.train_als

# Schedule Daily (Linux cron)
0 2 * * * python -m offline.als.train_als
```

**3. Start API**:

```bash
python -m api.app
```

### 6.2. Setup Chatbot System

**1. Environment Variables**:

```env
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# Content Store
CONTENT_STORE_TYPE=supabase
```

**2. Upload Sample Content**:

```bash
python -m scripts.upload_sample_content
```

**3. Test Chatbot**:

```bash
curl -X POST http://localhost:8000/chatbot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "iPhone 15 giá bao nhiêu?",
    "user_id": "test_user"
  }'
```

### 6.3. Frontend Integration

**Recommendation Widget**:

```javascript
// Personalized recommendations
async function loadRecommendations() {
  const res = await fetch(
    "/recommendations/personalized?method=hybrid&limit=10",
    {
      headers: { "user-id": getCurrentUserId() },
    }
  );
  const data = await res.json();
  renderProducts(data.recommendations);
}

// Similar products
async function loadSimilarProducts(productId) {
  const res = await fetch(`/recommendations/${productId}/similar?limit=6`);
  const data = await res.json();
  renderProducts(data.recommendations);
}

// Track view
async function trackProductView(productId) {
  await fetch(`/recommendations/track-view?product_id=${productId}`, {
    method: "POST",
    headers: { "user-id": getCurrentUserId() },
  });
}
```

**Chatbot Widget**:

```javascript
// Chat interface
async function sendMessage(query) {
  const res = await fetch("/chatbot/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query: query,
      user_id: getCurrentUserId(),
      top_k: 5,
    }),
  });
  const data = await res.json();
  displayAnswer(data.answer);
  displayContexts(data.contexts);
}
```

---

## Tóm Tắt

### Recommendation System

✅ 2-layer architecture (Product + Variant)  
✅ 4 phương pháp (ALS, Vector, Session, Hybrid)  
✅ Advanced ALS features (data quality, normalization, temporal weighting)  
✅ Variant selection với 5 scoring factors  
✅ Offline training + real-time serving

### Chatbot System

✅ RAG architecture (Retrieval + Augmentation + Generation)  
✅ 5 intent types (product_info, compare, policy, cskh, realtime)  
✅ GPT-4o-mini for Vietnamese generation  
✅ Shared vector store với recommendation  
✅ Admin content management

### Integration

✅ Shared Pinecone vector store  
✅ Shared Supabase backend  
✅ Cross-system data flow  
✅ Unified API layer

---

**Ngày tạo**: 2026-01-11  
**Phiên bản**: 1.0

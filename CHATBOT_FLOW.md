# Luồng Hoạt Động Chatbot AI

## Tổng Quan

Chatbot sử dụng kiến trúc RAG (Retrieval Augmented Generation) với khả năng phân loại intent tự động và xử lý 5 loại câu hỏi chính:
- **Thông tin sản phẩm**: Trả lời chi tiết về sản phẩm
- **So sánh sản phẩm**: So sánh nhiều sản phẩm với nhau
- **Chính sách**: Thông tin về chính sách đổi trả, bảo hành, vận chuyển
- **CSKH tự động**: Chăm sóc khách hàng tự động
- **Dữ liệu realtime**: Tồn kho, giá cả, đánh giá cập nhật

---

## 1. Luồng Tổng Quan

```
┌─────────────┐
│   User      │
│  (Frontend) │
└──────┬──────┘
       │ POST /chatbot/chat
       │ {query: "iPhone 15 giá bao nhiêu?"}
       ▼
┌─────────────────────────────────────┐
│      FastAPI Router                  │
│      /api/routes/chatbot.py         │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│    ChatbotService                    │
│    services/chatbot_service.py       │
│                                      │
│  1. _detect_intent(query)           │
│  2. Route to handler                │
│  3. Retrieve data                   │
│  4. Generate response                │
└──────────────┬──────────────────────┘
               │
       ┌───────┴───────┐
       │               │
       ▼               ▼
┌─────────────┐  ┌─────────────┐
│ Vector Store│  │Product Store│
│ (Pinecone)  │  │ (Supabase)  │
└─────────────┘  └─────────────┘
       │               │
       └───────┬───────┘
               ▼
┌─────────────────────────────────────┐
│    OpenAI API                        │
│    (GPT-4o-mini)                     │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│    Response                         │
│    {                                │
│      answer: "...",                 │
│      contexts: [...],              │
│      intent: "product_info"         │
│    }                                │
└─────────────────────────────────────┘
```

---

## 2. Luồng Chi Tiết: Intent Detection & Routing

```
User Query: "So sánh iPhone 15 và Samsung S24"
              │
              ▼
┌─────────────────────────────────────────┐
│  _detect_intent(query)                  │
│                                          │
│  Keywords Analysis:                     │
│  - "so sánh" → compare                  │
│  - "thông tin" → product_info          │
│  - "chính sách" → policy               │
│  - "hỗ trợ" → cskh                     │
│  - "còn hàng" → realtime               │
└──────────────┬──────────────────────────┘
               │
               ▼
        Intent: "compare"
               │
               ▼
┌─────────────────────────────────────────┐
│  compare_products(query, top_k=5)        │
│                                          │
│  1. retrieve(query) - Vector search     │
│  2. Get product details                 │
│  3. Extract comparison data             │
│  4. Build comparison prompt             │
│  5. Call OpenAI                         │
└──────────────┬──────────────────────────┘
               │
               ▼
         Response
```

---

## 3. Luồng Chi Tiết: Product Information

```
User: "Thông tin iPhone 15 Pro"
       │
       ▼
┌─────────────────────────────────────────┐
│  get_product_info(query, top_k=3)       │
│                                          │
│  Step 1: Vector Search                  │
│  ├── Embed query: "iPhone 15 Pro"       │
│  ├── Search Pinecone                    │
│  └── Get top 3 similar products         │
│                                          │
│  Step 2: Enrich Product Data            │
│  ├── For each product:                  │
│  │   ├── Get from Product Store         │
│  │   ├── Extract: name, price, rating   │
│  │   ├── Get variants (color, storage) │
│  │   └── Get specifications            │
│  └── Build product_details[]            │
│                                          │
│  Step 3: Build Prompt                    │
│  ├── Format product info                 │
│  ├── Include variants & specs           │
│  └── Add user query                     │
│                                          │
│  Step 4: Generate Response              │
│  └── Call OpenAI API                    │
└──────────────┬──────────────────────────┘
               │
               ▼
    Detailed Product Info Response
```

---

## 4. Luồng Chi Tiết: Product Comparison

```
User: "So sánh iPhone 15 và Samsung S24"
       │
       ▼
┌─────────────────────────────────────────┐
│  compare_products(query, top_k=5)       │
│                                          │
│  Step 1: Retrieve Products               │
│  ├── Vector search for "iPhone 15"      │
│  ├── Vector search for "Samsung S24"    │
│  └── Get top 5 candidates               │
│                                          │
│  Step 2: Extract Comparison Data        │
│  For each product:                      │
│  ├── Price (min/max if variants)        │
│  ├── Rating & sold count                │
│  ├── Brand & category                    │
│  ├── Key specifications                  │
│  └── Description                         │
│                                          │
│  Step 3: Build Comparison Table         │
│  ├── Format side-by-side                │
│  ├── Highlight differences              │
│  └── Prepare for LLM                    │
│                                          │
│  Step 4: Generate Comparison            │
│  └── OpenAI analyzes & compares         │
└──────────────┬──────────────────────────┘
               │
               ▼
    Comparison Response with Recommendations
```

---

## 5. Luồng Chi Tiết: Policy Information

```
User: "Chính sách đổi trả hàng"
       │
       ▼
┌─────────────────────────────────────────┐
│  get_policy_info(query, top_k=5)        │
│                                          │
│  Step 1: Search Policy Content          │
│  ├── Vector search (content type)        │
│  ├── Filter by category="policy"        │
│  └── Get relevant policies               │
│                                          │
│  Step 2: Fallback to Content Store       │
│  ├── If no vector results:              │
│  │   ├── Query Content Store            │
│  │   └── Filter category="policy"       │
│  └── Get policy documents                │
│                                          │
│  Step 3: Build Policy Prompt            │
│  ├── Include policy titles              │
│  ├── Include policy content              │
│  └── Add user question                  │
│                                          │
│  Step 4: Generate Response              │
│  └── OpenAI explains policy clearly      │
└──────────────┬──────────────────────────┘
               │
               ▼
    Clear Policy Explanation
```

---

## 6. Luồng Chi Tiết: CSKH (Customer Service)

```
User: "Tôi cần hỗ trợ về đơn hàng"
       │
       ▼
┌─────────────────────────────────────────┐
│  handle_cskh(query)                     │
│                                          │
│  Step 1: Search CSKH Content            │
│  ├── Vector search for FAQ/help          │
│  ├── Filter category="cskh" or "faq"   │
│  └── Get relevant help articles         │
│                                          │
│  Step 2: Build Helpful Response         │
│  ├── Include FAQ content                │
│  ├── Provide step-by-step guidance      │
│  └── Add contact info if needed         │
│                                          │
│  Step 3: Generate Friendly Response     │
│  └── OpenAI with friendly tone           │
└──────────────┬──────────────────────────┘
               │
               ▼
    Helpful CSKH Response
```

---

## 7. Luồng Chi Tiết: Realtime Data

```
User: "iPhone 15 còn hàng không?"
       │
       ▼
┌─────────────────────────────────────────┐
│  get_realtime_data(query, top_k=3)     │
│                                          │
│  Step 1: Find Product                   │
│  ├── Vector search for "iPhone 15"      │
│  └── Get product IDs                    │
│                                          │
│  Step 2: Fetch Fresh Data               │
│  For each product:                      │
│  ├── Query Product Store (fresh)         │
│  ├── Get current price                  │
│  ├── Get current rating                 │
│  ├── Get sold count                     │
│  └── Get variants with stock status     │
│                                          │
│  Step 3: Build Realtime Info            │
│  ├── Format stock status per variant    │
│  ├── Show current prices                │
│  └── Include last updated time          │
│                                          │
│  Step 4: Generate Response              │
│  └── OpenAI with realtime data           │
└──────────────┬──────────────────────────┘
               │
               ▼
    Realtime Stock & Price Info
```

---

## 8. Luồng Quản Lý Nội Dung (Admin)

```
┌─────────────┐
│   Admin     │
│  (CMS UI)   │
└──────┬──────┘
       │
       │ POST /content
       │ {title, content, category, tags}
       ▼
┌─────────────────────────────────────┐
│  ContentService                     │
│  services/content_service.py        │
│                                      │
│  1. Generate content_id (UUID)       │
│  2. Store to Content Store          │
│  3. Publish event                    │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Event Processor                     │
│  (Postgres/Kafka)                    │
│                                      │
│  Event: {                            │
│    event_type: "create",            │
│    content_id: "...",               │
│    data: {...}                      │
│  }                                   │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  ContentEventHandler                 │
│  services/content_event_handler.py   │
│                                      │
│  1. Receive event                    │
│  2. Fetch content from store          │
│  3. Generate embedding                │
│     (title + content)                 │
│  4. Upsert to Vector Store           │
│     with metadata: {                 │
│       type: "content",               │
│       category: "policy",            │
│       tags: [...]                    │
│     }                                │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Vector Store (Pinecone)             │
│                                      │
│  Content now searchable by chatbot   │
└─────────────────────────────────────┘
```

---

## 9. Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         CHATBOT DATA FLOW                        │
└─────────────────────────────────────────────────────────────────┘

User Query
    │
    ▼
┌─────────────────┐
│ Intent Detection│
└────────┬────────┘
    │
    ├──► product_info ──► Product Store ──► Vector Store
    │
    ├──► compare ───────► Product Store ──► Vector Store
    │
    ├──► policy ────────► Content Store ─► Vector Store
    │
    ├──► cskh ──────────► Content Store ─► Vector Store
    │
    └──► realtime ──────► Product Store ─► User Behavior
                              │
                              ▼
                    ┌─────────────────┐
                    │  Fresh Data      │
                    │  (Stock, Price)  │
                    └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  OpenAI API     │
                    │  (GPT-4o-mini)  │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  Response       │
                    │  + Contexts     │
                    └─────────────────┘
```

---

## 10. API Endpoints

### Chatbot Endpoints

```
POST /chatbot/chat
Request:
{
  "query": "iPhone 15 giá bao nhiêu?",
  "top_k": 5,
  "user_id": "user123" (optional)
}

Response:
{
  "answer": "iPhone 15 có giá từ 20.990.000 VNĐ...",
  "contexts": [
    {
      "id": "product_123",
      "type": "product",
      "score": 0.95,
      "data": {...}
    }
  ],
  "intent": "product_info",
  "capabilities": {
    "product_info": "Trả lời về thông tin sản phẩm",
    "compare": "So sánh sản phẩm",
    "policy": "Thông tin chính sách",
    "cskh": "Chăm sóc khách hàng tự động",
    "realtime": "Dữ liệu realtime (tồn kho, giá, đánh giá)"
  }
}
```

### Content Management Endpoints (Admin)

```
POST /content
Create new content

GET /content?category=policy&limit=10&offset=0
List content with filtering

GET /content/search?q=đổi trả&category=policy
Semantic search for content

GET /content/{content_id}
Get specific content

PUT /content/{content_id}
Update content

DELETE /content/{content_id}
Delete content

GET /content/categories
Get all categories
```

---

## 11. Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CHATBOT ARCHITECTURE                      │
└─────────────────────────────────────────────────────────────┘

┌──────────────────┐
│  API Layer       │
│  - chatbot.py    │  ← User requests
│  - content.py    │  ← Admin requests
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Service Layer   │
│  - ChatbotService│  ← Intent detection, routing, response
│  - ContentService│  ← Content CRUD, search
└────────┬─────────┘
         │
         ├──────────────────┬──────────────────┐
         ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Vector Store │  │Product Store │  │Content Store │
│ (Pinecone)   │  │ (Supabase)   │  │ (Supabase)   │
└──────────────┘  └──────────────┘  └──────────────┘
         │                  │                  │
         └──────────────────┴──────────────────┘
                           │
                           ▼
                  ┌──────────────┐
                  │ OpenAI API   │
                  │ (GPT-4o-mini)│
                  └──────────────┘
```

---

## 12. Intent Detection Keywords

### Product Information
- `thông tin`, `thông số`, `spec`, `chi tiết`, `mô tả`
- `giá`, `giá bán`, `giá bao nhiêu`
- Product names: `sản phẩm`, `máy`, `điện thoại`, `laptop`, etc.

### Comparison
- `so sánh`, `compare`, `khác nhau`, `giống nhau`
- `nên mua`, `nên chọn`

### Policy
- `chính sách`, `policy`, `đổi trả`, `bảo hành`
- `vận chuyển`, `giao hàng`, `thanh toán`, `hoàn tiền`

### CSKH
- `hỗ trợ`, `tư vấn`, `liên hệ`, `hotline`, `email`
- `cskh`, `customer service`, `help`, `giúp đỡ`

### Realtime Data
- `còn hàng`, `hết hàng`, `tồn kho`, `stock`
- `số lượng`, `còn lại`, `realtime`, `thời gian thực`

---

## 13. Error Handling

```
User Query
    │
    ▼
┌─────────────────┐
│ Intent Detection │
└────────┬────────┘
    │
    ▼
┌─────────────────┐
│ Data Retrieval   │
│ (with fallback)  │
└────────┬────────┘
    │
    ├──► Success ──► Generate Response
    │
    └──► Error ──► Fallback Response
                    "Xin lỗi, tôi không tìm thấy..."
                    "Vui lòng liên hệ CSKH..."
```

---

## 14. Performance Optimization

1. **Caching**: Vector search results cached
2. **Parallel Processing**: Multiple product queries in parallel
3. **Lazy Loading**: Product details loaded only when needed
4. **Connection Pooling**: Database connections reused
5. **Async Operations**: Non-blocking API calls

---

## 15. Monitoring & Logging

- Intent detection accuracy
- Response generation time
- Vector search performance
- OpenAI API latency
- Error rates by intent type
- User satisfaction metrics

---

## Kết Luận

Chatbot sử dụng kiến trúc RAG với khả năng:
- ✅ Tự động phân loại intent
- ✅ Truy xuất thông tin từ nhiều nguồn
- ✅ Tạo câu trả lời tự nhiên bằng tiếng Việt
- ✅ Hỗ trợ 5 loại câu hỏi chính
- ✅ Quản lý nội dung dễ dàng cho admin
- ✅ Cập nhật realtime dữ liệu


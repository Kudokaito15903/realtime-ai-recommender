# Luồng Truy Vấn Vector Database của Chatbot

## Tổng Quan

Chatbot **CÓ truy vấn vector database** để tìm kiếm semantic similarity cho:
1. **Products** - Thông tin sản phẩm
2. **Policy Documents** - Chính sách (bảo hành, đổi trả, vận chuyển, thanh toán)
3. **CSKH Knowledge** - Kiến thức hỗ trợ khách hàng

## Kiến Trúc Vector Search

```
┌─────────────────────────────────────────────────────────┐
│              Chatbot RAG Engine                         │
└─────────────────────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
┌──────────┐    ┌──────────────┐  ┌──────────────┐
│ Products │    │   Policy     │  │    CSKH      │
│ Handler  │    │   Handler    │  │   Handler    │
└────┬─────┘    └──────┬───────┘  └──────┬───────┘
     │                 │                  │
     ▼                 ▼                  ▼
┌─────────────────────────────────────────────────────┐
│         RAG Engine - retrieve_*_chunks()            │
└─────────────────────────────────────────────────────┘
     │                 │                  │
     │                 ▼                  ▼
     │          ┌──────────────┐  ┌──────────────┐
     │          │ContentService│  │ContentService│
     │          │.search_      │  │.search_      │
     │          │content()     │  │content()     │
     │          └──────┬───────┘  └──────┬───────┘
     │                 │                  │
     ▼                 ▼                  ▼
┌─────────────────────────────────────────────────────┐
│           Vector Store (Pinecone/Redis)             │
│                                                      │
│  Namespace: "products"    Namespace: "content"      │
│  ├─► Product embeddings  ├─► Policy embeddings      │
│                           └─► CSKH embeddings        │
└─────────────────────────────────────────────────────┘
```

## 1. Product Information Query

**Flow**: `ProductInfoHandler` → `RAGEngine.retrieve_product_chunks()`

```python
# Trong ProductInfoHandler
chunks = await rag_engine.retrieve_product_chunks(
    query="iPhone 17 Pro có những tính năng gì?",
    top_k=3
)

# RAG Engine truy vấn vector database:
# 1. Generate embedding từ query
query_embedding = embedding_model.embed_text(query)

# 2. Search trong vector store (namespace="products")
results = vector_store.find_similar_products(
    embedding=query_embedding,
    limit=3,
    min_score=0.75,
    namespace="products"  # ← Truy vấn namespace "products"
)
```

**✅ TRUY VẤN VECTOR DATABASE**: Có - trực tiếp qua `vector_store.find_similar_products()`

## 2. Policy Query

**Flow**: `PolicyHandler` → `RAGEngine.retrieve_policy_chunks()` → `ContentService.search_content()`

```python
# Trong PolicyHandler
chunks = await rag_engine.retrieve_policy_chunks(
    query="Chính sách bảo hành như thế nào?",
    policy_type="warranty",
    top_k=3
)

# RAG Engine gọi ContentService
content_results = content_service.search_content(
    query=query,
    category="policy",
    limit=3
)

# ContentService truy vấn vector database:
# 1. Generate embedding
query_embedding = embedding_model.get_embedding(query)

# 2. Search trong vector store (namespace="content")
candidates = vector_store.find_similar_products(
    embedding=query_embedding,
    limit=6,
    min_score=0.3,
    namespace="content"  # ← Truy vấn namespace "content"
)

# 3. Filter theo metadata
for candidate in candidates:
    if candidate.metadata.get("type") == "content":
        if candidate.metadata.get("category") == "policy":
            # Lấy full content từ ContentStore
            content = content_store.get_content(candidate.id)
```

**✅ TRUY VẤN VECTOR DATABASE**: Có - qua `ContentService.search_content()` → `vector_store.find_similar_products(namespace="content")`

## 3. CSKH Query

**Flow**: `CSKHHandler` → `RAGEngine.retrieve_cskh_chunks()` → `ContentService.search_content()`

```python
# Trong CSKHHandler
chunks = await rag_engine.retrieve_cskh_chunks(
    query="Làm sao kiểm tra đơn hàng?",
    topic="order_tracking",
    top_k=2
)

# Tương tự Policy, gọi ContentService
# ContentService truy vấn vector database với namespace="content"
```

**✅ TRUY VẤN VECTOR DATABASE**: Có - qua `ContentService.search_content()` → `vector_store.find_similar_products(namespace="content")`

## Namespace Organization (Pinecone)

Với Pinecone, embeddings được tổ chức theo namespace:

```
Index: "product-recommendations"
├── Namespace: "products"
│   ├── product:embedding:iphone-17-pro
│   ├── product:embedding:laptop-dell-xps
│   └── ...
│
└── Namespace: "content"
    ├── content:policy-warranty
    ├── content:policy-return
    ├── content:cskh-order-tracking
    └── ...
```

## Vector Search Process

### Bước 1: Generate Query Embedding
```python
# Từ text query → vector embedding
query_embedding = embedding_model.embed_text("Chính sách bảo hành")
# Output: np.array([0.12, -0.45, 0.78, ...])  # 768 dimensions
```

### Bước 2: Vector Similarity Search
```python
# Cosine similarity search trong vector database
results = vector_store.find_similar_products(
    embedding=query_embedding,
    limit=5,
    min_score=0.75,
    namespace="content"  # Hoặc "products"
)
# Trả về top K vectors có similarity score cao nhất
```

### Bước 3: Filter & Format
```python
# Filter theo metadata (category, type, tags)
filtered = [
    r for r in results 
    if r.metadata.get("category") == "policy"
]

# Lấy full content từ ContentStore (nếu cần)
for result in filtered:
    content = content_store.get_content(result.id)
```

## Cấu Hình Vector Database

### Pinecone
- **Index Name**: `product-recommendations` (config: `PINECONE_INDEX_NAME`)
- **Dimension**: 768 (config: `VECTOR_DIMENSION`)
- **Namespaces**:
  - `"products"` - Product embeddings
  - `"content"` - Content embeddings (policy, CSKH)

### Redis (nếu dùng)
- **Index**: `product:vectors`
- **Key Pattern**: 
  - Products: `product:embedding:{product_id}`
  - Content: `content:embedding:{content_id}`

## Tóm Tắt

| Loại Query | Truy Vấn Vector DB? | Method | Namespace |
|------------|---------------------|--------|-----------|
| **Products** | ✅ Có | `RAGEngine.retrieve_product_chunks()` → `vector_store.find_similar_products()` | `"products"` |
| **Policy** | ✅ Có | `ContentService.search_content()` → `vector_store.find_similar_products()` | `"content"` |
| **CSKH** | ✅ Có | `ContentService.search_content()` → `vector_store.find_similar_products()` | `"content"` |

**Kết luận**: Chatbot **CÓ truy vấn vector database** cho tất cả loại queries!

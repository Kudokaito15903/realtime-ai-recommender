# Luồng Hoạt Động Dự Án: Real-time AI Recommender System

## Tổng Quan Kiến Trúc

Dự án này là một hệ thống gợi ý sản phẩm thời gian thực sử dụng AI, tích hợp chatbot và CMS để quản lý nội dung. Hệ thống sử dụng kiến trúc microservices với các thành phần chính:

- **Frontend**: Giao diện người dùng (không bao gồm trong repo này)
- **API Gateway**: FastAPI server xử lý requests
- **Vector Store**: Pinecone cho embeddings và similarity search
- **Database**: Supabase/PostgreSQL cho dữ liệu sản phẩm, nội dung, và user behavior
- **Message Queue**: Kafka cho event-driven processing
- **Embedding Model**: SentenceTransformer cho tạo embeddings
- **LLM**: OpenAI API cho chatbot (optional)

## 1. Luồng Khởi Tạo Hệ Thống

### 1.1 Khởi Động API Server
```
FastAPI App Startup
├── Load environment variables (.env)
├── Initialize adapters (Pinecone, Supabase, Kafka)
├── Start event handlers (ProductEventHandler, ContentEventHandler)
├── Start Kafka consumers để lắng nghe events
└── API server ready tại port 8000
```

### 1.2 Khởi Tạo Vector Store (Pinecone)
```
Pinecone Initialization
├── Connect to Pinecone cluster
├── Create/get index "product-recommendations"
├── Index config: dimension=384, metric=cosine
└── Ready cho embedding storage & search
```

## 2. Luồng Quản Lý Sản Phẩm (Product Management)

### 2.1 Admin Tạo/Cập Nhật Sản Phẩm
```
Admin → POST /products (ProductCreate)
├── Validate input data
├── Store product to Supabase (products table)
├── Publish event to Kafka: {"event_type": "create", "product_id": "...", "data": {...}}
└── Return success response
```

### 2.2 Event Handler Xử Lý Product Events
```
Kafka Consumer (ProductEventHandler)
├── Receive product event
├── Fetch product details từ Supabase
├── Generate embedding: SentenceTransformer(product.name + description + specs)
├── Upsert embedding to Pinecone với metadata
└── Log success/failure
```

### 2.3 User Xem Sản Phẩm
```
User → GET /products/{product_id}
├── Query Supabase for product data
├── Optional: Query Pinecone for similar products
└── Return product + similar products
```

## 3. Luồng Gợi Ý Sản Phẩm (Recommendation Engine)

### 3.1 Personalized Recommendations
```
User → GET /recommendations/personalized?user_id=123
├── Get user history từ Supabase (events table)
├── Parallel fetch embeddings từ Pinecone (ThreadPoolExecutor)
├── Build user vector: weighted average of product embeddings
├── Vector search trong Pinecone để tìm candidates
├── Filter out viewed products
├── Re-rank theo similarity + metadata (sold, rating, price)
└── Return top-10 recommendations
```

### 3.2 ALS Collaborative Filtering
```
GET /recommendations/als?user_id=123
├── Load ALS model từ disk (nếu có)
├── Nếu model stale: Train từ interaction data
├── Predict user-item scores
├── Filter & rank recommendations
└── Return results
```

### 3.3 Session-based Recommendations
```
GET /recommendations/session?user_id=123
├── Get recent user interactions
├── Build/load transition stats từ global data
├── Predict next items dựa trên session patterns
├── Vector search fallback nếu cần
└── Return session recommendations
```

### 3.4 Hybrid Recommendations
```
GET /recommendations/hybrid?user_id=123
├── Parallel call: session + ALS + personalized
├── Deduplicate & merge results
├── Re-rank theo confidence scores
└── Return top recommendations
```

## 4. Luồng Chatbot (RAG System)

### 4.1 Admin Quản Lý Nội Dung
```
Admin → POST /content (ContentCreate)
├── Validate content data (title, content, category, tags)
├── Store to Supabase (content table)
├── Publish event: {"event_type": "create", "content_id": "..."}
└── Return content_id
```

### 4.2 Content Event Processing
```
ContentEventHandler
├── Receive content event
├── Fetch content từ Supabase
├── Generate embedding: title + content
├── Upsert to Pinecone với metadata {"type": "content", "category": "..."}
└── Ready for retrieval
```

### 4.3 User Chat Với Bot
```
User → POST /chatbot/chat {"query": "Cách đổi trả?", "top_k": 5}
├── Embed query: SentenceTransformer(query)
├── Vector search Pinecone (products + content)
├── Retrieve top-K documents (enrich với DB data)
├── Build RAG prompt: context + query
├── Call OpenAI API (hoặc fallback message)
└── Return answer + sources
```

## 5. Luồng User Behavior Tracking

### 5.1 Track User Interactions
```
User actions (view, click, add_to_cart, purchase)
├── Frontend → POST /track (user_id, product_id, event_type)
├── Store to Supabase (events table)
├── Update popularity metrics
└── Trigger real-time recommendations update
```

### 5.2 Batch Processing (ALS Training)
```
Scheduled/Cron job
├── Query interaction data từ Supabase
├── Preprocess: filter cold starts, normalize, etc.
├── Train ALS model (implicit feedback)
├── Save model to disk (model_cache/als_model.npz)
└── Update model timestamp
```

## 6. Luồng Data Flow Tổng Quan

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Admin CMS     │────│   API Server     │────│   Database      │
│                 │    │  (FastAPI)       │    │  (Supabase)     │
│ • Manage        │    │                  │    │                 │
│   Products      │    │ • CRUD APIs      │    │ • Products      │
│ • Manage        │    │ • Recommendations│    │ • Content       │
│   Content       │    │ • Chatbot        │    │ • User Events    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Event Queue   │────│   Event Handlers │────│   Vector Store  │
│   (Kafka)       │    │                  │    │   (Pinecone)    │
│                 │    │ • ProductHandler │    │                 │
│ • Product       │    │ • ContentHandler │    │ • Product       │
│   Events        │    │                  │    │   Embeddings    │
│ • Content       │    │                  │    │ • Content       │
│   Events        │    │                  │    │   Embeddings    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                       │
                                                       │
                                                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   User Frontend │────│   Recommendations│────│   Chatbot       │
│                 │    │   Engine         │    │   (RAG)         │
│ • Browse        │    │                  │    │                 │
│   Products      │    │ • Personalized   │    │ • Answer        │
│ • Chat Support  │    │ • ALS            │    │   Questions     │
│ • View Recs     │    │ • Session-based  │    │ • Use Content   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 7. Luồng Error Handling & Monitoring

### 7.1 Error Scenarios
```
Vector Store Unavailable
├── Fallback to database-only recommendations
├── Log error, alert monitoring
└── Return popular products

LLM API Failure
├── Return fallback message
├── Log for debugging
└── Continue with retrieval-only

Database Connection Lost
├── Retry with exponential backoff
├── Use cached data if available
└── Graceful degradation

Kafka Consumer Failure
├── Restart consumer automatically
├── Alert on persistent failures
└── Manual intervention if needed
```

### 7.2 Monitoring Points
- API response times (X-Process-Time header)
- Embedding generation latency
- Vector search performance
- Event processing throughput
- Model training metrics
- Error rates per component

## 8. Luồng Deployment & Scaling

### 8.1 Development Setup
```
Local Development
├── docker-compose up (Kafka, Postgres, Redis)
├── python -m api.app (FastAPI server)
├── Pinecone cloud instance
├── Supabase project
└── Test with sample data
```

### 8.2 Production Deployment
```
Production Setup
├── Kubernetes cluster
├── Separate pods: API, Workers, DB
├── Load balancer for API
├── Redis cache layer
├── Monitoring: Prometheus + Grafana
└── Auto-scaling based on traffic
```

### 8.3 Scaling Considerations
- **Horizontal scaling**: Multiple API instances behind load balancer
- **Vector search**: Pinecone handles high QPS
- **Database**: Supabase/Postgres read replicas
- **Event processing**: Multiple Kafka consumers
- **Caching**: Redis for frequent queries
- **Model serving**: Pre-trained models, batch inference

## 9. Luồng Security & Compliance

### 9.1 Authentication
```
API Security
├── JWT tokens for admin operations
├── API keys for external integrations
├── Rate limiting per user/IP
└── Input validation & sanitization
```

### 9.2 Data Privacy
```
User Data Handling
├── GDPR compliance for user behavior
├── Data retention policies
├── Anonymization for analytics
└── Secure embedding storage
```

---

*Document version: 1.0 | Last updated: December 30, 2025*
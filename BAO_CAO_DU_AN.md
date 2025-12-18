# Báo cáo dự án: Realtime AI Recommender (E-commerce)

## 1) Tổng quan

**Tên dự án**: Realtime AI Recommender (E-commerce Real-time AI API)

**Mục tiêu**: Xây dựng hệ thống gợi ý sản phẩm theo thời gian thực cho thương mại điện tử, kết hợp:
- **Vector similarity** (gợi ý sản phẩm tương tự theo ngữ nghĩa)
- **Session-based** (gợi ý theo chuỗi hành vi gần đây trong phiên)
- **Collaborative Filtering (ALS)** (gợi ý theo tương tác ẩn/implicit feedback)
- **Hybrid** (kết hợp nhiều chiến lược)

**Điểm nổi bật**:
- Backend theo **adapter pattern** để có thể thay đổi nhà cung cấp (vector store, event processor, data store, behavior store) bằng cấu hình.
- Kiến trúc realtime theo mô hình **event-driven**: CRUD sản phẩm → phát event → consumer tạo embedding → lưu vector → API truy vấn gợi ý.

---

## 2) Công nghệ & thư viện chính

- **API**: FastAPI + Uvicorn (`api/app.py`)
- **Logging**: Loguru (`utils/logging.py`)
- **Embedding**: SentenceTransformer `all-MiniLM-L6-v2` (384 chiều) (`models/embeddings.py`)
- **Vector store (mặc định)**: Pinecone (`adapters/pinecone_adapter.py`)
- **Event processor + data store + behavior store (mặc định)**: Supabase (`adapters/supabase_adapter.py`)
- **Recommenders**:
  - Vector-based / semantic search
  - ALS implicit-feedback (tự cài đặt, dùng SciPy sparse) (`models/als_recommender.py`)
  - Session transitions (thống kê item→next-item) (`models/session_recommender.py`)

---

## 3) Cấu trúc thư mục

- **`api/`**: FastAPI app và routes
  - `api/app.py`: khởi tạo app, mount routes, `/health`
  - `api/routes/modern_products.py`: CRUD sản phẩm + search/similar, backend-agnostic
  - `api/routes/recommendations.py`: API gợi ý (similar/category/personalized/track-view/search)
- **`adapters/`**: lớp kết nối backend (interface + factory + triển khai)
  - `interfaces.py`: VectorStoreInterface, EventProcessorInterface, ProductStoreInterface, UserBehaviorInterface
  - `factory.py`: chọn adapter theo env
  - `pinecone_adapter.py`: PineconeVectorStore
  - `supabase_adapter.py`: SupabaseEventProcessor, SupabaseProductStore, SupabaseUserBehavior
- **`models/`**: embedding + thuật toán gợi ý
  - `embeddings.py`: sinh embedding từ text/sản phẩm
  - `recommendations.py`: ProductRecommender (vector/ALS/session/hybrid)
  - `als_recommender.py`: huấn luyện + suy luận ALS
  - `session_recommender.py`: thống kê chuyển trạng thái phiên
- **`services/`**: tiến trình nền
  - `modern_stream_consumer.py`: consumer backend-agnostic (event → embedding → vector store)
- **`config.py`**: cấu hình qua biến môi trường
- **`docker-compose*.yml`, `Dockerfile*`, `README.Docker.md`**: Docker hóa

---

## 4) Kiến trúc hệ thống (mô tả)

### 4.1 Các thành phần

- **FastAPI**: cung cấp REST API cho sản phẩm và gợi ý.
- **Event Processor (Supabase)**:
  - Khi tạo/sửa/xóa sản phẩm, API ghi event vào bảng `product_events`.
  - Consumer đọc các event `processed=false`, xử lý và cập nhật `processed=true`.
- **Embedding Model**:
  - Sinh embedding 384 chiều cho sản phẩm bằng cách ghép `name + description + category + attributes`.
- **Vector Store (Pinecone)**:
  - Lưu embedding theo `product_id`.
  - Thực hiện truy vấn tương tự bằng cosine similarity.
- **Behavior Store (Supabase)**:
  - Lưu lịch sử xem sản phẩm `user_views`.
  - Là nguồn dữ liệu cho personalized, session-based và ALS.

### 4.2 Luồng realtime (Product → Vector)

1. **Client gọi API** tạo/sửa/xóa sản phẩm (`POST/PUT/DELETE /products`)
2. API (tùy cấu hình) lưu dữ liệu vào product store (Supabase table `products`)
3. API ghi sự kiện vào `product_events`
4. **Consumer** (`services/modern_stream_consumer.py`) poll `product_events`:
   - `create/update`: sinh embedding → upsert vào Pinecone
   - `delete`: xóa vector trong Pinecone
5. Sau khi xử lý, consumer cập nhật `processed=true` để tránh xử lý lại.

---

## 5) API endpoints chính

### 5.1 Health
- **GET** `/health`

### 5.2 Products (backend-agnostic)
Prefix: `/products`
- **GET** `/products/backend-info`: thông tin backend hiện tại + trạng thái runtime
- **POST** `/products/`: tạo sản phẩm (publish event)
- **PUT** `/products/{product_id}`: cập nhật (publish event)
- **DELETE** `/products/{product_id}`: xóa (publish event)
- **GET** `/products/{product_id}?include_similar=true|false`: lấy sản phẩm, có thể kèm similar
- **GET** `/products/similar/{product_id}?limit=6&threshold=0.7`: tìm sản phẩm tương tự
- **GET** `/products/search/text?query=...&limit=10&category=...`: search theo text
- **GET** `/products/?category=...&limit=100&offset=0`: list (chỉ khi product store khả dụng)

### 5.3 Recommendations
Prefix: `/recommendations`
- **GET** `/recommendations/{product_id}/similar?limit=6` (Header tùy chọn `user-id`): tương tự theo vector
- **GET** `/recommendations/category/{category}?limit=10`: phổ biến theo danh mục (hiện tại behavior store trả về gần đây)
- **GET** `/recommendations/personalized?limit=10&method=vector|als|session|hybrid&recent_k=5`
  - Header bắt buộc: `user-id`
- **POST** `/recommendations/track-view?product_id=...` (Header bắt buộc `user-id`): ghi nhận xem
- **GET** `/recommendations/search?query=...&limit=10`: gợi ý theo text

---

## 6) Chiến lược gợi ý (Recommendation strategies)

### 6.1 Vector similarity (similar / search)
- Dùng embedding của sản phẩm (hoặc embedding từ query text) để query Pinecone.
- Ngưỡng tương đồng: `SIMILARITY_THRESHOLD` (mặc định 0.75).

### 6.2 Personalized (vector-history)
- Lấy lịch sử gần đây từ `user_views`.
- Với mỗi sản phẩm đã xem, lấy các sản phẩm tương tự.
- Loại trùng và loại các sản phẩm đã xem.

### 6.3 ALS (Collaborative Filtering)
- Nguồn dữ liệu: tổng hợp `count` theo cặp (user_id, product_id).
- Model được cache và có TTL theo `ALS_REFRESH_SECONDS`.
- Lưu model tại `ALS_MODEL_PATH` (mặc định `./model_cache/als_model.npz`).

### 6.4 Session-based
- Xây dựng thống kê chuyển trạng thái item→next-item từ chuỗi tương tác theo thời gian.
- Dùng `SESSION_GAP_SECONDS` để tách phiên.
- Lấy `recent_k` sản phẩm gần đây của user, rồi suy ra ứng viên kế tiếp.

### 6.5 Hybrid
- Gom candidates từ: session + ALS (không ép train) + vector-history.
- Khử trùng theo `product_id`, giữ score tốt nhất.

---

## 7) Cấu hình hệ thống (Environment variables)

Cấu hình nằm trong `config.py`.

### 7.1 Chọn backend
- `BACKEND_TYPE` (mặc định: `cloud`)
- `VECTOR_STORE_TYPE` (mặc định: `pinecone`)
- `EVENT_PROCESSOR_TYPE` (mặc định: `supabase`)
- `DATA_STORE_TYPE` (mặc định: `supabase`)
- `BEHAVIOR_STORE_TYPE` (mặc định: `supabase`)

**Lưu ý**: `adapters/factory.py` hiện chỉ implement `pinecone` cho vector store và `supabase` cho event/data/behavior.

### 7.2 Pinecone
- `PINECONE_API_KEY`
- `PINECONE_ENVIRONMENT` (mặc định: `us-east-1` trong `config.py`; adapter dùng mặc định `us-east-1-aws` nếu không set)
- `PINECONE_INDEX_NAME` (mặc định: `product-recommendations`)
- `VECTOR_DIMENSION` (mặc định: 384)

### 7.3 Supabase
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

### 7.4 API & Logging
- `API_HOST` (mặc định `0.0.0.0`)
- `API_PORT` (mặc định `8000`)
- `DEBUG_MODE` (mặc định `False`)
- `LOG_LEVEL` (mặc định `INFO`)

### 7.5 Recommender
- ALS: `ALS_*` (factors/iterations/regularization/alpha/refresh...)
- Session: `SESSION_*`

---

## 8) Yêu cầu dữ liệu (Supabase schema tối thiểu)

Hệ thống Supabase adapter kỳ vọng các bảng sau (tên cột như code đang truy cập):

```sql
-- Products
create table if not exists products (
  id bigserial primary key,
  product_id text unique not null,
  name text,
  description text,
  category text,
  price numeric,
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Product events (for realtime processing)
create table if not exists product_events (
  id bigserial primary key,
  event_type text not null,           -- create | update | delete
  product_id text not null,
  data text not null,                 -- JSON string
  timestamp timestamptz default now(),
  processed boolean default false,
  processed_at timestamptz,
  created_at timestamptz default now()
);

-- User views (behavior tracking)
create table if not exists user_views (
  id bigserial primary key,
  user_id text not null,
  product_id text not null,
  timestamp timestamptz default now()
);

-- Category popularity (best-effort counter)
create table if not exists category_popularity (
  category text primary key,
  view_count bigint default 0,
  last_updated timestamptz default now()
);
```

---

## 9) Hướng dẫn chạy

### 9.1 Chạy local (khuyến nghị khi dùng Pinecone+Supabase)

1) Tạo môi trường và cài dependencies:

```bash
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2) Tạo file `.env` (tham khảo `.env.example`) và set tối thiểu:
- `PINECONE_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

3) Chạy API:

```bash
python -m api.app
```

4) Chạy consumer (tạo embedding & upsert vectors):

```bash
python -m services.modern_stream_consumer
```

### 9.2 Chạy bằng Docker

Repo có `docker-compose.yml` và `docker-compose.dev.yml`. Tuy nhiên hiện có **độ lệch**:
- `docker-compose*.yml` đang gọi `python -m services.stream_consumer` nhưng trong codebase hiện tại **không có** `services/stream_consumer.py`.

**Cách chỉnh để chạy đúng theo code hiện tại**:
- Sửa `docker-compose.yml` và `docker-compose.dev.yml` service `stream-consumer` thành:
  - `command: python -m services.modern_stream_consumer`

**Lưu ý thêm**:
- Docker compose hiện cấu hình Redis; trong khi adapter hiện tại chỉ hỗ trợ cloud (Pinecone/Supabase). Nếu chạy cloud stack, Redis có thể không cần thiết.

---

## 10) Ví dụ gọi API (cURL)

### 10.1 Health
```bash
curl http://localhost:8000/health
```

### 10.2 Tạo sản phẩm
```bash
curl -X POST http://localhost:8000/products \
  -H "Content-Type: application/json" \
  -d '{
    "id": "p-001",
    "name": "Áo thun basic",
    "description": "Cotton 100%, form regular",
    "category": "fashion",
    "price": 199000,
    "sku": "TSHIRT-001",
    "attributes": {"color": "white", "size": "M"}
  }'
```

### 10.3 Track view + Personalized
```bash
curl -X POST "http://localhost:8000/recommendations/track-view?product_id=p-001" \
  -H "user-id: u-123"

curl "http://localhost:8000/recommendations/personalized?limit=10&method=hybrid" \
  -H "user-id: u-123"
```

### 10.4 Similar theo product
```bash
curl "http://localhost:8000/recommendations/p-001/similar?limit=6" \
  -H "user-id: u-123"
```

---

## 11) Đánh giá hiện trạng & rủi ro

- **Độ lệch cấu hình Docker**: compose gọi module consumer cũ; cần cập nhật sang `modern_stream_consumer`.
- **Redis mode chưa được triển khai trong adapter factory**: dù có cấu hình/requirements liên quan Redis, `adapters/factory.py` hiện chỉ hỗ trợ `pinecone` và `supabase`.
- **Popular products**: `SupabaseUserBehavior.get_popular_products()` hiện trả về sản phẩm gần đây, chưa phải ranking theo view_count thực.

---

## 12) Hướng phát triển đề xuất

- **Chuẩn hóa popularity**: tạo view/materialized view hoặc RPC để top theo `user_views`.
- **Event realtime thật sự**: thay polling bằng Supabase realtime subscription (nếu phù hợp).
- **Chuẩn hóa schema & migration**: thêm script SQL/migration chính thức cho Supabase.
- **Giám sát**: bổ sung metrics (Prometheus) + tracing (OpenTelemetry) cho API/consumer.
- **Chất lượng gợi ý**: chuẩn hóa score scale khi hybrid (hiện các nguồn có thang điểm khác nhau).

---

## 13) Kết luận

Dự án hiện triển khai **Realtime AI Recommender** theo hướng **cloud-native** (Pinecone + Supabase) với API FastAPI, consumer xử lý event để tạo embeddings và hỗ trợ 4 phương pháp gợi ý (vector/ALS/session/hybrid). Hệ thống phù hợp cho bài toán gợi ý sản phẩm thời gian thực, dễ mở rộng nhờ adapter pattern và tách riêng consumer nền.

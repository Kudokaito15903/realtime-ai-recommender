# 🚀 Hướng Dẫn Chạy Dự Án Real-time AI Recommender

Hướng dẫn chi tiết từng bước để setup và chạy dự án recommendation system.

## 📋 Yêu Cầu Hệ Thống

### Phần Mềm Cần Thiết
- **Python 3.8+** (khuyến nghị 3.9 hoặc 3.10)
- **Docker & Docker Compose** (nếu chạy bằng Docker)
- **PostgreSQL 12+** (hoặc dùng Docker Compose)
- **Git**

### Dịch Vụ Cloud (Tùy Chọn)
- **Pinecone** (cho vector store) - có thể dùng free tier
- **Supabase** (nếu muốn dùng thay vì PostgreSQL tự host)

---

## 🎯 Phương Pháp 1: Chạy Bằng Docker (Khuyến Nghị)

### Bước 1: Clone Repository
```bash
git clone <repository-url>
cd realtime-ai-recommender
```

### Bước 2: Tạo File `.env`
Tạo file `.env` trong thư mục gốc với nội dung:

```env
# Backend Configuration
BACKEND_TYPE=hybrid
VECTOR_STORE_TYPE=pinecone
EVENT_PROCESSOR_TYPE=postgres
DATA_STORE_TYPE=postgres
BEHAVIOR_STORE_TYPE=postgres

# Pinecone Configuration (BẮT BUỘC nếu dùng Pinecone)
PINECONE_API_KEY=your_pinecone_api_key_here
PINECONE_ENVIRONMENT=us-east-1
PINECONE_INDEX_NAME=product-recommendations

# PostgreSQL Configuration (sẽ dùng từ Docker Compose)
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=realtime_ai
POSTGRES_USER=realtime_ai
POSTGRES_PASSWORD=realtime_ai

# Redis Configuration (optional, cho legacy)
REDIS_HOST=redis
REDIS_PORT=6379

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
DEBUG_MODE=true
LOG_LEVEL=INFO

# Model Configuration
EMBEDDING_MODEL_NAME=all-MiniLM-L6-v2
VECTOR_DIMENSION=384
SIMILARITY_THRESHOLD=0.75
MODEL_CACHE_DIR=./model_cache

# ALS Model Configuration
ALS_MODEL_PATH=./model_cache/als_model.npz
ALS_FACTORS=64
ALS_ITERATIONS=15
ALS_REGULARIZATION=0.1
ALS_ALPHA=40.0
ALS_TRAINING_INTERACTIONS_LIMIT=50000
```

**Lưu ý**: Thay `your_pinecone_api_key_here` bằng API key thật từ Pinecone.

### Bước 3: Khởi Tạo Pinecone Index (Nếu Dùng Pinecone)

1. Đăng ký tài khoản tại [pinecone.io](https://www.pinecone.io)
2. Tạo một index mới với:
   - **Dimension**: `384` (tương ứng với model `all-MiniLM-L6-v2`)
   - **Metric**: `cosine`
   - **Name**: `product-recommendations` (hoặc tên khác, nhớ cập nhật trong `.env`)

### Bước 4: Khởi Động Services

```bash
# Chạy development mode (có hot-reload)
docker-compose -f docker-compose.dev.yml up -d

# Hoặc chạy production mode
docker-compose up -d
```

Kiểm tra services đã chạy:
```bash
docker-compose ps
```

### Bước 5: Train ALS Model (Nếu Có Dữ Liệu)

**Nếu bạn đã có dữ liệu trong PostgreSQL:**

```bash
# Vào container API
docker-compose exec api bash

# Train ALS model từ dữ liệu thật
python -m services.model_trainer

# Hoặc train với fake data để test
python -m services.fake_als_data --num-users 200 --num-products 1000
```

**Nếu chưa có dữ liệu, tạo fake data để test:**

```bash
docker-compose exec api python -m services.fake_als_data \
  --num-users 200 \
  --num-products 1000 \
  --model-path ./model_cache/als_model.npz
```

### Bước 6: Kiểm Tra API

Mở trình duyệt hoặc dùng curl:

```bash
# Health check
curl http://localhost:8000/health

# API Documentation
# Mở: http://localhost:8000/docs
```

### Bước 7: Xem Logs (Nếu Cần)

```bash
# Xem logs tất cả services
docker-compose logs -f

# Xem logs API
docker-compose logs -f api

# Xem logs PostgreSQL
docker-compose logs -f postgres
```

---

## 🎯 Phương Pháp 2: Chạy Trực Tiếp (Không Docker)

### Bước 1: Cài Đặt Python Dependencies

```bash
# Tạo virtual environment (khuyến nghị)
python -m venv venv

# Kích hoạt virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Cài đặt dependencies
pip install -r requirements.txt
```

### Bước 2: Setup PostgreSQL

**Nếu dùng PostgreSQL local:**

1. Cài đặt PostgreSQL trên máy
2. Tạo database:
```sql
CREATE DATABASE realtime_ai;
CREATE USER realtime_ai WITH PASSWORD 'realtime_ai';
GRANT ALL PRIVILEGES ON DATABASE realtime_ai TO realtime_ai;
```

**Hoặc dùng Docker chỉ cho PostgreSQL:**
```bash
docker run -d \
  --name postgres-dev \
  -e POSTGRES_DB=realtime_ai \
  -e POSTGRES_USER=realtime_ai \
  -e POSTGRES_PASSWORD=realtime_ai \
  -p 5432:5432 \
  postgres:16
```

### Bước 3: Tạo File `.env`

Tạo file `.env` tương tự như trên, nhưng sửa:

```env
POSTGRES_HOST=localhost  # Thay vì "postgres"
REDIS_HOST=localhost    # Nếu có Redis local
```

### Bước 4: Khởi Tạo Pinecone Index

Giống như Bước 3 ở phương pháp Docker.

### Bước 5: Train ALS Model

```bash
# Train từ dữ liệu thật
python -m services.model_trainer

# Hoặc train với fake data
python -m services.fake_als_data --num-users 200 --num-products 1000
```

### Bước 6: Chạy API

```bash
# Chạy trực tiếp
python -m api.app

# Hoặc dùng uvicorn
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

---

## 📊 Import Dữ Liệu Vào Database

### Nếu Bạn Đã Có Dữ Liệu

**Option 1: Import vào PostgreSQL qua SQL**

```bash
# Kết nối vào PostgreSQL
docker-compose exec postgres psql -U realtime_ai -d realtime_ai

# Hoặc nếu chạy local
psql -U realtime_ai -d realtime_ai
```

Sau đó import dữ liệu vào các bảng:
- `products` - thông tin sản phẩm
- `user_views` - lịch sử tương tác của user

**Option 2: Import Qua API**

```bash
# Tạo sản phẩm
curl -X POST "http://localhost:8000/products" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "product_1",
    "name": "Sản phẩm 1",
    "description": "Mô tả sản phẩm",
    "category": "Điện tử",
    "price": 100000
  }'

# Track user view
curl -X POST "http://localhost:8000/recommendations/track-view?product_id=product_1" \
  -H "user_id: user_1"
```

### Tạo Dữ Liệu Mẫu (Fake Data)

Nếu chưa có dữ liệu, có thể tạo fake data:

```bash
# Tạo fake interactions cho ALS training
python -m services.fake_als_data \
  --num-users 500 \
  --num-products 2000 \
  --min-interactions-per-user 10 \
  --max-interactions-per-user 50
```

**Lưu ý**: Script này chỉ tạo dữ liệu trong memory để train ALS. Để có dữ liệu thật trong database, bạn cần import hoặc track qua API.

---

## 🧪 Test Các API Endpoints

### 1. Health Check
```bash
curl http://localhost:8000/health
```

### 2. Tạo Sản Phẩm
```bash
curl -X POST "http://localhost:8000/products" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "prod_001",
    "name": "Laptop Dell XPS 15",
    "description": "Laptop cao cấp với màn hình 15 inch",
    "category": "Điện tử",
    "price": 25000000
  }'
```

### 3. Lấy Recommendations (Recency-Weighted)
```bash
curl -X GET "http://localhost:8000/recommendations/personalized/recency-weighted?result_limit=10" \
  -H "user_id: user_123"
```

### 4. Lấy Similar Products
```bash
curl -X GET "http://localhost:8000/recommendations/prod_001/similar?limit=5" \
  -H "user_id: user_123"
```

### 5. Personalized Recommendations
```bash
curl -X GET "http://localhost:8000/recommendations/personalized?limit=10&method=hybrid" \
  -H "user_id: user_123"
```

### 6. Track User Behavior
```bash
# Track view
curl -X POST "http://localhost:8000/recommendations/track-view?product_id=prod_001" \
  -H "user_id: user_123"

# Track click
curl -X POST "http://localhost:8000/recommendations/track-click?product_id=prod_001" \
  -H "user_id: user_123"
```

---

## 🔧 Troubleshooting

### Lỗi: "Pinecone API key not found"
- Kiểm tra file `.env` có `PINECONE_API_KEY` chưa
- Đảm bảo API key hợp lệ

### Lỗi: "Cannot connect to PostgreSQL"
- Kiểm tra PostgreSQL đã chạy chưa: `docker-compose ps`
- Kiểm tra connection string trong `.env`
- Test kết nối: `docker-compose exec postgres psql -U realtime_ai -d realtime_ai`

### Lỗi: "ALS model not found"
- Train model trước: `python -m services.model_trainer`
- Hoặc dùng fake data: `python -m services.fake_als_data`

### Lỗi: "No embeddings found for product"
- Đảm bảo đã tạo embeddings cho sản phẩm
- Kiểm tra Pinecone index đã có dữ liệu chưa
- Có thể cần chạy stream consumer để generate embeddings

### API không chạy được
- Kiểm tra port 8000 đã bị chiếm chưa: `netstat -an | grep 8000` (Linux/Mac) hoặc `netstat -an | findstr 8000` (Windows)
- Xem logs: `docker-compose logs api`

---

## 📚 Tài Liệu Tham Khảo

- **API Documentation**: http://localhost:8000/docs (khi API đã chạy)
- **Docker Guide**: Xem `README.Docker.md`
- **Project Report**: Xem `BAO_CAO_DU_AN.md`

---

## ✅ Checklist Trước Khi Chạy

- [ ] Đã cài đặt Python 3.8+ và Docker (nếu dùng Docker)
- [ ] Đã tạo file `.env` với đầy đủ thông tin
- [ ] Đã setup Pinecone index (nếu dùng Pinecone)
- [ ] Đã khởi động PostgreSQL (qua Docker hoặc local)
- [ ] Đã train ALS model (hoặc sẽ train sau)
- [ ] Đã import dữ liệu sản phẩm vào database
- [ ] Đã test health check endpoint

---

## 🎉 Hoàn Thành!

Sau khi hoàn thành các bước trên, bạn có thể:
1. Truy cập API docs tại: http://localhost:8000/docs
2. Test các endpoints recommendation
3. Bắt đầu tích hợp vào frontend hoặc ứng dụng của bạn

Chúc bạn thành công! 🚀


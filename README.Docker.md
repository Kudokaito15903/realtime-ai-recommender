# 🐳 Docker Setup Guide

Hướng dẫn chạy dự án Real-time AI Recommender với Docker và Docker Compose.

## 📋 Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- Git

## 🚀 Quick Start

### 1. Clone Repository
```bash
git clone <repository-url>
cd realtime-ai-recommender
```

### 2. Setup Environment
```bash
# Copy example environment file
cp .env.example .env

# Edit .env nếu cần (thường không cần cho local development)
# nano .env
```

### 3. Start Services (Production)
```bash
docker-compose up -d
```

### 4. Start Services (Development với hot-reload)
```bash
docker-compose -f docker-compose.dev.yml up
```

## 📊 Services

### Production (`docker-compose.yml`)

| Service | Port | Description |
|--------|------|-------------|
| **API** | 8000 | FastAPI application |
| **Redis** | 6379 | Redis với RedisSearch module |
| **Stream Consumer** | - | Background worker cho event processing |
| **RedisInsight** | 8001 | Redis monitoring tool (optional, profile: tools) |

### Development (`docker-compose.dev.yml`)

Giống production nhưng có:
- Hot-reload cho API
- Debug logging
- Development tools

## 🛠️ Docker Commands

### Start Services
```bash
# Start all services
docker-compose up -d

# Start with logs
docker-compose up

# Start development mode
docker-compose -f docker-compose.dev.yml up
```

### Stop Services
```bash
# Stop all services
docker-compose down

# Stop and remove volumes
docker-compose down -v
```

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api
docker-compose logs -f stream-consumer
docker-compose logs -f redis
```

### Restart Services
```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart api
```

### Execute Commands in Container
```bash
# API container
docker-compose exec api bash

# Stream consumer
docker-compose exec stream-consumer bash

# Redis CLI
docker-compose exec redis redis-cli
```

### Rebuild Images
```bash
# Rebuild all
docker-compose build

# Rebuild specific service
docker-compose build api

# Rebuild without cache
docker-compose build --no-cache api
```

## 📝 Service Details

### API Service

**Health Check**: `http://localhost:8000/health`

**API Documentation**: `http://localhost:8000/docs`

**Configuration**:
- Workers: 2 (production)
- Hot-reload: Enabled (development)
- Log level: INFO (production), DEBUG (development)

### Redis Service

**Features**:
- RedisSearch module for vector similarity search
- Persistence: AOF (Append Only File)
- Memory limit: 2GB (production), 1GB (development)
- Eviction policy: LRU

**Connect from host**:
```bash
redis-cli -h localhost -p 6379
```

**Or from container**:
```bash
docker-compose exec redis redis-cli
```

### Stream Consumer Service

**Function**: Process events from Redis Streams, generate embeddings, store vectors

**Manual Start**:
```bash
docker-compose exec stream-consumer python -m services.stream_consumer
```

**Use Modern Consumer**:
Thay đổi command trong `docker-compose.yml`:
```yaml
command: python -m services.modern_stream_consumer
```

## 🔧 Configuration

### Environment Variables

Chỉnh sửa `.env` file:

```bash
# Redis
REDIS_HOST=redis  # Service name in docker-compose
REDIS_PORT=6379

# API
API_PORT=8000
DEBUG_MODE=false

# Vector Search
VECTOR_DIMENSION=384
SIMILARITY_THRESHOLD=0.75
```

### Redis Memory Configuration

Trong `docker-compose.yml`, adjust:
```yaml
command: >
  redis-server
  --maxmemory 2gb
  --maxmemory-policy allkeys-lru
```

## 🧪 Testing

### Run Tests
```bash
# In API container
docker-compose exec api pytest

# With coverage
docker-compose exec api pytest --cov
```

### Test API Endpoints
```bash
# Health check
curl http://localhost:8000/health

# Create product
curl -X POST http://localhost:8000/products \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test-1",
    "name": "Test Product",
    "description": "A test product",
    "category": "electronics",
    "price": 99.99,
    "sku": "TEST-001"
  }'

# Get recommendations
curl http://localhost:8000/recommendations/test-1/similar
```

## 📊 Monitoring

### RedisInsight

Start với profile `tools`:
```bash
docker-compose --profile tools up redisinsight
```

Access: `http://localhost:8001`

### Check Service Status
```bash
# All services
docker-compose ps

# Specific service health
docker-compose exec api curl http://localhost:8000/health
```

### View Resource Usage
```bash
docker stats
```

## 🐛 Troubleshooting

### Services Not Starting

1. **Check logs**:
   ```bash
   docker-compose logs
   ```

2. **Check Redis connection**:
   ```bash
   docker-compose exec redis redis-cli ping
   ```

3. **Verify environment**:
   ```bash
   docker-compose exec api env | grep REDIS
   ```

### Redis Connection Issues

1. **Check if Redis is healthy**:
   ```bash
   docker-compose ps redis
   ```

2. **Test connection**:
   ```bash
   docker-compose exec api python -c "import redis; r=redis.Redis(host='redis'); r.ping()"
   ```

### API Not Responding

1. **Check API logs**:
   ```bash
   docker-compose logs api
   ```

2. **Restart API**:
   ```bash
   docker-compose restart api
   ```

3. **Check port binding**:
   ```bash
   netstat -an | grep 8000
   ```

### Stream Consumer Not Processing

1. **Check consumer logs**:
   ```bash
   docker-compose logs stream-consumer
   ```

2. **Check Redis Stream**:
   ```bash
   docker-compose exec redis redis-cli XINFO STREAM product:updates
   ```

3. **Restart consumer**:
   ```bash
   docker-compose restart stream-consumer
   ```

## 🔐 Security Considerations

### Production Deployment

1. **Set Redis password**:
   ```yaml
   environment:
     - REDIS_PASSWORD=${REDIS_PASSWORD}
   ```

2. **Limit exposed ports**:
   - Remove Redis port mapping
   - Use internal network only

3. **Use secrets for API keys**:
   ```yaml
   secrets:
     - pinecone_api_key
     - supabase_key
   ```

4. **Enable CORS properly**:
   Uncomment and configure CORS in `api/app.py`

## 📈 Scaling

### Scale API Workers

Trong `docker-compose.yml`:
```yaml
api:
  deploy:
    replicas: 3
```

### Scale Stream Consumers

```yaml
stream-consumer:
  deploy:
    replicas: 2
```

Hoặc manual:
```bash
docker-compose up -d --scale stream-consumer=3
```

## 🗑️ Cleanup

### Remove Everything
```bash
# Stop and remove containers, networks, volumes
docker-compose down -v

# Remove images
docker-compose down --rmi all

# Clean up system
docker system prune -a
```

### Remove Specific Volumes
```bash
# List volumes
docker volume ls

# Remove specific volume
docker volume rm realtime-ai-recommender_redis_data
```

## 📚 Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Redis Stack Documentation](https://redis.io/docs/stack/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

## 🆘 Support

Nếu gặp vấn đề:
1. Check logs: `docker-compose logs`
2. Verify configuration: `.env` file
3. Check service health: `docker-compose ps`
4. Review troubleshooting section above


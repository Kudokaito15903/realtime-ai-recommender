# Kiến Trúc Dự Án - Realtime AI Recommender

## Cấu Trúc Thư Mục

```
realtime-ai-recommender/
│
├── api/                        # Presentation Layer
│   ├── app.py                  # FastAPI application entry point
│   ├── routes/
│   │   ├── recommend.py        # Recommendation API endpoints
│   │   └── modern_products.py  # Product management endpoints
│   └── middleware/
│       └── logging.py          # Request logging middleware
│
├── consumers/                  # Event-driven entrypoint
│   └── modern_product_event_consumer.py  # Product event consumer
│
├── services/                   # Application Layer
│   ├── recommendation_service.py      # Main recommendation service
│   ├── embedding_service.py            # Embedding generation service
│   └── interaction_service.py          # User interaction tracking service
│
├── domain/                     # CORE business logic
│   ├── recommenders/
│   │   ├── als_recommender.py          # ALS collaborative filtering
│   │   ├── session_recommender.py      # Session-based recommendations
│   │   └── hybrid_recommender.py       # Hybrid recommendation strategy
│   │
│   ├── embeddings/
│   │   ├── user_vector_builder.py      # User embedding construction
│   │   ├── product_embeddings.py       # Product embedding generation
│   │   └── similarity.py               # Similarity calculations
│   │
│   └── ranking/
│       ├── reranker.py                 # Re-ranking logic
│       └── business_rules.py           # Business rule filters
│
├── adapters/                   # Infrastructure
│   ├── vector_store/
│   │   ├── interfaces.py              # Vector store interface
│   │   └── pinecone_adapter.py        # Pinecone implementation
│   │
│   ├── database/
│   │   ├── postgres_adapter.py        # PostgreSQL adapter
│   │   └── supabase_adapter.py        # Supabase adapter
│   │
│   └── factory.py                     # Adapter factory pattern
│
├── offline/                    # Offline ML pipeline
│   ├── als/
│   │   ├── interaction_features.py    # Feature engineering
│   │   ├── build_matrix.py            # Matrix construction
│   │   ├── train_als.py                # ALS model training
│   │   └── export_embeddings.py        # Embedding export
│   │
│   └── evaluation/
│       └── offline_metrics.py          # Offline evaluation metrics
│
├── utils/                      # Stateless helpers
│   ├── normalization.py                # Data normalization
│   ├── metrics.py                      # Metrics collection
│   ├── logging.py                      # Logging utilities
│   ├── data_quality.py                 # Data quality checks
│   └── ab_testing.py                   # A/B testing utilities
│
├── model_cache/                # Trained model storage
├── data/                       # Data schemas and models
├── tests/                      # Test files
└── logs/                       # Application logs
```

## Kiến Trúc Layers

### 1. Presentation Layer (`api/`)
- **Responsibility**: HTTP API endpoints, request/response handling
- **Components**:
  - `app.py`: FastAPI application setup
  - `routes/`: API route handlers
  - `middleware/`: Request/response middleware

### 2. Application Layer (`services/`)
- **Responsibility**: Orchestration, business workflows
- **Components**:
  - `recommendation_service.py`: Main recommendation orchestration
  - `embedding_service.py`: Embedding generation coordination
  - `interaction_service.py`: User interaction management

### 3. Domain Layer (`domain/`)
- **Responsibility**: Core business logic, algorithms
- **Components**:
  - `recommenders/`: Recommendation algorithms (ALS, Session, Hybrid)
  - `embeddings/`: Embedding generation and similarity
  - `ranking/`: Re-ranking and business rules

### 4. Infrastructure Layer (`adapters/`)
- **Responsibility**: External system integration
- **Components**:
  - `vector_store/`: Vector database adapters
  - `database/`: Database adapters
  - `factory.py`: Adapter factory pattern

### 5. Event Layer (`consumers/`)
- **Responsibility**: Real-time event processing
- **Components**:
  - `modern_product_event_consumer.py`: Product event stream consumer

### 6. Offline Pipeline (`offline/`)
- **Responsibility**: Batch processing, model training
- **Components**:
  - `als/`: ALS model training pipeline
  - `evaluation/`: Offline evaluation

## Design Patterns

1. **Adapter Pattern**: Infrastructure adapters for different backends
2. **Factory Pattern**: Adapter factory for dependency injection
3. **Singleton Pattern**: Services as singletons
4. **Strategy Pattern**: Multiple recommendation strategies

## Data Flow

1. **API Request** → `api/routes/` → `services/` → `domain/` → `adapters/`
2. **Event Stream** → `consumers/` → `services/` → `adapters/`
3. **Offline Training** → `offline/` → `domain/` → `model_cache/`

## Notes

- All layers are decoupled through interfaces
- Domain layer has no dependencies on infrastructure
- Services orchestrate domain logic
- Adapters handle external system integration


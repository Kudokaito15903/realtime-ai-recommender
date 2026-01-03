import sys
import os
import time
import random
import numpy as np
from typing import List, Dict, Any
from unittest.mock import MagicMock

# Ensure we can import from root
sys.path.append(os.getcwd())

from services.recommendation_service import RecommendationService
from domain.recommenders.als_recommender import load_als_model, ALSModel
from config import ALS_MODEL_PATH

def mock_recommendation_service():
    """Create a service with mocked dependencies for isolation."""
    print("[INFO] Creating MOCKED Recommendation Service...")
    service = RecommendationService.__new__(RecommendationService)
    
    # Mock Vector Store
    service.vector_store = MagicMock()
    service.vector_store.find_similar_products.return_value = [
        {"product_id": f"p_{i}", "similarity_score": 0.85 - (i * 0.05)}
        for i in range(5)
    ]
    service.vector_store.get_product_embedding.return_value = [0.1] * 64

    # Mock Embedding Model
    service.embedding_model = MagicMock()
    service.embedding_model.get_embedding.return_value = [0.1] * 64
    service.embedding_model.embedding_dimension = 64

    # Mock User Behavior
    service.user_behavior = MagicMock()
    service.user_behavior.get_user_history.return_value = [
        {"product_id": "p_history_1", "timestamp": time.time(), "event_type": "view"},
        {"product_id": "p_history_2", "timestamp": time.time() - 100, "event_type": "view"},
    ]
    service.user_behavior.get_popular_products.return_value = [
        {"product_id": f"pop_{i}", "count": 1000 - (i*100)} for i in range(5)
    ]
    # Mock recent interactions for session
    service.user_behavior.get_recent_interactions.return_value = [
        {"user_id": "u1", "product_id": "p_A", "timestamp": time.time() - 200, "session_id": "s1"},
        {"user_id": "u1", "product_id": "p_B", "timestamp": time.time() - 100, "session_id": "s1"},
        {"user_id": "u1", "product_id": "p_A", "timestamp": time.time() - 50, "session_id": "s1"},
    ]

    # Mock Product Store
    service.product_store = MagicMock()
    service.product_store.get_product.return_value = {"price": 100, "category": "electronics"}

    # Locks
    service._als_lock = MagicMock()
    service._session_lock = MagicMock()
    service._als_model = None
    service._session_stats = None
    service._als_loaded_at = 0
    service._session_loaded_at = 0
    
    # Mock methods that might fail
    service._train_and_save_als_model = MagicMock()
    service._ensure_session_stats = MagicMock()
    
    # Manually trigger session stats build if we want (requires real logic or mock stats)
    # For now let's just use the mock or partial logic
    
    return service

def get_real_service():
    """Try to get the real service."""
    try:
        from services.recommendation_service import get_recommendation_service
        # Check if we can actually connect to something?
        # Just return it, if it crashes later we catch it
        return get_recommendation_service()
    except Exception as e:
        print(f"Failed to initialize real service: {e}")
        return None

def main():
    print("=== Debugging Recommendation Scores ===")
    
    # 1. Load ALS Model to find a valid user
    model = load_als_model(ALS_MODEL_PATH)
    user_id = "test_user"
    if model:
        print(f"[OK] ALS Model loaded. Users: {model.n_users}, Items: {model.n_items}")
        if len(model.user_ids) > 0:
            user_id = str(model.user_ids[0])
            print(f"[INFO] Using real user_id from model: {user_id}")
    else:
        print("[WARN] ALS Model not found. Using 'test_user'.")

    # 2. Initialize Service
    # Try real first, else mock
    service = get_real_service()
    if not service:
        service = mock_recommendation_service()

    print(f"\n--- Checking Scores for User: {user_id} ---\n")

    # 3. Test ALS
    print("[1] ALS Strategy:")
    try:
        # Force load model into service if real
        if model and service._als_model is None:
             service._als_model = model
             
        als_recs = service.get_als_recommendations(user_id, limit=3, train_if_missing=False)
        for rec in als_recs:
            print(f"   - Product: {rec['product_id']}, Score: {rec.get('score')}")
    except Exception as e:
        print(f"   [ERR] Failed: {e}")

    # 4. Test Session
    print("\n[2] Session Strategy:")
    try:
        # If mocking, we need to inject stats or ensure they exist
        if isinstance(service.user_behavior, MagicMock):
             # Inject a dummy transition stats if needed or rely on mocked ensure_session_stats
             pass
             
        session_recs = service.get_session_based_recommendations(user_id, limit=3)
        for rec in session_recs:
             print(f"   - Product: {rec['product_id']}, Score: {rec.get('score')}")
    except Exception as e:
        print(f"   [ERR] Failed: {e}")

    # 5. Test Vector (Personalized)
    print("\n[3] Vector/Content Strategy:")
    try:
        vector_recs = service.get_personalized_recommendations(user_id, limit=3)
        for rec in vector_recs:
            print(f"   - Product: {rec['product_id']}, Score: {rec.get('score')}")
    except Exception as e:
        print(f"   [ERR] Failed: {e}")

    # 6. Test Popularity (Fallback)
    print("\n[4] Popularity Strategy:")
    try:
        pop_recs = service.get_popular_in_category(category=None, limit=3)
        for rec in pop_recs:
            print(f"   - Product: {rec['product_id']}, Score: {rec.get('score')}")
    except Exception as e:
        print(f"   [ERR] Failed: {e}")
        
    # 7. Hybrid
    print("\n[5] HYBRID Combined:")
    try:
        hybrid_recs = service.get_hybrid_recommendations(user_id, limit=5)
        for rec in hybrid_recs:
            print(f"   - Product: {rec['product_id']}, Score: {rec.get('score'):.4f}, Org: {rec.get('original_score', 'N/A')}, Type: {rec.get('recommendation_type')}")
    except Exception as e:
        print(f"   [ERR] Failed: {e}")

    print("\n=== End Debug ===")

if __name__ == "__main__":
    main()

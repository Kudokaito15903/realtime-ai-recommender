import sys
import os
import time
import numpy as np
from typing import List, Dict, Any, Set
from collections import defaultdict
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from loguru import logger
from adapters.factory import get_user_behavior
from services.recommendation_service import get_recommendation_service, RecommendationService
from domain.recommenders.als_recommender import load_als_model
from offline.evaluation.data_split import split_data_by_time
from offline.evaluation.offline_metrics import evaluate_recommendations
from config import ALS_MODEL_PATH

class MockUserBehavior:
    """
    Mocks UserBehavior to return specific history for offline evaluation.
    """
    def __init__(self, train_interactions: List[Dict[str, Any]]):
        self.history_by_user = defaultdict(list)
        # Build history from TRAIN data
        # Sort by timestamp descending (recency) as expected by service
        sorted_interactions = sorted(
            train_interactions, 
            key=lambda x: x.get("timestamp", 0), 
            reverse=True
        )
        for x in sorted_interactions:
            uid = str(x.get("user_id"))
            self.history_by_user[uid].append(x)
            
    def get_user_history(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return self.history_by_user[str(user_id)][:limit]
        
    def get_recent_interactions(self, limit: int = 20000, offset: int = 0) -> List[Dict[str, Any]]:
        # Return all train interactions for session builder
        # Flattened list?
        all_items = []
        for items in self.history_by_user.values():
            all_items.extend(items)
        # re-sort
        all_items.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return all_items[:limit]

    # Mock other methods to avoid errors
    def get_popular_products(self, category=None, limit=10):
        return []
    
    def track_view(self, *args): pass
    def track_click(self, *args): pass
    def track_add_to_cart(self, *args): pass
    def track_purchase(self, *args): pass

def evaluate_hybrid_model(limit: int = 50000):
    logger.info("Starting Offline HYBRID Evaluation...")
    
    # 1. Fetch Real Data
    real_behavior = get_user_behavior()
    interactions = real_behavior.get_recent_interactions(limit=limit)
    if not interactions:
        logger.error("No data found.")
        return

    # 2. Split Data
    train_data, test_data = split_data_by_time(interactions, test_ratio=0.2)
    
    # 3. Setup Mock Behavior with TRAIN data
    mock_behavior = MockUserBehavior(train_data)
    
    # 4. Initialize Service and Inject Mock
    # We need to ensure ALS model is loaded (from file)
    # The service will try to load ALS model from disk.
    # We assume 'evaluate_als.py' or 'train_als.py' has been run to generate the model.
    if not os.path.exists(ALS_MODEL_PATH):
        logger.warning(f"ALS Model not found at {ALS_MODEL_PATH}. Hybrid might degrade.")
        
    service = get_recommendation_service()
    
    # Inject Mock
    # We need to bypass the singleton or modify it
    # RecommendationService is a singleton, so modification affects it globally (fine for script)
    original_behavior = service.user_behavior
    service.user_behavior = mock_behavior
    
    # IMPORTANT: Start fresh session stats based on MOCK data (Train set)
    # Force rebuild of session stats using train data
    service._session_stats = None 
    service._session_loaded_at = 0
    # This will trigger _ensure_session_stats which calls mock_behavior.get_recent_interactions
    
    # 5. Evaluate
    test_ground_truth: Dict[str, Set[str]] = defaultdict(set)
    for x in test_data:
        uid = x.get("user_id")
        pid = x.get("product_id")
        if uid and pid:
            test_ground_truth[str(uid)].add(str(pid))
            
    logger.info(f"Evaluating on {len(test_ground_truth)} test users...")
    
    all_metrics = defaultdict(list)
    k_values = [5, 10, 20]
    
    import time
    start_eval = time.time()
    count = 0
    
    for user_id, ground_truth in test_ground_truth.items():
        # Get Hybrid Recommendations
        try:
            recs = service.get_hybrid_recommendations(user_id, limit=20)
            rec_ids = [r["product_id"] for r in recs]
            
            metrics = evaluate_recommendations(rec_ids, ground_truth, k_values)
            
            for k, v in metrics.items():
                all_metrics[k].append(v)
            
            count += 1
            if count % 100 == 0:
                print(f"Processed {count} users...", end="\r")
        except Exception as e:
            # logger.warning(f"Error for user {user_id}: {e}")
            pass
            
    eval_time = time.time() - start_eval
    
    # Restore behavior (good practice)
    service.user_behavior = original_behavior

    # 6. Report
    print("\n" + "="*50)
    print(f"HYBRID MODEL EVALUATION RESULTS")
    print(f"Train/Test Split: {len(train_data)} / {len(test_data)}")
    print(f"Eval Time: {eval_time:.2f}s")
    print("="*50)
    
    results = {}
    for k in sorted(all_metrics.keys()):
        avg_score = np.mean(all_metrics[k])
        results[k] = avg_score
        print(f"{k:<15}: {avg_score:.4f}")
        
    print("="*50 + "\n")

if __name__ == "__main__":
    evaluate_hybrid_model()

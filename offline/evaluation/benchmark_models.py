import sys
import os
import time
import numpy as np
from typing import List, Dict, Any, Set, Tuple
from collections import defaultdict, Counter

# Add project root to path
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from loguru import logger
from adapters.factory import get_user_behavior
from services.recommendation_service import get_recommendation_service
from offline.evaluation.data_split import split_data_by_time
from offline.evaluation.offline_metrics import evaluate_recommendations, coverage
from config import ALS_MODEL_PATH

class MockUserBehavior:
    """
    Mocks UserBehavior to return historical interactions from TRAIN set.
    """
    def __init__(self, train_interactions: List[Dict[str, Any]]):
        self.history_by_user = defaultdict(list)
        self.all_interactions = train_interactions
        
        # Sort by timestamp descending
        sorted_interactions = sorted(
            train_interactions, 
            key=lambda x: x.get("timestamp", 0), 
            reverse=True
        )
        for x in sorted_interactions:
            uid = str(x.get("user_id"))
            self.history_by_user[uid].append(x)
            
        # Pre-calc popularity
        self.pop_counter = Counter()
        for x in train_interactions:
            pid = x.get("product_id")
            if pid:
                self.pop_counter[str(pid)] += 1
                
    def get_user_history(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return self.history_by_user[str(user_id)][:limit]
        
    def get_recent_interactions(self, limit: int = 20000, offset: int = 0) -> List[Dict[str, Any]]:
        return self.all_interactions[:limit]

    def get_popular_products(self, category=None, limit=10) -> List[Dict[str, Any]]:
        # Return mostly mocked structure
        # We ignore category for simplicity in this benchmark or filter if needed
        # Assuming category=None for global popularity which is common fallback
        top_k = self.pop_counter.most_common(limit)
        return [{"product_id": pid, "count": count} for pid, count in top_k]
    
    def track_view(self, *args): pass
    def track_click(self, *args): pass

def run_benchmark(limit: int = 50000):
    logger.info("Starting Benchmark...")
    
    # 1. Pipeline Setup
    real_behavior = get_user_behavior()
    interactions = real_behavior.get_recent_interactions(limit=limit)
    if not interactions:
        logger.error("No data found.")
        return

    train_data, test_data = split_data_by_time(interactions, test_ratio=0.2)
    mock_behavior = MockUserBehavior(train_data)
    
    # All train items for coverage calculation
    all_train_items = {str(x.get("product_id")) for x in train_data if x.get("product_id")}
    
    # 2. Service Injection
    service = get_recommendation_service()
    original_behavior = service.user_behavior
    service.user_behavior = mock_behavior
    service._session_stats = None 
    service._session_loaded_at = 0
    
    # 3. Test Set Prep
    test_ground_truth: Dict[str, Set[str]] = defaultdict(set)
    for x in test_data:
        uid = x.get("user_id")
        pid = x.get("product_id")
        if uid and pid:
            test_ground_truth[str(uid)].add(str(pid))
            
    test_users = list(test_ground_truth.keys())
    # Limit users for speed if needed, but let's run full set
    # test_users = test_users[:50] 
    
    models = ["Popularity", "ALS", "Embedding", "Hybrid"]
    results = {m: defaultdict(list) for m in models}
    coverage_sets = {m: set() for m in models}
    
    logger.info(f"Evaluating {len(test_users)} users across {len(models)} models...")
    
    for i, user_id in enumerate(test_users):
        ground_truth = test_ground_truth[user_id]
        
        # --- Evaluate per model ---
        
        # 1. Popularity
        try:
            # direct call to mock behavior or service wrapper
            pop_items = service.get_popular_in_category(None, limit=20)
            recs = [str(x["product_id"]) for x in pop_items]
            metrics = evaluate_recommendations(recs, ground_truth, [10, 20])
            results["Popularity"]["hr@10"].append(metrics["hr@10"])
            results["Popularity"]["ndcg@10"].append(metrics["ndcg@10"])
            results["Popularity"]["recall@20"].append(metrics["recall@20"])
            coverage_sets["Popularity"].update(recs)
        except Exception: pass
        
        # 2. ALS
        try:
            als_items = service.get_als_recommendations(user_id, limit=20, train_if_missing=False)
            recs = [str(x["product_id"]) for x in als_items]
            metrics = evaluate_recommendations(recs, ground_truth, [10, 20])
            results["ALS"]["hr@10"].append(metrics["hr@10"])
            results["ALS"]["ndcg@10"].append(metrics["ndcg@10"])
            results["ALS"]["recall@20"].append(metrics["recall@20"])
            coverage_sets["ALS"].update(recs)
        except Exception: pass

        # 3. Embedding (Personalized Vector)
        try:
            emb_items = service.get_personalized_recommendations(user_id, limit=20)
            recs = [str(x["product_id"]) for x in emb_items]
            metrics = evaluate_recommendations(recs, ground_truth, [10, 20])
            results["Embedding"]["hr@10"].append(metrics["hr@10"])
            results["Embedding"]["ndcg@10"].append(metrics["ndcg@10"])
            results["Embedding"]["recall@20"].append(metrics["recall@20"])
            coverage_sets["Embedding"].update(recs)
        except Exception: pass

        # 4. Hybrid
        try:
            hyb_items = service.get_hybrid_recommendations(user_id, limit=20)
            recs = [str(x["product_id"]) for x in hyb_items]
            metrics = evaluate_recommendations(recs, ground_truth, [10, 20])
            results["Hybrid"]["hr@10"].append(metrics["hr@10"])
            results["Hybrid"]["ndcg@10"].append(metrics["ndcg@10"])
            results["Hybrid"]["recall@20"].append(metrics["recall@20"])
            coverage_sets["Hybrid"].update(recs)
        except Exception: pass
        
        if i % 50 == 0:
            print(f"Processed {i}/{len(test_users)} users...", end="\r")

    # Restore behavior
    service.user_behavior = original_behavior

    # Print Table
    print("\n\n" + "="*65)
    print(f"{'Model':<20} | {'Recall@20':<10} | {'NDCG@10':<10} | {'HR@10':<10} | {'Coverage':<10}")
    print("-" * 65)
    
    total_items_count = len(all_train_items) if all_train_items else 1
    
    start_bold = "\033[1m"
    end_bold = "\033[0m"
    
    def fmt_num(n): return f"{n:.3f}"
    
    # Sort models by NDCG or defined order
    for model in models:
        m_res = results[model]
        if not m_res["ndcg@10"]:
            continue
            
        r20 = np.mean(m_res["recall@20"])
        n10 = np.mean(m_res["ndcg@10"])
        h10 = np.mean(m_res["hr@10"])
        cov = len(coverage_sets[model]) / total_items_count * 100
        
        # Simple bold logic for Hybrid if it's the best (assumed)
        row_str = f"{model:<20} | {fmt_num(r20):<10} | {fmt_num(n10):<10} | {fmt_num(h10):<10} | {cov:.1f}%"
        print(row_str)
        
    print("="*65 + "\n")

if __name__ == "__main__":
    run_benchmark()

"""
Offline Version of Session Recommender Evaluation
"""

import sys
import os
import time
import math
from typing import List, Dict, Any, Tuple
from collections import defaultdict
import numpy as np

# Add project root to path
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from loguru import logger
from adapters.database.mongodb_adapter import get_mongodb_user_behavior, get_mongodb_product_store
from domain.recommenders.session_recommender import (
    build_session_transitions,
    recommend_next_items,
    SessionTransitionStats,
)
from offline.evaluation.offline_metrics import evaluate_recommendations  # Reusing existing metrics

def reconstruct_sessions(
    interactions: List[Dict[str, Any]], 
    session_gap_seconds: int = 1800
) -> List[List[Dict[str, Any]]]:
    """
    Group interactions into sessions.
    Respects explicit 'session_id' if present, otherwise infers by time gap.
    """
    # 1. Group by session_key (explicit ID or user_id)
    grouped = defaultdict(list)
    for row in interactions:
        sid = row.get("session_id")
        uid = row.get("user_id")
        
        if sid:
            key = f"sid:{sid}"
        elif uid:
            key = f"uid:{uid}"
        else:
            continue
            
        grouped[key].append(row)
        
    final_sessions = []
    
    # 2. Split by time gap for inferred sessions
    for key, items in grouped.items():
        # Sort by timestamp
        items.sort(key=lambda x: x.get("timestamp", ""))
        
        if key.startswith("sid:"):
            # Explicit session, take as is
            final_sessions.append(items)
        else:
            # Inferred session, split by gap
            current_session = []
            last_ts = 0
            
            for item in items:
                ts_str = item.get("timestamp")
                # Parse ts (assuming isoformat or similar, or float)
                # For simplicity in this script, let's assume valid ISO strings from DB adapter
                try:
                    if isinstance(ts_str, str):
                        # Simple check for Z
                        s = ts_str.replace("Z", "+00:00")
                        ts = time.mktime(time.fromisoformat(s).timetuple())
                    else:
                        ts = float(ts_str)
                except Exception:
                    ts = 0
                    
                if not current_session:
                    current_session.append(item)
                    last_ts = ts
                else:
                    if (ts - last_ts) > session_gap_seconds:
                        final_sessions.append(current_session)
                        current_session = [item]
                    else:
                        current_session.append(item)
                    last_ts = ts
                    
            if current_session:
                final_sessions.append(current_session)
                
    return final_sessions

def evaluate_session_recommender():
    logger.info("Starting Offline Session Recommender Evaluation...")
    
    behavior = get_mongodb_user_behavior()
    product_store = get_mongodb_product_store()
    
    # 1. Fetch Interactions (Limit to recent 50000 for speed)
    interactions = behavior.get_recent_interactions(limit=50000)
    logger.info(f"Fetched {len(interactions)} raw interactions.")
    
    if not interactions:
        logger.warning("No interactions found. Aborting.")
        return

    # 2. Reconstruct Sessions
    sessions = reconstruct_sessions(interactions, session_gap_seconds=1800)
    # Filter short sessions
    sessions = [s for s in sessions if len(s) >= 2]
    logger.info(f"Reconstructed {len(sessions)} sessions (length >= 2).")
    
    if len(sessions) < 5:
        logger.warning("Not enough sessions for split. Need at least 5.")
        return

    # 3. Train/Test Split (80/20)
    # Shuffle first? preserving time order is better usually, but sessions are distinct units
    # Let's shuffle session-wise for randomness in limited data
    import random
    random.shuffle(sessions)
    
    split_idx = int(len(sessions) * 0.8)
    train_sessions = sessions[:split_idx]
    test_sessions = sessions[split_idx:]
    
    logger.info(f"Train sessions: {len(train_sessions)}")
    logger.info(f"Test sessions: {len(test_sessions)}")
    
    # Flatten train sessions for build_session_transitions
    train_interactions = [item for session in train_sessions for item in session]
    
    # 4. Build Model (Transition Stats)
    logger.info("Building transition stats from training data...")
    start_time = time.time()
    stats = build_session_transitions(train_interactions, product_store=product_store)
    logger.info(f"Built stats in {time.time() - start_time:.4f}s")
    
    # 5. Evaluate on Test Set
    logger.info("Evaluating on Test Set...")
    
    k_values = [5, 10, 20]
    metrics_sum = defaultdict(float)
    count = 0
    
    for session in test_sessions:
        # Leave-one-out evaluation
        # Given items[0...N-1], predict items[N]
        # Or evaluated at every step? Let's do "Predict Last Item" for simplicity of a session goal.
        
        ground_truth_item = session[-1].get("product_id")
        context_items = [x.get("product_id") for x in session[:-1]]
        
        if not ground_truth_item or not context_items:
            continue
            
        # Get recommendations
        # Note: recommend_next_items returns list of (pid, score) tuples
        recs = recommend_next_items(
            stats=stats,
            current_session_items=context_items,
            limit=20
        )
        
        rec_ids = [r[0] for r in recs]
        
        # Calculate metrics
        ground_truth_set = {str(ground_truth_item)}
        
        # Using evaluate_recommendations from offline_metrics
        session_metrics = evaluate_recommendations(rec_ids, ground_truth_set, k_values)
        
        for k, v in session_metrics.items():
            metrics_sum[k] += v
        count += 1

    # 6. Report Results
    if count == 0:
        logger.warning("No valid test cases found.")
        return

    print("\n" + "="*50)
    print(f"SESSION RECOMMENDER EVALUATION RESULTS")
    print(f"Test Cases: {count}")
    print("="*50)
    
    results = {}
    for k in sorted(metrics_sum.keys()):
        avg_score = metrics_sum[k] / count
        results[k] = avg_score
        print(f"{k:<15}: {avg_score:.4f}")
        
    print("="*50 + "\n")

if __name__ == "__main__":
    evaluate_session_recommender()

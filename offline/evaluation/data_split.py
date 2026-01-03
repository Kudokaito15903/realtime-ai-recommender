import time
from typing import List, Dict, Any, Tuple
from loguru import logger

def split_data_by_time(
    interactions: List[Dict[str, Any]],
    test_ratio: float = 0.2,
    min_interactions: int = 5
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Split interactions into train and test sets based on time.
    
    Args:
        interactions: List of interaction dictionaries. Must contain 'timestamp'.
        test_ratio: Fraction of data to use for testing (based on time).
        min_interactions: Minimum interactions required for a user to be included in Test.
        
    Returns:
        Tuple of (train_interactions, test_interactions)
    """
    if not interactions:
        return [], []
        
    # Sort by timestamp
    try:
        sorted_interactions = sorted(
            interactions, 
            key=lambda x: parse_timestamp(x.get("timestamp"))
        )
    except Exception as e:
        logger.error(f"Failed to sort interactions by timestamp: {e}")
        return [], []
        
    split_index = int(len(sorted_interactions) * (1 - test_ratio))
    
    # Initial split
    train_data = sorted_interactions[:split_index]
    test_candidates = sorted_interactions[split_index:]
    
    # Validation: Ensure users in Test also exist in Train (Cold-start handling)
    # For offline evaluation of algorithms like ALS, we typically want to evaluate 
    # on users the model has seen at least once.
    
    train_users = {str(x.get("user_id")) for x in train_data if x.get("user_id")}
    
    final_test = []
    dropped_test_count = 0
    
    for item in test_candidates:
        user_id = str(item.get("user_id"))
        if user_id in train_users:
            final_test.append(item)
        else:
            # If user is not in train, we can't evaluate personalized recs for them 
            # (unless checking cold-start specifically). For now, move to train 
            # or drop? moving to train effectively ignores them for test.
            # Let's drop them from evaluation to keep test set clean.
            dropped_test_count += 1
            
    logger.info(f"Data Split Summary:")
    logger.info(f"  Total Interactions: {len(interactions)}")
    logger.info(f"  Train Set: {len(train_data)}")
    logger.info(f"  Test Set: {len(final_test)} (Dropped {dropped_test_count} cold-start events)")
    
    return train_data, final_test

def parse_timestamp(ts: Any) -> float:
    """Helper to parse timestamp to float."""
    if isinstance(ts, (int, float)):
        return float(ts)
    if isinstance(ts, str):
        # Basic parsing, can be improved based on DB format
        try:
            return time.mktime(time.fromisoformat(ts.replace("Z", "+00:00")).timetuple())
        except:
            return 0.0
    return 0.0

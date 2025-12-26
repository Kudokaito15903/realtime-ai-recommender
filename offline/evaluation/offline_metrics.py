"""
Offline Metrics - Offline ML Pipeline
Evaluation metrics for recommendation models.
"""

import os
import sys
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict

import numpy as np
from loguru import logger

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def precision_at_k(
    recommended: List[str],
    relevant: Set[str],
    k: int,
) -> float:
    """
    Calculate Precision@K.
    
    Args:
        recommended: List of recommended item IDs
        relevant: Set of relevant (ground truth) item IDs
        k: Number of top recommendations to consider
        
    Returns:
        Precision@K score
    """
    if k == 0:
        return 0.0
    
    top_k = recommended[:k]
    if not top_k:
        return 0.0
    
    relevant_count = sum(1 for item in top_k if item in relevant)
    return relevant_count / len(top_k)


def recall_at_k(
    recommended: List[str],
    relevant: Set[str],
    k: int,
) -> float:
    """
    Calculate Recall@K.
    
    Args:
        recommended: List of recommended item IDs
        relevant: Set of relevant (ground truth) item IDs
        k: Number of top recommendations to consider
        
    Returns:
        Recall@K score
    """
    if not relevant:
        return 0.0
    
    top_k = recommended[:k]
    if not top_k:
        return 0.0
    
    relevant_count = sum(1 for item in top_k if item in relevant)
    return relevant_count / len(relevant)


def ndcg_at_k(
    recommended: List[str],
    relevant: Set[str],
    k: int,
) -> float:
    """
    Calculate Normalized Discounted Cumulative Gain@K.
    
    Args:
        recommended: List of recommended item IDs
        relevant: Set of relevant (ground truth) item IDs
        k: Number of top recommendations to consider
        
    Returns:
        NDCG@K score
    """
    if not relevant or k == 0:
        return 0.0
    
    top_k = recommended[:k]
    if not top_k:
        return 0.0
    
    # Calculate DCG
    dcg = 0.0
    for i, item in enumerate(top_k):
        if item in relevant:
            # Position is i+1 (1-indexed)
            dcg += 1.0 / np.log2(i + 2)  # log2(i+2) because position is i+1
    
    # Calculate IDCG (ideal DCG)
    idcg = 0.0
    num_relevant = min(len(relevant), k)
    for i in range(num_relevant):
        idcg += 1.0 / np.log2(i + 2)
    
    if idcg == 0:
        return 0.0
    
    return dcg / idcg


def mean_reciprocal_rank(
    recommended: List[str],
    relevant: Set[str],
) -> float:
    """
    Calculate Mean Reciprocal Rank (MRR).
    
    Args:
        recommended: List of recommended item IDs
        relevant: Set of relevant (ground truth) item IDs
        
    Returns:
        MRR score
    """
    if not relevant:
        return 0.0
    
    for i, item in enumerate(recommended):
        if item in relevant:
            return 1.0 / (i + 1)
    
    return 0.0


def coverage(
    all_recommendations: List[List[str]],
    all_items: Set[str],
) -> float:
    """
    Calculate catalog coverage (percentage of items recommended).
    
    Args:
        all_recommendations: List of recommendation lists for all users
        all_items: Set of all available items
        
    Returns:
        Coverage score (0.0 to 1.0)
    """
    if not all_items:
        return 0.0
    
    recommended_items = set()
    for recommendations in all_recommendations:
        recommended_items.update(recommendations)
    
    return len(recommended_items) / len(all_items)


def diversity(
    recommendations: List[str],
    item_features: Optional[Dict[str, Any]] = None,
) -> float:
    """
    Calculate diversity of recommendations (intra-list diversity).
    
    Args:
        recommendations: List of recommended item IDs
        item_features: Optional dictionary mapping item IDs to feature vectors
        
    Returns:
        Diversity score (higher = more diverse)
    """
    if len(recommendations) < 2:
        return 0.0
    
    if item_features is None:
        # Simple diversity: count unique items
        return len(set(recommendations)) / len(recommendations)
    
    # Calculate average pairwise distance
    features = []
    for item_id in recommendations:
        if item_id in item_features:
            features.append(item_features[item_id])
    
    if len(features) < 2:
        return 0.0
    
    features_array = np.array(features)
    distances = []
    for i in range(len(features_array)):
        for j in range(i + 1, len(features_array)):
            dist = np.linalg.norm(features_array[i] - features_array[j])
            distances.append(dist)
    
    if not distances:
        return 0.0
    
    return np.mean(distances)


def evaluate_recommendations(
    recommendations: List[str],
    ground_truth: Set[str],
    k_values: List[int] = [5, 10, 20],
) -> Dict[str, float]:
    """
    Evaluate recommendations against ground truth.
    
    Args:
        recommendations: List of recommended item IDs
        ground_truth: Set of relevant (ground truth) item IDs
        k_values: List of K values for evaluation
        
    Returns:
        Dictionary of metric scores
    """
    metrics = {}
    
    for k in k_values:
        metrics[f"precision@{k}"] = precision_at_k(recommendations, ground_truth, k)
        metrics[f"recall@{k}"] = recall_at_k(recommendations, ground_truth, k)
        metrics[f"ndcg@{k}"] = ndcg_at_k(recommendations, ground_truth, k)
    
    metrics["mrr"] = mean_reciprocal_rank(recommendations, ground_truth)
    
    return metrics


def evaluate_model_offline(
    test_data: List[Dict[str, Any]],
    recommendation_function: callable,
    k_values: List[int] = [5, 10, 20],
) -> Dict[str, float]:
    """
    Evaluate a recommendation model on test data.
    
    Args:
        test_data: List of test cases, each with 'user_id' and 'ground_truth' (set of item IDs)
        recommendation_function: Function that takes user_id and returns list of recommended item IDs
        k_values: List of K values for evaluation
        
    Returns:
        Dictionary of average metric scores
    """
    all_metrics = defaultdict(list)
    
    for test_case in test_data:
        user_id = test_case.get("user_id")
        ground_truth = test_case.get("ground_truth", set())
        
        if not user_id or not ground_truth:
            continue
        
        try:
            recommendations = recommendation_function(user_id)
            if not recommendations:
                continue
            
            metrics = evaluate_recommendations(recommendations, ground_truth, k_values)
            
            for metric_name, value in metrics.items():
                all_metrics[metric_name].append(value)
        except Exception as e:
            logger.warning(f"Error evaluating for user {user_id}: {e}")
            continue
    
    # Calculate averages
    avg_metrics = {}
    for metric_name, values in all_metrics.items():
        if values:
            avg_metrics[metric_name] = np.mean(values)
        else:
            avg_metrics[metric_name] = 0.0
    
    logger.info(f"Evaluated {len(test_data)} test cases")
    return avg_metrics


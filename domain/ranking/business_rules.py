"""
Business Rules - Domain Layer
Core business logic for filtering and applying business rules to recommendations.
"""

from typing import List, Dict, Any, Optional, Callable
from loguru import logger


def filter_by_business_rules(
    products: List[Dict[str, Any]],
    rules: Optional[List[Callable[[Dict[str, Any]], bool]]] = None
) -> List[Dict[str, Any]]:
    """
    Filter products based on business rules.
    
    Args:
        products: List of products to filter
        rules: Optional list of rule functions (predicates)
        
    Returns:
        Filtered list of products
    """
    if not products:
        return []
    
    if rules is None:
        # Default rules
        rules = [
            lambda p: p.get("price", 0) > 0,  # Must have price
            lambda p: p.get("status") != "out_of_stock",  # Must be in stock
        ]
    
    filtered = []
    for product in products:
        if all(rule(product) for rule in rules):
            filtered.append(product)
        else:
            logger.debug(f"Product {product.get('product_id')} filtered by business rules")
    
    return filtered


def apply_business_rules(
    products: List[Dict[str, Any]],
    rules: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Apply business rules to products (filtering, boosting, etc.).
    
    Args:
        products: List of products
        rules: Optional dictionary of rule configurations
        
    Returns:
        Products with business rules applied
    """
    if not products:
        return []
    
    if rules is None:
        rules = {
            "min_price": 0,
            "max_price": float("inf"),
            "exclude_categories": [],
            "boost_categories": [],
            "require_in_stock": True,
        }
    
    filtered = []
    for product in products:
        # Apply filters
        price = float(product.get("price", 0) or 0)
        if price < rules.get("min_price", 0):
            continue
        if price > rules.get("max_price", float("inf")):
            continue
        
        category = product.get("category", "")
        if category in rules.get("exclude_categories", []):
            continue
        
        if rules.get("require_in_stock", True):
            if product.get("status") == "out_of_stock":
                continue
        
        # Apply boosts
        boost = 1.0
        if category in rules.get("boost_categories", []):
            boost = 1.2
        
        # Add boost to score
        if "score" in product:
            product["score"] = float(product["score"]) * boost
        if "similarity_score" in product:
            product["similarity_score"] = float(product["similarity_score"]) * boost
        
        filtered.append(product)
    
    return filtered


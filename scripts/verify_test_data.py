
import sys
import os
from loguru import logger

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.factory import get_product_store, get_content_store

def verify_data():
    logger.info("Verifying Data Insertion...")
    
    # Check Products
    p_store = get_product_store()
    phones = p_store.list_products(category="smartphone") # categoryId is lower case in generate script
    logger.info(f"Found {len(phones)} smartphones")
    for p in phones:
        logger.info(f"- {p['name']} ({p['id']})")
        
    laptops = p_store.list_products(category="laptop")
    logger.info(f"Found {len(laptops)} laptops")
    for p in laptops:
         logger.info(f"- {p['name']} ({p['id']})")
         
    # Check Content
    c_store = get_content_store()
    policies = c_store.list_content(category="Policy")
    logger.info(f"Found {len(policies)} policies")
    for c in policies:
        logger.info(f"- {c['title']} ({c['id']})")

if __name__ == "__main__":
    verify_data()

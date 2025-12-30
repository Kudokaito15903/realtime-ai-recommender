import requests
import random
import time
import concurrent.futures
from typing import List, Dict

# Configuration
API_BASE_URL = "http://localhost:8000/recommendations"
NUM_USERS = 20
TOTAL_INTERACTIONS = 500
CONCURRENCY = 10

# List of product IDs provided by the user
PRODUCT_IDS = [
    "6953da2295c7d448468c7cf4", "6953da2595c7d448468c7cf6", "6953da2795c7d448468c7cf8",
    "6953da2995c7d448468c7cfa", "6953da2b95c7d448468c7cfc", "6953da2d95c7d448468c7cfe",
    "6953da2f95c7d448468c7d00", "6953da3195c7d448468c7d02", "6953da3395c7d448468c7d04",
    "6953da3595c7d448468c7d06", "6953da3795c7d448468c7d08", "6953da3995c7d448468c7d0a",
    "6953da3b95c7d448468c7d0c", "6953da3d95c7d448468c7d0e", "6953da3f95c7d448468c7d10",
    "6953da4195c7d448468c7d12", "6953da4395c7d448468c7d14", "6953da4595c7d448468c7d16",
    "6953da4895c7d448468c7d18", "6953da4a95c7d448468c7d1a", "6953da4c95c7d448468c7d1c",
    "6953da4e95c7d448468c7d1e", "6953da5095c7d448468c7d20", "6953da5295c7d448468c7d22",
    "6953da5495c7d448468c7d24", "6953da5695c7d448468c7d26", "6953da5895c7d448468c7d28",
    "6953da5a95c7d448468c7d2a", "6953da5c95c7d448468c7d2c", "6953da5e95c7d448468c7d2e",
    "6953da6095c7d448468c7d30", "6953da6295c7d448468c7d32", "6953da6495c7d448468c7d34",
    "6953da6695c7d448468c7d36", "6953da6895c7d448468c7d38", "6953da6a95c7d448468c7d3a",
    "6953da6c95c7d448468c7d3c", "6953da6f95c7d448468c7d3e", "6953da7195c7d448468c7d40",
    "6953da7395c7d448468c7d42", "6953da7595c7d448468c7d44", "6953da7795c7d448468c7d46",
    "6953da7995c7d448468c7d48", "6953da7b95c7d448468c7d4a", "6953da7d95c7d448468c7d4c",
    "6953da7f95c7d448468c7d4e", "6953da8195c7d448468c7d50", "6953da8395c7d448468c7d52",
    "6953da8595c7d448468c7d54", "6953da8795c7d448468c7d56", "6953da8995c7d448468c7d58",
    "6953da8b95c7d448468c7d5a", "6953da8d95c7d448468c7d5c", "6953da8f95c7d448468c7d5e",
    "6953da9195c7d448468c7d60", "6953da9495c7d448468c7d62", "6953da9695c7d448468c7d64",
    "6953da9895c7d448468c7d66", "6953da9a95c7d448468c7d68", "6953da9c95c7d448468c7d6a",
    "6953da9e95c7d448468c7d6c", "6953daa095c7d448468c7d6e", "6953daa295c7d448468c7d70",
    "6953daa495c7d448468c7d72", "6953daa695c7d448468c7d74", "6953daa895c7d448468c7d76",
    "6953daaa95c7d448468c7d78", "6953daac95c7d448468c7d7a", "6953daae95c7d448468c7d7c",
    "6953dab095c7d448468c7d7e", "6953dab295c7d448468c7d80", "6953dab495c7d448468c7d82",
    "6953dab695c7d448468c7d84", "6953dab995c7d448468c7d86", "6953dabb95c7d448468c7d88",
    "6953dabd95c7d448468c7d8a", "6953dabf95c7d448468c7d8c", "6953dac195c7d448468c7d8e",
    "6953dac395c7d448468c7d90", "6953dac595c7d448468c7d92", "6953dac795c7d448468c7d94",
    "6953dac995c7d448468c7d96", "6953dacb95c7d448468c7d98", "6953dacd95c7d448468c7d9a",
    "6953dacf95c7d448468c7d9c", "6953dad195c7d448468c7d9e", "6953dad395c7d448468c7da0",
    "6953dad595c7d448468c7da2", "6953dad795c7d448468c7da4", "6953dad995c7d448468c7da6",
    "6953dadb95c7d448468c7da8", "6953dadd95c7d448468c7daa", "6953dae095c7d448468c7dac",
    "6953dae295c7d448468c7dae", "6953dae495c7d448468c7db0", "6953dae695c7d448468c7db2",
    "6953dae895c7d448468c7db4", "6953daea95c7d448468c7db6", "6953daec95c7d448468c7db8",
    "6953daee95c7d448468c7dba"
]

INTERACTION_TYPES = [
    # (endpoint, weight)
    ("track-view", 70),
    ("track-click", 20),
    ("track-add-to-cart", 7),
    ("track-purchase", 3)
]

def generate_users_and_clusters():
    """
    1. Organize products into hypothetical 'clusters' (categories).
    2. Create users and assign them preferred clusters to simulate 'taste'.
    """
    random.shuffle(PRODUCT_IDS)
    # Split products into 4 clusters
    n = len(PRODUCT_IDS)
    chunk_size = n // 4 + 1
    clusters = [PRODUCT_IDS[i:i + chunk_size] for i in range(0, n, chunk_size)]
    
    users = []
    for i in range(NUM_USERS):
        user_id = f"user_{i+1:03d}"
        # User prefers 1 main cluster and 1 secondary cluster
        preferences = random.sample(range(len(clusters)), 2)
        users.append({
            "id": user_id,
            "main_cluster": preferences[0],
            "secondary_cluster": preferences[1]
        })
    
    return clusters, users

def perform_interaction(user, clusters):
    # Determine which product to interact with based on user preference
    roll = random.random()
    if roll < 0.6:
        # 60% chance: Choose from main cluster
        cluster_idx = user["main_cluster"]
    elif roll < 0.8:
        # 20% chance: Choose from secondary cluster
        cluster_idx = user["secondary_cluster"]
    else:
        # 20% chance: Random cluster (exploration)
        cluster_idx = random.randint(0, len(clusters) - 1)
        
    cluster_products = clusters[cluster_idx]
    if not cluster_products:
        product_id = random.choice(PRODUCT_IDS)
    else:
        product_id = random.choice(cluster_products)
    
    # Select interaction type based on weights
    types, weights = zip(*INTERACTION_TYPES)
    interaction_type = random.choices(types, weights=weights, k=1)[0]
    
    endpoint = f"{API_BASE_URL}/{interaction_type}"
    params = {"product_id": product_id}
    headers = {"user-id": user["id"]}
    
    try:
        response = requests.post(endpoint, params=params, headers=headers, timeout=5)
        return response.status_code == 200, interaction_type, user["id"], product_id
    except Exception:
        return False, interaction_type, user["id"], product_id

def main():
    print(f"Preparing to simulate {TOTAL_INTERACTIONS} interactions for {NUM_USERS} users...", flush=True)
    
    clusters, users = generate_users_and_clusters()
    print(f"Created {len(clusters)} product clusters", flush=True)
    print(f"Created {len(users)} users with preferences", flush=True)

    success_count = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = []
        for _ in range(TOTAL_INTERACTIONS):
            user = random.choice(users)
            futures.append(executor.submit(perform_interaction, user, clusters))
            
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            success, itype, uid, pid = future.result()
            if success:
                success_count += 1
                if i % 10 == 0:  # Print more frequently (every 10)
                    print(f"[{i}/{TOTAL_INTERACTIONS}] Success: {itype} by {uid}", flush=True)
            else:
                 if i % 10 == 0:
                    print(f"[{i}/{TOTAL_INTERACTIONS}] Failed", flush=True)

    print(f"\nSimulation complete! Successful interactions: {success_count}/{TOTAL_INTERACTIONS}", flush=True)

if __name__ == "__main__":
    main()

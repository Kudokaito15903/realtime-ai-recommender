import requests
import random
import time
import concurrent.futures
from typing import List, Dict, Tuple
from collections import Counter

# =========================
# CONFIGURATION
# =========================
API_BASE_URL = "http://localhost:8000/recommendations"
API_PRODUCTS_URL = "http://localhost:8000/products/"

NUM_USERS = 20
TOTAL_INTERACTIONS = 5000
CONCURRENCY = 10
REQUEST_TIMEOUT = 5
MAX_RETRIES = 2

RANDOM_SEED = 42
random.seed(RANDOM_SEED)

# Interaction types with weights (implicit feedback)
INTERACTION_TYPES = [
    ("track-view", 70),
    ("track-click", 20),
    ("track-add-to-cart", 7),
    ("track-purchase", 3),
]

# =========================
# FETCH PRODUCTS
# =========================
def get_real_product_ids(limit: int = 100) -> List[str]:
    try:
        resp = requests.get(
            API_PRODUCTS_URL,
            params={"limit": limit},
            timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()

        products = resp.json()
        ids = [p["id"] for p in products if "id" in p]

        print(f"[INFO] Fetched {len(ids)} products")
        return ids

    except Exception as e:
        print(f"[ERROR] Failed to fetch products: {e}")
        return []


PRODUCT_IDS = get_real_product_ids()

if not PRODUCT_IDS:
    raise RuntimeError("No products found. Stop simulation.")


# =========================
# USER + CLUSTER GENERATION
# =========================
def generate_users_and_clusters(
    product_ids: List[str],
    num_users: int,
    num_clusters: int = 4
) -> Tuple[List[List[str]], List[Dict]]:
    """
    - Split products into clusters (simulating categories)
    - Assign each user a main & secondary preference
    """
    shuffled = product_ids[:]
    random.shuffle(shuffled)

    chunk_size = len(shuffled) // num_clusters + 1
    clusters = [
        shuffled[i:i + chunk_size]
        for i in range(0, len(shuffled), chunk_size)
    ]

    users = []
    for i in range(num_users):
        main, secondary = random.sample(range(len(clusters)), 2)
        users.append({
            "id": f"user_{i+1:03d}",
            "main_cluster": main,
            "secondary_cluster": secondary
        })

    return clusters, users


# =========================
# INTERACTION LOGIC
# =========================
def choose_product(user: Dict, clusters: List[List[str]]) -> str:
    """
    User behavior:
    - 60% main interest
    - 20% secondary interest
    - 20% exploration
    """
    r = random.random()

    if r < 0.7:
        cluster = clusters[user["main_cluster"]]
    elif r < 0.9:
        cluster = clusters[user["secondary_cluster"]]
    else:
        # 10% chance: Random cluster (exploration)
        cluster = random.choice(clusters)

    if cluster:
        return random.choice(cluster)

    return random.choice(PRODUCT_IDS)


def choose_interaction_type() -> str:
    types, weights = zip(*INTERACTION_TYPES)
    return random.choices(types, weights=weights, k=1)[0]


def send_event(
    user_id: str,
    product_id: str,
    interaction_type: str
) -> bool:
    endpoint = f"{API_BASE_URL}/{interaction_type}"

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.post(
                endpoint,
                params={"product_id": product_id},
                headers={"user-id": user_id},
                timeout=REQUEST_TIMEOUT
            )
            return resp.status_code == 200

        except Exception:
            if attempt == MAX_RETRIES:
                return False
            time.sleep(0.2)


def perform_interaction(
    user: Dict,
    clusters: List[List[str]]
) -> Tuple[bool, str]:
    product_id = choose_product(user, clusters)
    interaction_type = choose_interaction_type()

    success = send_event(
        user_id=user["id"],
        product_id=product_id,
        interaction_type=interaction_type
    )

    return success, interaction_type


# =========================
# MAIN SIMULATION
# =========================
def main():
    print("=" * 60)
    print("USER BEHAVIOR SIMULATION START")
    print("=" * 60)

    clusters, users = generate_users_and_clusters(
        PRODUCT_IDS,
        NUM_USERS
    )

    print(f"[INFO] Users        : {len(users)}")
    print(f"[INFO] Clusters     : {len(clusters)}")
    print(f"[INFO] Interactions : {TOTAL_INTERACTIONS}")
    print(f"[INFO] Concurrency  : {CONCURRENCY}")
    print("-" * 60)

    success_count = 0
    interaction_counter = Counter()

    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=CONCURRENCY
    ) as executor:

        futures = [
            executor.submit(
                perform_interaction,
                random.choice(users),
                clusters
            )
            for _ in range(TOTAL_INTERACTIONS)
        ]

        for idx, future in enumerate(
            concurrent.futures.as_completed(futures),
            start=1
        ):
            success, interaction_type = future.result()

            if success:
                success_count += 1
                interaction_counter[interaction_type] += 1

            if idx % 25 == 0:
                print(
                    f"[{idx}/{TOTAL_INTERACTIONS}] "
                    f"Success: {success_count}"
                )

    elapsed = time.time() - start_time

    print("\n" + "=" * 60)
    print("SIMULATION SUMMARY")
    print("=" * 60)
    print(f"Successful events : {success_count}/{TOTAL_INTERACTIONS}")
    print(f"Elapsed time     : {elapsed:.2f}s")
    print("\nInteraction distribution:")
    for k, v in interaction_counter.items():
        print(f"  - {k:20s}: {v}")

    print("=" * 60)


if __name__ == "__main__":
    main()

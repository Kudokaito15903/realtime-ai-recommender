"""
Offline Manual Verification (Time-Decay Aware)
"""

import time
from loguru import logger

from domain.recommenders.session_recommender import (
    build_session_transitions,
    recommend_next_items,
)


def run_manual_check():
    logger.info("Running Offline Manual Check (with valid time decay)...")

    now = time.time()

    # Synthetic history with realistic timestamps
    interactions = [
        # Session A: Phone -> Case (recent)
        {
            "user_id": "u1",
            "session_id": "s1",
            "product_id": "phone_123",
            "timestamp": now - 600,
        },
        {
            "user_id": "u1",
            "session_id": "s1",
            "product_id": "case_123",
            "timestamp": now - 590,
        },
        # Session B: Phone -> Case (recent)
        {
            "user_id": "u2",
            "session_id": "s2",
            "product_id": "phone_123",
            "timestamp": now - 500,
        },
        {
            "user_id": "u2",
            "session_id": "s2",
            "product_id": "case_123",
            "timestamp": now - 490,
        },
        # Session C: Phone -> Charger (older → weaker)
        {
            "user_id": "u3",
            "session_id": "s3",
            "product_id": "phone_123",
            "timestamp": now - 3 * 24 * 3600,
        },
        {
            "user_id": "u3",
            "session_id": "s3",
            "product_id": "charger_123",
            "timestamp": now - 3 * 24 * 3600 + 10,
        },
        # Session D: Case -> Charger (very recent)
        {
            "user_id": "u4",
            "session_id": "s4",
            "product_id": "case_123",
            "timestamp": now - 300,
        },
        {
            "user_id": "u4",
            "session_id": "s4",
            "product_id": "charger_123",
            "timestamp": now - 290,
        },
        # Session E: Case -> Charger (recent)
        {
            "user_id": "u5",
            "session_id": "s5",
            "product_id": "case_123",
            "timestamp": now - 200,
        },
        {
            "user_id": "u5",
            "session_id": "s5",
            "product_id": "charger_123",
            "timestamp": now - 190,
        },
    ]

    stats = build_session_transitions(interactions)

    tests = [
        {
            "context": ["phone_123"],
            "expected": "case_123",
            "desc": "After Phone → Case should dominate (recent + frequent)",
        },
        {
            "context": ["case_123"],
            "expected": "charger_123",
            "desc": "After Case → Charger dominates",
        },
        {
            "context": ["phone_123", "case_123"],
            "expected": "charger_123",
            "desc": "Recency: Case dominates Phone",
        },
    ]

    print("\n" + "=" * 60)
    print("SESSION RECOMMENDER – TIME DECAY TEST")
    print("=" * 60)

    for i, t in enumerate(tests, 1):
        recs = recommend_next_items(
            stats=stats,
            current_session_items=t["context"],
            limit=3,
            time_decay_half_life_days=7.0,
        )

        top_pid, score = recs[0] if recs else (None, 0.0)

        status = "[PASS]" if top_pid == t["expected"] else "[FAIL]"

        print(f"\nTest #{i}: {t['desc']}")
        print(f"Context:   {t['context']}")
        print(f"Expected:  {t['expected']}")
        print(f"Got:       {top_pid}")
        print(f"Score:     {score:.6f}")
        print(f"Result:    {status}")


if __name__ == "__main__":
    run_manual_check()

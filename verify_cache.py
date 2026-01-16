import requests
import time
import json
import uuid

BASE_URL = "http://localhost:8000/chatbot/chat"

def test_caching():
    session_id = str(uuid.uuid4())
    query = "Chính sách đổi trả như thế nào?"
    
    payload = {
        "query": query,
        "session_id": session_id,
        "top_k": 3
    }
    
    print(f"Testing with Session ID: {session_id}")
    print(f"Query: {query.encode('ascii', 'xmlcharrefreplace').decode()}")
    print("-" * 50)

    # 1. Simple Intent (Greeting) - Expect < 50ms
    print("1. Sending Simple Intent ('Xin chào')...")
    start_time = time.time()
    resp_simple = requests.post(BASE_URL, json={"query": "Xin chào", "session_id": session_id})
    resp_simple.raise_for_status()
    dur_simple = time.time() - start_time
    print(f"   Response received in {dur_simple:.3f}s")
    if dur_simple < 1.0: # Giving some buffer for network/fastapi overhead
        print("✅ SUCCESS: Simple intent is FAST.")
    else:
        print(f"⚠️ WARNING: Simple intent took too long ({dur_simple:.3f}s)")

    # 2. Complex Query (First Time) - Expect ~2s
    print("\n2. Sending Complex Query (First Time - LLM)...")
    start_time = time.time()
    resp1 = requests.post(BASE_URL, json=payload)
    resp1.raise_for_status()
    data1 = resp1.json()
    dur1 = time.time() - start_time
    print(f"   Response received in {dur1:.3f}s")
    print(f"   Intent: {data1.get('intent', {}).get('primary')}")

    # 3. Complex Query (Second Time) - Expect < 50ms (Cache)
    print("\n3. Sending Complex Query (Second Time - Cache)...")
    start_time = time.time()
    resp2 = requests.post(BASE_URL, json=payload)
    resp2.raise_for_status()
    data2 = resp2.json()
    dur2 = time.time() - start_time
    print(f"   Response received in {dur2:.3f}s")
    
    if dur2 < 0.2:
        print("✅ SUCCESS: Cache HIT is Instant.")
    elif dur2 < dur1 * 0.5:
        print("✅ SUCCESS: Significantly faster.")
    else:
        print(f"❌ FAILURE: Cache did not improve speed significantly ({dur2:.3f}s vs {dur1:.3f}s)")

if __name__ == "__main__":
    test_caching()

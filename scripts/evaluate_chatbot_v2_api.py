
import requests
import json
import time
from tabulate import tabulate

API_URL = "http://localhost:8000/chatbot/chat/v2"

TEST_CASES = [
    {
        "category": "Greeting",
        "query": "Xin chào",
        "expected_intent": "greeting"
    },
    {
        "category": "Price Info",
        "query": "Giá iPhone 15 Pro Max là bao nhiêu?",
        "expected_keywords": ["34,990,000", "34.990.000"],
        "expected_intent": "product_info"
    },
    {
        "category": "Specs Info (Battery)",
        "query": "Pin iPhone 15 Pro Max dung lượng bao nhiêu?",
        "expected_keywords": ["4422", "mAh"],
        "expected_intent": "product_info"
    },
    {
        "category": "Specs Info (CPU)",
        "query": "Chip của Samsung S24 là gì?",
        "expected_keywords": ["Snapdragon 8 Gen 3"],
        "expected_intent": "product_info"
    },
    {
        "category": "Comparison",
        "query": "So sánh iPhone 15 Pro Max và Samsung Galaxy S24",
        "expected_intent": "compare",
        "expected_keywords": ["So sánh", "iPhone 15 Pro Max", "Samsung Galaxy S24"]
    },
    {
        "category": "Policy",
        "query": "Chính sách bảo hành thế nào?",
        "expected_intent": "policy",
        "expected_keywords": ["bảo hành", "12 tháng"]
    },
    {
        "category": "Edge Case (Wait)",
        "query": "Thời tiết hôm nay thế nào?",
        "expected_intent": "general", # or product_search fallback
        "note": "Should not crash or Hallucinate"
    }
]

def evaluate():
    print(f"Starting Evaluation on {API_URL}...\n")
    results = []
    
    for case in TEST_CASES:
        query = case["query"]
        print(f"Testing: '{query}' ({case['category']})...", end="", flush=True)
        
        start_time = time.time()
        try:
            # V2 uses "message" field, not "query"
            response = requests.post(API_URL, json={"message": query, "conversation_id": "eval_v2"})
            duration = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                res_text = ""
                intent = "unknown"
                
                # V2 response format check
                if "response" in data and isinstance(data["response"], dict):
                    res_text = data["response"].get("message", "")
                    intent = data.get("intent", "unknown")
                    
                    # Handle comparison format
                    if data["response"].get("type") == "compare":
                        comp = data["response"].get("comparison", {})
                        if comp:
                            res_text += f" [Comparison Table with {len(comp.get('products', []))} products]"

                elif "response" in data: # Fallback simple format
                     res_text = str(data["response"])
                
                # Validation
                status = "PASS"
                reasons = []
                
                # Check Intent
                if "expected_intent" in case:
                    if case["expected_intent"] != intent:
                         # Allow reasonable mismatches (e.g. product_search vs product_info)
                         if not (case["expected_intent"] in ["product_info", "product_search"] and intent in ["product_info", "product_search"]):
                            status = "FAIL"
                            reasons.append(f"Intent mismatch: exp '{case['expected_intent']}' got '{intent}'")
                
                # Check Keywords
                if "expected_keywords" in case:
                    missing = [kw for kw in case["expected_keywords"] if kw.lower() not in res_text.lower()]
                    if missing:
                        status = "FAIL"
                        reasons.append(f"Missing keywords: {missing}")

                print(f" {status} ({duration:.2f}s)")
                results.append([
                    case["category"], 
                    query, 
                    intent, 
                    status, 
                    f"{duration:.2f}s", 
                    ", ".join(reasons) if reasons else "OK"
                ])
                
            else:
                print(" ERROR HTTP", response.status_code)
                results.append([case["category"], query, "HTTP Error", "ERROR", f"{duration:.2f}s", f"Status {response.status_code}"])
                
        except Exception as e:
            print(" EXCEPTION")
            results.append([case["category"], query, "Exception", "ERROR", "0s", str(e)])

    print("\n" + "="*80)
    print(tabulate(results, headers=["Category", "Query", "Received Intent", "Status", "Time", "Details"], tablefmt="grid"))
    print("="*80)

if __name__ == "__main__":
    evaluate()

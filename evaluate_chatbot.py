import sys
import os
import json
import time

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.chatbot_service import ChatbotService
from loguru import logger

def evaluate_chatbot():
    """
    Run a set of test questions covering all intents and sample data.
    """
    service = ChatbotService()
    session_id = f"eval_session_{int(time.time())}"
    
    logger.info(f"🤖 Starting Chatbot Evaluation (Session: {session_id})")
    
    test_cases = [
        {
            "category": "Greeting",
            "query": "Xin chào, bạn có thể giúp gì cho tôi?",
            "expected_intent": "greeting"
        },
        {
            "category": "Product Search (Electronics)",
            "query": "Tìm cho tôi tai nghe không dây bluetooth",
            "expected_intent": "product_search"
        },
        {
            "category": "Product Info (Specific Brand)",
            "query": "Tai nghe SoundMax có tính năng gì nổi bật?",
            "expected_intent": "product_info"
        },
         {
            "category": "Product Search (Gaming)",
            "query": "Có bàn phím cơ nào chơi game tốt không?",
            "expected_intent": "product_search"
        },
        {
            "category": "Comparison",
            "query": "So sánh tai nghe AudioPro và tai nghe BeatX",
            "expected_intent": "compare"
        },
        {
            "category": "Policy (Shipping)",
            "query": "Phí vận chuyển đi Hà Nội là bao nhiêu?",
            "expected_intent": "policy"
        },
        {
            "category": "Policy (Return)",
            "query": "Tôi muốn đổi trả sản phẩm thì làm thế nào?",
            "expected_intent": "policy"
        },
        {
            "category": "Guide (Payment)",
            "query": "Shop có hỗ trợ thanh toán qua Ví MoMo không?",
            "expected_intent": "policy" # or guide/faq mapped to policy
        },
        {
            "category": "CSKH / Support",
            "query": "Tôi cần gặp nhân viên hỗ trợ gấp",
            "expected_intent": "support"
        },
        {
            "category": "Realtime Stock (Mock)",
            "query": "Giày chạy bộ RunFast còn hàng không?",
            "expected_intent": "stock_check" 
        },
        {
            "category": "Contextual Follow-up",
            "query": "Nó có màu đỏ không?", # Referring to previous product
            "expected_intent": "product_info"
        }
    ]

    for i, case in enumerate(test_cases):
        print(f"\n{'='*60}")
        print(f"🔹 Test Case {i+1}: {case['category']}")
        print(f"❓ Query: {case['query']}")
        
        start_time = time.time()
        try:
            # Call Answer
            answer, contexts, intent = service.answer(
                query=case['query'],
                session_id=session_id
            )
            duration = time.time() - start_time
            
            # Print Result
            print(f"⏱️  Time: {duration:.2f}s")
            print(f"🧠 Intent: {intent.primary} (Conf: {intent.confidence:.2f})")
            print(f"📝 Answer: {answer}")
            
            # Validation
            if case['expected_intent'] and intent.primary != case['expected_intent']:
                print(f"⚠️  Intent mismatch! Expected: {case['expected_intent']}, Got: {intent.primary}")
            else:
                 print(f"✅ Intent matched.")
            
            if not answer or "Xin lỗi" in answer[:20]:
                print(f"⚠️  Warning: Bot might have failed to answer.")
            
            # Print Contexts Brief
            if contexts:
                print(f"📚 Contexts ({len(contexts)}):")
                for ctx in contexts[:3]:
                    c_type = ctx.get('type', 'unknown')
                    c_name = "N/A"
                    if c_type == 'product':
                        c_name = ctx.get('data', {}).get('name')
                    elif c_type == 'content':
                        c_name = ctx.get('data', {}).get('title')
                    print(f"   - [{c_type}] {c_name} (Score: {ctx.get('score', 0):.2f})")
            else:
                print(f"📚 Contexts: 0 (No Retrieval)")

        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    evaluate_chatbot()

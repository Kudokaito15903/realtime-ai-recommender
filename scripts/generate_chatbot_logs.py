import asyncio
import sys
import os
import json
import time

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domain.chatbot.chatbot import ChatbotOrchestrator
from loguru import logger

# Disable detailed logging to console for this script to keep output clean
logger.remove()
logger.add(sys.stderr, level="ERROR")

# Force utf-8 for stdout/stderr to handle Vietnamese characters on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

async def generate_logs():
    print("Initializing Chatbot...")
    chatbot = ChatbotOrchestrator()
    
    test_queries = [
        # General
        "Xin chào",
        # Product Info
        "iPhone 17 Pro có những tính năng gì?",
        # Compare
        "So sánh iPhone và Samsung",
        # Policy
        "Chính sách bảo hành như thế nào?",
        # CSKH
        "Làm sao kiểm tra đơn hàng?",
        # Complex/Edge case
        "Tôi muốn trả hàng",
        "Có hỗ trợ thanh toán visa không?"
    ]
    
    logs = []
    
    print(f"Processing {len(test_queries)} queries...")
    
    for query in test_queries:
        print(f"  - Sending: {query}")
        start_time = time.time()
        
        # Simulate a request
        request_data = {
            "message": query,
            "user_id": "log_gen_user",
            "conversation_id": "log_gen_session"
        }
        
        try:
            response = await chatbot.process_message(
                message=query,
                user_id="log_gen_user",
                conversation_id="log_gen_session"
            )
            
            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000
            
            log_entry = {
                "request": request_data,
                "response": response,
                "metadata": {
                    "execution_time_ms": duration_ms,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
            }
            logs.append(log_entry)
            
        except Exception as e:
            print(f"Error processing {query}: {e}")
            logs.append({
                "request": request_data,
                "error": str(e)
            })

    output_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
        "chatbot_detailed_logs.json"
    )
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)
        
    print(f"\n✅ Generated logs for {len(logs)} interactions.")
    print(f"📁 Saved to: {output_path}")

if __name__ == "__main__":
    asyncio.run(generate_logs())

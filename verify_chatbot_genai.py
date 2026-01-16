
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# Fix for Windows console encoding
sys.stdout.reconfigure(encoding='utf-8')

from services.chatbot_service import ChatbotService
import config

def verify_chatbot():
    print("Verifying Chatbot Service with Google GenAI...")
    
    # Check for API Key
    if not os.getenv("GOOGLE_API_KEY"):
        print("WARNING: GOOGLE_API_KEY is not set. Please set it to run this test.")
        # We can't proceed without a key for a real test, but we can verify instantiation
    
    try:
        service = ChatbotService(enable_cache=False)
        print("Service initialized successfully.")
        
        query = "Bên mình có thể các phương thức thanh toán nào"
        print(f"\nQuery: {query}")
        
        # Test answer
        answer, contexts, intent = service.answer(query)
        
        print("\nResponse:")
        print(f"Intent: {intent.primary}")
        print("-" * 20)
        print(answer)
        print("-" * 20)
        
        if answer:
            print("\nSUCCESS: Chatbot generated a response.")
        else:
            print("\nFAILURE: Chatbot returned empty response.")
            
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_chatbot()

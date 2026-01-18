"""
General Intent Handler (greetings, chitchat, unclear intent)
"""

from typing import Dict, Any, List, Optional
from loguru import logger


class GeneralHandler:
    """
    Handle general queries (greetings, chitchat, unclear intent).
    
    Examples:
    - "Xin chào"
    - "Cảm ơn bạn"
    - "Tạm biệt"
    """

    GREETINGS_RESPONSES = {
        "xin chào": "Xin chào! Tôi có thể giúp gì cho bạn? Tôi có thể tư vấn về sản phẩm, chính sách, hoặc hỗ trợ khách hàng.",
        "hello": "Hello! How can I help you today? I can assist with product information, policies, or customer support.",
        "hi": "Hi there! How can I assist you?",
        "chào": "Chào bạn! Bạn cần hỗ trợ gì không?",
        "hey": "Hey! How can I help?",
    }

    THANKS_RESPONSES = {
        "cảm ơn": "Không có gì! Nếu bạn còn câu hỏi nào khác, cứ hỏi nhé! 😊",
        "thank": "You're welcome! Feel free to ask if you have any other questions!",
        "thanks": "My pleasure! Let me know if you need anything else!",
    }

    GOODBYE_RESPONSES = {
        "tạm biệt": "Tạm biệt! Chúc bạn một ngày tốt lành! 👋",
        "bye": "Goodbye! Have a great day!",
        "goodbye": "See you later! Take care!",
    }

    def __init__(self):
        pass

    async def handle(
        self,
        query: str,
        conversation_history: Optional[List[Dict]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Handle general query.
        """
        logger.info(f"Handling general: {query[:50]}...")

        query_lower = query.lower().strip()

        # Check for greetings
        for keyword, response in self.GREETINGS_RESPONSES.items():
            if keyword in query_lower:
                return {
                    "type": "general",
                    "sub_type": "greeting",
                    "message": response,
                    "quick_actions": [
                        {"label": "Tìm sản phẩm", "action": "search_products"},
                        {"label": "Chính sách", "action": "ask_policy"},
                        {"label": "Hỗ trợ", "action": "contact_support"},
                    ],
                }

        # Check for thanks
        for keyword, response in self.THANKS_RESPONSES.items():
            if keyword in query_lower:
                return {
                    "type": "general",
                    "sub_type": "thanks",
                    "message": response,
                }

        # Check for goodbye
        for keyword, response in self.GOODBYE_RESPONSES.items():
            if keyword in query_lower:
                return {
                    "type": "general",
                    "sub_type": "goodbye",
                    "message": response,
                }

        # Default response for unclear intent
        return {
            "type": "general",
            "sub_type": "unclear",
            "message": """Xin chào! Tôi có thể giúp bạn với:

🔍 **Thông tin sản phẩm**: Hỏi về tính năng, thông số, giá cả
📋 **So sánh sản phẩm**: So sánh giữa các sản phẩm
📖 **Chính sách**: Bảo hành, đổi trả, thanh toán, vận chuyển
💬 **Hỗ trợ khách hàng**: Kiểm tra đơn hàng, tài khoản

Bạn muốn hỏi gì?""",
            "quick_actions": [
                {"label": "Tìm sản phẩm", "action": "search_products"},
                {"label": "Chính sách", "action": "ask_policy"},
                {"label": "Hỗ trợ", "action": "contact_support"},
            ],
        }

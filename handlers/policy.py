"""
Policy Intent Handler
"""

from typing import Dict, Any, List, Optional
from loguru import logger

from domain.chatbot.rag_engine import RAGEngine
from domain.chatbot.response_generator import ResponseGenerator
from utils.formatters import format_policy_response


class PolicyHandler:

    POLICY_KEYWORDS = {
        "warranty": [
            "bảo hành",
            "warranty",
            "bảo hàng",
            "sửa chữa",
            "lỗi kỹ thuật",
            "hỏng",
            "hư",
        ],
        "return": [
            "đổi trả",
            "return",
            "hoàn tiền",
            "refund",
            "trả hàng",
            "đổi hàng",
            "không vừa ý",
        ],
        "shipping": [
            "giao hàng",
            "vận chuyển",
            "shipping",
            "delivery",
            "ship",
            "phí giao",
            "thời gian giao",
            "giao nhanh",
        ],
        "payment": [
            "thanh toán",
            "payment",
            "trả tiền",
            "phương thức",
            "cod",
            "chuyển khoản",
            "thẻ",
            "ví điện tử",
            "trả góp",
            "ngân hàng",
        ],
    }

    def __init__(self):
        self.rag_engine = RAGEngine()
        self.response_generator = ResponseGenerator()

    async def handle(
        self,
        query: str,
        conversation_history: Optional[List[Dict]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:

        logger.info(f"Handling policy: {query[:50]}...")

        # Step 1: Detect policy type
        policy_type = self._detect_policy_type(query)
        logger.debug(f"Detected policy type: {policy_type}")

        # Step 2: Retrieve relevant policy chunks
        chunks = await self.rag_engine.retrieve_policy_chunks(
            query=query, policy_type=policy_type, top_k=3
        )

        if not chunks:
            return self._no_policy_response(query)

        # Step 3: Build context
        context_text = self.rag_engine.build_context(chunks, max_tokens=1500)

        # Step 4: Generate response
        response_text = await self.response_generator.generate_policy_response(
            query=query, context=context_text, conversation_history=conversation_history
        )

        # Step 5: Format response
        formatted_response = format_policy_response(
            message=response_text, policy_type=policy_type, sources=chunks
        )

        logger.info(f"✅ Policy response generated (type: {policy_type})")

        return formatted_response

    def _detect_policy_type(self, query: str) -> Optional[str]:

        query_lower = query.lower()

        scores = {}
        for policy_type, keywords in self.POLICY_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in query_lower)
            if score > 0:
                scores[policy_type] = score

        if not scores:
            return None

        return max(scores, key=scores.get)

    def _no_policy_response(self, query: str) -> Dict[str, Any]:

        return {
            "type": "policy",
            "message": """Xin lỗi, tôi không tìm thấy chính sách liên quan đến câu hỏi của bạn.

Bạn có thể hỏi về:
- Chính sách bảo hành
- Chính sách đổi trả
- Chính sách giao hàng
- Phương thức thanh toán

Hoặc liên hệ CSKH để được hỗ trợ chi tiết hơn.""",
            "quick_actions": [
                {
                    "label": "Chính sách bảo hành",
                    "action": "ask_policy",
                    "policy_type": "warranty",
                },
                {
                    "label": "Chính sách đổi trả",
                    "action": "ask_policy",
                    "policy_type": "return",
                },
                {
                    "label": "Phí giao hàng",
                    "action": "ask_policy",
                    "policy_type": "shipping",
                },
                {"label": "Liên hệ CSKH", "action": "contact_support"},
            ],
        }

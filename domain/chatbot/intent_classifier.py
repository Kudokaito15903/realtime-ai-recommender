"""
Intent Classification Service
"""

from typing import Tuple, List, Dict, Any
from loguru import logger
import re
import config

try:
    import google.generativeai as genai
except ImportError:
    genai = None


class IntentClassifier:
    """
    Classify user intent using LLM or rule-based approach.

    Intents:
    - product_info: Questions about product specs, features
    - compare: Compare multiple products
    - policy: Questions about policies (warranty, return, shipping, payment)
    - cskh: Customer support (order tracking, account management)
    - general: Greetings, chitchat, unclear intent
    """

    INTENTS = {
        "product_info": {
            "description": "Hỏi về thông tin, tính năng, cấu hình sản phẩm cụ thể",
            "keywords": [
                "thông số", "cấu hình", "tính năng", "màu", "giá", "pin", "camera",
                "màn hình", "cpu", "ram", "bộ nhớ", "spec", "chi tiết", "chip", "vi xử lý",
            ],
            "examples": [
                "iPhone 17 Pro có những tính năng gì?",
                "Cho tôi biết về laptop Dell XPS",
                "Máy này pin trâu không?",
                "Cấu hình như thế nào?",
            ],
        },
        "greeting": {
            "description": "Chào hỏi",
            "keywords": ["xin chào", "chào", "hello", "hi", "good morning", "alo"],
            "examples": ["Xin chào", "Hello bot"],
        },
        "product_search": {
            "description": "Tìm kiếm sản phẩm theo tiêu chí chung",
            "keywords": [
                "tìm", "mua", "cần", "muốn", "có", "bán", "gợi ý", "tư vấn",
                "tai nghe", "bàn phím", "chuột", "laptop", "điện thoại",
                "gaming", "văn phòng", "giá rẻ", "tốt nhất",
            ],
            "examples": [
                "Tìm cho tôi tai nghe không dây",
                "Có bàn phím cơ nào chơi game tốt không?",
                "Tư vấn laptop văn phòng dưới 15 triệu",
            ],
        },

        "compare": {
            "description": "So sánh sản phẩm",
            "keywords": [
                "so sánh",
                "khác biệt",
                "nên mua",
                "tốt hơn",
                "vs",
                "hay",
                "giữa",
                "hoặc",
                "chọn",
            ],
            "examples": [
                "So sánh iPhone 17 Pro và Samsung S25",
                "Nên mua laptop nào giữa Dell và HP?",
                "Khác biệt giữa 2 sản phẩm này",
                "Cái nào tốt hơn?",
            ],
        },
        "policy": {
            "description": "Hỏi về chính sách",
            "keywords": [
                "bảo hành",
                "đổi trả",
                "giao hàng",
                "vận chuyển",
                "thanh toán",
                "hoàn tiền",
                "chính sách",
                "quy định",
                "ship",
                "cod",
                "chuyển khoản",
                "trả góp",
            ],
            "examples": [
                "Chính sách bảo hành như thế nào?",
                "Đổi trả trong bao lâu?",
                "Có giao hàng miễn phí không?",
                "Thanh toán qua thẻ được không?",
            ],
        },
        "cskh": {
            "description": "Yêu cầu hỗ trợ khách hàng",
            "keywords": [
                "đơn hàng",
                "kiểm tra",
                "tài khoản",
                "hủy",
                "mật khẩu",
                "địa chỉ",
                "cập nhật",
                "liên hệ",
                "hotline",
                "hỗ trợ",
                "tracking",
                "order",
            ],
            "examples": [
                "Làm sao kiểm tra đơn hàng?",
                "Tôi quên mật khẩu",
                "Cập nhật địa chỉ giao hàng",
                "Hủy đơn hàng",
            ],
        },
        "general": {
            "description": "Chào hỏi, chitchat, không rõ ràng",
            "keywords": [
                "xin chào",
                "hello",
                "hi",
                "chào",
                "hey",
                "cảm ơn",
                "thank",
                "bye",
                "tạm biệt",
            ],
            "examples": ["Xin chào", "Hello", "Cảm ơn bạn", "Tạm biệt"],
        },
    }

    def __init__(self):
        # Initialize GenAI if available
        self.genai_model = None
        if genai:
            try:
                api_key = config.GOOGLE_API_KEY
                if api_key:
                    genai.configure(api_key=api_key)
                    self.genai_model = genai.GenerativeModel(
                        getattr(config, "GOOGLE_MODEL", "gemini-pro")
                    )
            except Exception as e:
                logger.warning(f"Failed to initialize GenAI: {e}")
        
        # Simple in-memory cache (can be replaced with Redis later)
        self._cache = {}

    async def classify(
        self, message: str, conversation_history: List[Dict[str, str]] = None
    ) -> Tuple[str, float]:
        """
        Classify intent of user message.

        Args:
            message: User message
            conversation_history: Previous messages for context

        Returns:
            Tuple of (intent, confidence_score)
        """
        # Check cache first
        cache_key = f"intent:{message.lower()[:100]}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            logger.debug(f"Intent cache hit: {cached}")
            return cached["intent"], cached["confidence"]

        # Try rule-based classification first (fast)
        intent, confidence = self._rule_based_classify(message)

        if confidence >= 0.8:
            # High confidence from rules, use it
            self._cache[cache_key] = {"intent": intent, "confidence": confidence}
            return intent, confidence

        # Low confidence, use LLM classification
        intent, confidence = await self._llm_classify(message, conversation_history)

        # Cache result
        self._cache[cache_key] = {"intent": intent, "confidence": confidence}

        return intent, confidence

    def _rule_based_classify(self, message: str) -> Tuple[str, float]:
        """
        Fast rule-based classification using keywords.

        Returns:
            Tuple of (intent, confidence_score)
        """
        message_lower = message.lower()

        # Score each intent
        scores = {}
        for intent, config in self.INTENTS.items():
            score = 0
            keywords = config["keywords"]

            for keyword in keywords:
                if keyword in message_lower:
                    # Weight longer keywords higher
                    score += len(keyword.split())

            if score > 0:
                scores[intent] = score

        if not scores:
            return "general", 0.3

        # Get intent with highest score
        best_intent = max(scores, key=scores.get)
        max_score = scores[best_intent]

        # Normalize confidence (heuristic)
        total_score = sum(scores.values())
        confidence = max_score / total_score if total_score > 0 else 0.5

        # Boost confidence for clear patterns


        if self._has_comparison_pattern(message_lower):
            if best_intent == "compare":
                confidence = max(confidence, 0.9)

        if self._has_product_info_pattern(message_lower):
            if best_intent == "product_info":
                confidence = max(confidence, 0.9)
            elif best_intent == "general":
                 # Override general if price pattern detected
                 best_intent = "product_info"
                 confidence = 0.85

        if self._has_greeting_pattern(message_lower):
            # Override to greeting for clear greeting patterns
            best_intent = "greeting"
            confidence = 0.95

        logger.debug(f"Rule-based: {best_intent} (confidence: {confidence:.2f})")

        return best_intent, confidence



    def _has_comparison_pattern(self, text: str) -> bool:
        """Check if text has comparison pattern"""
        patterns = [
            r"so sánh .+ và .+",
            r".+ vs .+",
            r".+ hay .+",
            r"nên mua .+ hay .+",
            r"khác biệt giữa .+ và .+",
        ]
        return any(re.search(p, text) for p in patterns)

    def _has_product_info_pattern(self, text: str) -> bool:
        """Check if text is asking about product info (price, specs)"""
        patterns = [
            r"giá .+",
            r".+ giá bao nhiêu",
            r".+ giá thế nào",
            r".+ bao nhiêu tiền",
            r"cấu hình .+",
            r"thông số .+",
            r"chip .+",
            r".+ chip là gì",
            r"pin .+",
            r".+ pin bao nhiêu",
            r"ram .+",
            r"cpu .+",
        ]
        return any(re.search(p, text) for p in patterns)

    def _has_greeting_pattern(self, text: str) -> bool:
        """Check if text is a greeting"""
        greetings = [
            "xin chào",
            "hello",
            "hi ",
            "chào ",
            "hey",
            "good morning",
            "good afternoon",
            "good evening",
        ]
        return any(g in text for g in greetings)

    async def _llm_classify(
        self, message: str, conversation_history: List[Dict[str, str]] = None
    ) -> Tuple[str, float]:
        """
        Use LLM to classify intent.

        Returns:
            Tuple of (intent, confidence_score)
        """
        # Build context from history
        context_text = ""
        if conversation_history:
            recent = conversation_history[-3:]  # Last 3 messages
            context_text = "\n".join(
                [f"{msg['role']}: {msg['content']}" for msg in recent]
            )

        # Build prompt
        intent_descriptions = "\n".join(
            [
                f"{i+1}. {intent}: {config['description']}"
                for i, (intent, config) in enumerate(self.INTENTS.items())
            ]
        )

        prompt = f"""Phân loại intent của tin nhắn người dùng vào một trong các loại sau:

{intent_descriptions}

Context hội thoại trước (nếu có):
{context_text if context_text else "Không có"}

Tin nhắn mới của người dùng: {message}

Hãy phân tích và trả lời JSON format:
{{
  "intent": "...",
  "confidence": 0.0-1.0,
  "reasoning": "Giải thích ngắn gọn"
}}

Chỉ trả lời JSON, không thêm text nào khác."""

        try:
            # Call LLM if available
            if not self.genai_model:
                # Fallback to rule-based if LLM not available
                return self._rule_based_classify(message)
            
            # Call GenAI
            full_prompt = f"""Bạn là hệ thống phân loại intent chính xác. Chỉ trả lời JSON.

{prompt}"""
            
            # GenAI synchronous call (can be wrapped in asyncio if needed)
            import asyncio
            loop = asyncio.get_event_loop()
            
            # Configure safety settings to avoid blocking harmless content
            safety_settings = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_NONE",
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_NONE",
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_NONE",
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_NONE",
                },
            ]

            response_obj = await loop.run_in_executor(
                None,
                lambda: self.genai_model.generate_content(
                    full_prompt,
                    generation_config={
                        "temperature": 0.1, # Lower temperature for consistency
                        "max_output_tokens": 150,
                    },
                    safety_settings=safety_settings
                )
            )
            
            # Check if response was blocked or empty
            if not response_obj.parts:
                 logger.warning(f"LLM returned no parts. Finish reason: {response_obj.finish_reason}")
                 return self._rule_based_classify(message)

            response = response_obj.text

            # Clean Markdown code blocks if present
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            
            response = response.strip()

            # Parse JSON response
            import json

            result = json.loads(response)

            intent = result.get("intent", "general")
            confidence = float(result.get("confidence", 0.5))
            reasoning = result.get("reasoning", "")

            # Validate intent
            if intent not in self.INTENTS:
                logger.warning(
                    f"Invalid intent from LLM: {intent}, defaulting to general"
                )
                intent = "general"
                confidence = 0.5

            logger.info(
                f"LLM classified: {intent} "
                f"(confidence: {confidence:.2f}) "
                f"- {reasoning}"
            )

            return intent, confidence

        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            # Fallback to rule-based on error
            return self._rule_based_classify(message)

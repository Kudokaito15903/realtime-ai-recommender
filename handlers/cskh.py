"""
CSKH (Customer Support) Intent Handler
"""

from typing import Dict, Any, List, Optional
from loguru import logger
import re

from domain.chatbot.rag_engine import RAGEngine
from domain.chatbot.response_generator import ResponseGenerator
from utils.formatters import format_cskh_response


class CSKHHandler:
    """
    Handle customer support queries.

    CSKH topics:
    - order_tracking: Kiểm tra đơn hàng
    - account_management: Quản lý tài khoản (quên mật khẩu, đổi thông tin)
    - order_cancellation: Hủy đơn hàng
    - contact_support: Liên hệ hỗ trợ
    - address_management: Quản lý địa chỉ

    Examples:
    - "Làm sao kiểm tra đơn hàng?"
    - "Tôi quên mật khẩu"
    - "Cập nhật địa chỉ giao hàng"
    - "Hủy đơn hàng #12345"
    """

    TOPIC_KEYWORDS = {
        "order_tracking": [
            "kiểm tra đơn",
            "tracking",
            "đơn hàng",
            "order",
            "trạng thái",
            "theo dõi",
            "đã giao chưa",
        ],
        "account_management": [
            "tài khoản",
            "account",
            "quên mật khẩu",
            "password",
            "đổi mật khẩu",
            "reset",
            "đăng nhập",
            "thông tin cá nhân",
            "cập nhật thông tin",
        ],
        "order_cancellation": [
            "hủy đơn",
            "cancel",
            "hủy order",
            "không muốn mua",
            "đổi ý",
        ],
        "address_management": [
            "địa chỉ",
            "address",
            "giao hàng",
            "thêm địa chỉ",
            "sửa địa chỉ",
            "đổi địa chỉ",
        ],
        "contact_support": [
            "liên hệ",
            "contact",
            "hotline",
            "hỗ trợ",
            "gọi",
            "email",
            "chat",
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
        """
        Handle CSKH query.
        """
        logger.info(f"Handling CSKH: {query[:50]}...")

        # Step 1: Detect CSKH topic
        topic = self._detect_topic(query)
        logger.debug(f"Detected CSKH topic: {topic}")

        # Step 2: Check if needs API call (order tracking, etc.)
        api_response = await self._try_api_actions(
            query=query, topic=topic, context=context
        )

        if api_response:
            logger.info("✅ CSKH handled via API")
            return api_response

        # Step 3: Retrieve knowledge base
        chunks = await self.rag_engine.retrieve_cskh_chunks(
            query=query, topic=topic, top_k=2
        )

        if not chunks:
            return self._default_cskh_response()

        # Step 4: Build context
        context_text = self.rag_engine.build_context(chunks, max_tokens=1500)

        # Step 5: Generate response
        response_text = await self.response_generator.generate_cskh_response(
            query=query, context=context_text, conversation_history=conversation_history
        )

        # Step 6: Format response
        formatted_response = format_cskh_response(
            message=response_text, topic=topic, sources=chunks
        )

        logger.info(f"✅ CSKH response generated (topic: {topic})")

        return formatted_response

    def _detect_topic(self, query: str) -> Optional[str]:
        """Detect CSKH topic from query."""
        query_lower = query.lower()

        scores = {}
        for topic, keywords in self.TOPIC_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in query_lower)
            if score > 0:
                scores[topic] = score

        if not scores:
            return None

        return max(scores, key=scores.get)

    async def _try_api_actions(
        self, query: str, topic: Optional[str], context: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Try to handle query with API calls.

        Returns:
            Response dict if handled, None otherwise
        """
        # ORDER TRACKING
        if topic == "order_tracking":
            order_id = self._extract_order_id(query, context)

            if order_id:
                return await self._handle_order_tracking(order_id)

        # ACCOUNT PASSWORD RESET
        if topic == "account_management" and "quên mật khẩu" in query.lower():
            return await self._handle_password_reset(context)

        return None

    def _extract_order_id(
        self, query: str, context: Optional[Dict[str, Any]]
    ) -> Optional[str]:
        """
        Extract order ID from query or context.

        Patterns:
        - "đơn hàng #12345"
        - "order 12345"
        - "ORD-2024-12345"
        """
        # Pattern 1: #12345
        match = re.search(r"#(\w+)", query)
        if match:
            return match.group(1)

        # Pattern 2: order 12345
        match = re.search(r"order\s+(\w+)", query, re.IGNORECASE)
        if match:
            return match.group(1)

        # Pattern 3: ORD-xxx
        match = re.search(r"(ORD-[\w-]+)", query, re.IGNORECASE)
        if match:
            return match.group(1)

        # From context
        if context and "order_id" in context:
            return context["order_id"]

        return None

    async def _handle_order_tracking(self, order_id: str) -> Dict[str, Any]:
        """
        Handle order tracking query with API.
        """
        try:
            # TODO: Implement order service integration
            # For now, return a placeholder response
            order = None  # await self.order_service.get_order(order_id)
            
            # If order service not available, return helpful message
            if order is None:
                return {
                    "type": "cskh",
                    "message": f"Không tìm thấy đơn hàng #{order_id}. Vui lòng kiểm tra lại mã đơn hàng hoặc liên hệ CSKH để được hỗ trợ.",
                    "quick_actions": [
                        {"label": "Liên hệ CSKH", "action": "contact_support"},
                        {"label": "Xem đơn hàng của tôi", "action": "view_my_orders"},
                    ],
                }

            # Format order status
            status_messages = {
                "pending": "Đơn hàng đang chờ xác nhận",
                "confirmed": "Đơn hàng đã được xác nhận, đang chuẩn bị hàng",
                "processing": "Đang đóng gói và chuẩn bị giao hàng",
                "shipping": "Đang giao hàng",
                "delivered": "Đã giao hàng thành công",
                "cancelled": "Đơn hàng đã bị hủy",
                "returned": "Đơn hàng đã được trả lại",
            }

            status = order.get("status", "unknown")
            status_msg = status_messages.get(status, "Không xác định")

            # Build response message
            message = f"""**Đơn hàng #{order_id}**

📦 **Trạng thái:** {status_msg}

🛍️ **Sản phẩm:**
{self._format_order_items(order.get('items', []))}

💰 **Tổng tiền:** {order.get('total_amount', 0):,.0f}đ

📍 **Địa chỉ giao hàng:**
{order.get('shipping_address', {}).get('full_address', 'N/A')}

📞 **SĐT nhận hàng:** {order.get('shipping_address', {}).get('phone', 'N/A')}
"""

            if order.get("tracking_number"):
                message += f"\n🚚 **Mã vận đơn:** {order['tracking_number']}"

            if order.get("estimated_delivery"):
                message += f"\n⏰ **Dự kiến giao:** {order['estimated_delivery']}"

            # Quick actions based on status
            quick_actions = []

            if status in ["pending", "confirmed"]:
                quick_actions.append(
                    {
                        "label": "Hủy đơn hàng",
                        "action": "cancel_order",
                        "order_id": order_id,
                    }
                )

            if status == "delivered":
                quick_actions.append(
                    {
                        "label": "Đánh giá sản phẩm",
                        "action": "review_order",
                        "order_id": order_id,
                    }
                )
                quick_actions.append(
                    {
                        "label": "Yêu cầu đổi trả",
                        "action": "request_return",
                        "order_id": order_id,
                    }
                )

            if status == "shipping":
                quick_actions.append(
                    {
                        "label": "Theo dõi vận chuyển",
                        "action": "track_shipping",
                        "tracking_number": order.get("tracking_number"),
                    }
                )

            quick_actions.append({"label": "Liên hệ CSKH", "action": "contact_support"})

            return {
                "type": "cskh",
                "sub_type": "order_tracking",
                "message": message,
                "order": {
                    "id": order_id,
                    "status": status,
                    "total_amount": order.get("total_amount"),
                    "items": order.get("items", []),
                },
                "quick_actions": quick_actions,
            }

        except Exception as e:
            logger.error(f"Order tracking failed: {e}", exc_info=True)
            return {
                "type": "cskh",
                "message": f"Có lỗi khi kiểm tra đơn hàng #{order_id}. Vui lòng thử lại sau hoặc liên hệ CSKH.",
                "quick_actions": [
                    {"label": "Liên hệ CSKH", "action": "contact_support"}
                ],
            }

    def _format_order_items(self, items: List[Dict[str, Any]]) -> str:
        """Format order items for display."""
        if not items:
            return "Không có sản phẩm"

        lines = []
        for item in items[:3]:  # Max 3 items
            name = item.get("product_name", "N/A")
            quantity = item.get("quantity", 1)
            price = item.get("price", 0)
            lines.append(f"• {name} x{quantity} - {price:,.0f}đ")

        if len(items) > 3:
            lines.append(f"• ... và {len(items) - 3} sản phẩm khác")

        return "\n".join(lines)

    async def _handle_password_reset(
        self, context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Handle password reset request.
        """
        return {
            "type": "cskh",
            "sub_type": "password_reset",
            "message": """**Đặt lại mật khẩu**

Để đặt lại mật khẩu, vui lòng làm theo các bước sau:

1️⃣ Truy cập trang đăng nhập
2️⃣ Click vào "Quên mật khẩu"
3️⃣ Nhập email hoặc số điện thoại đã đăng ký
4️⃣ Nhận mã OTP qua email/SMS
5️⃣ Nhập mã OTP và đặt mật khẩu mới

**Lưu ý:**
- Mã OTP có hiệu lực trong 5 phút
- Mật khẩu mới phải có ít nhất 8 ký tự, bao gồm chữ hoa, chữ thường và số

Nếu không nhận được mã OTP, vui lòng kiểm tra hộp thư spam hoặc liên hệ CSKH.""",
            "quick_actions": [
                {"label": "Đặt lại mật khẩu", "action": "reset_password"},
                {"label": "Liên hệ CSKH", "action": "contact_support"},
            ],
        }

    def _default_cskh_response(self) -> Dict[str, Any]:
        """
        Default CSKH response when no specific topic detected.
        """
        return {
            "type": "cskh",
            "message": """Tôi có thể hỗ trợ bạn với:

📦 **Đơn hàng**
- Kiểm tra trạng thái đơn hàng
- Hủy đơn hàng
- Theo dõi vận chuyển

👤 **Tài khoản**
- Quên mật khẩu
- Cập nhật thông tin cá nhân
- Quản lý địa chỉ giao hàng

📞 **Liên hệ hỗ trợ**
- Hotline: 1900 xxxx (8h-22h)
- Email: support@example.com
- Live chat

Bạn cần hỗ trợ gì cụ thể không?""",
            "quick_actions": [
                {"label": "Kiểm tra đơn hàng", "action": "track_order"},
                {"label": "Quên mật khẩu", "action": "reset_password"},
                {"label": "Cập nhật địa chỉ", "action": "manage_address"},
                {"label": "Gọi hotline", "action": "call_hotline", "phone": "1900xxxx"},
            ],
        }

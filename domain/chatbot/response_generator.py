"""
Response Generator for generating chatbot responses using LLM
"""

from typing import List, Dict, Any, Optional
from loguru import logger

try:
    import google.generativeai as genai
except ImportError:
    genai = None

import config


class ResponseGenerator:

    def __init__(self):
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

    async def generate_product_response(
        self,
        query: str,
        context: str,
        conversation_history: Optional[List[Dict]] = None,
    ) -> str:

        if not context or not context.strip():
            logger.warning(f"Empty context for product query: {query[:50]}...")
            return f"Xin lỗi, tôi không tìm thấy thông tin về '{query}' trong dữ liệu hiện có. Vui lòng thử lại với tên sản phẩm cụ thể hơn hoặc liên hệ bộ phận hỗ trợ."
        
        system_prompt = """Bạn là tư vấn viên sản phẩm chuyên nghiệp. 
Nhiệm vụ: Trả lời câu hỏi về sản phẩm dựa TRỪNG MỰC trên thông tin có sẵn trong CONTEXT.

QUY TẮC NGHIÊM NGẶT - TUYỆT ĐỐI TUÂN THỦ:
1. CHỈ sử dụng thông tin được cung cấp bên dưới - KHÔNG được bịa đặt, suy đoán
2. Nếu thông tin KHÔNG có, bạn PHẢI nói rõ: "Tôi không tìm thấy thông tin này trong dữ liệu"
3. TRẢ LỜI TỰ NHIÊN: Không được nhắc đến từ "CONTEXT" hay "ngữ cảnh" trong câu trả lời. Thay vào đó hãy nói "Theo thông tin sản phẩm..." hoặc "Dữ liệu cho thấy..."
4. Nếu thông tin không đủ, chỉ trả lời phần có.
5. Tên sản phẩm, thông số, giá cả PHẢI KHỚP chính xác.

CÁCH TRẢ LỜI:
- Trả lời trực tiếp vào câu hỏi.
- Tổng hợp thông tin một cách có tổ chức.
- Sử dụng ngôn ngữ tự nhiên, thân thiện."""

        prompt = self._build_prompt(
            query=query,
            context=context,
            conversation_history=conversation_history,
            system_prompt=system_prompt,
        )

        return await self._generate(prompt)

    async def generate_policy_response(
        self,
        query: str,
        context: str,
        conversation_history: Optional[List[Dict]] = None,
    ) -> str:

        if not context or not context.strip():
            logger.warning(f"Empty context for policy query: {query[:50]}...")
            return f"Xin lỗi, tôi không tìm thấy thông tin về '{query}' trong chính sách hiện tại. Vui lòng liên hệ bộ phận hỗ trợ để được giải đáp chi tiết."
        
        system_prompt = """Bạn là chuyên viên chính sách. 
Nhiệm vụ: Giải thích các chính sách dựa TRỪNG MỰC trên thông tin trong CONTEXT.

QUY TẮC NGHIÊM NGẶT:
1. CHỈ sử dụng thông tin được cung cấp - KHÔNG được bịa đặt
2. Nếu thông tin không có, nói rõ: "Thông tin này không có trong chính sách hiện tại"
3. TRẢ LỜI TỰ NHIÊN: Không nhắc đến từ "CONTEXT".
4. Liệt kê đầy đủ các phương thức/điều kiện có trong dữ liệu.
5. Sử dụng danh sách có số thứ tự để trình bày rõ ràng."""

        prompt = self._build_prompt(
            query=query,
            context=context,
            conversation_history=conversation_history,
            system_prompt=system_prompt,
        )

        return await self._generate(prompt)

    async def generate_cskh_response(
        self,
        query: str,
        context: str,
        conversation_history: Optional[List[Dict]] = None,
    ) -> str:

        if not context or not context.strip():
            logger.warning(f"Empty context for CSKH query: {query[:50]}...")
            return f"Xin lỗi, tôi không tìm thấy thông tin về '{query}' trong dữ liệu hỗ trợ hiện có. Vui lòng liên hệ bộ phận hỗ trợ khách hàng để được giúp đỡ."
        
        system_prompt = """Bạn là nhân viên hỗ trợ khách hàng.
Nhiệm vụ: Hỗ trợ khách hàng dựa TRỪNG MỰC trên thông tin trong CONTEXT.

QUY TẮC NGHIÊM NGẶT:
1. CHỈ sử dụng thông tin được cung cấp
2. Nếu thông tin không có, nói rõ: "Tôi cần kiểm tra lại thông tin này"
3. TRẢ LỜI TỰ NHIÊN: Không dùng từ "CONTEXT".
4. Thân thiện, chuyên nghiệp."""

        prompt = self._build_prompt(
            query=query,
            context=context,
            conversation_history=conversation_history,
            system_prompt=system_prompt,
        )

        return await self._generate(prompt)

    async def generate_comparison_response(
        self,
        query: str,
        context: str,
        conversation_history: Optional[List[Dict]] = None,
    ) -> str:

        if not context or not context.strip():
            logger.warning(f"Empty context for comparison query: {query[:50]}...")
            return f"Xin lỗi, tôi không tìm thấy đủ thông tin để so sánh các sản phẩm trong câu hỏi của bạn. Vui lòng thử lại với tên sản phẩm cụ thể hơn."
        
        system_prompt = """Bạn là chuyên gia so sánh sản phẩm.
Nhiệm vụ: So sánh các sản phẩm dựa TRỪNG MỰC trên thông tin trong CONTEXT.

QUY TẮC NGHIÊM NGẶT:
1. CHỈ so sánh các thông tin ĐƯỢC CUNG CẤP - KHÔNG được bịa đặt
2. Nếu thông tin so sánh không có, nói rõ: "Thông tin này chưa được cập nhật"
3. TRẢ LỜI TỰ NHIÊN: Không nhắc đến từ "CONTEXT".
4. Trình bày dễ so sánh (bảng hoặc danh sách)."""

        prompt = self._build_prompt(
            query=query,
            context=context,
            conversation_history=conversation_history,
            system_prompt=system_prompt,
        )

        return await self._generate(prompt)

    def _build_prompt(
        self,
        query: str,
        context: str,
        system_prompt: str,
        conversation_history: Optional[List[Dict]] = None,
    ) -> str:
        parts = [system_prompt]
        
        parts.append("\n⚠️ LƯU Ý QUAN TRỌNG:")
        parts.append("- Bạn CHỈ được sử dụng thông tin trong phần CONTEXT bên dưới")
        parts.append("- Nếu CONTEXT trống hoặc không có thông tin liên quan, bạn PHẢI nói rõ điều đó")
        parts.append("- KHÔNG được sử dụng kiến thức ngoài CONTEXT, KHÔNG được bịa đặt")
        parts.append("- Nếu không chắc chắn thông tin có trong CONTEXT hay không, hãy nói 'Tôi không tìm thấy thông tin này'")
        
        if context and context.strip():
            parts.append(f"\n## CONTEXT (CHỈ SỬ DỤNG THÔNG TIN NÀY):\n{context}")
        else:
            parts.append("\n## CONTEXT:\n[KHÔNG CÓ THÔNG TIN]")
            parts.append("⚠️ CONTEXT trống - bạn PHẢI trả lời rằng không có thông tin để trả lời câu hỏi này.")
        
        if conversation_history:
            history_text = "\n".join(
                [f"{msg.get('role', 'user')}: {msg.get('content', '')}" 
                 for msg in conversation_history[-3:]]
            )
            parts.append(f"\n## CONVERSATION HISTORY:\n{history_text}")
        
        parts.append(f"\n## QUESTION:\n{query}")
        parts.append("\n## ANSWER (CHỈ dựa trên CONTEXT, KHÔNG bịa đặt):")
        
        return "\n".join(parts)

    async def _generate(self, prompt: str) -> str:
        if not self.genai_model:
            logger.warning("GenAI model not available, using context-based fallback")
            return self._generate_fallback_from_context(prompt)
        
        try:

            response_obj = self.genai_model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.1,
                    "max_output_tokens": 1500,
                    "top_p": 0.8,
                }
            )
            response_text = response_obj.text.strip()
            
            logger.debug(f"Generated response: {response_text[:200]}...")
            
            return response_text
        except Exception as e:
            logger.error(f"Error generating response: {e}", exc_info=True)
            return self._generate_fallback_from_context(prompt)
    
    def _generate_fallback_from_context(self, prompt: str) -> str:
        lines = prompt.split("\n")
        context = ""
        query = ""
        system_prompt = ""
        in_context = False
        in_question = False
        in_system = True
        
        for line in lines:
            if "## CONTEXT:" in line:
                in_context = True
                in_question = False
                in_system = False
                continue
            elif "## QUESTION:" in line:
                in_context = False
                in_question = True
                in_system = False
                continue
            elif "## ANSWER:" in line or "## CONVERSATION HISTORY:" in line or "## ANSWER" in line:
                in_context = False
                in_question = False
                in_system = False
                break
            
            if in_system:
                system_prompt += line + "\n"
            elif in_context:
                context += line + "\n"
            elif in_question:
                query = line.strip()
        
        context = context.strip()
        query = query.strip()
        
        if context:
            context_clean = context.replace("[Nguồn", "").replace("]", "")
            context_lines = [l.strip() for l in context_clean.split("\n") if l.strip()]
            
            is_policy = "chính sách" in system_prompt.lower() or "policy" in system_prompt.lower()
            is_product = "sản phẩm" in system_prompt.lower() or "product" in system_prompt.lower()
            is_cskh = "hỗ trợ" in system_prompt.lower() or "support" in system_prompt.lower()
            is_compare = "so sánh" in system_prompt.lower() or "compare" in system_prompt.lower()
            
          
            meaningful_lines = [l for l in context_lines if l and len(l.strip()) > 15]
            
            if not meaningful_lines:
                
                if context_lines:
                    return "Tôi tìm thấy một số thông tin trong dữ liệu:\n\n" + "\n".join(context_lines[:5]) + "\n\nLưu ý: Thông tin trên là tất cả những gì tôi có trong dữ liệu. Nếu bạn cần thông tin chi tiết hơn, vui lòng liên hệ bộ phận hỗ trợ."
                return "Xin lỗi, tôi không tìm thấy thông tin chi tiết về câu hỏi này trong dữ liệu hiện có. Vui lòng thử lại với câu hỏi cụ thể hơn hoặc liên hệ bộ phận hỗ trợ."
            
            if is_policy:
                if query:
                    response = f"Về câu hỏi '{query}', "
                    if "bảo hành" in query.lower() or "warranty" in query.lower():
                        response += "chính sách bảo hành của chúng tôi như sau:\n\n"
                    elif "đổi trả" in query.lower() or "return" in query.lower() or "hoàn tiền" in query.lower():
                        response += "chính sách đổi trả và hoàn tiền như sau:\n\n"
                    elif "giao hàng" in query.lower() or "vận chuyển" in query.lower() or "shipping" in query.lower():
                        response += "chính sách vận chuyển và giao hàng như sau:\n\n"
                    elif "thanh toán" in query.lower() or "payment" in query.lower():
                        response += "các phương thức thanh toán như sau:\n\n"
                    else:
                        response += "thông tin như sau:\n\n"
                else:
                    response = "Chính sách của chúng tôi:\n\n"
                
                for line in meaningful_lines[:12]:
                    response += f"{line}\n"
                    
            elif is_product:
                if query:
                    product_keywords = ["iphone", "samsung", "laptop", "dell", "xps", "máy", "sản phẩm"]
                    product_mentioned = any(kw in query.lower() for kw in product_keywords)
                    
                    if product_mentioned:
                        response = f"Dựa trên thông tin có sẵn về sản phẩm bạn hỏi:\n\n"
                    else:
                        response = f"Về câu hỏi '{query}', thông tin sản phẩm:\n\n"
                else:
                    response = "Thông tin sản phẩm:\n\n"
                
                for line in meaningful_lines[:10]:
                    response += f"{line}\n"
                    
            elif is_compare:
                response = "So sánh các sản phẩm:\n\n"
                for line in meaningful_lines[:12]:
                    response += f"{line}\n"
                    
            elif is_cskh:
                if query:
                    if "đơn hàng" in query.lower() or "order" in query.lower() or "tracking" in query.lower():
                        response = "Để kiểm tra đơn hàng:\n\n"
                    elif "mật khẩu" in query.lower() or "password" in query.lower():
                        response = "Để đặt lại mật khẩu:\n\n"
                    else:
                        response = f"Về câu hỏi '{query}':\n\n"
                else:
                    response = "Thông tin hỗ trợ:\n\n"
                
                for line in meaningful_lines[:10]:
                    response += f"{line}\n"
            else:
                if query:
                    response = f"Về câu hỏi '{query}':\n\n"
                else:
                    response = "Thông tin:\n\n"
                
                for line in meaningful_lines[:15]:
                    response += f"- {line}\n"
            
            response = response.strip()
            
            if response and not response.endswith(".") and not response.endswith("?") and not response.endswith(":"):
                response += "."
            
            return response
        
        # No context availabe - be explicit about not having information
        if query:
            return f"Xin lỗi, tôi không tìm thấy thông tin về '{query}' trong dữ liệu hiện có. Vui lòng thử lại với câu hỏi cụ thể hơn hoặc liên hệ bộ phận hỗ trợ để được giúp đỡ."
        return "Xin lỗi, tôi không tìm thấy thông tin phù hợp để trả lời câu hỏi này trong dữ liệu hiện có. Vui lòng thử lại với câu hỏi cụ thể hơn hoặc liên hệ bộ phận hỗ trợ."

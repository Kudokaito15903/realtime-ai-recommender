"""
Product Information Intent Handler
"""

from typing import Dict, Any, List, Optional
from loguru import logger
import re

from domain.chatbot.rag_engine import RAGEngine
from domain.chatbot.response_generator import ResponseGenerator
from utils.formatters import format_product_info_response
from adapters.factory import get_product_store


class ProductInfoHandler:
    """
    Handle product information queries.
    
    Examples:
    - "iPhone 17 Pro có những tính năng gì?"
    - "Cho tôi biết về laptop Dell XPS"
    - "Máy này pin trâu không?"
    - "Cấu hình như thế nào?"
    """

    def __init__(self):
        self.rag_engine = RAGEngine()
        self.response_generator = ResponseGenerator()
        self.product_store = get_product_store()

    async def handle(
        self,
        query: str,
        conversation_history: Optional[List[Dict]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Handle product info query.
        """
        logger.info(f"Handling product_info: {query[:50]}...")

        # Step 1: Extract product entities from query
        product_ids = self._extract_product_ids(query, context)
        intent = context.get("intent") if context else "product_info"


        if intent == "product_search":
            return await self._handle_product_search(query)

        # Step 2: Retrieve product knowledge chunks
        chunks = await self.rag_engine.retrieve_product_chunks(
            query=query,
            product_ids=product_ids,
            top_k=3
        )

        if not chunks:
            return self._no_product_response()

        # Step 3: Get product details
        products = await self._get_products_from_chunks(chunks)

        # Step 4: Build context
        context_text = self.rag_engine.build_context(chunks, max_tokens=2000)
        
        # Log context for debugging
        logger.debug(f"Context text length: {len(context_text)} chars")
        logger.debug(f"Context preview: {context_text[:200]}...")

        # Step 5: Generate response
        response_text = await self.response_generator.generate_product_response(
            query=query,
            context=context_text,
            conversation_history=conversation_history
        )
        
        logger.debug(f"Generated response length: {len(response_text)} chars")
        logger.debug(f"Response preview: {response_text[:200]}...")

        # Step 6: Format response
        formatted_response = format_product_info_response(
            message=response_text,
            products=products,
            sources=chunks
        )

        logger.info(f"✅ Product info response generated ({len(products)} products)")

        return formatted_response



    async def _handle_product_search(self, query: str) -> Dict[str, Any]:
        """Handle product search intent."""
        logger.info(f"Handling product_search: {query[:50]}...")
        
        chunks = await self.rag_engine.retrieve_product_chunks(query=query, top_k=5)
        logger.debug(f"Retrieved {len(chunks)} chunks for product search")
        
        products = await self._get_products_from_chunks(chunks)

        if not products:
            logger.warning("No products found from chunks in product_search")
            return self._no_product_response()

        # Build comprehensive context
        context_text = self.rag_engine.build_context(chunks, max_tokens=2000)
        
        # Enrich context with hydrated product specs
        for p in products:
            p_name = p.get('name', 'Unknown')
            specs = p.get('specifications', [])
            if specs:
                context_text += f"\n\nThông số kỹ thuật chi tiết của {p_name}:\n"
                valid_keys = ["CPU", "RAM", "Dung lượng", "Màn hình", "Pin", "Camera sau", "Camera trước", "Sạc"]
                for s in specs:
                    if s.get("key") in valid_keys:
                        context_text += f"- {s.get('key')}: {s.get('value')}\n"
        
        # Enhance query to ensure LLM understands we want detailed product info
        enhanced_query = f"""Người dùng muốn biết thông tin chi tiết về sản phẩm: {query}

Hãy cung cấp thông tin ĐẦY ĐỦ về:
- Tên sản phẩm chính xác
- Thông số kỹ thuật (CPU, RAM, bộ nhớ, màn hình, camera, pin, v.v.)
- Tính năng nổi bật
- Giá cả (nếu có trong context)
- Thông tin bảo hành
- Bất kỳ thông tin quan trọng nào khác về sản phẩm"""

        response_text = await self.response_generator.generate_product_response(
             query=enhanced_query,
             context=context_text,
             conversation_history=[]
        )

        return format_product_info_response(response_text, products, chunks)

    def _extract_product_ids(
        self, query: str, context: Optional[Dict[str, Any]]
    ) -> Optional[List[str]]:
        """Extract product IDs from query or context."""
        """Extract product IDs from query or context."""
        # Simple extraction - can be enhanced with NER
        if context and "product_ids" in context:
            return context["product_ids"]
            
        ids = []
        # Pattern like #12345
        match = re.search(r"#(\w+)", query)
        if match:
             ids.append(match.group(1))
             
        return ids if ids else None

    async def _get_products_from_chunks(
        self, chunks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Get product details from chunks, fetching fresh data from DB."""
        products = []
        product_ids_seen = set()

        for chunk in chunks:
            # Extract product_id from metadata
            metadata = chunk.get("metadata", {})
            product_id = metadata.get("product_id")
            
            if not product_id or product_id in product_ids_seen:
                continue

            # Fetch fresh product data from store
            try:
                product_data = self.product_store.get_product(product_id)
                if product_data:
                    # Enrich with vector score for context if needed
                    product_data["similarity_score"] = chunk.get("score", 0)
                    products.append(product_data)
                    product_ids_seen.add(product_id)
                    logger.debug(f"Hydrated product {product_id} from DB")
                else:
                    logger.warning(f"Product {product_id} not found in DB, falling back to metadata")
                    # Fallback to metadata
                    if metadata:
                        cleaned_text = metadata.get("text", "").replace("\n", " ").strip()
                        products.append({
                            "id": product_id,
                            "name": metadata.get("product_name", "Unknown Product"),
                            "brand": metadata.get("brand", ""),
                            "description": cleaned_text[:300] + "..." if len(cleaned_text) > 300 else cleaned_text,
                            "similarity_score": chunk.get("score", 0),
                            "is_fallback": True
                        })
                        product_ids_seen.add(product_id)
            except Exception as e:
                 logger.error(f"Failed to fetch product {product_id}: {e}")
                 # Fallback to metadata if DB fetch fails
                 if metadata:
                     products.append({
                         "id": product_id,
                         "name": metadata.get("product_name", "Unknown"),
                         "description": metadata.get("text", ""),
                     })
                     product_ids_seen.add(product_id)
        
        return products

    def _no_product_response(self) -> Dict[str, Any]:
        """Response when no product found."""
        return {
            "type": "product_info",
            "message": "Xin lỗi, tôi không tìm thấy thông tin về sản phẩm bạn đang tìm. Vui lòng thử lại với tên sản phẩm cụ thể hơn.",
            "products": [],
            "sources": [],
            "quick_actions": [
                {"label": "Tìm kiếm sản phẩm", "action": "search_products"},
                {"label": "Xem danh mục", "action": "browse_categories"},
            ],
        }

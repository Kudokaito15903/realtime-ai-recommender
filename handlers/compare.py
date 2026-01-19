"""
Product Comparison Intent Handler
"""

from typing import Dict, Any, List, Optional
from loguru import logger
import re

from domain.chatbot.rag_engine import RAGEngine
from domain.chatbot.response_generator import ResponseGenerator
from utils.formatters import format_comparison_response
from adapters.factory import get_product_store


class CompareHandler:
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

        logger.info(f"Handling compare: {query[:50]}...")

        product_ids = None
        if context and "product_ids" in context:
             product_ids = context["product_ids"]


        chunks = await self.rag_engine.retrieve_product_chunks(
            query=query,
            product_ids=product_ids,
            top_k=5  
        )

        if len(chunks) < 2:
            return self._insufficient_products_response()

        products = await self._get_products_from_chunks(chunks)

        if len(products) < 2:
            return self._insufficient_products_response()

        context_text = self.rag_engine.build_context(chunks, max_tokens=2500)

        response_text = await self.response_generator.generate_comparison_response(
            query=query,
            context=context_text,
            conversation_history=conversation_history
        )

        formatted_response = format_comparison_response(
            message=response_text,
            products=products
        )

        logger.info(f"✅ Comparison response generated ({len(products)} products)")

        return formatted_response

    async def _handle_comparison_query(self, query: str) -> Dict[str, Any]:
        pass 
        
    def _extract_product_ids_for_comparison(
        self, query: str, context: Optional[Dict[str, Any]]
    ) -> Optional[List[str]]:
        if context and "product_ids" in context:
            ids = context["product_ids"]
            return ids if isinstance(ids, list) else [ids]
        
        ids = []
        
        match = re.search(r"so sánh (.+) và (.+)", query, re.IGNORECASE)
        if match:
            ids.extend([match.group(1).strip(), match.group(2).strip()])
            
        if not ids:
            match = re.search(r"(.+) vs (.+)", query, re.IGNORECASE)
            if match:
                ids.extend([match.group(1).strip(), match.group(2).strip()])

        if not ids:
             match = re.search(r"giữa (.+) và (.+)", query, re.IGNORECASE)
             if match:
                ids.extend([match.group(1).strip(), match.group(2).strip()])
        
        return ids if ids else None

        return products[:3]  # Limit to 3 products for comparison

    def _normalize_product_specs(self, product: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize product specifications for comparison table.
        Maps raw specs (list of dicts) to normalized keys.
        """
        specs = product.get("specifications", [])
        normalized = {}
        
        # Mapping from raw key to normalized key
        key_map = {
            "CPU": "cpu",
            "RAM": "ram_gb", 
            "Dung lượng": "storage_gb",
            "Màn hình": "screen_size_inch",
            "Camera sau": "camera_mp",
            "Pin": "battery_hours",
            "Sạc": "charging_speed",
            "Chất liệu": "material"
        }

        for spec in specs:
             raw_key = spec.get("key")
             value = spec.get("value")
             
             if raw_key in key_map:
                 norm_key = key_map[raw_key]
                 # Simple cleaning logic
                 if norm_key == "ram_gb":
                     value = value.replace("GB", "").strip()
                 elif norm_key == "storage_gb":
                     value = value.replace("GB", "").strip()
                 elif norm_key == "screen_size_inch":
                     value = value.split(" inch")[0].strip()
                 elif norm_key == "battery_hours":
                     value = value.replace(" mAh", "").strip()
                 
                 normalized[norm_key] = value
                 
        return normalized

    async def _get_products_from_chunks(
        self, chunks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Get product details from chunks."""
        products = []
        product_ids_seen = set()

        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            product_id = metadata.get("product_id")

            if product_id and product_id not in product_ids_seen:
                try:
                    product = self.product_store.get_product(product_id)
                    if product:
                        # Normalize specs for comparison
                        product["specs_normalized"] = self._normalize_product_specs(product)
                        products.append(product)
                        product_ids_seen.add(product_id)
                except Exception as e:
                    logger.warning(f"Error fetching product {product_id}: {e}")

        return products[:3]  # Limit to 3 products for comparison

    def _insufficient_products_response(self) -> Dict[str, Any]:
        """Response when not enough products for comparison."""
        return {
            "type": "compare",
            "message": "Để so sánh sản phẩm, vui lòng cung cấp ít nhất 2 tên sản phẩm cụ thể. Ví dụ: 'So sánh iPhone 17 Pro và Samsung S25'",
            "comparison": None,
            "quick_actions": [
                {"label": "Tìm sản phẩm", "action": "search_products"},
                {"label": "Xem danh mục", "action": "browse_categories"},
            ],
        }

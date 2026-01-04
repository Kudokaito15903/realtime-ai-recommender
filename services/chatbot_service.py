import os
import time
import json
import re
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from loguru import logger
from urllib import request as urlrequest
from urllib.error import HTTPError
from openai import AsyncOpenAI
import redis.asyncio as redis

from adapters.factory import get_vector_store, get_product_store, get_content_store, get_user_behavior
from domain.embeddings.product_embeddings import get_embedding_model
import config

class ChatbotService:
    def __init__(self):
        self.vector_store = get_vector_store()
        self.embedding_model = get_embedding_model()
        self.product_store = get_product_store()
        self.content_store = get_content_store()
        self.user_behavior = get_user_behavior()
        
        # Async OpenAI Client
        self.client = AsyncOpenAI(
            base_url=config.OPENAI_API_URL,
            api_key=config.OPENAI_API_KEY,
        )
        
        self.brand_personality = config.BRAND_PERSONALITY
        self.collect_data = config.COLLECT_FINE_TUNING_DATA
        self.data_file = os.path.join("data", "fine_tuning_data.jsonl")
        
        # Redis Caching
        self.conf = config.Config()
        self.redis = redis.from_url(self.conf.get_redis_url())

    async def _get_embedding_async(self, query: str):
        """Run blocking embedding generation in a thread."""
        return await asyncio.to_thread(self.embedding_model.get_embedding, query)

    async def _find_similar_products_async(self, embedding, limit):
        """Run blocking vector search in a thread."""
        return await asyncio.to_thread(
            self.vector_store.find_similar_products,
            embedding=embedding,
            limit=limit,
            min_score=0.0
        )

    async def _fetch_product_async(self, pid):
        """Run blocking product fetch in a thread."""
        # Check if product store is available
        if not self.product_store:
            return None
        try:
             return await asyncio.to_thread(self.product_store.get_product, pid)
        except Exception as e:
            logger.warning(f"Error fetching product {pid}: {e}")
            return None

    async def _fetch_content_async(self, cid):
        """Run blocking content fetch in a thread."""
        if not self.content_store:
            return None
        try:
            return await asyncio.to_thread(self.content_store.get_content, cid)
        except Exception:
            return None

    async def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Retrieve top-K documents asynchronously."""
        if not query:
            return []
            
        # 1. Generate Embedding
        q_emb = await self._get_embedding_async(query)
        
        # 2. Vector Search
        candidates = await self._find_similar_products_async(q_emb, top_k * 2)
        
        # 3. Enrich Results Concurrently
        tasks = []
        for c in candidates:
            pid = c.get("product_id")
            meta = c.get("metadata", {}) or {}
            item_type = meta.get("type", "product")
            
            if item_type == "product":
                tasks.append(self._fetch_product_async(pid))
            elif item_type == "content":
                tasks.append(self._fetch_content_async(pid))
            else:
                tasks.append(asyncio.sleep(0)) # No op

        # Run all data fetches in parallel
        details_list = await asyncio.gather(*tasks)
        
        results: List[Dict[str, Any]] = []
        for c, details in zip(candidates, details_list):
            if details is None:
                continue
                
            pid = c.get("product_id")
            meta = c.get("metadata", {}) or {}
            item_type = meta.get("type", "product")
            
            results.append({
                "id": pid,
                "type": item_type,
                "score": float(c.get("similarity_score", c.get("score", 0.0))),
                "metadata": meta,
                "data": details,
            })
            
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def _build_prompt(self, query: str, contexts: List[Dict[str, Any]]) -> str:
        """Construct a simple RAG prompt combining contexts and user query."""
        context_texts = []
        for i, ctx in enumerate(contexts):
            item_type = ctx.get("type", "product")
            data = ctx.get("data") or {}
            meta = ctx.get("metadata", {}) or {}
            snippet = []

            if item_type == "product":
                title = data.get("name") if isinstance(data, dict) else None
                if title:
                    snippet.append(f"Product Title: {title}")
                # include some metadata fields if present
                for k in ("price", "avgRating", "sold"):
                    if k in meta:
                        snippet.append(f"{k}: {meta.get(k)}")
                # include short description if available
                if isinstance(data, dict) and data.get("description"):
                    snippet.append(f"Description: {data.get('description')[:200]}")
            elif item_type == "content":
                title = data.get("title") if isinstance(data, dict) else None
                if title:
                    snippet.append(f"Content Title: {title}")
                category = data.get("category") if isinstance(data, dict) else None
                if category:
                    snippet.append(f"Category: {category}")
                # include short content
                if isinstance(data, dict) and data.get("content"):
                    snippet.append(f"Content: {data.get('content')[:300]}")

            context_texts.append(f"[{i+1}] " + " | ".join(snippet))

        contexts_combined = "\n".join(context_texts)
        prompt = (
            "You are a helpful e-commerce assistant. Use the provided product and content information to answer the user's question. "
            "If you don't know the answer, say you don't know.\n"
            f"{self.brand_personality}\n\n"
        )
        if contexts_combined:
            prompt += f"Context:\n{contexts_combined}\n\n"
        prompt += f"User question: {query}\nAnswer concisely."
        return prompt

    def _build_product_info_prompt(self, query: str, products: List[Dict[str, Any]]) -> str:
        """Build prompt for product information queries."""
        product_texts = []
        for i, product in enumerate(products):
            text = f"\nSản phẩm {i+1}: {product.get('name', 'N/A')}\n"
            text += f"- ID: {product.get('id', 'N/A')}\n"
            if product.get('price'):
                text += f"- Giá: {product.get('price'):,.0f} VNĐ\n"
            if product.get('brand'):
                text += f"- Thương hiệu: {product.get('brand')}\n"
            if product.get('rating'):
                text += f"- Đánh giá: {product.get('rating')}/5\n"
            if product.get('sold'):
                text += f"- Đã bán: {product.get('sold')} sản phẩm\n"
            if product.get('description'):
                text += f"- Mô tả: {product.get('description')}\n"
            
            if product.get('variants'):
                text += "- Các phiên bản:\n"
                for v in product['variants']:
                    text += f"  + {v.get('variantName', 'N/A')} ({v.get('color', 'N/A')}): {v.get('price', 0):,.0f} VNĐ\n"
            
            if product.get('specifications'):
                text += "- Thông số kỹ thuật:\n"
                for spec in product['specifications']:
                    text += f"  + {spec.get('key', 'N/A')}: {spec.get('value', 'N/A')}\n"
            
            product_texts.append(text)
        
        prompt = (
            "Bạn là trợ lý bán hàng thông minh. Hãy trả lời câu hỏi của khách hàng về thông tin sản phẩm "
            "dựa trên dữ liệu sản phẩm được cung cấp.\n"
            f"{self.brand_personality}\n\n"
        )
        prompt += "Thông tin sản phẩm:\n" + "\n".join(product_texts)
        prompt += f"\n\nCâu hỏi của khách hàng: {query}\n"
        prompt += "Hãy trả lời bằng tiếng Việt một cách tự nhiên và hữu ích."
        return prompt

    def _build_comparison_prompt(self, query: str, products: List[Dict[str, Any]]) -> str:
        """Build prompt for product comparison queries."""
        comparison_text = "So sánh các sản phẩm sau:\n\n"
        
        for i, product in enumerate(products):
            comparison_text += f"=== Sản phẩm {i+1}: {product.get('name', 'N/A')} ===\n"
            comparison_text += f"ID: {product.get('id', 'N/A')}\n"
            if product.get('price'):
                comparison_text += f"Giá: {product.get('price'):,.0f} VNĐ\n"
            if product.get('price_range'):
                min_p, max_p = product['price_range']
                comparison_text += f"Khoảng giá: {min_p:,.0f} - {max_p:,.0f} VNĐ\n"
            if product.get('rating'):
                comparison_text += f"Đánh giá: {product.get('rating')}/5 sao\n"
            if product.get('sold'):
                comparison_text += f"Đã bán: {product.get('sold')} sản phẩm\n"
            if product.get('brand'):
                comparison_text += f"Thương hiệu: {product.get('brand')}\n"
            if product.get('category'):
                comparison_text += f"Danh mục: {product.get('category')}\n"
            if product.get('description'):
                comparison_text += f"Mô tả: {product.get('description')}\n"
            if product.get('key_specs'):
                comparison_text += "Thông số chính:\n"
                for key, value in product['key_specs'].items():
                    comparison_text += f"  - {key}: {value}\n"
            comparison_text += "\n"
        
        prompt = (
            "Bạn là chuyên gia tư vấn sản phẩm. Hãy so sánh các sản phẩm được liệt kê dưới đây "
            "dựa trên giá cả, đánh giá, thông số kỹ thuật và các đặc điểm khác. "
            "Hãy đưa ra nhận xét khách quan và gợi ý sản phẩm phù hợp nhất.\n"
            f"{self.brand_personality}\n\n"
        )
        prompt += comparison_text
        prompt += f"\nCâu hỏi của khách hàng: {query}\n"
        prompt += "Hãy trả lời bằng tiếng Việt, so sánh chi tiết và đưa ra lời khuyên hữu ích."
        return prompt

    def _build_policy_prompt(self, query: str, contexts: List[Dict[str, Any]]) -> str:
        """Build prompt for policy queries."""
        policy_texts = []
        for i, ctx in enumerate(contexts):
            data = ctx.get("data", {})
            if isinstance(data, dict):
                title = data.get("title", "Chính sách")
                content = data.get("content", "")
                category = data.get("category", "")
                policy_texts.append(f"\n[{i+1}] {title} ({category})\n{content[:500]}\n")
        
        prompt = (
            "Bạn là nhân viên tư vấn chính sách. Hãy trả lời câu hỏi của khách hàng về các chính sách "
            "của cửa hàng dựa trên thông tin được cung cấp.\n"
            f"{self.brand_personality}\n\n"
        )
        if policy_texts:
            prompt += "Thông tin chính sách:\n" + "\n".join(policy_texts)
        prompt += f"\n\nCâu hỏi của khách hàng: {query}\n"
        prompt += "Hãy trả lời bằng tiếng Việt, giải thích chi tiết và cung cấp thông tin liên hệ nếu cần."
        return prompt

    def _build_cskh_prompt(self, query: str, contexts: List[Dict[str, Any]]) -> str:
        """Build prompt for customer service queries."""
        context_texts = []
        for i, ctx in enumerate(contexts):
            data = ctx.get("data", {})
            if isinstance(data, dict):
                if ctx.get("type") == "content":
                    title = data.get("title", "")
                    content = data.get("content", "")
                    context_texts.append(f"[{i+1}] {title}\n{content[:300]}\n")
                elif ctx.get("type") == "product":
                    name = data.get("name", "")
                    desc = data.get("description", "")
                    context_texts.append(f"[{i+1}] Sản phẩm: {name}\n{desc[:200]}\n")
        
        prompt = (
            "Bạn là nhân viên chăm sóc khách hàng chuyên nghiệp. Hãy trả lời câu hỏi của khách hàng "
            "một cách hữu ích và chuyên nghiệp. Nếu không có thông tin, hãy hướng dẫn khách hàng liên hệ bộ phận hỗ trợ.\n"
            f"{self.brand_personality}\n\n"
        )
        if context_texts:
            prompt += "Thông tin tham khảo:\n" + "\n".join(context_texts)
        prompt += f"\n\nCâu hỏi của khách hàng: {query}\n"
        prompt += "Hãy trả lời bằng tiếng Việt một cách thân thiện và hữu ích."
        return prompt

    def _build_realtime_prompt(self, query: str, realtime_data: List[Dict[str, Any]]) -> str:
        """Build prompt for realtime data queries."""
        data_texts = []
        for i, data in enumerate(realtime_data):
            text = f"\nSản phẩm {i+1}: {data.get('name', 'N/A')}\n"
            text += f"- ID: {data.get('product_id', 'N/A')}\n"
            if data.get('current_price'):
                text += f"- Giá hiện tại: {data.get('current_price'):,.0f} VNĐ\n"
            if data.get('rating'):
                text += f"- Đánh giá: {data.get('rating')}/5 sao\n"
            if data.get('sold_count'):
                text += f"- Đã bán: {data.get('sold_count')} sản phẩm\n"
            
            if data.get('variants_stock'):
                text += "- Tình trạng tồn kho các phiên bản:\n"
                for v in data['variants_stock']:
                    stock_status = v.get('stock', 'unknown')
                    if stock_status == True or stock_status == 'in_stock' or stock_status == 'còn hàng':
                        stock_text = "Còn hàng"
                    elif stock_status == False or stock_status == 'out_of_stock' or stock_status == 'hết hàng':
                        stock_text = "Hết hàng"
                    else:
                        stock_text = str(stock_status)
                    
                    text += f"  + {v.get('variantName', 'N/A')} ({v.get('color', 'N/A')}): {stock_text}"
                    if v.get('price'):
                        text += f" - {v.get('price'):,.0f} VNĐ"
                    text += "\n"
            
            if data.get('last_updated'):
                text += f"- Cập nhật lần cuối: {data.get('last_updated')}\n"
            
            data_texts.append(text)
        
        prompt = (
            "Bạn là trợ lý bán hàng. Hãy trả lời câu hỏi của khách hàng về tình trạng tồn kho, "
            "giá cả và thông tin realtime của sản phẩm dựa trên dữ liệu được cung cấp.\n"
            f"{self.brand_personality}\n\n"
        )
        prompt += "Dữ liệu realtime:\n" + "\n".join(data_texts)
        prompt += f"\n\nCâu hỏi của khách hàng: {query}\n"
        prompt += "Hãy trả lời bằng tiếng Việt, cung cấp thông tin realtime chính xác."
        return prompt

    async def _call_openai_chat(self, prompt: str) -> str:
        """
        Call OpenRouter Chat Completions API via Async Client.
        """
        try:
            completion = await self.client.chat.completions.create(
                model= config.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": f"You are an e-commerce recommendation assistant. {self.brand_personality}"},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=512,
                temperature=0.2,
                extra_headers={
                    "HTTP-Referer": "http://localhost:8000",
                    "X-Title": "realtime-ai-recommender",
                }
            )

            return completion.choices[0].message.content

        except Exception as e:
            logger.exception("LLM call failed")
            return "Xin lỗi, hệ thống AI đang bận. Vui lòng thử lại sau."

    def _detect_intent(self, query: str) -> str:
        """
        Detect user intent from query.
        Returns: 'product_info', 'compare', 'policy', 'cskh', 'realtime', or 'general'
        """
        query_lower = query.lower()
        
        # Product comparison keywords
        compare_keywords = ['so sánh', 'compare', 'khác nhau', 'giống nhau', 'nên mua', 'nên chọn']
        if any(kw in query_lower for kw in compare_keywords):
            return 'compare'
        
        # Product information keywords
        product_info_keywords = ['thông tin', 'thông số', 'spec', 'chi tiết', 'mô tả', 'giá', 'giá bán', 'giá bao nhiêu']
        product_name_pattern = r'(sản phẩm|product|máy|điện thoại|laptop|tivi|tủ lạnh|máy giặt|iphone|samsung|xiaomi)'
        if any(kw in query_lower for kw in product_info_keywords) or re.search(product_name_pattern, query_lower):
            return 'product_info'
        
        # Policy keywords
        policy_keywords = ['chính sách', 'policy', 'đổi trả', 'bảo hành', 'vận chuyển', 'giao hàng', 'thanh toán', 'hoàn tiền']
        if any(kw in query_lower for kw in policy_keywords):
            return 'policy'
        
        # CSKH keywords
        cskh_keywords = ['hỗ trợ', 'tư vấn', 'liên hệ', 'hotline', 'email', 'cskh', 'customer service', 'help', 'giúp đỡ']
        if any(kw in query_lower for kw in cskh_keywords):
            return 'cskh'
        
        # Realtime data keywords
        realtime_keywords = ['còn hàng', 'hết hàng', 'tồn kho', 'stock', 'số lượng', 'còn lại', 'realtime', 'thời gian thực']
        if any(kw in query_lower for kw in realtime_keywords):
            return 'realtime'
        
        return 'general'

    async def get_product_info(self, query: str, top_k: int = 3) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Get detailed product information based on query.
        """
        # Try to extract product name/ID from query
        contexts = await self.retrieve(query, top_k=top_k)
        
        if not contexts:
            return "Xin lỗi, tôi không tìm thấy thông tin sản phẩm nào phù hợp với câu hỏi của bạn.", []
        
        # Build detailed product information
        product_details = []
        for ctx in contexts:
            if ctx.get("type") == "product":
                product = ctx.get("data", {})
                if not product:
                    continue
                
                detail = {
                    "id": product.get("id"),
                    "name": product.get("name"),
                    "description": product.get("description", "")[:500],
                    "price": product.get("price"),
                    "category": product.get("category"),
                    "brand": product.get("brandName"),
                    "rating": product.get("avgRating"),
                    "sold": product.get("sold"),
                }
                
                # Add variants if available
                variants = product.get("productVariants", [])
                if variants:
                    detail["variants"] = [
                        {
                            "sku": v.get("sku"),
                            "variantName": v.get("variantName"),
                            "color": v.get("color"),
                            "price": v.get("price"),
                        }
                        for v in variants[:5]  # Limit to 5 variants
                    ]
                
                # Add specifications if available
                specs = product.get("specifications", [])
                if specs:
                    detail["specifications"] = [
                        {"key": s.get("key"), "value": s.get("value")}
                        for s in specs[:10]  # Limit to 10 specs
                    ]
                
                product_details.append(detail)
        
        # Build prompt with detailed product info
        prompt = self._build_product_info_prompt(query, product_details)
        answer = await self._call_openai_chat(prompt)
        
        return answer, product_details

    async def compare_products(self, query: str, top_k: int = 5) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Compare multiple products based on query.
        """
        # Extract product names/IDs from query
        contexts = await self.retrieve(query, top_k=top_k)
        
        if len(contexts) < 2:
            return "Để so sánh sản phẩm, vui lòng cung cấp tên hoặc mô tả của ít nhất 2 sản phẩm.", []
        
        # Get product details for comparison
        products_to_compare = []
        for ctx in contexts[:5]:  # Limit to 5 products
            if ctx.get("type") == "product":
                product = ctx.get("data", {})
                if not product:
                    continue
                
                # Get best variant price
                variants = product.get("productVariants", [])
                min_price = None
                max_price = None
                if variants:
                    prices = [v.get("price", 0) for v in variants if v.get("price")]
                    if prices:
                        min_price = min(prices)
                        max_price = max(prices)
                
                product_info = {
                    "id": product.get("id"),
                    "name": product.get("name"),
                    "price": product.get("price") or min_price,
                    "price_range": (min_price, max_price) if min_price and max_price else None,
                    "rating": product.get("avgRating", 0),
                    "sold": product.get("sold", 0),
                    "brand": product.get("brandName"),
                    "category": product.get("category"),
                    "description": product.get("description", "")[:300],
                }
                
                # Add key specifications
                specs = product.get("specifications", [])
                if specs:
                    product_info["key_specs"] = {
                        s.get("key"): s.get("value")
                        for s in specs[:5]  # Top 5 specs
                    }
                
                products_to_compare.append(product_info)
        
        if len(products_to_compare) < 2:
            return "Không tìm đủ sản phẩm để so sánh. Vui lòng cung cấp tên sản phẩm cụ thể hơn.", []
        
        # Build comparison prompt
        prompt = self._build_comparison_prompt(query, products_to_compare)
        answer = await self._call_openai_chat(prompt)
        
        return answer, products_to_compare

    async def get_policy_info(self, query: str, top_k: int = 5) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Get policy information (return, warranty, shipping, payment, etc.)
        """
        # Search for policy content
        contexts = await self.retrieve(query, top_k=top_k)
        
        # Filter for content type (policies)
        policy_contexts = [
            ctx for ctx in contexts
            if ctx.get("type") == "content" or 
            ctx.get("metadata", {}).get("category", "").lower() in ["policy", "chính sách", "cskh"]
        ]
        
        # Helper to check for CSKH keywords
        cskh_keywords = ['hỗ trợ', 'tư vấn', 'liên hệ', 'hotline', 'email', 'cskh', 'customer service', 'help', 'giúp đỡ']
        has_cskh = any(kw in query.lower() for kw in cskh_keywords)

        if not policy_contexts:
            # Fallback: search content store directly
            if self.content_store:
                try:
                    # Fetch broader categories
                    categories_to_fetch = ["policy"]
                    if has_cskh:
                        categories_to_fetch.append("cskh")

                    for cat in categories_to_fetch:
                        # self.content_store.list_content is blocking, ensure wrapping if needed
                        # For now assume mostly fast or need to wrap in to_thread
                        all_content = await asyncio.to_thread(self.content_store.list_content, category=cat, limit=5)
                        for content in all_content:
                            policy_contexts.append({
                                "id": content.get("id"),
                                "type": "content",
                                "data": content,
                                "score": 0.5,
                            })
                except Exception as e:
                    logger.warning(f"Error fetching policy content: {e}")
        
        # If query contains explicit CSKH intent but we didn't get any CSKH content in vector results,
        # explicitly fetch it.
        if has_cskh and self.content_store:
             # Check if we already have cskh content
            has_cskh_context = any(
                ctx.get("data", {}).get("category") == "cskh" or 
                ctx.get("metadata", {}).get("category") == "cskh" 
                for ctx in policy_contexts
            )
            
            if not has_cskh_context:
                try:
                    cskh_content = await asyncio.to_thread(self.content_store.list_content, category="cskh", limit=3)
                    for content in cskh_content:
                         policy_contexts.append({
                            "id": content.get("id"),
                            "type": "content",
                            "data": content,
                            "score": 0.6, # Artificial boost
                        })
                except Exception as e:
                    logger.warning(f"Error fetching CSKH content: {e}")

        if not policy_contexts:
            return "Xin lỗi, tôi không tìm thấy thông tin chính sách phù hợp. Vui lòng liên hệ CSKH để được hỗ trợ.", []
        
        # Build policy prompt
        prompt = self._build_policy_prompt(query, policy_contexts)
        answer = await self._call_openai_chat(prompt)
        
        return answer, policy_contexts

    async def handle_cskh(self, query: str) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Handle customer service queries automatically.
        """
        # Search for CSKH content
        contexts = await self.retrieve(query, top_k=5)
        
        # Filter for CSKH content
        cskh_contexts = [
            ctx for ctx in contexts
            if ctx.get("type") == "content" or
            ctx.get("metadata", {}).get("category", "").lower() in ["cskh", "faq", "help", "support"]
        ]
        
        # If no specific content, use general retrieval
        if not cskh_contexts:
            cskh_contexts = contexts
        
        # Build CSKH prompt with helpful responses
        prompt = self._build_cskh_prompt(query, cskh_contexts)
        answer = await self._call_openai_chat(prompt)
        
        return answer, cskh_contexts

    async def get_realtime_data(self, query: str, top_k: int = 3) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Get realtime data (stock, price, rating updates).
        """
        # Extract product from query
        contexts = await self.retrieve(query, top_k=top_k)
        
        if not contexts:
            return "Xin lỗi, tôi không tìm thấy sản phẩm nào. Vui lòng cung cấp tên sản phẩm cụ thể.", []
        
        # Get realtime data for products
        realtime_info = []
        for ctx in contexts:
            if ctx.get("type") == "product":
                product = ctx.get("data", {})
                if not product:
                    continue
                
                product_id = product.get("id")
                
                # Get fresh product data using thread
                fresh_product = None
                if self.product_store:
                    try:
                        fresh_product = await asyncio.to_thread(self.product_store.get_product, product_id)
                    except Exception as e:
                        logger.warning(f"Error fetching fresh product data: {e}")
                
                if not fresh_product:
                    fresh_product = product
                
                # Get variants with stock info
                variants = fresh_product.get("productVariants", [])
                stock_info = []
                for variant in variants:
                    stock_info.append({
                        "sku": variant.get("sku"),
                        "variantName": variant.get("variantName"),
                        "price": variant.get("price"),
                        "stock": variant.get("stock", variant.get("inStock", "unknown")),
                        "color": variant.get("color"),
                    })
                
                # Get recent interaction stats if available
                # This would need to be implemented in user_behavior interface
                # For now, pass
                
                realtime_data = {
                    "product_id": product_id,
                    "name": fresh_product.get("name"),
                    "current_price": fresh_product.get("price"),
                    "rating": fresh_product.get("avgRating", 0),
                    "sold_count": fresh_product.get("sold", 0),
                    "variants_stock": stock_info,
                    "last_updated": fresh_product.get("updated_at"),
                }
                
                realtime_info.append(realtime_data)
        
        # Build realtime data prompt
        prompt = self._build_realtime_prompt(query, realtime_info)
        answer = await self._call_openai_chat(prompt)
        
        return answer, realtime_info

    def _log_interaction(self, query: str, contexts: List[Dict[str, Any]], answer: str, intent: str):
        """Log interaction for fine-tuning. (Sync is fine here)"""
        if not self.collect_data:
            return

        try:
            # Format context for logging
            context_str = json.dumps([
                {
                    "id": c.get("id"),
                    "type": c.get("type"),
                    "name": c.get("data", {}).get("name") if c.get("type") == "product" else c.get("data", {}).get("title")
                } 
                for c in contexts
            ], ensure_ascii=False)

            log_entry = {
                "timestamp": time.time(),
                "intent": intent,
                "user_query": query,
                "context_summary": context_str,
                "model_answer": answer,
                "training_prompt": f"User: {query}\nContext: {context_str}",
                "training_completion": answer
            }
            
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            with open(self.data_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
                
        except Exception as e:
            # Don't let logging fail the response
            logger.warning(f"Failed to log interaction: {e}")

    async def answer(self, query: str, top_k: int = 5) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Main answer method with intent routing.
        """
        intent = self._detect_intent(query)
        logger.debug(f"Detected intent: {intent} for query: {query}")
        
        # Check Cache
        cache_key = f"chatbot:{intent}:{query}"
        try:
            cached = await self.redis.get(cache_key)
            if cached:
                logger.debug(f"Cache hit for {cache_key}")
                data = json.loads(cached)
                return data["answer"], data["contexts"]
        except Exception as e:
            logger.warning(f"Cache get failed: {e}")

        if intent == 'product_info':
            answer, contexts = await self.get_product_info(query, top_k=top_k)
        elif intent == 'compare':
            answer, contexts = await self.compare_products(query, top_k=top_k)
        elif intent == 'policy':
            answer, contexts = await self.get_policy_info(query, top_k=top_k)
        elif intent == 'cskh':
            answer, contexts = await self.handle_cskh(query)
        elif intent == 'realtime':
            answer, contexts = await self.get_realtime_data(query, top_k=top_k)
        else:
            # General query - use original RAG approach
            contexts = await self.retrieve(query, top_k=top_k)
            prompt = self._build_prompt(query, contexts)
            answer = await self._call_openai_chat(prompt)
        
        # Log the interaction (sync is okay, or wrap in thread if file IO is slow)
        self._log_interaction(query, contexts, answer, intent)
        
        # Set Cache
        try:
            ttl = 60 # Default 60s
            if intent == 'realtime':
                ttl = 10 # Short cache for realtime
            elif intent == 'product_info':
                ttl = 3600 # 1h for static info
                
            await self.redis.setex(
                cache_key,
                ttl,
                json.dumps({"answer": answer, "contexts": contexts}, ensure_ascii=False)
            )
        except Exception as e:
             logger.warning(f"Cache set failed: {e}")

        return answer, contexts

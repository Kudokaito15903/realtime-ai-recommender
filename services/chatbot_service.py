"""
Enhanced Chatbot Service with Redis Cache Integration
"""

import os
import time
import json
import re
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from loguru import logger
from openai import OpenAI

from adapters.factory import get_vector_store, get_product_store, get_content_store, get_user_behavior
from domain.embeddings.product_embeddings import get_embedding_model
from redis_cache import RedisCache, cache_result 
import config


@dataclass
class Intent:
    """Structured intent classification result"""
    primary: str
    secondary: List[str]
    confidence: float
    entities: Dict[str, Any]
    
    def to_dict(self):
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict):
        return cls(**data)


@dataclass
class ConversationTurn:
    """Single turn in conversation"""
    query: str
    answer: str
    contexts: List[Dict[str, Any]]
    intent: Optional[Intent]
    timestamp: float
    metrics: Optional[Dict[str, float]] = None
    
    def to_dict(self):
        return {
            'query': self.query,
            'answer': self.answer,
            'contexts': self.contexts,
            'intent': self.intent.to_dict() if self.intent else None,
            'timestamp': self.timestamp,
            'metrics': self.metrics
        }
    
    @classmethod
    def from_dict(cls, data: Dict):
        intent_data = data.get('intent')
        intent = Intent.from_dict(intent_data) if intent_data else None
        return cls(
            query=data['query'],
            answer=data['answer'],
            contexts=data['contexts'],
            intent=intent,
            timestamp=data['timestamp'],
            metrics=data.get('metrics')
        )


class ChatbotService:
    """Enhanced Chatbot Service with Redis caching"""
    
    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: Optional[str] = None,
        enable_cache: bool = True
    ):
        """
        Initialize Chatbot Service with Redis cache
        
        Args:
            redis_host: Redis server host
            redis_port: Redis server port
            redis_db: Redis database number
            redis_password: Redis password
            enable_cache: Whether to enable caching
        """
        # Initialize adapters
        self.vector_store = get_vector_store()
        self.embedding_model = get_embedding_model()
        self.product_store = get_product_store()
        self.content_store = get_content_store()
        self.user_behavior = get_user_behavior()
        
        # Initialize OpenAI client
        self.client = OpenAI(
            base_url=config.OPENAI_API_URL,
            api_key=config.OPENAI_API_KEY,
        )
        
        # Initialize Redis cache
        self.enable_cache = enable_cache
        if enable_cache:
            self.cache = RedisCache(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password
            )
            logger.info("Redis cache initialized")
        else:
            self.cache = None
            logger.info("Cache disabled")
        
        # Cache configuration
        self.CACHE_CONFIG = {
            'product_ttl': 300,          # 5 minutes
            'embedding_ttl': 3600,       # 1 hour
            'query_result_ttl': 180,     # 3 minutes
            'conversation_ttl': 1800,    # 30 minutes
            'intent_ttl': 600,           # 10 minutes
        }
    
    # ==================== CACHING METHODS ====================
    
    def _get_cache_key(self, *parts) -> str:
        """Generate cache key from parts"""
        key_str = ":".join(str(p) for p in parts)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get_product_cached(self, product_id: str) -> Optional[Dict[str, Any]]:
        """Get product with Redis caching"""
        if not self.enable_cache or not self.cache:
            return self._fetch_product_from_db(product_id)
        
        # Try cache first
        cached = self.cache.get(product_id, prefix='product')
        if cached:
            logger.debug(f"Product cache HIT: {product_id}")
            return cached
        
        # Cache miss
        logger.debug(f"Product cache MISS: {product_id}")
        product = self._fetch_product_from_db(product_id)
        
        if product:
            self.cache.set(
                product_id,
                product,
                prefix='product',
                ttl=self.CACHE_CONFIG['product_ttl']
            )
        
        return product
    
    def _fetch_product_from_db(self, product_id: str) -> Optional[Dict[str, Any]]:
        """Fetch product from database"""
        try:
            if self.product_store:
                return self.product_store.get_product(product_id)
        except Exception as e:
            logger.error(f"Failed to fetch product {product_id}: {e}")
        return None
    
    def get_embedding_cached(self, text: str) -> List[float]:
        """Get text embedding with caching"""
        if not self.enable_cache or not self.cache:
            return self.embedding_model.get_embedding(text)
        
        # Use hash of text as cache key
        cache_key = self._get_cache_key(text)
        
        cached = self.cache.get(cache_key, prefix='embedding')
        if cached:
            logger.debug(f"Embedding cache HIT")
            return cached
        
        # Generate embedding
        logger.debug(f"Embedding cache MISS")
        embedding = self.embedding_model.get_embedding(text)
        
        # Cache the embedding
        self.cache.set(
            cache_key,
            embedding,
            prefix='embedding',
            ttl=self.CACHE_CONFIG['embedding_ttl']
        )
        
        return embedding
    
    def save_conversation_turn(
        self,
        session_id: str,
        turn: ConversationTurn
    ):
        """Save conversation turn to Redis"""
        if not self.enable_cache or not self.cache:
            return
        
        try:
            # Get existing conversation
            conversation = self.cache.get_list(session_id, prefix='conversation') or []
            
            # Append new turn
            conversation.append(turn.to_dict())
            
            # Keep only last 10 turns
            conversation = conversation[-10:]
            
            # Save back to cache
            self.cache.set_list(
                session_id,
                conversation,
                prefix='conversation',
                ttl=self.CACHE_CONFIG['conversation_ttl']
            )
            logger.debug(f"Saved conversation turn for session {session_id}")
        except Exception as e:
            logger.warning(f"Failed to save conversation turn: {e}")
    
    def get_conversation_history(self, session_id: str) -> List[ConversationTurn]:
        """Get conversation history from Redis"""
        if not self.enable_cache or not self.cache:
            return []
        
        try:
            conversation_data = self.cache.get_list(session_id, prefix='conversation') or []
            return [ConversationTurn.from_dict(turn) for turn in conversation_data]
        except Exception as e:
            logger.warning(f"Failed to get conversation history: {e}")
            return []
    
    def clear_conversation(self, session_id: str):
        """Clear conversation history"""
        if self.enable_cache and self.cache:
            self.cache.delete(session_id, prefix='conversation')
            logger.info(f"Cleared conversation for session {session_id}")
    
    def cache_query_result(
        self,
        query: str,
        result: List[Dict[str, Any]],
        ttl: Optional[int] = None
    ):
        """Cache query result"""
        if not self.enable_cache or not self.cache:
            return
        
        cache_key = self._get_cache_key(query)
        self.cache.set(
            cache_key,
            result,
            prefix='query_result',
            ttl=ttl or self.CACHE_CONFIG['query_result_ttl']
        )
    
    def get_cached_query_result(self, query: str) -> Optional[List[Dict[str, Any]]]:
        """Get cached query result"""
        if not self.enable_cache or not self.cache:
            return None
        
        cache_key = self._get_cache_key(query)
        return self.cache.get(cache_key, prefix='query_result')
    
    def invalidate_product_cache(self, product_id: str):
        """Invalidate product cache (call when product is updated)"""
        if self.enable_cache and self.cache:
            self.cache.delete(product_id, prefix='product')
            # Also invalidate related query results
            self.cache.invalidate_pattern(f"{self.cache.PREFIXES['query_result']}*")
            logger.info(f"Invalidated cache for product {product_id}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        if self.enable_cache and self.cache:
            return self.cache.get_stats()
        return {'enabled': False}
    
    # ==================== CORE CHATBOT METHODS ====================
    
    def _resolve_coreferences(self, query: str, history: List[ConversationTurn]) -> str:
        """Resolve pronouns and references from conversation history"""
        if not history:
            return query
        
        query_lower = query.lower()
        pronouns = ['nó', 'nó đó', 'cái đó', 'cái này', 'sản phẩm đó', 'cái kia']
        
        for pronoun in pronouns:
            if pronoun in query_lower:
                for turn in reversed(history[-3:]):
                    if turn.contexts:
                        for ctx in turn.contexts:
                            if ctx.get('type') == 'product':
                                data = ctx.get('data')
                                if data:  # Safety check for None
                                    product_name = data.get('name')
                                    if product_name:
                                        resolved = query.replace(pronoun, product_name)
                                        logger.info(f"Resolved '{pronoun}' to '{product_name}'")
                                        return resolved
        
        return query
    
    def _detect_intent_llm(self, query: str, history: List[ConversationTurn]) -> Intent:
        """Advanced intent detection using LLM with caching"""
        
        # Check cache first
        if self.enable_cache and self.cache:
            cache_key = self._get_cache_key('intent', query, len(history))
            cached_intent = self.cache.get(cache_key, prefix='query_result')
            if cached_intent:
                logger.debug("Intent cache HIT")
                return Intent.from_dict(cached_intent)
        
        # Build context from history
        history_context = ""
        if history:
            recent = history[-3:]
            history_context = "Lịch sử hội thoại:\n"
            for i, turn in enumerate(recent):
                history_context += f"{i+1}. Khách: {turn.query}\n   Bot: {turn.answer[:100]}...\n"
        
        intent_prompt = f"""Phân tích câu hỏi của khách hàng và trả về intent dưới dạng JSON.

{history_context}

Câu hỏi hiện tại: "{query}"

Các intent có thể:
- product_search: Tìm kiếm sản phẩm
- product_info: Hỏi chi tiết về sản phẩm
- compare: So sánh sản phẩm
- stock_check: Kiểm tra tồn kho
- policy: Hỏi về chính sách
- support: Hỗ trợ chung
- greeting: Chào hỏi
- general: Câu hỏi chung

Trả về JSON (KHÔNG có markdown):
{{
  "primary_intent": "...",
  "secondary_intents": [],
  "confidence": 0.9,
  "entities": {{
    "product_names": [],
    "brands": [],
    "price_range": null,
    "keywords": []
  }},
  "reasoning": "..."
}}"""

        try:
            response = self._call_openai_chat(intent_prompt, max_tokens=300, temperature=0.1)
            response = response.strip()
            if response.startswith('```'):
                response = re.sub(r'^```json?\s*|\s*```$', '', response, flags=re.MULTILINE)
            
            intent_data = json.loads(response)
            intent = Intent(
                primary=intent_data.get('primary_intent', 'general'),
                secondary=intent_data.get('secondary_intents', []),
                confidence=intent_data.get('confidence', 0.7),
                entities=intent_data.get('entities', {})
            )
            
            # Cache the intent
            if self.enable_cache and self.cache:
                cache_key = self._get_cache_key('intent', query, len(history))
                self.cache.set(
                    cache_key,
                    intent.to_dict(),
                    prefix='query_result',
                    ttl=self.CACHE_CONFIG['intent_ttl']
                )
            
            return intent
            
        except Exception as e:
            logger.warning(f"LLM intent detection failed: {e}")
            return self._detect_intent_fallback(query)
    
    def _detect_intent_fallback(self, query: str) -> Intent:
        """Fallback rule-based intent detection"""
        query_lower = query.lower()
        
        if any(kw in query_lower for kw in ['xin chào', 'hello', 'hi', 'chào']):
            return Intent('greeting', [], 0.9, {})
        
        if any(kw in query_lower for kw in ['so sánh', 'compare', 'khác nhau']):
            return Intent('compare', [], 0.8, {})
        
        if any(kw in query_lower for kw in ['còn hàng', 'hết hàng', 'tồn kho']):
            return Intent('stock_check', [], 0.8, {})
        
        if any(kw in query_lower for kw in ['chính sách', 'đổi trả', 'bảo hành']):
            return Intent('policy', [], 0.8, {})
        
        if any(kw in query_lower for kw in ['hỗ trợ', 'liên hệ', 'hotline']):
            return Intent('support', [], 0.8, {})
        
        if any(kw in query_lower for kw in ['thông số', 'chi tiết', 'giá']):
            return Intent('product_info', [], 0.7, {})
        
        return Intent('product_search', [], 0.6, {})
    
    def retrieve(self, query: str, top_k: int = 5, use_cache: bool = True) -> List[Dict[str, Any]]:
        """Retrieve with optional caching"""
        if not query:
            return []
        
        # Check cache first
        if use_cache:
            cached_result = self.get_cached_query_result(query)
            if cached_result:
                logger.debug(f"Query result cache HIT: {query[:50]}")
                return cached_result[:top_k]
        
        # Get embedding (cached)
        q_emb = self.get_embedding_cached(query)
        
        # Search vector store
        candidates = self.vector_store.find_similar_products(
            embedding=q_emb,
            limit=top_k * 3,
            min_score=0.0
        )

        results: List[Dict[str, Any]] = []
        for c in candidates:
            pid = c.get("product_id")
            meta = c.get("metadata", {}) or {}
            item_type = meta.get("type", "product")

            if item_type == "product":
                # Get product (cached)
                details = self.get_product_cached(pid)
                results.append({
                    "id": pid,
                    "type": "product",
                    "score": float(c.get("similarity_score", c.get("score", 0.0))),
                    "metadata": meta,
                    "data": details,
                })
            elif item_type == "content":
                details = None
                try:
                    if self.content_store:
                        details = self.content_store.get_content(pid)
                except Exception:
                    pass

                results.append({
                    "id": pid,
                    "type": "content",
                    "score": float(c.get("similarity_score", c.get("score", 0.0))),
                    "metadata": meta,
                    "data": details,
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        
        # Cache the result
        if use_cache:
            self.cache_query_result(query, results)
        
        return results[:top_k]
    
    def _rerank_contexts(self, query: str, contexts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Re-rank contexts using LLM"""
        if len(contexts) <= 3:
            return contexts
        
        try:
            context_descs = []
            for i, ctx in enumerate(contexts[:10]):
                if not ctx:
                    continue
                if ctx.get('type') == 'product':
                    data = ctx.get('data', {}) or {}
                    desc = f"{i}. {data.get('name', 'N/A')} - {data.get('description', '')[:100]}"
                else:
                    data = ctx.get('data', {}) or {}
                    desc = f"{i}. {data.get('title', 'N/A')} - {data.get('content', '')[:100]}"
                context_descs.append(desc)
            
            rerank_prompt = f"""Xếp hạng độ liên quan với câu hỏi.

Câu hỏi: "{query}"

Các mục:
{chr(10).join(context_descs)}

Trả về array JSON chỉ số từ liên quan nhất đến ít liên quan:"""

            response = self._call_openai_chat(rerank_prompt, max_tokens=100, temperature=0.1)
            response = response.strip()
            
            if response.startswith('['):
                ranking = json.loads(response)
                reranked = []
                for idx in ranking:
                    if 0 <= idx < len(contexts):
                        reranked.append(contexts[idx])
                
                added_ids = set(contexts[i]['id'] for i in ranking if 0 <= i < len(contexts))
                for ctx in contexts:
                    if ctx['id'] not in added_ids:
                        reranked.append(ctx)
                
                return reranked
        except Exception as e:
            logger.warning(f"Re-ranking failed: {e}")
        
        return contexts
    
    def retrieve_with_reranking(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.4,
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """Retrieve with re-ranking"""
        candidates = self.retrieve(query, top_k=top_k * 2, use_cache=use_cache)
        
        if not candidates:
            return []
        
        reranked = self._rerank_contexts(query, candidates)
        filtered = [c for c in reranked if c['score'] >= min_score]
        
        if len(filtered) < 2 and candidates:
            filtered = reranked[:max(2, top_k)]
        
        return filtered[:top_k]
    
    def _extract_product_info(self, data: Dict, metadata: Dict) -> Dict[str, Any]:
        """
        Extract comprehensive product information from data and metadata.
        Handles both flat structure and JSON string metadata fields.
        
        Args:
            data: Product data from database
            metadata: Product metadata from vector store
            
        Returns:
            Dict containing all extracted product information
        """
        import json
        
        info = {
            'name': data.get('name', 'N/A'),
            'price': data.get('price'),
            'rating': data.get('avgRating') or data.get('avg_rating'),
            'brand': None,
            'description': data.get('description'),
            'material': None,
            'gender': None,
            'category': None,
            'in_stock': True,
            'list_price': None,
            'variants': []
        }
        
        # Helper to safely parse JSON strings
        def safe_json_parse(json_str):
            if not json_str:
                return None
            if isinstance(json_str, dict):
                return json_str
            if isinstance(json_str, str):
                try:
                    return json.loads(json_str)
                except:
                    return None
            return None
        
        # Parse attributes (can be in data or metadata)
        attributes_str = data.get('attributes') or metadata.get('attributes')
        attributes = safe_json_parse(attributes_str)
        if attributes:
            general = attributes.get('general', {})
            info['brand'] = general.get('brand')
            info['gender'] = general.get('gender')
            
            material_info = attributes.get('material', {})
            info['material'] = material_info.get('material')
        
        # Parse commercial info
        commercial_str = data.get('commercial') or metadata.get('commercial')
        commercial = safe_json_parse(commercial_str)
        if commercial:
            info['in_stock'] = commercial.get('in_stock', True)
            info['list_price'] = commercial.get('list_price')
            if not info['price']:
                info['price'] = commercial.get('price')
        
        # Parse taxonomy
        taxonomy_str = data.get('taxonomy') or metadata.get('taxonomy')
        taxonomy = safe_json_parse(taxonomy_str)
        if taxonomy:
            info['category'] = taxonomy.get('category')
        
        # Parse variants
        variants_str = data.get('variants') or metadata.get('variants')
        variants = safe_json_parse(variants_str)
        if variants and isinstance(variants, list):
            info['variants'] = variants
        
        # Parse AI metadata for description if not already set
        if not info['description']:
            ai_str = data.get('ai') or metadata.get('ai')
            ai_meta = safe_json_parse(ai_str)
            if ai_meta:
                embedding_text = ai_meta.get('embedding_text', '')
                # Try to extract description from embedding_text
                if 'designed for' in embedding_text.lower() or 'features' in embedding_text.lower():
                    # Extract the descriptive part
                    parts = embedding_text.split('.')
                    for part in parts:
                        if any(kw in part.lower() for kw in ['designed', 'features', 'perfect for']):
                            info['description'] = part.strip() + '.'
                            break
        
        return info
    
    def _build_enhanced_prompt(
        self,
        query: str,
        contexts: List[Dict[str, Any]],
        intent: Intent,
        history: List[ConversationTurn]
    ) -> str:
        """Build enhanced prompt"""
        context_texts = []
        for i, ctx in enumerate(contexts):
            item_type = ctx.get("type", "product")
            data = ctx.get("data") or {}
            metadata = ctx.get("metadata") or {}
            entity_type = metadata.get("entity_type", "product")
            
            # Case 1: Product Data
            if entity_type == "product" and data:
                # Use comprehensive product info extraction
                product = self._extract_product_info(data, metadata)
                
                name = product['name']
                text = f"[Sản phẩm {i+1}] {name}"
                
                # Add brand
                if product['brand']:
                    text += f"\n- Thương hiệu: {product['brand']}"
                
                # Add category
                if product['category']:
                    text += f"\n- Danh mục: {product['category']}"
                
                # Add price information
                if product['price']:
                    text += f"\n- Giá: {product['price']:,.0f}đ"
                    if product['list_price'] and product['list_price'] > product['price']:
                        text += f" (Giá gốc: {product['list_price']:,.0f}đ)"
                
                # Add rating
                if product['rating']:
                    text += f"\n- Đánh giá: {product['rating']}/5 sao"
                
                # Add material
                if product['material']:
                    text += f"\n- Chất liệu: {product['material']}"
                
                # Add gender
                if product['gender']:
                    text += f"\n- Dành cho: {product['gender']}"
                
                # Add stock status
                stock_text = "Còn hàng" if product['in_stock'] else "Hết hàng"
                text += f"\n- Tình trạng: {stock_text}"
                
                # Add description
                if product['description']:
                    # Limit description length
                    desc = product['description']
                    if len(desc) > 200:
                        desc = desc[:200] + "..."
                    text += f"\n- Mô tả: {desc}"
                
                # Add variants if available
                if product['variants']:
                    text += f"\n- Biến thể ({len(product['variants'])}):"
                    for variant in product['variants'][:3]:  # Limit to 3 variants
                        v_name = variant.get('name', '')
                        v_color = variant.get('color', '')
                        v_price = variant.get('price')
                        v_sku = variant.get('sku', '')
                        
                        v_text = f"\n  • {v_name}" if v_name else f"\n  • SKU: {v_sku}"
                        if v_color:
                            v_text += f" (Màu: {v_color})"
                        if v_price:
                            v_text += f" - {v_price:,.0f}đ"
                        text += v_text
                    
                    if len(product['variants']) > 3:
                        text += f"\n  ... và {len(product['variants']) - 3} biến thể khác"
                
                context_texts.append(text)
            
            # Case 2: Content/Policy Data (often in metadata)
            elif entity_type == "content":
                title = data.get("title") or metadata.get("title", f"Thông tin {i+1}")
                content = data.get("content") or metadata.get("content", "")
                text = f"[Nội dung {i+1}] {title}\n{content}"
                context_texts.append(text)
        
        contexts_combined = "\n\n".join(context_texts) if context_texts else "Không có thông tin."

        
        system_instructions = self._get_system_instructions(intent)
        
        prompt = f"""{system_instructions}

# THÔNG TIN
{contexts_combined}

# CÂU HỎI
{query}

# QUY TẮC
1. Trả lời trực tiếp, đi thẳng vào vấn đề
2. CHỈ được sử dụng thông tin CÓ TRONG dữ liệu tham khảo
3. KHÔNG được:
   - Tự đánh số sản phẩm nếu dữ liệu không có
   - Tự suy diễn đặc điểm
   - Tự viết lại mô tả theo ý hiểu
4. Nếu nhiều sản phẩm trùng tên, PHẢI phân biệt bằng:
   - SKU
   - Brand
   - Price
5. Độ dài: 2-4 câu

# CÂU TRẢ LỜI
"""
        return prompt
    
    def _get_system_instructions(self, intent: Intent) -> str:
        """Get system instructions"""
        instructions = {
            'product_search': "# VAI TRÒ\nBạn là chuyên viên tư vấn sản phẩm.",
            'product_info': "# VAI TRÒ\nBạn là chuyên gia sản phẩm.",
            'compare': "# VAI TRÒ\nBạn là chuyên gia so sánh sản phẩm.",
            'support': "# VAI TRÒ\nBạn là nhân viên CSKH.",
        }
        return instructions.get(intent.primary, instructions['product_search'])
    
    def _call_openai_chat(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.2,
        retry: int = 3
    ) -> str:
        """Call OpenAI with retry"""
        for attempt in range(retry):
            try:
                completion = self.client.chat.completions.create(
                    model=config.OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": "You are a helpful e-commerce assistant."},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                    extra_headers={
                        "HTTP-Referer": "http://localhost:8000",
                        "X-Title": "realtime-ai-recommender",
                    }
                )
                return completion.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"LLM call attempt {attempt + 1} failed: {e}")
                if attempt < retry - 1:
                    time.sleep(1 * (attempt + 1))
                else:
                    raise
    
    def _get_canned_response(self, query: str, intent: Intent) -> str:
        """Fallback responses"""
        responses = {
            'greeting': "Xin chào! Tôi có thể giúp bạn tìm sản phẩm hoặc giải đáp thắc mắc.",
            'support': "Liên hệ: Hotline 1900-xxxx hoặc email support@example.com",
        }
        return responses.get(
            intent.primary,
            "Xin lỗi, tôi không thể trả lời. Vui lòng liên hệ hỗ trợ."
        )
    
    def answer(
        self,
        query: str,
        session_id: str = "default",
        top_k: int = 5,
        use_reranking: bool = True,
        use_cache: bool = True
    ) -> Tuple[str, List[Dict[str, Any]], Intent]:
        """Main answer method with caching"""
        try:
            # Get history (from cache)
            history = self.get_conversation_history(session_id)
            
            # Resolve coreferences
            resolved_query = self._resolve_coreferences(query, history)
            
            # Detect intent (cached)
            intent = self._detect_intent_llm(resolved_query, history)
            logger.info(f"Intent: {intent.primary} ({intent.confidence})")
            
            # Greeting
            if intent.primary == 'greeting':
                answer = self._get_canned_response(query, intent)
                turn = ConversationTurn(query, answer, [], intent, time.time())
                self.save_conversation_turn(session_id, turn)
                return answer, [], intent
            
            # Retrieve (cached)
            if use_reranking:
                contexts = self.retrieve_with_reranking(
                    resolved_query, top_k, use_cache=use_cache
                )
            else:
                contexts = self.retrieve(resolved_query, top_k, use_cache=use_cache)
            
            if not contexts:
                answer = self._get_canned_response(query, intent)
                turn = ConversationTurn(query, answer, [], intent, time.time())
                self.save_conversation_turn(session_id, turn)
                return answer, [], intent
            
            # Build prompt
            prompt = self._build_enhanced_prompt(resolved_query, contexts, intent, history)
            
            # Call LLM
            answer = self._call_openai_chat(prompt)
            
            # Save to cache
            turn = ConversationTurn(query, answer, contexts, intent, time.time())
            self.save_conversation_turn(session_id, turn)
            
            return answer, contexts, intent
            
        except Exception as e:
            logger.exception(f"Error: {e}")
            intent = self._detect_intent_fallback(query)
            
            contexts = locals().get('contexts', [])
            if contexts:
                top_ctx = contexts[0]
                meta = top_ctx.get('metadata', {})
                data = top_ctx.get('data', {}) or {}
                
                title = meta.get('title') or data.get('name') or "Nội dung liên quan"
                content = meta.get('content') or data.get('description') or "..."
                
                answer = f"⚠️ [Offline Mode] Tôi tìm thấy thông tin này có thể hữu ích:\n\n**{title}**\n{content}\n\n(Hệ thống LLM đang bận, đây là kết quả tìm kiếm thô)"
                return answer, contexts, intent
            
            answer = self._get_canned_response(query, intent)
            return answer, [], intent
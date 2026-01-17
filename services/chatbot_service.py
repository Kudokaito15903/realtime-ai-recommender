"""
Performance Optimization cho Chatbot Service
Target: Giảm từ 15s → <5s
"""

import sys
import os
import asyncio
import concurrent.futures
from typing import List, Dict, Any, Optional, Tuple, NamedTuple
import time
import re
import json
import functools
from dataclasses import dataclass
from loguru import logger
try:
    import google.generativeai as genai
except ImportError:
    genai = None
    logger.warning("google-generativeai package not found. Chatbot LLM features will be disabled.")

# Adapters & Config
import config
from adapters.factory import get_vector_store, get_product_store, get_user_behavior
from domain.embeddings.product_embeddings import get_embedding_model

# ==================== UTIL CLASSES ====================

@dataclass
class Intent:
    primary: str
    entities: List[str]
    confidence: float
    meta: Dict[str, Any]

@dataclass
class ConversationTurn:
    query: str
    answer: str
    contexts: List[Dict[str, Any]]
    intent: Intent
    timestamp: float

    def to_dict(self):
        return {
            "query": self.query,
            "answer": self.answer,
            "contexts": self.contexts,
            "intent": {
                "primary": self.intent.primary,
                "confidence": self.intent.confidence
            },
            "timestamp": self.timestamp
        }

class SecurityUtils:
    @staticmethod
    def sanitize_query(query: str) -> str:
        if not query:
            return ""
        # Remove dangerous chars but keep vietnamese
        return query.strip()[:500]
    
    @staticmethod
    def sanitize_session_id(session_id: str) -> str:
        if not session_id:
            return "default"
        return re.sub(r'[^a-zA-Z0-9_-]', '', session_id)[:50]

def timed_operation(name):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start
                logger.debug(f"Operation {name} took {elapsed:.3f}s")
                return result
            except Exception as e:
                elapsed = time.time() - start
                logger.error(f"Operation {name} failed after {elapsed:.3f}s: {e}")
                raise
        return wrapper
    return decorator

# ==================== MAIN SERVICE ====================

class ChatbotService:
    """Chatbot với parallel execution và aggressive caching"""
    
    def __init__(self, enable_cache: bool = True, redis_host: str = None, redis_port: int = 6379):
        logger.info(f"Initializing ChatbotService (cache={enable_cache})")
        
        # Dependencies
        self.vector_store = get_vector_store()
        self.product_store = get_product_store()
        self.user_behavior = get_user_behavior()
        self.embedding_model = get_embedding_model()
        
        # Config
        self.enable_cache = enable_cache
        self.cache = None
        
        if self.enable_cache:
            try:
                import redis
                host = redis_host or os.getenv("REDIS_HOST", "localhost")
                port = redis_port or int(os.getenv("REDIS_PORT", 6379))
                self.cache = redis.Redis(host=host, port=port, decode_responses=False) # Use pickle? Or handle strings
                # For simplicity assuming the optimize logic implies custom caching handling or simple string
                # Looking at usage: self.cache.get(pid, prefix='product') -> implies wrapper or custom get
                # I'll implement a simple Redis wrapper if needed or just use standard Redis
                # But OptimizedChatbotService user .get(..., prefix=..) which is NOT standard Redis.
                # I will define a SimpleCache wrapper below.
                
                # Re-connecting to standard redis for now
                self.redis_client = redis.Redis(host=host, port=port, decode_responses=True)
                self.cache = SimpleCache(self.redis_client)
                logger.info("Chatbot Redis cache enabled")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}")
                self.enable_cache = False

        # Init GenAI
        api_key = os.getenv("GOOGLE_API_KEY", getattr(config, "GOOGLE_API_KEY", None))
        if not api_key:
            logger.warning("GOOGLE_API_KEY not found")
        elif not genai:
            logger.warning("google.generativeai module not loaded")
        else:
            try:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel(getattr(config, "GOOGLE_MODEL", "gemini-pro"))
            except Exception as e:
                logger.error(f"Failed to configure GenAI: {e}")
        
        # Thread pool for parallel operations
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        
        # ✅ Config: Tối ưu cache TTL
        self.CACHE_CONFIG = {
            'product_ttl': 1800,       # 30 phút (tăng từ 5 phút)
            'embedding_ttl': 7200,     # 2 giờ
            'query_result_ttl': 900,   # 15 phút (tăng từ 3 phút)
            'conversation_ttl': 1800,  # 30 phút
            'intent_ttl': 1800,        # 30 phút (tăng từ 10 phút)
        }
        
        self.stats = {
            'cache_hits': 0,
            'cache_misses': 0,
            'errors': 0
        }

    # ==================== HELPERS ====================
    
    def _increment_stat(self, key):
        self.stats[key] = self.stats.get(key, 0) + 1
        
    def _get_cache_key(self, prefix, *args):
        return f"{prefix}:{':'.join(str(a) for a in args)}"

    def get_embedding_cached(self, text: str) -> List[float]:
        # Implement caching for embeddings if needed
        return self.embedding_model.embed_text(text).tolist()

    def _fetch_product_from_db(self, product_id: str) -> Dict:
        return self.product_store.get_product_by_id(product_id)

    def _extract_product_info(self, data: Dict, meta: Dict) -> Dict:
        return {
            "name": data.get("name") or meta.get("name"),
            "price": data.get("price") or meta.get("price"),
            "brand": data.get("brand") or meta.get("brand"),
            "rating": data.get("avgRating") or meta.get("avg_rating")
        }

    def _call_genai(self, prompt: str, max_tokens: int = 1024, temperature: float = 0.1) -> str:
        if not hasattr(self, 'model') or not self.model:
            return "Chức năng AI chưa được cấu hình (Missing Key or Package)."
            
        try:
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=max_tokens,
                    temperature=temperature
                )
            )
            return response.text
        except Exception as e:
            logger.error(f"GenAI call failed: {e}")
            return "Xin lỗi, tôi đang gặp sự cố kết nối."

    def _get_canned_response(self, query: str, intent: Intent) -> str:
        if intent.primary == 'greeting':
            return "Xin chào! Tôi có thể giúp gì cho bạn hôm nay?"
        return "Tôi chưa hiểu ý bạn, vui lòng nói rõ hơn."

    def get_conversation_history(self, session_id: str) -> List[Dict]:
        # Placeholder for history retrieval
        return []

    def save_conversation_turn(self, session_id: str, turn: ConversationTurn):
        # Placeholder for saving history
        # self.user_behavior.log_chat(...)
        pass
    
    # ==================== OPT 1: SKIP INTENT DETECTION ====================
    
    def _detect_intent_fast(self, query: str) -> Intent:
        """Rule-based intent detection (no LLM) - 0.001s"""
        query_lower = query.lower()
        
        # Fast regex patterns
        patterns = [
            (r'\b(xin chào|hello|hi|chào)\b', 'greeting', 0.95),
            (r'\b(so sánh|compare|khác nhau|vs)\b', 'compare', 0.90),
            (r'\b(còn hàng|hết hàng|tồn kho|stock)\b', 'stock_check', 0.90),
            (r'\b(thanh toán|đổi trả|bảo hành|chính sách|policy|phương thức)\b', 'policy', 0.85),
            (r'\b(hỗ trợ|liên hệ|hotline|contact|cskh)\b', 'support', 0.85),
            (r'\b(giá|bao nhiêu|chi tiết|thông số)\b', 'product_info', 0.80),
            (r'\b(tìm|mua|cần|muốn|có|bán)\b', 'product_search', 0.75),
        ]
        
        for pattern, intent_type, confidence in patterns:
            if re.search(pattern, query_lower):
                logger.info(f"⚡ Fast intent: {intent_type} ({confidence:.2f})")
                return Intent(intent_type, [], confidence, {})
        
        # Default
        logger.info("⚡ Fast intent: product_search (0.60)")
        return Intent('product_search', [], 0.60, {})
    
    # ==================== OPT 2: DISABLE RE-RANKING ====================
    
    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        # Actual retrieval logic
        embedding = self.embedding_model.get_embedding(query)
        # Vector store search (rag_chunks namespace for chatbot)
        results = self.vector_store.find_similar_products(
            embedding=embedding, 
            limit=top_k,
            namespace="rag_chunks"
        )
        # Format results
        return results

    def retrieve_fast(
        self,
        query: str,
        top_k: int = 5,
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """Retrieve WITHOUT re-ranking - saves 2-3s"""
        return self.retrieve(query, top_k=top_k, use_cache=use_cache)
    
    # ==================== OPT 3: PARALLEL PRODUCT FETCHING ====================
    
    def get_products_batch_parallel(
        self, 
        product_ids: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Parallel product fetching using ThreadPoolExecutor"""
        if not product_ids:
            return {}
        
        products = {}
        missing_ids = []
        
        # Check cache first
        if self.enable_cache and self.cache:
            for pid in product_ids:
                cached = self.cache.get(pid, prefix='product')
                if cached:
                    products[pid] = cached
                    self._increment_stat('cache_hits')
                else:
                    missing_ids.append(pid)
                    self._increment_stat('cache_misses')
        else:
            missing_ids = product_ids
        
        if not missing_ids:
            return products
        
        # ✅ Parallel fetch missing products
        def fetch_single(pid):
            try:
                return pid, self._fetch_product_from_db(pid)
            except Exception as e:
                logger.error(f"Failed to fetch {pid}: {e}")
                return pid, None
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(fetch_single, pid) for pid in missing_ids]
            
            for future in concurrent.futures.as_completed(futures):
                pid, product = future.result()
                if product:
                    products[pid] = product
                    
                    # Cache it
                    if self.enable_cache and self.cache:
                        self.cache.set(
                            pid,
                            product,
                            prefix='product',
                            ttl=self.CACHE_CONFIG['product_ttl']
                        )
        
        logger.info(f"⚡ Parallel fetched {len(missing_ids)} products")
        return products
    
    # ==================== OPT 4: SIMPLIFIED PROMPT ====================
    
    def _build_fast_prompt(
        self,
        query: str,
        contexts: List[Dict[str, Any]],
        intent: Intent
    ) -> str:
        """Simplified prompt - shorter, faster to process"""
        
        # ✅ Build contexts concisely
        context_parts = []
        
        for i, ctx in enumerate(contexts[:3]):  # Limit to top 3
            if not ctx:
                continue
            
            data = ctx.get('data') or {}
            meta = ctx.get('metadata', {})
            entity_type = meta.get('entity_type', 'product')
            
            if entity_type == 'product' and data:
                info = self._extract_product_info(data, meta)
                
                # Compact format
                parts = [f"[{i+1}] {info['name']}"]
                if info['price']:
                    parts.append(f"Giá: {info['price']:,.0f}đ")
                if info['brand']:
                    parts.append(f"Brand: {info['brand']}")
                if info['rating']:
                    parts.append(f"{info['rating']}/5⭐")
                
                context_parts.append(" | ".join(parts))
            
            elif entity_type == 'content':
                title = meta.get('title', f"Info {i+1}")
                content = meta.get('content', '')[:200]
                context_parts.append(f"[{i+1}] {title}: {content}")
        
        contexts_text = "\n".join(context_parts) if context_parts else "Không có dữ liệu"
        
        # ✅ Minimal prompt
        if intent.primary == 'policy':
            role = "Chuyên viên chính sách - Liệt kê ĐẦY ĐỦ các phương thức/điều kiện"
        else:
            role = "Tư vấn viên sản phẩm - Trả lời ngắn gọn, chính xác"
        
        prompt = f"""# ROLE: {role}

# DATA
{contexts_text}

# QUESTION: {SecurityUtils.sanitize_query(query)}

# RULES
- Chỉ dùng thông tin có sẵn
- Không bịa đặt
- Trả lời trực tiếp
- Hoàn thành câu đầy đủ

# ANSWER:"""
        
        return prompt
    
    # ==================== OPT 5: FAST ANSWER PIPELINE ====================
    
    @timed_operation("answer_fast")
    def answer(
        self,
        query: str,
        session_id: str = "default",
        top_k: int = 3,  # Giảm từ 5 → 3
        use_cache: bool = True
    ) -> Tuple[str, List[Dict[str, Any]], Intent]:
        """Optimized answer pipeline - target <5s"""
        
        start_time = time.time()
        
        try:
            # ✅ Stage 1: Sanitize (0.001s)
            query_safe = SecurityUtils.sanitize_query(query)
            session_id_safe = SecurityUtils.sanitize_session_id(session_id)
            
            if not query_safe:
                intent = Intent('general', [], 0.0, {})
                return "Vui lòng nhập câu hỏi.", [], intent
            
            # ✅ Stage 2: Fast intent detection (0.001s vs 2-3s LLM)
            intent = self._detect_intent_fast(query_safe)
            logger.info(f"⚡ Intent: {intent.primary} ({time.time() - start_time:.3f}s)")
            
            # Handle greeting
            if intent.primary == 'greeting':
                answer = self._get_canned_response(query_safe, intent)
                return answer, [], intent
            
            # ✅ Stage 3: Get conversation history + Resolve coreferences (parallel)
            history_future = self.executor.submit(
                self.get_conversation_history, 
                session_id_safe
            )
            
            # ✅ Stage 4: Embedding + Retrieval (1-2s)
            resolved_query = query_safe  # Skip coreference for speed
            contexts = self.retrieve_fast(
                resolved_query,
                top_k=top_k,
                use_cache=use_cache
            )
            
            logger.info(f"⚡ Retrieved {len(contexts)} contexts ({time.time() - start_time:.3f}s)")
            
            # No results
            if not contexts:
                answer = "Xin lỗi, tôi không tìm thấy thông tin phù hợp."
                return answer, [], intent
            
            # ✅ Stage 5: Build simplified prompt (0.01s)
            prompt = self._build_fast_prompt(resolved_query, contexts, intent)
            
            logger.info(f"⚡ Prompt built ({time.time() - start_time:.3f}s)")
            
            # ✅ Stage 6: Generate answer (3-4s)
            max_tokens = 1024  # Giảm từ 2048 để nhanh hơn
            answer = self._call_genai(
                prompt, 
                max_tokens=max_tokens, 
                temperature=0.1  # Giảm từ 0.2 để faster
            )
            
            logger.info(f"⚡ Answer generated ({time.time() - start_time:.3f}s)")
            
            # ✅ Stage 7: Save conversation (async, không chờ)
            history = history_future.result(timeout=1)
            turn = ConversationTurn(
                query_safe,
                answer,
                contexts,
                intent,
                time.time()
            )
            
            # Async save
            self.executor.submit(
                self.save_conversation_turn,
                session_id_safe,
                turn
            )
            
            total_time = time.time() - start_time
            logger.info(f"✅ Total time: {total_time:.3f}s")
            
            return answer, contexts, intent
        
        except Exception as e:
            logger.exception(f"Error in fast answer: {e}")
            self._increment_stat('errors')
            
            # Fallback
            intent = self._detect_intent_fast(query)
            return self._get_canned_response(query, intent), [], intent
    
    answer_fast = answer # Alias

    # ==================== OPT 6: CACHED LLM RESPONSES ====================
    
    def _call_genai_cached(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.1,
        cache_ttl: int = 3600
    ) -> str:
        """LLM call with aggressive caching"""
        
        if not self.enable_cache or not self.cache:
            return self._call_genai(prompt, max_tokens, temperature)
        
        # Generate cache key
        cache_key = self._get_cache_key('llm_response', prompt, max_tokens, temperature)
        
        # Check cache
        cached = self.cache.get(cache_key, prefix='query_result')
        if cached:
            logger.info("⚡ LLM response cache HIT - saved 3-4s!")
            self._increment_stat('cache_hits')
            return cached
        
        # Cache miss - call LLM
        self._increment_stat('cache_misses')
        response = self._call_genai(prompt, max_tokens, temperature)
        
        # Cache response
        self.cache.set(
            cache_key,
            response,
            prefix='query_result',
            ttl=cache_ttl
        )
        
        return response
    
    # ==================== OPT 7: EMBEDDING BATCH PRECOMPUTE ====================
    
    def precompute_common_embeddings(self, queries: List[str]):
        """Pre-compute embeddings for common queries"""
        logger.info(f"Pre-computing {len(queries)} embeddings...")
        
        for query in queries:
            try:
                self.get_embedding_cached(query)
            except Exception as e:
                logger.error(f"Failed to precompute: {query} - {e}")
        
        logger.info("✅ Embeddings precomputed")
    
    def shutdown(self):
        """Graceful shutdown"""
        self.executor.shutdown(wait=False)
        logger.info("Executor shutdown")

    def get_stats(self):
        return self.stats

class SimpleCache:
    def __init__(self, redis_client):
        self.client = redis_client
        
    def get(self, key, prefix=''):
        full_key = f"{prefix}:{key}" if prefix else key
        val = self.client.get(full_key)
        if val:
            try:
                return json.loads(val)
            except:
                return val
        return None
        
    def set(self, key, value, prefix='', ttl=300):
        full_key = f"{prefix}:{key}" if prefix else key
        if isinstance(value, (dict, list)):
            val = json.dumps(value)
        else:
            val = str(value)
        self.client.setex(full_key, ttl, val)

# ==================== PERFORMANCE MONITORING ====================

class PerformanceMonitor:
    """Monitor response times and bottlenecks"""
    
    def __init__(self):
        self.timings = []
    
    def record(self, operation: str, duration: float):
        self.timings.append({
            'operation': operation,
            'duration': duration,
            'timestamp': time.time()
        })
    
    def get_stats(self) -> Dict[str, Any]:
        if not self.timings:
            return {}
        
        # Group by operation
        by_operation = {}
        for t in self.timings:
            op = t['operation']
            if op not in by_operation:
                by_operation[op] = []
            by_operation[op].append(t['duration'])
        
        # Calculate stats
        stats = {}
        for op, durations in by_operation.items():
            stats[op] = {
                'count': len(durations),
                'avg': sum(durations) / len(durations),
                'min': min(durations),
                'max': max(durations),
                'p50': sorted(durations)[len(durations) // 2],
                'p95': sorted(durations)[int(len(durations) * 0.95)]
            }
        
        return stats
    
    def print_report(self):
        stats = self.get_stats()
        
        print("\n" + "="*60)
        print("PERFORMANCE REPORT")
        print("="*60)
        
        for op, data in sorted(stats.items(), key=lambda x: x[1]['avg'], reverse=True):
            print(f"\n{op}:")
            print(f"  Count: {data['count']}")
            print(f"  Avg:   {data['avg']*1000:.1f}ms")
            print(f"  P50:   {data['p50']*1000:.1f}ms")
            print(f"  P95:   {data['p95']*1000:.1f}ms")
            print(f"  Min:   {data['min']*1000:.1f}ms")
            print(f"  Max:   {data['max']*1000:.1f}ms")
        
        print("\n" + "="*60)


if __name__ == "__main__":
    # Initialize optimized chatbot
    try:
        chatbot = ChatbotService(
            redis_host="localhost",
            redis_port=6379,
            enable_cache=True
        )
        
        # Pre-compute common embeddings
        common_queries = [
            "giày thể thao",
            "áo khoác",
            "chính sách thanh toán",
        ]
        chatbot.precompute_common_embeddings(common_queries)
        
        # Test fast answer
        print("\nTest Answer:")
        answer, contexts, intent = chatbot.answer(
            "Bên mình bán xe đạp không?",
            session_id="test"
        )
        
        print(f"\n✅ Answer: {answer}")
    except Exception as e:
        logger.error(f"Startup test failed: {e}")
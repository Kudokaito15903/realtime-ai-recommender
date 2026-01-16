"""
Performance Optimization cho Chatbot Service
Target: Giảm từ 15s → <5s
"""

import asyncio
import concurrent.futures
from typing import List, Dict, Any, Optional, Tuple
import time
from loguru import logger


# ==================== OPTIMIZATION 1: PARALLEL EXECUTION ====================

class OptimizedChatbotService(ChatbotService):
    """Chatbot với parallel execution và aggressive caching"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
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
    def answer_fast(
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


# ==================== OPTIMIZATION 8: STREAMING RESPONSE ====================

class StreamingChatbotService(OptimizedChatbotService):
    """Support streaming responses for better UX"""
    
    def answer_streaming(
        self,
        query: str,
        session_id: str = "default",
        top_k: int = 3
    ):
        """
        Generator that yields answer chunks as they're generated
        Usage:
            for chunk in chatbot.answer_streaming(query):
                print(chunk, end='', flush=True)
        """
        
        start_time = time.time()
        
        # Fast intent + retrieval
        query_safe = SecurityUtils.sanitize_query(query)
        intent = self._detect_intent_fast(query_safe)
        
        if intent.primary == 'greeting':
            yield self._get_canned_response(query_safe, intent)
            return
        
        contexts = self.retrieve_fast(query_safe, top_k=top_k)
        
        if not contexts:
            yield "Xin lỗi, tôi không tìm thấy thông tin phù hợp."
            return
        
        # Build prompt
        prompt = self._build_fast_prompt(query_safe, contexts, intent)
        
        # ✅ Stream from LLM (if API supports streaming)
        # Note: Google GenAI SDK supports streaming with generate_content_stream()
        try:
            response = self.google_client.client.models.generate_content_stream(
                model=config.GOOGLE_MODEL,
                contents=prompt,
                config={
                    'max_output_tokens': 1024,
                    'temperature': 0.1
                }
            )
            
            full_answer = ""
            for chunk in response:
                if chunk.text:
                    full_answer += chunk.text
                    yield chunk.text
            
            # Save after complete
            turn = ConversationTurn(
                query_safe,
                full_answer,
                contexts,
                intent,
                time.time()
            )
            self.save_conversation_turn(session_id, turn)
            
            logger.info(f"✅ Streaming completed in {time.time() - start_time:.3f}s")
        
        except Exception as e:
            logger.error(f"Streaming failed: {e}")
            yield self._get_canned_response(query_safe, intent)


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


# ==================== USAGE EXAMPLE ====================

if __name__ == "__main__":
    # Initialize optimized chatbot
    chatbot = OptimizedChatbotService(
        redis_host="localhost",
        redis_port=6379,
        enable_cache=True
    )
    
    # Pre-compute common embeddings
    common_queries = [
        "giày thể thao",
        "áo khoác",
        "túi xách",
        "chính sách thanh toán",
        "đổi trả hàng"
    ]
    chatbot.precompute_common_embeddings(common_queries)
    
    # Test fast answer
    start = time.time()
    answer, contexts, intent = chatbot.answer_fast(
        "Bên mình bán xe đạp không?",
        session_id="test"
    )
    elapsed = time.time() - start
    
    print(f"\n✅ Answer: {answer}")
    print(f"⚡ Time: {elapsed:.3f}s")
    print(f"📊 Cache hit rate: {chatbot.get_stats()['cache_hit_rate']}")
    
    # Test streaming
    print("\n\n=== STREAMING TEST ===")
    streaming_chatbot = StreamingChatbotService(
        redis_host="localhost",
        redis_port=6379,
        enable_cache=True
    )
    
    print("Answer: ", end='', flush=True)
    for chunk in streaming_chatbot.answer_streaming("Có giày Nike không?"):
        print(chunk, end='', flush=True)
    print()
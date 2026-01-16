import os
import time
import json
import re
import hashlib
import threading
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from contextlib import contextmanager
from functools import lru_cache, wraps
from loguru import logger
from google import genai
import numpy as np

from adapters.factory import get_vector_store, get_product_store, get_content_store, get_user_behavior
from domain.embeddings.product_embeddings import get_embedding_model
from redis_cache import RedisCache
import config


# ==================== SECURITY UTILITIES ====================

class SecurityUtils:
    """Security utilities for input sanitization"""
    
    MAX_QUERY_LENGTH = 1000
    MAX_SESSION_ID_LENGTH = 100
    
    @staticmethod
    def sanitize_query(query: str) -> str:
        """Sanitize user query to prevent prompt injection"""
        if not query:
            return ""
        
        # Remove control characters
        query = re.sub(r'[\x00-\x1F\x7F]', '', query)
        
        # Limit length
        query = query[:SecurityUtils.MAX_QUERY_LENGTH]
        
        # Remove suspicious patterns
        suspicious_patterns = [
            r'ignore\s+all\s+previous\s+instructions',
            r'you\s+are\s+now',
            r'system\s*:',
            r'<\s*script',
        ]
        for pattern in suspicious_patterns:
            query = re.sub(pattern, '', query, flags=re.IGNORECASE)
        
        return query.strip()
    
    @staticmethod
    def sanitize_session_id(session_id: str) -> str:
        """Sanitize session ID"""
        if not session_id:
            return "default"
        
        # Only allow alphanumeric, dash, underscore
        session_id = re.sub(r'[^a-zA-Z0-9_-]', '', session_id)
        return session_id[:SecurityUtils.MAX_SESSION_ID_LENGTH] or "default"
    
    @staticmethod
    def repair_json(json_str: str) -> str:
        """Repair common JSON errors (unquoted keys, single quotes)"""
        # Add quotes to unquoted keys
        json_str = re.sub(r'([{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', json_str)
        return json_str

    @staticmethod
    def safe_json_parse(json_str: Any) -> Optional[Dict]:
        """Safely parse JSON with improved error handling for LLM responses"""
        if not json_str:
            return None
        
        if isinstance(json_str, dict):
            return json_str
        
        if isinstance(json_str, str):
            original_str = json_str
            
            # ✅ FIX 1: Remove common LLM preambles
            json_str = re.sub(
                r'^(Here is the JSON.*?:|Sure[,!].*?:|Here you go.*?:|```json\s*|```\s*)', 
                '', 
                json_str, 
                flags=re.IGNORECASE | re.MULTILINE
            ).strip()
            
            # ✅ FIX 2: Remove trailing markdown
            json_str = re.sub(r'```\s*$', '', json_str).strip()
            
            # ✅ FIX 3: Remove any leading/trailing whitespace and newlines
            json_str = json_str.strip()
            
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                # ✅ FIX 4: Try to extract JSON object using regex
                match = re.search(r'(\{.*\})', json_str, re.DOTALL)
                if match:
                    try:
                        extracted = match.group(1).strip()
                        return json.loads(extracted)
                    except json.JSONDecodeError:
                        pass
                
                # ✅ FIX 5: Try to extract JSON array
                match = re.search(r'(\[.*\])', json_str, re.DOTALL)
                if match:
                    try:
                        extracted = match.group(1).strip()
                        return json.loads(extracted)
                    except json.JSONDecodeError:
                        pass
                
                # Try to repair
                try:
                    repaired = SecurityUtils.repair_json(json_str)
                    return json.loads(repaired)
                except Exception as e:
                    logger.warning(
                        f"JSON decode error: {e}. "
                        f"Original: {original_str[:100]}... "
                        f"Cleaned: {json_str[:100]}..."
                    )
                    return None
            except Exception as e:
                logger.error(f"Unexpected error parsing JSON: {e}")
                return None
        
        return None


# ==================== DATA CLASSES ====================

@dataclass
class Intent:
    """Structured intent classification result"""
    primary: str
    secondary: List[str] = field(default_factory=list)
    confidence: float = 0.0
    entities: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Intent':
        return cls(
            primary=data.get('primary', 'general'),
            secondary=data.get('secondary', []),
            confidence=data.get('confidence', 0.0),
            entities=data.get('entities', {})
        )


@dataclass
class ConversationTurn:
    """Single turn in conversation"""
    query: str
    answer: str
    contexts: List[Dict[str, Any]]
    intent: Optional[Intent]
    timestamp: float
    metrics: Optional[Dict[str, float]] = None
    
    def to_dict(self) -> Dict:
        return {
            'query': self.query,
            'answer': self.answer,
            'contexts': self.contexts,
            'intent': self.intent.to_dict() if self.intent else None,
            'timestamp': self.timestamp,
            'metrics': self.metrics
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ConversationTurn':
        intent_data = data.get('intent')
        intent = Intent.from_dict(intent_data) if intent_data else None
        return cls(
            query=data['query'],
            answer=data['answer'],
            contexts=data.get('contexts', []),
            intent=intent,
            timestamp=data['timestamp'],
            metrics=data.get('metrics')
        )


# ==================== PERFORMANCE UTILITIES ====================

def timed_operation(operation_name: str):
    """Decorator to measure operation time"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start
                logger.debug(f"{operation_name} took {elapsed:.3f}s")
                return result
            except Exception as e:
                elapsed = time.time() - start
                logger.error(f"{operation_name} failed after {elapsed:.3f}s: {e}")
                raise
        return wrapper
    return decorator


class CircuitBreaker:
    """Circuit breaker for external API calls"""
    
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self._lock = threading.Lock()
    
    def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        with self._lock:
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.timeout:
                    self.state = "HALF_OPEN"
                    logger.info("Circuit breaker entering HALF_OPEN state")
                else:
                    raise Exception("Circuit breaker is OPEN")
        
        try:
            result = func(*args, **kwargs)
            with self._lock:
                if self.state == "HALF_OPEN":
                    self.state = "CLOSED"
                    self.failures = 0
                    logger.info("Circuit breaker reset to CLOSED")
            return result
        
        except Exception as e:
            with self._lock:
                self.failures += 1
                self.last_failure_time = time.time()
                
                if self.failures >= self.failure_threshold:
                    self.state = "OPEN"
                    logger.warning(f"Circuit breaker opened after {self.failures} failures")
            raise


# ==================== SINGLETON GOOGLE GENAI CLIENT ====================

class GoogleGenAIClientSingleton:
    """Thread-safe singleton for Google GenAI client"""
    
    _instance = None
    _lock = threading.Lock()
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self.client = genai.Client(api_key=config.GOOGLE_API_KEY)
                    self.circuit_breaker = CircuitBreaker(
                        failure_threshold=5,
                        timeout=60
                    )
                    self.__class__._initialized = True
                    logger.info("Google GenAI client initialized")
    
    def generate_content(self, **kwargs):
        """Generate content with circuit breaker"""
        return self.circuit_breaker.call(
            self.client.models.generate_content,
            **kwargs
        )


# ==================== MAIN CHATBOT SERVICE ====================

class ChatbotService:
    """Enhanced Chatbot Service with Fixed JSON Parsing and Dynamic Prompting"""
    
    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: Optional[str] = None,
        enable_cache: bool = True
    ):
        """Initialize Chatbot Service"""
        
        # Initialize adapters
        self.vector_store = get_vector_store()
        self.embedding_model = get_embedding_model()
        self.product_store = get_product_store()
        self.content_store = get_content_store()
        self.user_behavior = get_user_behavior()
        
        # Initialize Google GenAI client (singleton)
        self.google_client = GoogleGenAIClientSingleton()
        
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
            'product_ttl': 300,
            'embedding_ttl': 3600,
            'query_result_ttl': 180,
            'conversation_ttl': 1800,
            'intent_ttl': 600,
            'response_ttl': 3600,  # Cache full responses for 1 hour
        }
        
        # Performance monitoring
        self._stats = {
            'cache_hits': 0,
            'cache_misses': 0,
            'llm_calls': 0,
            'errors': 0
        }
        self._stats_lock = threading.Lock()
    
    # ==================== CACHING METHODS ====================
    
    def _get_cache_key(self, *parts) -> str:
        """Generate cache key from parts"""
        key_str = ":".join(str(p) for p in parts)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    @timed_operation("get_product_cached")
    def get_product_cached(self, product_id: str) -> Optional[Dict[str, Any]]:
        """Get product with Redis caching"""
        if not self.enable_cache or not self.cache:
            return self._fetch_product_from_db(product_id)
        
        try:
            # Try cache first
            cached = self.cache.get(product_id, prefix='product')
            if cached:
                logger.debug(f"Product cache HIT: {product_id}")
                self._increment_stat('cache_hits')
                return cached
            
            # Cache miss
            logger.debug(f"Product cache MISS: {product_id}")
            self._increment_stat('cache_misses')
            
            product = self._fetch_product_from_db(product_id)
            
            if product:
                self.cache.set(
                    product_id,
                    product,
                    prefix='product',
                    ttl=self.CACHE_CONFIG['product_ttl']
                )
            
            return product
        
        except Exception as e:
            logger.error(f"Cache error for product {product_id}: {e}")
            self._increment_stat('errors')
            return self._fetch_product_from_db(product_id)
    
    def get_products_batch(self, product_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Batch fetch products (optimized)"""
        if not product_ids:
            return {}
        
        products = {}
        missing_ids = []
        
        # Try to get from cache first
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
        
        # Batch fetch missing products
        if missing_ids:
            try:
                if hasattr(self.product_store, 'get_products_batch'):
                    fetched = self.product_store.get_products_batch(missing_ids)
                else:
                    # Fallback to individual fetches
                    fetched = {
                        pid: self._fetch_product_from_db(pid)
                        for pid in missing_ids
                    }
                
                # Cache fetched products
                if self.enable_cache and self.cache:
                    for pid, product in fetched.items():
                        if product:
                            self.cache.set(
                                pid,
                                product,
                                prefix='product',
                                ttl=self.CACHE_CONFIG['product_ttl']
                            )
                
                products.update(fetched)
            
            except Exception as e:
                logger.error(f"Batch fetch failed: {e}")
                self._increment_stat('errors')
        
        return products
    
    def _fetch_product_from_db(self, product_id: str) -> Optional[Dict[str, Any]]:
        """Fetch product from database (with error handling)"""
        try:
            if self.product_store:
                # Ensure product_id is sanitized (basic validation)
                if not re.match(r'^[a-zA-Z0-9_-]+$', product_id):
                    logger.warning(f"Invalid product_id format: {product_id}")
                    return None
                
                return self.product_store.get_product(product_id)
        except Exception as e:
            logger.error(f"Failed to fetch product {product_id}: {e}")
            self._increment_stat('errors')
        return None
    
    @lru_cache(maxsize=1000)
    def get_embedding_cached(self, text: str) -> np.ndarray:
        """Get text embedding with caching (LRU + Redis)"""
        if not text or not text.strip():
            return np.zeros(self.embedding_model.dimension, dtype=np.float32)
        
        # Check Redis cache
        if self.enable_cache and self.cache:
            cache_key = self._get_cache_key(text)
            cached = self.cache.get(cache_key, prefix='embedding')
            
            if cached is not None:
                logger.debug("Embedding cache HIT")
                self._increment_stat('cache_hits')
                return np.array(cached, dtype=np.float32)
            
            self._increment_stat('cache_misses')
        
        # Generate embedding
        embedding = self.embedding_model.get_embedding(text)
        
        # Cache the embedding
        if self.enable_cache and self.cache:
            cache_key = self._get_cache_key(text)
            self.cache.set(
                cache_key,
                embedding.tolist(),
                prefix='embedding',
                ttl=self.CACHE_CONFIG['embedding_ttl']
            )
        
        return embedding
    
    def save_conversation_turn(self, session_id: str, turn: ConversationTurn):
        """Save conversation turn to Redis"""
        if not self.enable_cache or not self.cache:
            return
        
        try:
            session_id = SecurityUtils.sanitize_session_id(session_id)
            
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
            self._increment_stat('errors')
    
    def get_conversation_history(self, session_id: str) -> List[ConversationTurn]:
        """Get conversation history from Redis"""
        if not self.enable_cache or not self.cache:
            return []
        
        try:
            session_id = SecurityUtils.sanitize_session_id(session_id)
            conversation_data = self.cache.get_list(session_id, prefix='conversation') or []
            return [ConversationTurn.from_dict(turn) for turn in conversation_data]
        
        except Exception as e:
            logger.warning(f"Failed to get conversation history: {e}")
            self._increment_stat('errors')
            return []
    
    def clear_conversation(self, session_id: str):
        """Clear conversation history"""
        if self.enable_cache and self.cache:
            session_id = SecurityUtils.sanitize_session_id(session_id)
            self.cache.delete(session_id, prefix='conversation')
            logger.info(f"Cleared conversation for session {session_id}")
    
    def cleanup_old_sessions(self, max_age_hours: int = 24):
        """Cleanup old conversation sessions"""
        if not self.enable_cache or not self.cache:
            return
        
        try:
            pattern = f"{self.cache.PREFIXES.get('conversation', 'conv')}:*"
            cleaned = 0
            
            for key in self.cache.scan_iter(pattern):
                ttl = self.cache.ttl(key)
                if ttl < 0:  # No expiry set
                    self.cache.delete_raw(key)
                    cleaned += 1
            
            logger.info(f"Cleaned up {cleaned} old sessions")
        
        except Exception as e:
            logger.error(f"Session cleanup failed: {e}")
    
    def invalidate_product_cache(self, product_id: str):
        """Invalidate product cache (with version bump)"""
        if self.enable_cache and self.cache:
            self.cache.delete(product_id, prefix='product')
            
            # Invalidate related query results
            try:
                pattern = f"{self.cache.PREFIXES.get('query_result', 'qr')}:*"
                for key in self.cache.scan_iter(pattern):
                    self.cache.delete_raw(key)
            except Exception as e:
                logger.warning(f"Query cache invalidation failed: {e}")
            
            logger.info(f"Invalidated cache for product {product_id}")
    
    # ==================== INTENT DETECTION ====================
    
    def _resolve_coreferences(self, query: str, history: List[ConversationTurn]) -> str:
        """Resolve pronouns and references (IMPROVED)"""
        if not history:
            return query
        
        query_lower = query.lower()
        pronouns = ['nó', 'nó đó', 'cái đó', 'cái này', 'sản phẩm đó', 'cái kia', 'em ấy', 'thằng này']
        
        # Find the most recent product mentioned
        last_product_name = None
        for turn in reversed(history[-3:]):
            if turn.contexts:
                for ctx in turn.contexts:
                    if ctx.get('type') == 'product':
                        data = ctx.get('data')
                        if data:
                            last_product_name = data.get('name')
                            break
                if last_product_name:
                    break
        
        if not last_product_name:
            return query
        
        # Replace ALL occurrences of pronouns
        resolved = query
        for pronoun in pronouns:
            if pronoun in query_lower:
                # Use word boundaries for accurate replacement
                pattern = r'\b' + re.escape(pronoun) + r'\b'
                resolved = re.sub(pattern, last_product_name, resolved, flags=re.IGNORECASE)
                logger.info(f"Resolved '{pronoun}' → '{last_product_name}'")
        
        return resolved
    
    @timed_operation("detect_intent")
    def _detect_intent_llm(self, query: str, history: List[ConversationTurn]) -> Intent:
        """Advanced intent detection using LLM with improved JSON parsing"""
        
        # Sanitize query
        query_safe = SecurityUtils.sanitize_query(query)
        
        # Check cache first
        if self.enable_cache and self.cache:
            cache_key = self._get_cache_key('intent', query_safe, len(history))
            cached_intent = self.cache.get(cache_key, prefix='query_result')
            
            if cached_intent:
                logger.debug("Intent cache HIT")
                self._increment_stat('cache_hits')
                return Intent.from_dict(cached_intent)
            
            self._increment_stat('cache_misses')
        
        # Build context from history
        history_context = ""
        if history:
            recent = history[-3:]
            history_parts = []
            for i, turn in enumerate(recent):
                history_parts.append(f"{i+1}. Khách: {turn.query}")
                history_parts.append(f"   Bot: {turn.answer[:100]}...")
            history_context = "Lịch sử hội thoại:\n" + "\n".join(history_parts)
        
        intent_prompt = f"""Phân tích câu hỏi và trả về intent dưới dạng JSON.

{history_context}

Câu hỏi: "{query_safe}"

Intent types:
- product_search: Tìm sản phẩm
- product_info: Hỏi chi tiết sản phẩm
- compare: So sánh
- stock_check: Kiểm tra tồn kho
- policy: Chính sách (thanh toán, đổi trả, vận chuyển, bảo mật)
- support: Hỗ trợ
- greeting: Chào hỏi
- general: Chung

Trả về ĐÚNG FORMAT JSON sau (KHÔNG thêm markdown, preamble):
{{
  "primary_intent": "string",
  "secondary_intents": ["string"],
  "confidence": 0.9,
  "entities": {{
    "product_names": ["string"],
    "brands": ["string"],
    "keywords": ["string"]
  }}
}}"""
        
        try:
            response = self._call_genai(
                intent_prompt,
                max_tokens=400,  # ✅ Increased from 300
                temperature=0.1,
                json_mode=True
            )
            
            # ✅ IMPROVED CLEANING
            original_response = response
            response = response.strip()
            
            # Remove preambles and markdown
            response = re.sub(
                r'^(Here is the JSON.*?:|Sure[,!].*?:|Here you go.*?:|```json\s*|```\s*)', 
                '', 
                response, 
                flags=re.IGNORECASE | re.MULTILINE
            ).strip()
            
            # Remove trailing markdown
            response = re.sub(r'```\s*$', '', response).strip()
            
            # Extract JSON object
            match = re.search(r'(\{.*\})', response, re.DOTALL)
            if match:
                response = match.group(1).strip()
            
            logger.debug(f"LLM Intent - Original: {original_response[:100]}...")
            logger.debug(f"LLM Intent - Cleaned: {response[:200]}...")

            # Parse JSON safely
            intent_data = SecurityUtils.safe_json_parse(response)
            
            if not intent_data:
                logger.warning("LLM returned invalid JSON for intent, using fallback")
                return self._detect_intent_fallback(query)
            
            intent = Intent(
                primary=intent_data.get('primary_intent', 'general'),
                secondary=intent_data.get('secondary_intents', []),
                confidence=intent_data.get('confidence', 0.7),
                entities=intent_data.get('entities', {})
            )
            
            logger.info(f"✅ Intent detected: {intent.primary} (confidence: {intent.confidence:.2f})")
            
            # Cache the intent
            if self.enable_cache and self.cache:
                cache_key = self._get_cache_key('intent', query_safe, len(history))
                self.cache.set(
                    cache_key,
                    intent.to_dict(),
                    prefix='query_result',
                    ttl=self.CACHE_CONFIG['intent_ttl']
                )
            
            return intent
        
        except Exception as e:
            logger.warning(f"LLM intent detection failed: {e}")
            self._increment_stat('errors')
            return self._detect_intent_fallback(query)
    
    def _detect_intent_fallback(self, query: str) -> Intent:
        """Fallback rule-based intent detection"""
        query_lower = query.lower()
        
        rules = [
            (['xin chào', 'hello', 'hi', 'chào'], 'greeting', 0.9),
            (['so sánh', 'compare', 'khác nhau'], 'compare', 0.8),
            (['còn hàng', 'hết hàng', 'tồn kho'], 'stock_check', 0.8),
            (['chính sách', 'đổi trả', 'bảo hành', 'thanh toán', 'trả tiền', 'phương thức'], 'policy', 0.8),
            (['hỗ trợ', 'liên hệ', 'hotline'], 'support', 0.8),
            (['thông số', 'chi tiết', 'giá'], 'product_info', 0.7),
        ]
        
        for keywords, intent, confidence in rules:
            if any(kw in query_lower for kw in keywords):
                logger.info(f"✅ Fallback intent: {intent} (confidence: {confidence:.2f})")
                return Intent(intent, [], confidence, {})
        
        logger.info("✅ Default intent: product_search")
        return Intent('product_search', [], 0.6, {})
    
    # ==================== RETRIEVAL ====================
    
    @timed_operation("retrieve")
    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """Retrieve with batch optimization"""
        if not query:
            return []
        
        query_safe = SecurityUtils.sanitize_query(query)
        
        # Check cache
        if use_cache and self.enable_cache and self.cache:
            cache_key = self._get_cache_key('query', query_safe, top_k)
            cached = self.cache.get(cache_key, prefix='query_result')
            
            if cached:
                logger.debug(f"Query cache HIT: {query_safe[:50]}")
                self._increment_stat('cache_hits')
                return cached
            
            self._increment_stat('cache_misses')
        
        # Get embedding
        q_emb = self.get_embedding_cached(query_safe)
        
        # Search vector store
        candidates = self.vector_store.find_similar_products(
            embedding=q_emb,
            limit=top_k * 3,
            min_score=0.0
        )
        
        # Batch fetch products
        product_ids = [
            c.get('product_id')
            for c in candidates
            if c.get('metadata', {}).get('type') == 'product'
        ]
        
        products_map = self.get_products_batch(product_ids)
        
        # Build results
        results = []
        for c in candidates:
            pid = c.get('product_id')
            meta = c.get('metadata', {}) or {}
            item_type = meta.get('type', 'product')
            
            if item_type == 'product':
                details = products_map.get(pid)
                results.append({
                    'id': pid,
                    'type': 'product',
                    'score': float(c.get('similarity_score', c.get('score', 0.0))),
                    'metadata': meta,
                    'data': details
                })
            
            elif item_type == 'content':
                try:
                    details = self.content_store.get_content(pid) if self.content_store else None
                except Exception as e:
                    logger.warning(f"Failed to fetch content {pid}: {e}")
                    details = None
                
                results.append({
                    'id': pid,
                    'type': 'content',
                    'score': float(c.get('similarity_score', c.get('score', 0.0))),
                    'metadata': meta,
                    'data': details
                })
        
        results.sort(key=lambda x: x['score'], reverse=True)
        results = results[:top_k]
        
        # Cache results
        if use_cache and self.enable_cache and self.cache:
            cache_key = self._get_cache_key('query', query_safe, top_k)
            self.cache.set(
                cache_key,
                results,
                prefix='query_result',
                ttl=self.CACHE_CONFIG['query_result_ttl']
            )
        
        return results
    
    def _rerank_contexts(
        self,
        query: str,
        contexts: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Re-rank contexts using LLM (with better error handling)"""
        if len(contexts) <= 3:
            return contexts
        
        try:
            # Build context descriptions
            context_descs = []
            for i, ctx in enumerate(contexts[:10]):
                if not ctx:
                    continue
                
                data = ctx.get('data') or {}
                if ctx.get('type') == 'product':
                    name = data.get('name', 'N/A')
                    desc = data.get('description', '')[:100]
                    context_descs.append(f"{i}. {name} - {desc}")
                else:
                    title = data.get('title') or ctx.get('metadata', {}).get('title', 'N/A')
                    content = data.get('content', '')[:100]
                    context_descs.append(f"{i}. {title} - {content}")
            
            if not context_descs:
                return contexts
            
            rerank_prompt = f"""Xếp hạng độ liên quan.

Câu hỏi: "{SecurityUtils.sanitize_query(query)}"

Mục:
{chr(10).join(context_descs)}

Trả về JSON array chứa các chỉ số (index) của các mục có liên quan nhất, sắp xếp từ cao đến thấp.
Ví dụ: [0, 2, 1]

Chỉ trả về JSON array, không thêm text khác:"""
            
            response = self._call_genai(
                rerank_prompt,
                max_tokens=100,
                temperature=0.1,
                json_mode=True
            )
            
            response = response.strip()
            
            # Extract JSON array
            match = re.search(r'\[[\d,\s]+\]', response)
            if match:
                ranking = json.loads(match.group())
                
                # Validate indices
                ranking = [idx for idx in ranking if 0 <= idx < len(contexts)]
                
                # Rerank
                reranked = [contexts[idx] for idx in ranking if idx < len(contexts)]
                
                # Add remaining contexts
                added_ids = {contexts[idx]['id'] for idx in ranking if idx < len(contexts)}
                for ctx in contexts:
                    if ctx['id'] not in added_ids:
                        reranked.append(ctx)
                
                logger.debug(f"Re-ranked {len(reranked)} contexts")
                return reranked
        
        except Exception as e:
            logger.warning(f"Re-ranking failed: {e}")
            self._increment_stat('errors')
        
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
        filtered = [c for c in reranked if c.get('score', 0) >= min_score]
        
        if len(filtered) < 2 and candidates:
            filtered = reranked[:max(2, top_k)]
        
        return filtered[:top_k]
    
    # ==================== RESPONSE GENERATION ====================
    
    def _extract_product_info(self, data: Dict, metadata: Dict) -> Dict[str, Any]:
        """Extract comprehensive product info (NULL-SAFE)"""
        
        info = {
            'name': data.get('name') or 'N/A',
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
        
        # Parse attributes
        attributes_str = data.get('attributes') or metadata.get('attributes')
        attributes = SecurityUtils.safe_json_parse(attributes_str)
        
        if attributes:
            general = attributes.get('general', {})
            info['brand'] = general.get('brand')
            info['gender'] = general.get('gender')
            
            material_info = attributes.get('material', {})
            info['material'] = material_info.get('material')
        
        # Parse commercial
        commercial_str = data.get('commercial') or metadata.get('commercial')
        commercial = SecurityUtils.safe_json_parse(commercial_str)
        
        if commercial:
            info['in_stock'] = commercial.get('in_stock', True)
            info['list_price'] = commercial.get('list_price')
            if not info['price']:
                info['price'] = commercial.get('price')
        
        # Parse taxonomy
        taxonomy_str = data.get('taxonomy') or metadata.get('taxonomy')
        taxonomy = SecurityUtils.safe_json_parse(taxonomy_str)
        
        if taxonomy:
            info['category'] = taxonomy.get('category')
        
        # Parse variants
        variants_str = data.get('variants') or metadata.get('variants')
        variants = SecurityUtils.safe_json_parse(variants_str)
        
        if variants and isinstance(variants, list):
            info['variants'] = variants
        
        return info
    
    def _get_system_instructions(self, intent: Intent) -> str:
        """Get system instructions based on intent with improved formatting"""
        instructions_map = {
            'product_search': """# VAI TRÒ
Bạn là chuyên viên tư vấn sản phẩm thân thiện và chuyên nghiệp.""",
            
            'product_info': """# VAI TRÒ
Bạn là chuyên gia sản phẩm với kiến thức sâu rộng.""",
            
            'compare': """# VAI TRÒ
Bạn là chuyên gia so sánh sản phẩm khách quan và chi tiết.""",
            
            'support': """# VAI TRÒ
Bạn là nhân viên CSKH nhiệt tình, sẵn sàng hỗ trợ.""",
            
            'policy': """# VAI TRÒ
Bạn là chuyên viên chính sách, giải thích rõ ràng và đầy đủ.

# ĐẶC BIỆT QUAN TRỌNG
- Khi khách hỏi về "các phương thức", "phương thức nào", "có những gì": PHẢI liệt kê ĐẦY ĐỦ TẤT CẢ
- KHÔNG rút gọn hoặc bỏ sót bất kỳ thông tin nào
- Sử dụng numbered list (1., 2., 3.) để liệt kê rõ ràng
- Bao gồm chi tiết quan trọng (số tài khoản, hotline, thời gian, phí...)""",
            
            'stock_check': """# VAI TRÒ
Bạn là chuyên viên kiểm tra tồn kho.""",
        }
        return instructions_map.get(intent.primary, instructions_map['product_search'])
    
    def _get_formatting_guide(self, intent: Intent) -> str:
        """Get formatting guide based on intent"""
        guides = {
            'policy': """
# HƯỚNG DẪN ĐỊNH DẠNG
- Với câu hỏi "có những...", "các...", "phương thức nào": Liệt kê ĐẦY ĐỦ bằng numbered list
- Với quy trình: Trình bày từng bước (Bước 1, Bước 2...)
- Với điều kiện: Dùng bullet points (-)
- Bao gồm CHI TIẾT QUAN TRỌNG: số tài khoản, hotline, email, địa chỉ, thời gian, phí
- KHÔNG rút gọn thông tin quan trọng""",
            
            'compare': """
# HƯỚNG DẪN ĐỊNH DẠNG
- So sánh theo từng tiêu chí rõ ràng
- Dùng bảng hoặc bullet points
- Nêu rõ điểm mạnh/yếu từng sản phẩm""",
            
            'product_search': """
# HƯỚNG DẪN ĐỊNH DẠNG
- Giới thiệu 2-3 sản phẩm phù hợp nhất
- Đề cập giá, đặc điểm nổi bật
- Ngắn gọn, dễ đọc""",
            
            'product_info': """
# HƯỚNG DẪN ĐỊNH DẠNG
- Trình bày thông tin theo thứ tự: Tên, Giá, Đặc điểm, Chất liệu
- Ngắn gọn 3-4 câu""",
        }
        return guides.get(intent.primary, "")
    
    def _get_dynamic_rules(self, intent: Intent) -> List[str]:
        """Get dynamic rules based on intent"""
        base_rules = [
            "1. Trả lời trực tiếp, đi thẳng vào vấn đề",
            "2. CHỈ sử dụng thông tin CÓ TRONG dữ liệu",
            "3. KHÔNG tự suy diễn hoặc bịa đặt",
            "4. Hoàn thành câu trả lời đầy đủ, không cắt ngang giữa câu"
        ]
        
        if intent.primary == 'policy':
            base_rules.extend([
                "4. Với câu hỏi liệt kê: Liệt kê ĐẦY ĐỦ TẤT CẢ, KHÔNG bỏ sót",
                "5. Bao gồm CHI TIẾT: số tài khoản, hotline, email, địa chỉ, thời gian",
                "6. Sử dụng numbered list hoặc bullet points để dễ đọc"
            ])
        elif intent.primary == 'product_info':
            base_rules.extend([
                "4. Phân biệt sản phẩm bằng SKU/Brand/Price nếu trùng tên",
                "5. Độ dài: 3-4 câu"
            ])
        elif intent.primary == 'compare':
            base_rules.extend([
                "4. So sánh theo bảng hoặc bullet points",
                "5. Nêu rõ điểm mạnh/yếu từng sản phẩm"
            ])
        elif intent.primary == 'product_search':
            base_rules.extend([
                "4. Nếu tìm thấy sản phẩm: Giới thiệu 2-3 sản phẩm phù hợp nhất",
                "5. Nếu không tìm thấy sản phẩm: Trả lời với thông tin tìm kiếm không tìm thấy",
                "6. Độ dài: 3-5 câu"
            ])
        else:
            base_rules.append("4. Trả lời đầy đủ và rõ ràng")
        
        return base_rules
    
    def _build_enhanced_prompt(
        self,
        query: str,
        contexts: List[Dict[str, Any]],
        intent: Intent,
        history: List[ConversationTurn]
    ) -> str:
        """Build enhanced prompt with dynamic formatting"""
        
        context_texts = []
        
        for i, ctx in enumerate(contexts):
            if not ctx:
                continue
            
            item_type = ctx.get('type', 'product')
            data = ctx.get('data') or {}
            metadata = ctx.get('metadata', {})
            entity_type = metadata.get('entity_type', 'product')
            
            if entity_type == 'product' and data:
                product = self._extract_product_info(data, metadata)
                
                # Build product text efficiently
                parts = [f"[Sản phẩm {i+1}] {product['name']}"]
                
                if product['brand']:
                    parts.append(f"- Thương hiệu: {product['brand']}")
                
                if product['category']:
                    parts.append(f"- Danh mục: {product['category']}")
                
                if product['price']:
                    price_text = f"- Giá: {product['price']:,.0f}đ"
                    if product['list_price'] and product['list_price'] > product['price']:
                        price_text += f" (Gốc: {product['list_price']:,.0f}đ)"
                    parts.append(price_text)
                
                if product['rating']:
                    parts.append(f"- Đánh giá: {product['rating']}/5⭐")
                
                if product['material']:
                    parts.append(f"- Chất liệu: {product['material']}")
                
                if product['gender']:
                    parts.append(f"- Dành cho: {product['gender']}")
                
                stock = "Còn hàng" if product['in_stock'] else "Hết hàng"
                parts.append(f"- Tình trạng: {stock}")
                
                if product['description']:
                    desc = product['description'][:200]
                    if len(product['description']) > 200:
                        desc += "..."
                    parts.append(f"- Mô tả: {desc}")
                
                if product['variants']:
                    parts.append(f"- Biến thể ({len(product['variants'])}):")
                    for v in product['variants'][:3]:
                        v_parts = []
                        if v.get('name'):
                            v_parts.append(v['name'])
                        if v.get('color'):
                            v_parts.append(f"Màu: {v['color']}")
                        if v.get('price'):
                            v_parts.append(f"{v['price']:,.0f}đ")
                        
                        if v_parts:
                            parts.append(f"  • {' - '.join(v_parts)}")
                    
                    if len(product['variants']) > 3:
                        parts.append(f"  ... còn {len(product['variants']) - 3} biến thể")
                
                context_texts.append("\n".join(parts))
            
            elif entity_type == 'content':
                title = data.get('title') or metadata.get('title', f"Nội dung {i+1}")
                content = data.get('content') or metadata.get('content', '')
                
                # ✅ For policy content, preserve full content
                if intent.primary == 'policy':
                    context_texts.append(f"[Thông tin {i+1}] {title}\n{content}")
                else:
                    # For other intents, can truncate
                    content_preview = content[:500] if len(content) > 500 else content
                    if len(content) > 500:
                        content_preview += "..."
                    context_texts.append(f"[Nội dung {i+1}] {title}\n{content_preview}")
        
        contexts_combined = "\n\n".join(context_texts) if context_texts else "Không có thông tin."
        
        system_instructions = self._get_system_instructions(intent)
        formatting_guide = self._get_formatting_guide(intent)
        dynamic_rules = self._get_dynamic_rules(intent)
        
        prompt_parts = [
            system_instructions,
            formatting_guide,
            "",
            "# THÔNG TIN",
            contexts_combined,
            "",
            "# CÂU HỎI",
            SecurityUtils.sanitize_query(query),
            "",
            "# QUY TẮC",
            *dynamic_rules,
            "",
            "# CÂU TRẢ LỜI"
        ]
        
        return "\n".join(prompt_parts)
    
    @timed_operation("call_genai")
    def _call_genai(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.2,
        retry: int = 3,
        json_mode: bool = False
    ) -> str:
        """Call Google GenAI with retry and circuit breaker"""
        
        self._increment_stat('llm_calls')
        
        generation_config = {
            'max_output_tokens': max_tokens,
            'temperature': temperature
        }
        
        if json_mode:
            generation_config['response_mime_type'] = 'application/json'
        
        for attempt in range(retry):
            try:
                # Use Google GenAI SDK
                response = self.google_client.generate_content(
                    model=config.GOOGLE_MODEL,
                    contents=prompt,
                    config=generation_config
                )
                
                if not response.parts:
                     logger.warning("LLM returned empty response")
                     return ""
                     
                return response.text if response.text else ""
            
            except Exception as e:
                logger.warning(f"LLM call attempt {attempt + 1}/{retry} failed: {e}")
                self._increment_stat('errors')
                
                if attempt < retry - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    raise
    
    def _get_canned_response(self, query: str, intent: Intent) -> str:
        """Get canned responses for simple intents"""
        responses = {
            'greeting': "Xin chào! Tôi có thể giúp bạn tìm sản phẩm hoặc giải đáp thắc mắc. 😊",
            'support': "📞 Liên hệ hỗ trợ:\n- Hotline: 1900-xxxx\n- Email: support@example.com\n- Chat: 24/7",
        }
        
        return responses.get(
            intent.primary,
            "Xin lỗi, tôi không thể trả lời câu hỏi này. Vui lòng liên hệ bộ phận hỗ trợ."
        )
    
    # ==================== MAIN API ====================
    
    @timed_operation("answer")
    def answer(
        self,
        query: str,
        session_id: str = "default",
        top_k: int = 5,
        use_reranking: bool = True,
        use_cache: bool = True
    ) -> Tuple[str, List[Dict[str, Any]], Intent]:
        """Main answer method with full pipeline"""
        
        try:
            # Sanitize inputs
            query_safe = SecurityUtils.sanitize_query(query)
            session_id_safe = SecurityUtils.sanitize_session_id(session_id)
            
            if not query_safe:
                intent = Intent('general', [], 0.0, {})
                return "Vui lòng nhập câu hỏi.", [], intent
            
            # Get conversation history
            history = self.get_conversation_history(session_id_safe)
            
            # Resolve coreferences
            resolved_query = self._resolve_coreferences(query_safe, history)
            
            # Detect intent
            intent = self._detect_intent_llm(resolved_query, history)
            logger.info(f"Intent: {intent.primary} (conf={intent.confidence:.2f})")
            
            # Handle greetings
            if intent.primary == 'greeting':
                answer = self._get_canned_response(query_safe, intent)
                turn = ConversationTurn(query_safe, answer, [], intent, time.time())
                self.save_conversation_turn(session_id_safe, turn)
                return answer, [], intent

            # Check for cached response (only if not greeting)
            if use_cache and self.enable_cache and self.cache:
                # Use resolved query and intent for more robust cache key
                # We include intent to differentiate if same query led to different intent (unlikely but safer)
                cache_key_str = f"response:{resolved_query}:{intent.primary}:{top_k}"
                cache_key = hashlib.md5(cache_key_str.encode()).hexdigest()
                
                cached_response = self.cache.get(cache_key, prefix='query_result')
                if cached_response:
                    logger.info(f"✅ Response cache HIT for '{resolved_query}'")
                    self._increment_stat('cache_hits')
                    
                    # Reconstruct objects
                    cached_answer = cached_response.get('answer')
                    cached_contexts = cached_response.get('contexts', [])
                    # intent is already derived fresh, but we could use cached one if we cached it too
                    # current flow: fresh intent -> check cache -> return
                    
                    turn = ConversationTurn(
                        query_safe, 
                        cached_answer, 
                        cached_contexts, 
                        intent, 
                        time.time(),
                        metrics={'cache_hit': True}
                    )
                    self.save_conversation_turn(session_id_safe, turn)
                    return cached_answer, cached_contexts, intent

            # Retrieve contexts
            if use_reranking:
                contexts = self.retrieve_with_reranking(
                    resolved_query,
                    top_k=top_k,
                    use_cache=use_cache
                )
            else:
                contexts = self.retrieve(
                    resolved_query,
                    top_k=top_k,
                    use_cache=use_cache
                )
            
            # No results found
            if not contexts:
                answer = "Xin lỗi, tôi không tìm thấy thông tin phù hợp. Bạn có thể diễn đạt lại câu hỏi?"
                turn = ConversationTurn(query_safe, answer, [], intent, time.time())
                self.save_conversation_turn(session_id_safe, turn)
                return answer, [], intent
            
            # Build prompt
            prompt = self._build_enhanced_prompt(
                resolved_query,
                contexts,
                intent,
                history
            )
            
            max_tokens = 1536 if intent.primary == 'policy' else 1024  
            answer = self._call_genai(prompt, max_tokens=max_tokens, temperature=0.2)
            
            turn = ConversationTurn(
                query_safe,
                answer,
                contexts,
                intent,
                time.time(),
                metrics={'llm_calls': 1}
            )
            self.save_conversation_turn(session_id_safe, turn)
            
            logger.info(f"✅ Answer generated ({len(answer)} chars)")
            
            # Cache the response
            if use_cache and self.enable_cache and self.cache:
                try:
                    # Reuse the key calculation logic or re-calculate
                    cache_key_str = f"response:{resolved_query}:{intent.primary}:{top_k}"
                    cache_key = hashlib.md5(cache_key_str.encode()).hexdigest()
                    
                    cache_data = {
                        'answer': answer,
                        'contexts': contexts,
                        'intent': intent.to_dict(),
                        'timestamp': time.time()
                    }
                    
                    self.cache.set(
                        cache_key,
                        cache_data,
                        prefix='query_result',
                        ttl=self.CACHE_CONFIG['response_ttl']
                    )
                    logger.debug(f"Cached response for '{resolved_query}'")
                except Exception as e:
                    logger.warning(f"Failed to cache response: {e}")

            return answer, contexts, intent
        
        except Exception as e:
            logger.exception(f"Error in answer pipeline: {e}")
            self._increment_stat('errors')
            
            # Fallback response
            intent = self._detect_intent_fallback(query)
            contexts = locals().get('contexts', [])
            
            if contexts:
                top_ctx = contexts[0]
                data = top_ctx.get('data', {}) or {}
                meta = top_ctx.get('metadata', {})
                
                title = data.get('name') or meta.get('title', 'Nội dung liên quan')
                desc = data.get('description') or meta.get('content', '')
                
                answer = f"⚠️ [Offline Mode]\n\n**{title}**\n{desc[:200]}...\n\n(Hệ thống AI đang bận)"
                return answer, contexts, intent
            
            answer = self._get_canned_response(query, intent)
            return answer, [], intent
    
    # ==================== MONITORING ====================
    
    def _increment_stat(self, stat_name: str):
        """Thread-safe stat increment"""
        with self._stats_lock:
            self._stats[stat_name] = self._stats.get(stat_name, 0) + 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        with self._stats_lock:
            stats = self._stats.copy()
        
        # Calculate cache hit rate
        total_cache_requests = stats.get('cache_hits', 0) + stats.get('cache_misses', 0)
        cache_hit_rate = (
            stats.get('cache_hits', 0) / total_cache_requests
            if total_cache_requests > 0
            else 0.0
        )
        
        stats['cache_hit_rate'] = f"{cache_hit_rate:.2%}"
        
        if self.enable_cache and self.cache:
            stats['redis_stats'] = self.cache.get_stats()
        
        return stats
    
    def reset_stats(self):
        """Reset statistics"""
        with self._stats_lock:
            self._stats = {
                'cache_hits': 0,
                'cache_misses': 0,
                'llm_calls': 0,
                'errors': 0
            }
        logger.info("Statistics reset")
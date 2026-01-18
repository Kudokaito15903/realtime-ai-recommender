"""
RAG (Retrieval-Augmented Generation) Engine
"""

from typing import List, Dict, Any, Optional
from loguru import logger
import numpy as np

import config
from adapters.factory import get_vector_store
from domain.embeddings.product_embeddings import get_embedding_model


class RAGEngine:
    """
    RAG Engine for retrieving relevant chunks from vector database.

    Features:
    - Hybrid search (vector + keyword)
    - Filtering by metadata
    - Reranking with cross-encoder
    - Context window management
    """

    def __init__(self):
        self.vector_store = get_vector_store()
        self.embedding_model = get_embedding_model()
        
        # ContentService for policy and CSKH content
        try:
            from services.content_service import ContentService
            self.content_service = ContentService()
        except Exception as e:
            logger.warning(f"ContentService not available: {e}")
            self.content_service = None

    async def retrieve(
        self,
        query: str,
        collection: str,
        top_k: int = None,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: float = None,
        rerank: bool = None,
        namespace: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant chunks for query.

        Args:
            query: User query
            collection: Collection type hint (products_knowledge, policies_knowledge, etc.)
                       NOTE: This is only used to determine namespace. The actual collection/index
                       is configured in PineconeVectorStore (default: "product-recommendations")
            top_k: Number of results to return
            filters: Metadata filters (not yet implemented for Pinecone)
            score_threshold: Minimum relevance score
            rerank: Whether to rerank with cross-encoder
            namespace: Vector store namespace (auto-detect if not provided)
                      - "rag_chunks" for product chunks
                      - "content" for policy/CSKH content
                      - "products" for recommendation embeddings

        Returns:
            List of retrieved chunks with metadata
        """
        # Use defaults if not specified
        top_k = top_k or 5
        score_threshold = score_threshold or 0.75
        rerank = rerank if rerank is not None else False

        # Generate query embedding
        query_embedding = self.embedding_model.embed_text(query)

        # Determine namespace if not provided
        if namespace is None:
            # Product chunks are stored in "rag_chunks" namespace
            # Content (policy, CSKH) are stored in "content" namespace
            if "product" in collection.lower():
                namespace = "rag_chunks"
            else:
                namespace = "products"
        
        # Retrieve from vector store
        initial_results = self.vector_store.find_similar_products(
            embedding=query_embedding,
            limit=top_k * 2 if rerank else top_k,
            min_score=score_threshold,
            namespace=namespace,
        )

        if not initial_results:
            logger.warning(f"No results found for query: {query[:50]}...")
            return []

        logger.info(f"Retrieved {len(initial_results)} initial results")

        # Convert to chunk format
        # Chunks from rag_chunks namespace have metadata with "text" field
        formatted_results = []
        for i, result in enumerate(initial_results[:top_k]):
            metadata = result.get("metadata", {})
            
            # Get chunk text from metadata (stored by product_event_handler)
            chunk_text = metadata.get("text", "") or metadata.get("description", "")
            
            # Get chunk_id from result (Pinecone returns id as "product_id" field)
            chunk_id = result.get("product_id", f"chunk_{i}")
            
            # Get chunk_type from metadata
            chunk_type = metadata.get("chunk_type", "product")
            
            formatted_results.append(
                {
                    "rank": i + 1,
                    "chunk_id": chunk_id,
                    "score": result.get("similarity_score", 0.0),
                    "text": chunk_text,
                    "chunk_type": chunk_type,
                    "metadata": metadata,
                }
            )

        return formatted_results

    async def _rerank(self, query: str, candidates: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        """
        Rerank candidates using cross-encoder.

        This provides more accurate relevance scoring than pure vector similarity.
        """
        try:
            from sentence_transformers import CrossEncoder

            # Initialize cross-encoder (cache this in production)
            cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

            # Create pairs for scoring
            pairs = []
            for candidate in candidates:
                text = candidate.get("text", "") or candidate.get("metadata", {}).get("text", "")
                pairs.append([query, text])

            # Score all pairs
            scores = cross_encoder.predict(pairs)

            # Combine scores with candidates
            for i, candidate in enumerate(candidates):
                candidate["rerank_score"] = float(scores[i])

            # Sort by rerank score
            reranked = sorted(candidates, key=lambda x: x.get("rerank_score", x.get("score", 0)), reverse=True)

            return reranked[:top_k]
        except Exception as e:
            logger.error(f"Error reranking: {e}")
            return candidates[:top_k]

    async def retrieve_product_chunks(
        self,
        query: str,
        product_ids: Optional[List[str]] = None,
        device_type: Optional[str] = None,
        top_k: int = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve product knowledge chunks.

        Args:
            query: User query
            product_ids: Filter by specific product IDs
            device_type: Filter by device type (smartphone, laptop, etc.)
            top_k: Number of results

        Returns:
            List of product chunks
        """
        # Build filters
        filters = {}

        if product_ids:
            filters["product_id"] = {"$in": product_ids}

        if device_type:
            filters["device_type"] = device_type

        # Retrieve product chunks from "rag_chunks" namespace
        # Note: Product chunks are stored separately from recommendation embeddings
        # Recommendation embeddings are in "products" namespace
        # RAG chunks are in "rag_chunks" namespace
        results = await self.retrieve(
            query=query,
            collection="products_knowledge",
            top_k=top_k,
            filters=filters if filters else None,
            namespace="rag_chunks",  # Explicitly use rag_chunks namespace
        )
        
        # Apply additional filters if needed
        if product_ids:
            # Filter chunks by product_id in metadata
            filtered_results = []
            for result in results:
                metadata = result.get("metadata", {})
                chunk_product_id = metadata.get("product_id")
                if chunk_product_id and chunk_product_id in product_ids:
                    filtered_results.append(result)
            results = filtered_results[:top_k] if top_k else filtered_results
        
        if device_type:
            # Filter chunks by device_type in metadata
            filtered_results = []
            for result in results:
                metadata = result.get("metadata", {})
                if metadata.get("device_type") == device_type:
                    filtered_results.append(result)
            results = filtered_results[:top_k] if top_k else filtered_results

        logger.info(f"Retrieved {len(results)} product chunks from rag_chunks namespace")
        return results

    async def retrieve_policy_chunks(
        self, query: str, policy_type: Optional[str] = None, top_k: int = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve policy knowledge chunks.

        Args:
            query: User query
            policy_type: Filter by policy type (warranty, return, shipping, payment)
            top_k: Number of results

        Returns:
            List of policy chunks
        """
        # Use ContentService to search policy content
        if not self.content_service:
            logger.warning("ContentService not available for policy retrieval")
            return []
        
        try:
            # Semantic search for policy content
            # Note: category should match sample_content.py (case-insensitive matching)
            policy_type_tag = policy_type  # warranty, return, shipping, payment
            content_results = self.content_service.search_content(
                query=query,
                category="Policy",  # Match sample_content.py category
                limit=top_k or 3
            )
            
            # Filter by policy_type if provided
            if policy_type_tag:
                content_results = [
                    c for c in content_results
                    if policy_type_tag in c.get("tags", [])
                ]
            
            # Convert to chunk format
            chunks = []
            for i, content in enumerate(content_results[:top_k or 3]):
                chunks.append({
                    "rank": i + 1,
                    "chunk_id": content.get("id", f"policy_{i}"),
                    "score": content.get("similarity_score", 0.8),
                    "text": f"{content.get('title', '')}\n{content.get('content', '')}",
                    "chunk_type": "policy",
                    "metadata": {
                        "policy_type": policy_type_tag,
                        "content_id": content.get("id"),
                        "title": content.get("title"),
                        "tags": content.get("tags", []),
                    },
                })
            
            logger.info(f"Retrieved {len(chunks)} policy chunks")
            return chunks
            
        except Exception as e:
            logger.error(f"Error retrieving policy chunks: {e}", exc_info=True)
            return []

    async def retrieve_cskh_chunks(
        self, query: str, topic: Optional[str] = None, top_k: int = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve CSKH (customer support) knowledge chunks.

        Args:
            query: User query
            topic: Filter by topic (order_tracking, account_management, etc.)
            top_k: Number of results

        Returns:
            List of CSKH chunks
        """
        # Use ContentService to search CSKH content
        if not self.content_service:
            logger.warning("ContentService not available for CSKH retrieval")
            return []
        
        try:
            # Semantic search for CSKH content
            content_results = self.content_service.search_content(
                query=query,
                category="cskh",
                limit=top_k or 2
            )
            
            # Filter by topic if provided
            if topic:
                content_results = [
                    c for c in content_results
                    if topic in c.get("tags", [])
                ]
            
            # Convert to chunk format
            chunks = []
            for i, content in enumerate(content_results[:top_k or 2]):
                chunks.append({
                    "rank": i + 1,
                    "chunk_id": content.get("id", f"cskh_{i}"),
                    "score": content.get("similarity_score", 0.8),
                    "text": f"{content.get('title', '')}\n{content.get('content', '')}",
                    "chunk_type": "cskh",
                    "metadata": {
                        "topic": topic,
                        "content_id": content.get("id"),
                        "title": content.get("title"),
                        "tags": content.get("tags", []),
                    },
                })
            
            logger.info(f"Retrieved {len(chunks)} CSKH chunks")
            return chunks
            
        except Exception as e:
            logger.error(f"Error retrieving CSKH chunks: {e}", exc_info=True)
            return []

    def build_context(
        self, chunks: List[Dict[str, Any]], max_tokens: int = 2000
    ) -> str:
        """
        Build context string from retrieved chunks.

        Args:
            chunks: Retrieved chunks
            max_tokens: Maximum tokens for context (rough estimate: 1 token ≈ 4 chars)

        Returns:
            Context string
        """
        if not chunks:
            return ""

        context_parts = []
        total_length = 0
        max_length = max_tokens * 4  # Rough char estimate

        for i, chunk in enumerate(chunks):
            text = chunk.get("text", "")
            chunk_type = chunk.get("chunk_type", "")

            # Format chunk
            chunk_text = f"[Nguồn {i+1} - {chunk_type}]\n{text}\n"

            # Check if adding this chunk exceeds limit
            if total_length + len(chunk_text) > max_length:
                break

            context_parts.append(chunk_text)
            total_length += len(chunk_text)

        context = "\n".join(context_parts)

        logger.debug(
            f"Built context from {len(context_parts)} chunks ({total_length} chars)"
        )

        return context

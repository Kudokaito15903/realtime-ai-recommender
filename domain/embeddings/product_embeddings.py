"""
Product embedding generation using SentenceTransformer.
Supports DUAL strategy:
1. Multi-chunk for RAG chatbot
2. Single embedding for content-based recommendation
"""

import os
import sys
import time
import threading
import re
from typing import List, Dict, Any, Tuple
from bs4 import BeautifulSoup
import numpy as np
from loguru import logger
from sentence_transformers import SentenceTransformer

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from config import VECTOR_DIMENSION


class ProductEmbeddingModel:
    """
    SentenceTransformer-based embedding model with DUAL strategy.

    Strategy:
    1. Multi-chunk embeddings (for RAG chatbot Q&A)
    2. Single product embedding (for content-based recommendation)
    """

    _instance = None
    _lock = threading.Lock()

    MODEL_NAME = "intfloat/multilingual-e5-base"

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                start_time = time.time()
                logger.info("Loading SentenceTransformer model...")

                instance = super().__new__(cls)
                instance.model = SentenceTransformer(cls.MODEL_NAME, device="cpu")

                instance.dimension = instance.model.get_sentence_embedding_dimension()

                if instance.dimension != VECTOR_DIMENSION:
                    logger.warning(
                        f"VECTOR_DIMENSION={VECTOR_DIMENSION} "
                        f"!= model dimension={instance.dimension}"
                    )

                logger.info(
                    f"Model loaded in {time.time() - start_time:.2f}s "
                    f"(dim={instance.dimension})"
                )

                cls._instance = instance

            return cls._instance

    # =========================
    # Helper Methods
    # =========================

    @staticmethod
    def clean_html(html_text: str) -> str:
        """Clean HTML tags from description."""
        if not html_text:
            return ""

        soup = BeautifulSoup(html_text, "html.parser")
        text = soup.get_text(separator=" ")
        text = re.sub(r"\s+", " ", text).strip()

        return text

    @staticmethod
    def get_spec_by_key(
        specifications: List[Dict], key_pattern: str, group: str = None
    ) -> str:
        """Get specification value by key pattern and optional group."""
        if not specifications:
            return ""

        key_pattern_lower = key_pattern.lower()

        for spec in specifications:
            spec_key = spec.get("key", "").lower()
            spec_group = spec.get("group", "")

            if key_pattern_lower in spec_key:
                if group and spec_group != group:
                    continue
                return str(spec.get("value", ""))

        return ""

    @staticmethod
    def get_specs_by_group(specifications: List[Dict], group: str) -> List[str]:
        """Get all specifications in a group."""
        if not specifications:
            return []

        specs = []
        for spec in specifications:
            if spec.get("group") == group and spec.get("value"):
                key = spec.get("key", "")
                value = spec.get("value", "")
                specs.append(f"{key}: {value}")

        return specs

    @staticmethod
    def normalize_device_type(categories: List[Dict]) -> str:
        """Infer device type from categories."""
        if not categories:
            return "unknown"

        category_names = [cat.get("name", "").lower() for cat in categories]
        category_text = " ".join(category_names)

        if any(
            k in category_text for k in ["phone", "smartphone", "điện thoại", "mobile"]
        ):
            return "smartphone"
        elif any(k in category_text for k in ["laptop", "notebook"]):
            return "laptop"
        elif any(k in category_text for k in ["pc", "desktop", "máy tính bàn"]):
            return "pc"
        elif any(k in category_text for k in ["tablet", "máy tính bảng"]):
            return "tablet"
        elif any(k in category_text for k in ["watch", "smartwatch", "đồng hồ"]):
            return "smartwatch"
        else:
            return "electronics"

    # =========================
    # NEW: Single Product Embedding for Recommendation
    # =========================

    def create_product_embedding_text(self, product_data: Dict[str, Any]) -> str:
        """
        Create a SINGLE comprehensive text for product-level embedding.
        Used for content-based recommendation.

        This combines ALL important aspects into ONE text:
        - Name, brand, description
        - Key specifications (CPU, RAM, Storage, Display, Camera, Battery)
        - Categories
        - NOT including: price, ratings, SKU, IDs, dates

        Returns:
            Single text string representing the entire product
        """
        text_parts = []

        # Basic info
        name = product_data.get("name", "")
        brand = product_data.get("brand", "")
        description = self.clean_html(product_data.get("description", ""))
        specifications = product_data.get("specifications", [])
        categories = product_data.get("categories", [])

        # 1. Name and brand
        if name and brand:
            text_parts.append(f"{name} {brand}")
        elif name:
            text_parts.append(name)

        # 2. Categories (semantic meaning)
        category_names = [cat.get("name", "") for cat in categories if cat.get("name")]
        if category_names:
            text_parts.append(f"Danh mục: {', '.join(category_names)}")

        # 3. Description (cleaned)
        if description:
            text_parts.append(description)

        warranty = product_data.get("warranty")
        if warranty:
            text_parts.append(f"Bảo hành: {warranty}")

        # 4. Key specifications - group by importance
        device_type = self.normalize_device_type(categories)

        # Performance specs (critical for similarity)
        cpu = self.get_spec_by_key(
            specifications, "phiên bản cpu", "Performance"
        ) or self.get_spec_by_key(specifications, "cpu", "Performance")
        if cpu:
            text_parts.append(f"Bộ xử lý: {cpu}")

        ram = self.get_spec_by_key(specifications, "dung lượng", "RAM")
        if ram:
            text_parts.append(f"RAM: {ram}")

        storage = self.get_spec_by_key(specifications, "dung lượng", "Storage")
        if storage:
            text_parts.append(f"Bộ nhớ: {storage}")

        # Display specs (important for phones/laptops)
        screen_size = self.get_spec_by_key(specifications, "kích thước", "Display")
        screen_tech = self.get_spec_by_key(specifications, "công nghệ", "Display")
        if screen_size or screen_tech:
            text_parts.append(f"Màn hình: {screen_size} {screen_tech}".strip())

        # GPU (important for laptops/PCs)
        if device_type in ["laptop", "pc"]:
            gpu = self.get_spec_by_key(specifications, "chip đồ họa", "Graphic")
            if gpu:
                text_parts.append(f"Card đồ họa: {gpu}")

        # Camera (important for smartphones/tablets)
        if device_type in ["smartphone", "tablet"]:
            camera = self.get_spec_by_key(specifications, "độ phân giải", "Camera")
            if camera:
                text_parts.append(f"Camera: {camera}")

        # Battery (important for mobile devices)
        battery = self.get_spec_by_key(specifications, "dung lượng pin", "Battery")
        if battery:
            text_parts.append(f"Pin: {battery}")

        # OS
        os_name = self.get_spec_by_key(specifications, "tên os", "OperatingSystem")
        if os_name:
            text_parts.append(f"Hệ điều hành: {os_name}")

        # Combine all parts
        combined_text = " ".join(text_parts)

        logger.debug(f"Created product embedding text ({len(combined_text)} chars)")

        return combined_text

    def get_product_recommendation_embedding(
        self, product_data: Dict[str, Any]
    ) -> np.ndarray:
        """
        Generate SINGLE embedding vector for product-level recommendation.

        Use this for:
        - Content-based recommendation
        - Product similarity search
        - "Similar products" feature

        Returns:
            numpy array of shape (dimension,) - normalized embedding vector
        """
        text = self.create_product_embedding_text(product_data)
        embedding = self.embed_text(text)

        logger.debug(
            f"Generated recommendation embedding for product {product_data.get('id')}"
        )

        return embedding

    # =========================
    # EXISTING: Multi-Chunk for RAG Chatbot
    # =========================

    def create_product_chunks(
        self, product_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Create MULTIPLE chunks for one product (for RAG chatbot).
        Each chunk focuses on different aspect for better Q&A retrieval.

        Use this for:
        - Chatbot Q&A
        - Specific product information queries

        Returns:
            List of chunks, each containing:
            - chunk_type: str
            - text: str
            - metadata: dict
        """
        chunks = []

        # Extract basic info
        product_id = product_data.get("id")
        name = product_data.get("name", "")
        brand = product_data.get("brand", "")
        description = self.clean_html(product_data.get("description", ""))
        specifications = product_data.get("specifications", [])
        categories = product_data.get("categories", [])
        variants = product_data.get("productVariants", [])

        device_type = self.normalize_device_type(categories)
        category_names = [cat.get("name", "") for cat in categories if cat.get("name")]
        colors = list(set([v.get("color") for v in variants if v.get("color")]))

        base_metadata = {
            "product_id": product_id,
            "product_name": name,
            "brand": brand,
            "device_type": device_type,
            "category_names": category_names,
            "available_colors": colors,
        }

        # CHUNK 1: OVERVIEW
        overview_parts = []
        overview_parts.append(f"{name} của thương hiệu {brand}")
        if description:
            overview_parts.append(description)
        if category_names:
            overview_parts.append(f"Danh mục: {', '.join(category_names)}")

        chunks.append(
            {
                "chunk_type": "overview",
                "text": " ".join(overview_parts),
                "metadata": {
                    **base_metadata,
                    "focus": "overview",
                    "chunk_id": f"{product_id}_overview",
                },
            }
        )

        # CHUNK 2: TECHNICAL SPECIFICATIONS
        tech_parts = [f"Thông số kỹ thuật {name}:"]

        cpu = self.get_spec_by_key(
            specifications, "cpu", "Performance"
        ) or self.get_spec_by_key(specifications, "phiên bản cpu", "Performance")
        if cpu:
            tech_parts.append(f"CPU: {cpu}")

        cpu_cores = self.get_spec_by_key(
            specifications, "số nhân", "Performance"
        ) or self.get_spec_by_key(specifications, "loại cpu", "Performance")
        if cpu_cores:
            tech_parts.append(f"Loại CPU: {cpu_cores}")

        ram = self.get_spec_by_key(specifications, "dung lượng", "RAM")
        if ram:
            tech_parts.append(f"RAM: {ram}")

        storage = self.get_spec_by_key(specifications, "dung lượng", "Storage")
        if storage:
            tech_parts.append(f"Bộ nhớ trong: {storage}")

        screen_size = self.get_spec_by_key(specifications, "kích thước", "Display")
        screen_tech = self.get_spec_by_key(specifications, "công nghệ", "Display")
        screen_std = self.get_spec_by_key(specifications, "chuẩn", "Display")
        resolution = self.get_spec_by_key(specifications, "độ phân giải", "Display")

        if screen_size or screen_tech:
            display_text = (
                f"Màn hình: {screen_size or ''} {screen_tech or ''} {screen_std or ''}"
            )
            if resolution:
                display_text += f" độ phân giải {resolution}"
            tech_parts.append(display_text.strip())

        gpu = self.get_spec_by_key(specifications, "chip đồ họa", "Graphic")
        if gpu:
            tech_parts.append(f"Card đồ họa: {gpu}")

        os_name = self.get_spec_by_key(specifications, "tên os", "OperatingSystem")
        os_version = self.get_spec_by_key(
            specifications, "phiên bản os", "OperatingSystem"
        )
        if os_name:
            os_text = f"Hệ điều hành: {os_name}"
            if os_version:
                os_text += f" {os_version}"
            tech_parts.append(os_text)

        if len(tech_parts) > 1:
            chunks.append(
                {
                    "chunk_type": "technical",
                    "text": " ".join(tech_parts),
                    "metadata": {
                        **base_metadata,
                        "focus": "specs",
                        "chunk_id": f"{product_id}_technical",
                    },
                }
            )

        # CHUNK 3: DESIGN & BUILD
        design_parts = [f"Thiết kế và chất liệu {name}:"]
        design_specs = self.get_specs_by_group(specifications, "Design")
        if design_specs:
            design_parts.extend(design_specs)
        if colors:
            design_parts.append(f"Màu sắc: {', '.join(colors)}")

        if len(design_parts) > 1:
            chunks.append(
                {
                    "chunk_type": "design",
                    "text": " ".join(design_parts),
                    "metadata": {
                        **base_metadata,
                        "focus": "design",
                        "chunk_id": f"{product_id}_design",
                    },
                }
            )

        # CHUNK 4: CAMERA (for smartphones/tablets)
        if device_type in ["smartphone", "tablet"]:
            camera_parts = [f"Camera {name}:"]
            camera_specs = self.get_specs_by_group(specifications, "Camera")
            if camera_specs:
                camera_parts.extend(camera_specs)

            if len(camera_parts) > 1:
                chunks.append(
                    {
                        "chunk_type": "camera",
                        "text": " ".join(camera_parts),
                        "metadata": {
                            **base_metadata,
                            "focus": "camera",
                            "chunk_id": f"{product_id}_camera",
                        },
                    }
                )

        # CHUNK 5: BATTERY & CONNECTIVITY
        battery_parts = [f"Pin và kết nối {name}:"]
        battery_specs = self.get_specs_by_group(specifications, "Battery")
        if battery_specs:
            battery_parts.extend(battery_specs)

        connectivity_specs = self.get_specs_by_group(specifications, "Connectivity")
        if connectivity_specs:
            battery_parts.append("Kết nối: " + ", ".join(connectivity_specs))

        if len(battery_parts) > 1:
            chunks.append(
                {
                    "chunk_type": "battery_connectivity",
                    "text": " ".join(battery_parts),
                    "metadata": {
                        **base_metadata,
                        "focus": "battery_connectivity",
                        "chunk_id": f"{product_id}_battery_connectivity",
                    },
                }
            )

        # CHUNK 6: WARRANTY INFO
        warranty = product_data.get("warranty")
        if warranty:
            chunks.append(
                {
                    "chunk_type": "warranty",
                    "text": f"Bảo hành {name}: {warranty}",
                    "metadata": {
                        **base_metadata,
                        "focus": "warranty",
                        "chunk_id": f"{product_id}_warranty",
                    },
                }
            )

        logger.debug(f"Created {len(chunks)} chunks for product {product_id}")

        return chunks

    def embed_product_chunks(
        self, product_data: Dict[str, Any]
    ) -> List[Tuple[np.ndarray, Dict]]:
        """
        Generate embeddings for all chunks of a product (for RAG chatbot).

        Returns:
            List of (embedding_vector, chunk_metadata) tuples
        """
        chunks = self.create_product_chunks(product_data)
        texts = [chunk["text"] for chunk in chunks]
        embeddings = self.embed_batch(texts)

        results = []
        for i, chunk in enumerate(chunks):
            results.append(
                (
                    embeddings[i],
                    {
                        "chunk_type": chunk["chunk_type"],
                        "text": chunk["text"],
                        "metadata": chunk["metadata"],
                    },
                )
            )

        return results

    # =========================
    # Core Embedding Methods
    # =========================

    def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for semantic text."""
        if not text or not text.strip():
            logger.warning("Empty text for embedding, returning epsilon vector")
            return np.zeros(self.dimension, dtype=np.float32)

        return self.model.encode(
            text,
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).astype(np.float32)

    def embed_batch(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings for a batch of texts."""
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)

        return self.model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).astype(np.float32)

    # =========================
    # DEPRECATED (for backward compatibility)
    # =========================

    def get_product_embedding(self, product_data: Dict[str, Any]) -> np.ndarray:
        """
        DEPRECATED: Use specific methods instead:
        - get_product_recommendation_embedding() for recommendation
        - embed_product_chunks() for RAG chatbot

        Kept for backward compatibility.
        Defaults to recommendation embedding.
        """
        logger.warning(
            "get_product_embedding() is deprecated. Use:\n"
            "- get_product_recommendation_embedding() for recommendation\n"
            "- embed_product_chunks() for RAG chatbot"
        )
        return self.get_product_recommendation_embedding(product_data)

    def get_embedding(self, text: str) -> np.ndarray:
        """Alias for embed_text for backward compatibility."""
        return self.embed_text(text)

    @property
    def embedding_dimension(self) -> int:
        return self.dimension


# =========================
# Singleton accessors
# =========================


def get_product_embedding_model() -> ProductEmbeddingModel:
    return ProductEmbeddingModel()


def get_embedding_model() -> ProductEmbeddingModel:
    return get_product_embedding_model()

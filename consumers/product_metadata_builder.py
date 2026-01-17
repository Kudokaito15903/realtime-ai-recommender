"""
Metadata builder for Vector DB upsert.
Used for filtering, ranking, variant selection.
"""

from typing import Dict, Any, List
from datetime import date
import json

class ProductMetadataBuilder:

    # =========================
    # Public API
    # =========================

    @classmethod
    def build(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Entry point: build full metadata object.
        """
        product_meta = cls._build_product_metadata(payload)
        variants_meta = cls._build_variants_metadata(payload.get("productVariants", []))
        stats_meta = cls._build_stats_metadata(variants_meta)

        # Flatten structure for Pinecone (metadata must be flat key-value pairs of str, number, bool, list[str])
        # But wait, Pinecone supports JSON objects? No, Pinecone metadata values must be strings, numbers, booleans, or lists of strings.
        # Nested dictionaries are NOT supported directly in Pinecone metadata values in most cases unless serialized.
        # However, the user provided code returns nested dicts: "product", "variants", "stats".
        # If this is intended for Pinecone, we might need to flatten it OR serialize the nested parts.
        # Given the error history ("Metadata value must be a string..."), I should probably serialize the complex parts 
        # OR flatten them. 
        # CHECK: The user's code returns: {"product": {...}, "variants": [...], "stats": {...}}
        # If I return this directly to Pinecone, it will fail again with "Metadata value must be ...".
        # I will modify the build to return a FLATTENED version or JSON dump complex fields.
        
        # Let's inspect the user's intent. They might want this structure for the application logic, 
        # but for Pinecone we need to adapt it. 
        # I will implement it EXACTLY as requested first in the class, but when using it in the handler, 
        # I will need to flatten it, OR I can modify the builder to produce Pinecone-compatible output.
        
        # Actually, looking at the previous error: "Metadata value must be a string... got 'null'".
        # If I use this builder, I must ensure the output is compatible.
        
        # Let's implement the class as is, but maybe add a method `build_pinecone_metadata` 
        # or handle compatibility in the handler.
        
        return {
            "product": product_meta,
            "variants": variants_meta,
            "stats": stats_meta
        }

    # =========================
    # Product-level metadata
    # =========================

    @staticmethod
    def _build_product_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
        warranty_months = ProductMetadataBuilder._calculate_warranty_months(
            payload.get("warrantyStartDate"),
            payload.get("warrantyEndDate")
        )

        return {
            "product_id": payload.get("id"),
            "name": payload.get("name"),
            "brand": payload.get("brand"),
            "categories": [
                c.get("name")
                for c in payload.get("categories", [])
                if c.get("name")
            ],
            "avg_rating": payload.get("avgRating", 0),
            "warranty_months": warranty_months,
            "created_at": ProductMetadataBuilder._to_iso_date(payload.get("createAt")),
            "updated_at": ProductMetadataBuilder._to_iso_date(payload.get("updateAt")),
        }

    # =========================
    # Variant-level metadata
    # =========================

    @staticmethod
    def _build_variants_metadata(variants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = []

        for v in variants:
            results.append({
                "variant_id": v.get("id"),
                "sku": v.get("sku"),
                "color": v.get("color"),
                "storage": ProductMetadataBuilder._extract_storage(v.get("variantName")),
                "price": v.get("price"),
                "in_stock": bool(v.get("inStock", True))
            })

        return results

    # =========================
    # Stats metadata
    # =========================

    @staticmethod
    def _build_stats_metadata(variants_meta: List[Dict[str, Any]]) -> Dict[str, Any]:
        prices = [
            v["price"]
            for v in variants_meta
            if isinstance(v.get("price"), (int, float))
        ]

        if not prices:
            return {}

        return {
            "min_price": min(prices),
            "max_price": max(prices)
        }

    # =========================
    # Helpers
    # =========================

    @staticmethod
    def _extract_storage(variant_name: str) -> str:
        """
        Extract storage info from variant name: 256GB, 512GB...
        """
        if not variant_name:
            return None

        variant_name = variant_name.upper()
        for token in ["64GB", "128GB", "256GB", "512GB", "1TB"]:
            if token in variant_name:
                return token

        return None

    @staticmethod
    def _calculate_warranty_months(start: str, end: str) -> int:
        if not start or not end:
            return 0

        try:
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end)
            return (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
        except Exception:
            return 0

    @staticmethod
    def _to_iso_date(date_arr) -> str:
        """
        Convert [yyyy, mm, dd] -> yyyy-mm-dd
        """
        if not isinstance(date_arr, list) or len(date_arr) < 3:
            return None

        try:
            return f"{date_arr[0]:04d}-{date_arr[1]:02d}-{date_arr[2]:02d}"
        except Exception:
            return None

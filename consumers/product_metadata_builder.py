"""
Metadata builder for Vector DB upsert.
Used for filtering, ranking, variant selection.
"""

from typing import Dict, Any, List
from datetime import date
import json


class ProductMetadataBuilder:

    @classmethod
    def build(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        product_meta = cls._build_product_metadata(payload)
        variants_meta = cls._build_variants_metadata(payload.get("productVariants", []))
        stats_meta = cls._build_stats_metadata(variants_meta)

        return {"product": product_meta, "variants": variants_meta, "stats": stats_meta}

    @staticmethod
    def _build_product_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
        warranty_months = ProductMetadataBuilder._calculate_warranty_months(
            payload.get("warrantyStartDate"), payload.get("warrantyEndDate")
        )

        return {
            "product_id": payload.get("id"),
            "name": payload.get("name"),
            "brand": payload.get("brand"),
            "categories": [
                c.get("name") for c in payload.get("categories", []) if c.get("name")
            ],
            "avg_rating": payload.get("avgRating", 0),
            "warranty_months": warranty_months,
            "created_at": ProductMetadataBuilder._to_iso_date(payload.get("createAt")),
            "updated_at": ProductMetadataBuilder._to_iso_date(payload.get("updateAt")),
        }

    @staticmethod
    def _build_variants_metadata(
        variants: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        results = []

        for v in variants:
            results.append(
                {
                    "variant_id": v.get("id"),
                    "sku": v.get("sku"),
                    "color": v.get("color"),
                    "storage": ProductMetadataBuilder._extract_storage(
                        v.get("variantName")
                    ),
                    "price": v.get("price"),
                    "in_stock": bool(v.get("inStock", True)),
                }
            )

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

        return {"min_price": min(prices), "max_price": max(prices)}

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
            return (end_date.year - start_date.year) * 12 + (
                end_date.month - start_date.month
            )
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

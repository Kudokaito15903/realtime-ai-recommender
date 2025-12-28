"""
Variant Selection Service
Implements Layer 2 of the recommendation architecture:
- Takes product recommendations (product_id)
- Selects best variant for each product based on user preferences
"""

from typing import Dict, Any, List, Optional
from loguru import logger
from adapters.factory import get_product_store


class VariantSelector:
    """
    Selects the best variant for a product recommendation based on:
    - User's historical variant preferences (color, storage, price range)
    - Stock availability
    - Price similarity to user's typical purchases
    - Popular variants
    """

    def __init__(self):
        self.product_store = get_product_store()

    def select_best_variant(
        self,
        product_id: str,
        user_id: Optional[str] = None,
        user_history: Optional[List[Dict[str, Any]]] = None,
        price_range: Optional[tuple] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Select the best variant for a product recommendation.

        Args:
            product_id: The product ID
            user_id: Optional user ID for personalization
            user_history: Optional user interaction history (for learning preferences)
            price_range: Optional (min_price, max_price) tuple

        Returns:
            Best variant dict or None if no variants available
        """
        try:
            # Get product with variants
            product = self.product_store.get_product(product_id)
            if not product:
                return None

            variants = product.get("productVariants")
            if not variants or len(variants) == 0:
                # No variants, return product as-is
                return None

            # Extract user preferences from history
            preferences = (
                self._extract_user_preferences(user_id, user_history) if user_id else {}
            )

            # Score each variant
            scored_variants = []
            for variant in variants:
                score = self._score_variant(variant, preferences, price_range)
                scored_variants.append((variant, score))

            # Sort by score (highest first)
            scored_variants.sort(key=lambda x: x[1], reverse=True)

            if scored_variants:
                best_variant, best_score = scored_variants[0]
                logger.debug(
                    f"Selected variant {best_variant.get('sku')} for product {product_id} "
                    f"with score {best_score:.2f}"
                )
                return best_variant

            return None

        except Exception as e:
            logger.error(f"Error selecting variant for product {product_id}: {e}")
            return None

    def _extract_user_preferences(
        self, user_id: str, user_history: Optional[List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """
        Extract user preferences from interaction history.
        Looks for patterns in:
        - Colors (most clicked/purchased)
        - Storage capacity (most purchased)
        - Price range (typical purchase range)
        """
        preferences = {
            "colors": {},
            "storage_values": {},
            "price_range": None,
        }

        if not user_history:
            return preferences

        prices = []
        colors = []
        storage_values = []

        for interaction in user_history:
            # Get variant info if available
            variant_id = interaction.get("variant_id") or interaction.get("sku")
            if not variant_id:
                continue

            # Get product to find variant details
            product_id = interaction.get("product_id")
            if not product_id:
                continue

            product = self.product_store.get_product(product_id)
            if not product:
                continue

            variants = product.get("productVariants", [])
            for variant in variants:
                if variant.get("sku") == variant_id:
                    # Extract preferences
                    color = variant.get("color")
                    if color:
                        colors.append(color)
                        preferences["colors"][color] = (
                            preferences["colors"].get(color, 0) + 1
                        )

                    price = variant.get("price")
                    if price:
                        prices.append(price)

                    # Extract storage from bestSpecifications
                    best_specs = variant.get("bestSpecifications", [])
                    for spec in best_specs:
                        if spec.get("key", "").lower() == "storage":
                            storage = spec.get("value")
                            if storage:
                                storage_values.append(str(storage))
                                preferences["storage_values"][str(storage)] = (
                                    preferences["storage_values"].get(str(storage), 0)
                                    + 1
                                )
                    break

        # Calculate price range (median ± 20%)
        if prices:
            sorted_prices = sorted(prices)
            median_price = sorted_prices[len(sorted_prices) // 2]
            preferences["price_range"] = (
                median_price * 0.8,
                median_price * 1.2,
            )

        # Get most preferred color
        if preferences["colors"]:
            preferences["preferred_color"] = max(
                preferences["colors"].items(), key=lambda x: x[1]
            )[0]

        # Get most preferred storage
        if preferences["storage_values"]:
            preferences["preferred_storage"] = max(
                preferences["storage_values"].items(), key=lambda x: x[1]
            )[0]

        return preferences

    def _score_variant(
        self,
        variant: Dict[str, Any],
        preferences: Dict[str, Any],
        price_range: Optional[tuple] = None,
    ) -> float:
        """
        Score a variant based on user preferences.

        Scoring formula:
        final_score =
            color_match * 0.2
            + storage_match * 0.2
            + price_similarity * 0.3
            + stock_boost * 0.1
            + popularity_boost * 0.2
        """
        score = 0.0

        # Color match (0.2 weight)
        variant_color = variant.get("color", "").lower()
        preferred_color = preferences.get("preferred_color", "").lower()
        if variant_color and preferred_color and variant_color == preferred_color:
            score += 0.2

        # Storage match (0.2 weight)
        best_specs = variant.get("bestSpecifications", [])
        variant_storage = None
        for spec in best_specs:
            if spec.get("key", "").lower() == "storage":
                variant_storage = str(spec.get("value", "")).lower()
                break

        preferred_storage = preferences.get("preferred_storage", "").lower()
        if (
            variant_storage
            and preferred_storage
            and variant_storage == preferred_storage
        ):
            score += 0.2

        # Price similarity (0.3 weight)
        variant_price = variant.get("price", 0)
        user_price_range = price_range or preferences.get("price_range")
        if user_price_range and variant_price:
            min_price, max_price = user_price_range
            if min_price <= variant_price <= max_price:
                # Within range: score based on how close to center
                center = (min_price + max_price) / 2
                distance = abs(variant_price - center) / (max_price - min_price)
                score += 0.3 * (1 - distance)
            elif variant_price < min_price:
                # Below range: partial score
                score += 0.15
            # Above range: no score (too expensive)

        # Stock boost (0.1 weight) - assume in stock if no stock field
        # In real implementation, check actual stock
        stock = variant.get("stock", variant.get("inStock", True))
        if stock:
            score += 0.1

        # Popularity boost (0.2 weight) - could be based on sales data
        # For now, give base score
        score += 0.2

        return score

    def enrich_recommendations_with_variants(
        self,
        recommendations: List[Dict[str, Any]],
        user_id: Optional[str] = None,
        user_history: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Enrich product recommendations with selected variants.

        This implements the 2-layer architecture:
        Layer 1: Product recommendations (already done)
        Layer 2: Variant selection (this method)

        Args:
            recommendations: List of product recommendations with product_id
            user_id: Optional user ID for personalization
            user_history: Optional user interaction history

        Returns:
            Enriched recommendations with recommended_variant field
        """
        enriched = []

        for rec in recommendations:
            product_id = rec.get("product_id")
            if not product_id:
                continue

            # Select best variant
            best_variant = self.select_best_variant(
                product_id=product_id,
                user_id=user_id,
                user_history=user_history,
            )

            # Add variant info to recommendation
            enriched_rec = rec.copy()
            if best_variant:
                enriched_rec["recommended_variant"] = {
                    "sku": best_variant.get("sku"),
                    "variantName": best_variant.get("variantName"),
                    "color": best_variant.get("color"),
                    "price": best_variant.get("price"),
                }
            else:
                # No variant selected, get default (first variant or product price)
                product = self.product_store.get_product(product_id)
                if product and product.get("productVariants"):
                    first_variant = product["productVariants"][0]
                    enriched_rec["recommended_variant"] = {
                        "sku": first_variant.get("sku"),
                        "variantName": first_variant.get("variantName"),
                        "color": first_variant.get("color"),
                        "price": first_variant.get("price"),
                    }

            enriched.append(enriched_rec)

        return enriched


# Singleton accessor
_variant_selector_instance = None


def get_variant_selector() -> VariantSelector:
    """Get the singleton VariantSelector instance"""
    global _variant_selector_instance
    if _variant_selector_instance is None:
        _variant_selector_instance = VariantSelector()
    return _variant_selector_instance

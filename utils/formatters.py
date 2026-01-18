"""
Additional formatters for Policy and CSKH responses
"""

from typing import List, Dict, Any, Optional


def _calculate_discount(price_avg: float, price_max: float) -> int:
    """
    Calculate discount percentage.
    
    Args:
        price_avg: Average/current price
        price_max: Original/maximum price
        
    Returns:
        Discount percentage (0-100)
    """
    if not price_max or price_max <= 0:
        return 0
    
    if not price_avg or price_avg >= price_max:
        return 0
    
    discount = ((price_max - price_avg) / price_max) * 100
    return int(round(discount))


def _get_product_badges(product: Dict[str, Any]) -> List[str]:
    """
    Get product badges based on product attributes.
    
    Args:
        product: Product dict
        
    Returns:
        List of badge labels
    """
    badges = []
    
    # New product badge
    if product.get("is_new", False):
        badges.append("Mới")
    
    # Best seller badge
    if product.get("is_bestseller", False) or product.get("sales_count", 0) > 1000:
        badges.append("Bán chạy")
    
    # Discount badge
    price_avg = product.get("price_avg", 0)
    price_max = product.get("price_max", 0)
    if price_max and price_avg < price_max:
        discount = _calculate_discount(price_avg, price_max)
        if discount >= 20:
            badges.append(f"Giảm {discount}%")
    
    # High rating badge
    rating = product.get("avg_rating", 0)
    if rating >= 4.5:
        badges.append("Đánh giá cao")
    
    # Limited stock badge
    if product.get("in_stock", True) and product.get("stock_quantity", 0) < 10:
        badges.append("Sắp hết hàng")
    
    return badges[:3]  # Limit to 3 badges


def format_product_info_response(
    message: str, products: List[Dict[str, Any]], sources: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Format product info response.

    Args:
        message: Generated response text
        products: List of product dicts
        sources: List of retrieved chunks

    Returns:
        Formatted response dict
    """
    # Format product cards
    product_cards = []
    for product in products[:3]:  # Max 3 products
        product_cards.append(
            {
                "id": product.get("id"),
                "name": product.get("name"),
                "brand": product.get("brand"),
                "price": product.get("price_avg") or product.get("listPrice", 0),
                "original_price": product.get("price_max") or product.get("originalPrice"),
                "discount_percent": _calculate_discount(
                    product.get("price_avg") or product.get("listPrice", 0), 
                    product.get("price_max") or product.get("originalPrice", 0)
                ),
                "image": product.get("thumbnail") or (product.get("images") and product.get("images")[0]),
                "url": f"/products/{product.get('id')}",
                "colors": product.get("available_colors", []),
                "rating": product.get("avg_rating", 0.0),
                "review_count": product.get("review_count", 0),
                "in_stock": product.get("in_stock", True),
                "badges": _get_product_badges(product),
            }
        )

    # Format sources
    source_refs = []
    for source in sources[:3]:
        source_refs.append(
            {
                "chunk_id": source.get("chunk_id"),
                "chunk_type": source.get("chunk_type"),
                "relevance_score": round(source.get("score", 0), 2),
                "text_preview": source.get("text", "")[:100] + "...",
            }
        )

    # Quick actions
    quick_actions = [
        (
            {
                "label": "Xem chi tiết",
                "action": "view_product",
                "product_id": product_cards[0]["id"],
            }
            if product_cards
            else None
        ),
        (
            {"label": "So sánh sản phẩm", "action": "compare"}
            if len(product_cards) >= 2
            else None
        ),
        {"label": "Thêm vào giỏ", "action": "add_to_cart"} if product_cards else None,
        (
            {"label": "Tìm sản phẩm tương tự", "action": "find_similar"}
            if product_cards
            else None
        ),
    ]
    quick_actions = [qa for qa in quick_actions if qa]  # Remove None

    return {
        "type": "product_info",
        "message": message,
        "products": product_cards,
        "sources": source_refs,
        "quick_actions": quick_actions,
    }


def format_comparison_response(
    message: str, products: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Format comparison response with table.
    """
    # Build comparison table
    specs_to_compare = [
        {"label": "CPU", "key": "cpu"},
        {"label": "RAM", "key": "ram_gb", "suffix": "GB"},
        {"label": "Bộ nhớ", "key": "storage_gb", "suffix": "GB"},
        {"label": "Màn hình", "key": "screen_size_inch", "suffix": "inch"},
        {"label": "Loại màn hình", "key": "screen_type"},
        {"label": "Camera", "key": "camera_mp", "suffix": "MP"},
        {"label": "Pin", "key": "battery_hours", "suffix": "giờ"},
        {"label": "Giá", "key": "price_avg", "format": "currency"},
    ]

    comparison_table = []
    for spec in specs_to_compare:
        row = {"spec": spec["label"], "values": []}

        for product in products:
            specs_norm = product.get("specs_normalized", {})
            price_info = product.get("price_info", {})

            # Get value
            if spec["key"] == "price_avg":
                value = price_info.get("price_avg") or product.get("listPrice", 0)
            else:
                value = specs_norm.get(spec["key"], "N/A")

            # Format value
            if spec.get("format") == "currency":
                value = f"{value:,}đ"
            elif spec.get("suffix"):
                value = f"{value}{spec['suffix']}"

            row["values"].append(value)

        comparison_table.append(row)

    # Format product cards
    product_cards = []
    for product in products:
        product_id = product.get("id") or product.get("product_id")
        product_name = product.get("name") or product.get("product_name")
        price_info = product.get("price_info", {}) or {}
        engagement_metrics = product.get("engagement_metrics", {}) or {}
        availability = product.get("availability", {}) or {}
        
        product_cards.append(
            {
                "id": product_id,
                "name": product_name,
                "brand": product.get("brand"),
                "price": price_info.get("price_avg") or product.get("price_avg") or product.get("listPrice", 0),
                "image": product.get("thumbnail"),
                "url": f"/products/{product_id}",
                "rating": engagement_metrics.get("avg_rating") or product.get("avg_rating", 0),
                "in_stock": availability.get("in_stock") if availability else product.get("in_stock", True),
            }
        )

    # Quick actions
    quick_actions = [
        {
            "label": "Xem chi tiết",
            "action": "view_product",
            "product_id": products[0].get("id") or products[0].get("product_id"),
        }
        if products else None,
        {"label": "So sánh sản phẩm", "action": "compare"},
        {"label": "Thêm vào giỏ", "action": "add_to_cart"},
        {"label": "Tìm sản phẩm tương tự", "action": "find_similar"},
    ]
    quick_actions = [qa for qa in quick_actions if qa]  # Remove None

    return {
        "type": "compare",
        "message": message,
        "comparison": {"products": product_cards, "table": comparison_table},
        "quick_actions": quick_actions,
    }


def format_policy_response(
    message: str, policy_type: Optional[str], sources: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Format policy response.

    Args:
        message: Generated response text
        policy_type: Type of policy (warranty, return, shipping, payment)
        sources: Retrieved policy chunks

    Returns:
        Formatted response dict
    """
    # Policy-specific quick actions
    policy_actions = {
        "warranty": [
            {"label": "Yêu cầu bảo hành", "action": "request_warranty"},
            {"label": "Tìm trung tâm bảo hành", "action": "find_service_center"},
        ],
        "return": [
            {"label": "Yêu cầu đổi trả", "action": "request_return"},
            {
                "label": "Kiểm tra điều kiện đổi trả",
                "action": "check_return_eligibility",
            },
        ],
        "shipping": [
            {"label": "Tính phí giao hàng", "action": "calculate_shipping"},
            {"label": "Xem thời gian giao", "action": "check_delivery_time"},
        ],
        "payment": [
            {"label": "Xem hướng dẫn thanh toán", "action": "payment_guide"},
            {"label": "Đăng ký trả góp", "action": "installment_register"},
        ],
    }

    quick_actions = policy_actions.get(policy_type, [])
    quick_actions.append({"label": "Liên hệ CSKH", "action": "contact_support"})

    # Format sources
    source_refs = []
    for source in sources[:2]:
        source_refs.append(
            {
                "policy_type": source.get("metadata", {}).get("policy_type"),
                "relevance_score": round(source.get("score", 0), 2),
            }
        )

    return {
        "type": "policy",
        "policy_type": policy_type,
        "message": message,
        "sources": source_refs,
        "quick_actions": quick_actions,
    }


def format_cskh_response(
    message: str, topic: Optional[str], sources: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Format CSKH response.

    Args:
        message: Generated response text
        topic: CSKH topic
        sources: Retrieved knowledge chunks

    Returns:
        Formatted response dict
    """
    # Topic-specific quick actions
    topic_actions = {
        "order_tracking": [
            {"label": "Kiểm tra đơn hàng", "action": "track_order"},
            {"label": "Xem lịch sử đơn hàng", "action": "view_order_history"},
        ],
        "account_management": [
            {"label": "Đặt lại mật khẩu", "action": "reset_password"},
            {"label": "Cập nhật thông tin", "action": "update_profile"},
        ],
        "order_cancellation": [
            {"label": "Hủy đơn hàng", "action": "cancel_order"},
            {"label": "Xem chính sách hoàn tiền", "action": "view_refund_policy"},
        ],
        "address_management": [
            {"label": "Thêm địa chỉ mới", "action": "add_address"},
            {"label": "Quản lý địa chỉ", "action": "manage_addresses"},
        ],
        "contact_support": [
            {
                "label": "Gọi hotline: 1900xxxx",
                "action": "call_hotline",
                "phone": "1900xxxx",
            },
            {"label": "Chat trực tiếp", "action": "live_chat"},
            {
                "label": "Gửi email",
                "action": "send_email",
                "email": "support@example.com",
            },
        ],
    }

    quick_actions = topic_actions.get(
        topic, [{"label": "Liên hệ CSKH", "action": "contact_support"}]
    )

    return {
        "type": "cskh",
        "topic": topic,
        "message": message,
        "quick_actions": quick_actions,
    }

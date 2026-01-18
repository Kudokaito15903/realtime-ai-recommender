
import sys
import os
import time
import uuid
import random
import json
from loguru import logger

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.factory import get_product_store, get_product_event_processor
from services.content_service import ContentService

# ==========================================
# 1. CONTENT DATA (Policies, FAQ)
# ==========================================

SAMPLE_CONTENT = [
    {
        "title": "Chính sách bảo hành vàng",
        "category": "Policy",
        "content": """
        1. Thời gian bảo hành:
            - iPhone/iPad: 12 tháng chính hãng + 12 tháng mở rộng (tổng 24 tháng).
            - Macbook: 12 tháng chính hãng.
            - Phụ kiện: 6 tháng 1 đổi 1.
            
        2. Điều kiện bảo hành:
            - Máy không rơi vỡ, cấn móp, vào nước.
            - Còn nguyên tem bảo hành (với máy cũ).
            - Có phiếu bảo hành hoặc hóa đơn mua hàng.
            
        3. Đặc quyền bảo hành vàng:
            - Thay pin miễn phí 1 lần trong năm đầu (nếu chai < 80%).
            - Hỗ trợ cài đặt phần mềm trọn đời máy.
            - Vệ sinh máy miễn phí định kỳ 3 tháng/lần.
        """,
        "tags": ["warranty", "policy", "bảo hành", "apple", "iphone"],
        "status": "published",
    },
    {
        "title": "Chính sách đổi trả 30 ngày",
        "category": "Policy",
        "content": """
        1. Đổi mới miễn phí trong 30 ngày đầu nếu:
            - Sản phẩm có lỗi từ nhà sản xuất (màn hình, main, nguồn...).
            - Sản phẩm không đúng mô tả.
            
        2. Đổi trả theo nhu cầu (không lỗi):
            - Thu phí 15% giá trị máy trong 15 ngày đầu.
            - Thu phí 20% giá trị máy từ ngày 16-30.
            
        3. Yêu cầu:
            - Máy còn như mới, không trầy xước.
            - Còn đầy đủ hộp, phụ kiện đi kèm.
        """,
        "tags": ["return", "refund", "policy", "đổi trả"],
        "status": "published",
    },
    {
        "title": "Hỗ trợ trả góp 0%",
        "category": "FAQ",
        "content": """
        Chúng tôi hỗ trợ trả góp qua 2 hình thức:
        
        1. Trả góp qua thẻ tín dụng (Visa/Mastercard):
            - Lãi suất: 0%.
            - Phí chuyển đổi: Tùy ngân hàng (thường 2-3%).
            - Kỳ hạn: 3, 6, 9, 12 tháng.
            - Không cần trả trước.
            
        2. Trả góp qua công ty tài chính (Home Credit, HD Saison):
            - Yêu cầu: CMND/CCCD + Bằng lái xe/Hộ khẩu.
            - Trả trước: Từ 30% giá trị máy.
            - Lãi suất: Thấp nhất từ 1.8%/tháng.
        """,
        "tags": ["installment", "payment", "faq", "trả góp"],
        "status": "published",
    }
]

# ==========================================
# 2. PRODUCT DATA (Rich Specs)
# ==========================================

def create_specs(category, variant="standard"):
    if category == "Smartphone":
        if variant == "pro_max":
            return [
                {"key": "CPU", "value": "Apple A17 Pro (3nm)", "group": "Performance"},
                {"key": "RAM", "value": "8GB", "group": "RAM"},
                {"key": "Dung lượng", "value": "256GB/512GB/1TB", "group": "Storage"},
                {"key": "Màn hình", "value": "6.7 inch Super Retina XDR OLED", "group": "Display"},
                {"key": "Tần số quét", "value": "120Hz ProMotion", "group": "Display"},
                {"key": "Camera sau", "value": "48MP + 12MP + 12MP (Zoom 5x)", "group": "Camera"},
                {"key": "Camera trước", "value": "12MP TrueDepth", "group": "Camera"},
                {"key": "Pin", "value": "4422 mAh", "group": "Battery"},
                {"key": "Sạc", "value": "Nhanh 20W, MagSafe 15W", "group": "Battery"},
                {"key": "Chất liệu", "value": "Khung Titan, Mặt lưng kính nhám", "group": "Design"},
            ]
        else:
             return [
                {"key": "CPU", "value": "Snapdragon 8 Gen 3", "group": "Performance"},
                {"key": "RAM", "value": "12GB", "group": "RAM"},
                {"key": "Dung lượng", "value": "256GB/512GB", "group": "Storage"},
                {"key": "Màn hình", "value": "6.2 inch Dynamic AMOLED 2X", "group": "Display"},
                {"key": "Tần số quét", "value": "120Hz", "group": "Display"},
                {"key": "Camera sau", "value": "50MP + 10MP + 12MP", "group": "Camera"},
                {"key": "Pin", "value": "4000 mAh", "group": "Battery"},
            ]
            
    elif category == "Laptop":
        if variant == "macbook":
             return [
                {"key": "CPU", "value": "Apple M3 Chip (8-core CPU)", "group": "Performance"},
                {"key": "GPU", "value": "Apple M3 GPU (10-core)", "group": "Graphic"},
                {"key": "RAM", "value": "16GB Unified Memory", "group": "RAM"},
                {"key": "SSD", "value": "512GB NVMe", "group": "Storage"},
                {"key": "Màn hình", "value": "13.6 inch Liquid Retina", "group": "Display"},
                {"key": "Pin", "value": "Lên đến 18 giờ", "group": "Battery"},
                {"key": "Trọng lượng", "value": "1.24 kg", "group": "Design"},
                {"key": "OS", "value": "macOS Sonoma", "group": "OperatingSystem"},
            ]
        else:
            return [
                {"key": "CPU", "value": "Intel Core i7-1360P", "group": "Performance"},
                {"key": "GPU", "value": "Intel Iris Xe Graphics", "group": "Graphic"},
                {"key": "RAM", "value": "16GB LPDDR5", "group": "RAM"},
                {"key": "SSD", "value": "1TB PCIe 4.0", "group": "Storage"},
                {"key": "Màn hình", "value": "13.4 inch FHD+ InfinityEdge", "group": "Display"},
                {"key": "Pin", "value": "55Wh", "group": "Battery"},
                {"key": "Trọng lượng", "value": "1.17 kg", "group": "Design"},
                {"key": "OS", "value": "Windows 11 Home", "group": "OperatingSystem"},
            ]
    return []

PRODUCTS = [
    {
        "id": "PROD_IP15PM",
        "name": "iPhone 15 Pro Max",
        "brand": "Apple",
        "description": "iPhone 15 Pro Max - Titan tự nhiên. Chip A17 Pro mạnh mẽ nhất. Nút tác vụ hoàn toàn mới. Camera Zoom quang học 5x.",
        "categories": [{"id": "smartphone", "name": "Smartphone"}],
        "listPrice": 34990000,
        "specifications": create_specs("Smartphone", "pro_max"),
        "warranty": "12 tháng chính hãng",
    },
    {
        "id": "PROD_S24",
        "name": "Samsung Galaxy S24",
        "brand": "Samsung",
        "description": "Galaxy S24 với Galaxy AI. Quyền năng AI trong tay bạn. Thiết kế vuông vức thời thượng, màn hình viền mỏng nhất từ trước đến nay.",
        "categories": [{"id": "smartphone", "name": "Smartphone"}],
        "listPrice": 22990000,
        "specifications": create_specs("Smartphone", "standard"),
        "warranty": "12 tháng chính hãng",
    },
    {
        "id": "PROD_MAC_M3",
        "name": "MacBook Air 13 M3",
        "brand": "Apple",
        "description": "MacBook Air M3. Siêu mỏng. Siêu nhanh. Siêu mạnh. Hoàn hảo cho công việc và học tập với thời lượng pin cả ngày dài.",
        "categories": [{"id": "laptop", "name": "Laptop"}],
        "listPrice": 27990000,
        "specifications": create_specs("Laptop", "macbook"),
        "warranty": "12 tháng chính hãng",
    },
    {
        "id": "PROD_DELL_XPS",
        "name": "Dell XPS 13 Plus",
        "brand": "Dell",
        "description": "Dell XPS 13 Plus 9320. Tuyệt tác thiết kế tương lai. Bàn phím tràn viền, Touchbar cảm ứng, màn hình vô cực.",
        "categories": [{"id": "laptop", "name": "Laptop"}],
        "listPrice": 45990000,
        "specifications": create_specs("Laptop", "windows"),
        "warranty": "12 tháng ProSupport",
    }
]

def run_integration():
    logger.info("🚀 STARTING CHATBOT TEST DATA GENERATION")
    
    # 1. Generate Content
    content_service = ContentService()
    logger.info("--- Generating Content ---")
    for item in SAMPLE_CONTENT:
        try:
            cid = content_service.create_content(item)
            logger.info(f"✅ Created Content: {item['title']} (ID: {cid})")
        except Exception as e:
            logger.error(f"❌ Failed Content {item['title']}: {e}")
            
    # 2. Generate Products
    # Ensure fresh start for verification
    product_store = get_product_store()
    event_processor = get_product_event_processor()
    
    logger.info("\n--- Generating Products ---")
    
    for prod in PRODUCTS:
        try:
            # Upsert DB
            pid = product_store.store_product(prod)
            
            # Publish Event (to trigger embeddings)
            event_data = {
                "event_type": "upsert",
                "entity_id": prod["id"],
                "timestamp": time.time(),
                "data": prod
            }
            publish_result = event_processor.publish_event(event_data)
            
            if publish_result:
                logger.info(f"✅ Published Event for {prod['name']}: {publish_result}")
            else:
                logger.warning(f"⚠️ Failed to publish event for {prod['name']}")
            
            logger.info(f"✅ Created Product: {prod['name']} (ID: {prod['id']})")
            time.sleep(1.0) # increased wait time for stability
        except Exception as e:
            logger.error(f"❌ Failed Product {prod['name']}: {e}")

    logger.info("\n🎉 DONE! Data generated successfully.")

if __name__ == "__main__":
    run_integration()

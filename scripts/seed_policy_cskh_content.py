"""
Script để seed policy và CSKH content vào hệ thống
Chạy script này để thêm sample content cho chatbot
"""

from services.content_service import ContentService
from loguru import logger


def seed_policy_content():
    """Thêm policy content mẫu"""
    content_service = ContentService()
    
    policies = [
        {
            "id": "policy-warranty",
            "title": "Chính sách bảo hành sản phẩm",
            "content": """## Chính sách bảo hành sản phẩm

### 1. Thời gian bảo hành
- **Điện thoại, Laptop**: 12 tháng kể từ ngày mua
- **Phụ kiện điện tử**: 6 tháng
- **Đồng hồ, Phụ kiện khác**: 3-6 tháng tùy loại

### 2. Điều kiện bảo hành
- Còn nguyên tem bảo hành của hãng
- Không bị va đập, rơi, nước vào
- Còn hóa đơn mua hàng hoặc phiếu bảo hành
- Lỗi do nhà sản xuất, không phải do người dùng

### 3. Quy trình bảo hành
1. Liên hệ hotline: **1900xxxx** hoặc chat với CSKH
2. Cung cấp mã đơn hàng và mô tả lỗi
3. Mang sản phẩm + hóa đơn đến trung tâm bảo hành
4. Thời gian xử lý: **3-5 ngày làm việc**

### 4. Không được bảo hành
- Hết thời hạn bảo hành
- Lỗi do người dùng (rơi, nước, va đập)
- Tem bảo hành bị rách, mất
- Sửa chữa ở nơi không được ủy quyền""",
            "category": "policy",
            "tags": ["warranty", "bảo hành", "sửa chữa"],
            "status": "published",
        },
        {
            "id": "policy-return",
            "title": "Chính sách đổi trả hàng",
            "content": """## Chính sách đổi trả hàng

### 1. Thời gian đổi trả
- **Đổi hàng**: Trong vòng 7 ngày kể từ ngày nhận hàng
- **Hoàn tiền**: Trong vòng 3 ngày nếu sản phẩm chưa sử dụng

### 2. Điều kiện đổi trả
- Sản phẩm còn nguyên seal, chưa qua sử dụng
- Còn đầy đủ hộp, phụ kiện, hóa đơn
- Không có dấu hiệu hư hỏng, trầy xước
- Có lý do chính đáng (sai mẫu, lỗi kỹ thuật)

### 3. Quy trình đổi trả
1. Liên hệ CSKH qua hotline hoặc chat
2. Cung cấp mã đơn hàng và lý do đổi trả
3. Gửi ảnh/video sản phẩm (nếu có lỗi)
4. Gửi hàng về kho (chúng tôi hỗ trợ phí ship)
5. Kiểm tra và xử lý trong 3-5 ngày

### 4. Các trường hợp không được đổi trả
- Quá thời hạn 7 ngày
- Đã sử dụng, mất seal
- Hư hỏng do người dùng
- Không còn đầy đủ phụ kiện""",
            "category": "policy",
            "tags": ["return", "đổi trả", "hoàn tiền", "refund"],
            "status": "published",
        },
        {
            "id": "policy-shipping",
            "title": "Chính sách giao hàng",
            "content": """## Chính sách giao hàng

### 1. Phí giao hàng
- **Miễn phí**: Đơn hàng từ 500.000đ
- **Có phí**: 30.000đ cho đơn hàng dưới 500.000đ
- **Giao nhanh (2-4h)**: 50.000đ (chỉ HCM, Hà Nội)

### 2. Thời gian giao hàng
- **Nội thành**: 1-2 ngày làm việc
- **Ngoại thành**: 2-5 ngày làm việc
- **Vùng sâu, vùng xa**: 5-7 ngày làm việc

### 3. Hình thức giao hàng
- **COD** (Thanh toán khi nhận hàng)
- **Chuyển khoản trước** (giao hàng nhanh hơn)
- **Ví điện tử** (Momo, ZaloPay)

### 4. Theo dõi đơn hàng
- Nhận mã vận đơn qua SMS/Email
- Kiểm tra trạng thái trên website
- Hoặc chat với bot: "Kiểm tra đơn hàng #MÃ_ĐƠN" """,
            "category": "policy",
            "tags": ["shipping", "giao hàng", "vận chuyển", "delivery"],
            "status": "published",
        },
        {
            "id": "policy-payment",
            "title": "Phương thức thanh toán",
            "content": """## Phương thức thanh toán

### 1. Thanh toán online
- **Ví điện tử**: Momo, ZaloPay, ShopeePay
- **Thẻ tín dụng/ghi nợ**: Visa, Mastercard
- **Internet Banking**: 40+ ngân hàng
- **QR Code**: Quét QR để thanh toán nhanh

### 2. Thanh toán khi nhận hàng (COD)
- Thanh toán bằng tiền mặt
- Chỉ áp dụng cho đơn hàng dưới 5.000.000đ
- Phí COD: 30.000đ

### 3. Trả góp
- **Trả góp 0% lãi suất** qua thẻ tín dụng
- Kỳ hạn: 3, 6, 9, 12 tháng
- Hỗ trợ: Fe Credit, Home Credit

### 4. Bảo mật thanh toán
- Mã hóa SSL 256-bit
- Không lưu trữ thông tin thẻ
- Tuân thủ chuẩn PCI DSS""",
            "category": "policy",
            "tags": ["payment", "thanh toán", "cod", "trả góp"],
            "status": "published",
        },
    ]
    
    created_count = 0
    for policy in policies:
        try:
            content_id = content_service.create_content(policy)
            logger.info(f"✅ Created policy: {content_id} - {policy['title']}")
            created_count += 1
        except Exception as e:
            logger.error(f"❌ Failed to create policy {policy['id']}: {e}")
    
    logger.info(f"📊 Created {created_count}/{len(policies)} policies")
    return created_count


def seed_cskh_content():
    """Thêm CSKH knowledge mẫu"""
    content_service = ContentService()
    
    cskh_knowledge = [
        {
            "id": "cskh-order-tracking",
            "title": "Cách kiểm tra đơn hàng",
            "content": """## Hướng dẫn kiểm tra đơn hàng

### Cách 1: Qua Website
1. Đăng nhập tài khoản của bạn
2. Vào **"Đơn hàng của tôi"**
3. Chọn đơn hàng cần kiểm tra
4. Xem chi tiết: trạng thái, mã vận đơn, thời gian giao

### Cách 2: Qua Chatbot
Nhắn tin với bot: **"Kiểm tra đơn hàng #MÃ_ĐƠN"**

Ví dụ: "Kiểm tra đơn hàng #ORD20240101001"

### Cách 3: Hotline
Gọi **1900xxxx** và cung cấp mã đơn hàng

### Trạng thái đơn hàng
- **Pending**: Đang chờ xác nhận
- **Confirmed**: Đã xác nhận, đang chuẩn bị
- **Processing**: Đang đóng gói
- **Shipping**: Đang giao hàng
- **Delivered**: Đã giao hàng thành công""",
            "category": "cskh",
            "tags": ["order_tracking", "kiểm tra đơn hàng", "đơn hàng"],
            "status": "published",
        },
        {
            "id": "cskh-account-management",
            "title": "Quản lý tài khoản",
            "content": """## Hướng dẫn quản lý tài khoản

### Đặt lại mật khẩu
1. Vào trang đăng nhập
2. Click **"Quên mật khẩu"**
3. Nhập email/SĐT đã đăng ký
4. Nhận mã OTP qua email/SMS
5. Nhập mã OTP và đặt mật khẩu mới

### Cập nhật thông tin
1. Đăng nhập tài khoản
2. Vào **"Thông tin cá nhân"**
3. Cập nhật: Họ tên, Email, SĐT
4. Lưu thay đổi

### Quản lý địa chỉ giao hàng
1. Vào **"Địa chỉ giao hàng"**
2. Thêm/Sửa/Xóa địa chỉ
3. Đặt địa chỉ mặc định""",
            "category": "cskh",
            "tags": ["account_management", "tài khoản", "mật khẩu", "quên mật khẩu"],
            "status": "published",
        },
        {
            "id": "cskh-contact-support",
            "title": "Liên hệ hỗ trợ",
            "content": """## Liên hệ hỗ trợ khách hàng

### Hotline
📞 **1900xxxx** (8h-22h hàng ngày)

### Email
📧 **support@example.com**

### Live Chat
💬 Chat trực tiếp trên website (24/7)

### Văn phòng
📍 **123 Đường ABC, Quận XYZ, TP.HCM**

### Thời gian hỗ trợ
- **Hotline**: 8h-22h hàng ngày
- **Live Chat**: 24/7
- **Email**: Phản hồi trong 24h""",
            "category": "cskh",
            "tags": ["contact_support", "liên hệ", "hotline", "hỗ trợ"],
            "status": "published",
        },
    ]
    
    created_count = 0
    for knowledge in cskh_knowledge:
        try:
            content_id = content_service.create_content(knowledge)
            logger.info(f"✅ Created CSKH: {content_id} - {knowledge['title']}")
            created_count += 1
        except Exception as e:
            logger.error(f"❌ Failed to create CSKH {knowledge['id']}: {e}")
    
    logger.info(f"📊 Created {created_count}/{len(cskh_knowledge)} CSKH knowledge")
    return created_count


if __name__ == "__main__":
    logger.info("🌱 Starting content seeding...")
    
    policy_count = seed_policy_content()
    cskh_count = seed_cskh_content()
    
    logger.info(f"✅ Done! Created {policy_count} policies and {cskh_count} CSKH knowledge")

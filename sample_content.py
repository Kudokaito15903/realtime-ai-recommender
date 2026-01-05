import sys
import os
import time

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.content_service import ContentService
from loguru import logger

def generate_sample_content():
    """
    Generate sample content (FAQ, Policies, Guides) for the Chatbot RAG system.
    """
    service = ContentService()
    
    # Danh sách nội dung mẫu (Tiếng Việt)
    samples = [
        {
            "title": "Chính sách vận chuyển và giao hàng",
            "category": "Policy",
            "content": """
            1. Thời gian giao hàng:
               - Nội thành Hà Nội & TP.HCM: 1-2 ngày làm việc.
               - Các tỉnh thành khác: 3-5 ngày làm việc.
               
            2. Phí vận chuyển:
               - Miễn phí vận chuyển cho đơn hàng từ 500.000đ trở lên.
               - Đơn hàng dưới 500.000đ: Phí đồng giá 30.000đ.
               
            3. Đối tác vận chuyển: Chúng tôi hợp tác với Giao Hàng Nhanh (GHN), Viettel Post và J&T Express.
            """,
            "tags": ["shipping", "delivery", "policy", "giao hàng"],
            "status": "published"
        },
        {
            "title": "Chính sách đổi trả và hoàn tiền",
            "category": "Policy",
            "content": """
            Chúng tôi cam kết quyền lợi của khách hàng với chính sách đổi trả minh bạch:
            
            1. Điều kiện đổi trả:
               - Sản phẩm còn nguyên tem mác, chưa qua sử dụng.
               - Yêu cầu đổi trả được gửi trong vòng 30 ngày kể từ ngày nhận hàng.
               - Có video quay lại quá trình mở hộp (khuyến khích).
               
            2. Quy trình đổi trả:
               - Bước 1: Liên hệ CSKH qua hotline hoặc chat.
               - Bước 2: Gửi sản phẩm về kho của chúng tôi.
               - Bước 3: Chúng tôi kiểm tra và hoàn tiền hoặc gửi sản phẩm mới trong 3 ngày làm việc.
            """,
            "tags": ["return", "refund", "policy", "đổi trả"],
            "status": "published"
        },
        {
            "title": "Hướng dẫn phương thức thanh toán",
            "category": "Guide",
            "content": """
            Chúng tôi hỗ trợ đa dạng các phương thức thanh toán:
            
            1. Thanh toán khi nhận hàng (COD): Áp dụng cho mọi đơn hàng.
            2. Chuyển khoản ngân hàng:
               - Ngân hàng: Vietcombank
               - STK: 99998888
               - Chủ TK: REALTIME AI SHOP
            3. Ví điện tử: Momo, Zalopay, VNPay.
            4. Thẻ tín dụng/ghi nợ quốc tế (Visa/Mastercard).
            """,
            "tags": ["payment", "guide", "thanh toán", "banking"],
            "status": "published"
        },
        {
            "title": "Làm sao để theo dõi đơn hàng?",
            "category": "FAQ",
            "content": """
            Để theo dõi đơn hàng của bạn:
            1. Đăng nhập vào tài khoản trên website/app.
            2. Vào mục "Đơn hàng của tôi" (My Orders).
            3. Chọn đơn hàng muốn kiểm tra.
            4. Mã vận đơn sẽ được hiển thị kèm theo trạng thái giao hàng hiện tại.
            
            Ngoài ra, bạn sẽ nhận được email/SMS thông báo khi trạng thái đơn hàng thay đổi.
            """,
            "tags": ["tracking", "order", "faq", "đơn hàng"],
            "status": "published"
        },
        {
            "title": "Chính sách bảo hành sản phẩm",
            "category": "Policy",
            "content": """
            Tất cả sản phẩm điện tử bán ra đều được bảo hành chính hãng.
            
            - Thời gian bảo hành: 12 tháng kể từ ngày kích hoạt hoặc ngày mua.
            - Địa điểm bảo hành: Tại các trung tâm bảo hành ủy quyền của hãng hoặc gửi về trung tâm hỗ trợ của chúng tôi.
            - Điều kiện: Lỗi do nhà sản xuất. Không bao gồm lỗi do người dùng (rơi vỡ, vào nước, tự ý tháo lắp).
            """,
            "tags": ["warranty", "policy", "bảo hành"],
            "status": "published"
        },
        {
            "title": "Liên hệ hỗ trợ khách hàng",
            "category": "General",
            "content": """
            Kênh hỗ trợ khách hàng (hoạt động 8:00 - 22:00 hàng ngày):
            
            - Hotline: 1900 1234
            - Email: support@realtime-ai-shop.vn
            - Live Chat: Tại góc phải màn hình website.
            - Địa chỉ văn phòng: Tòa nhà Bitexco, Q1, TP.HCM.
            """,
            "tags": ["support", "contact", "liên hệ", "cskh"],
            "status": "published"
        },
        {
            "title": "Hướng dẫn chọn size quần áo",
            "category": "Guide",
            "content": """
            Bảng quy đổi size tham khảo (Form chuẩn):
            
            - Size S: 1m50 - 1m60, 45-50kg
            - Size M: 1m60 - 1m65, 51-58kg
            - Size L: 1m65 - 1m72, 59-68kg
            - Size XL: 1m72 - 1m78, 69-78kg
            - Size XXL: > 1m78, > 78kg
            
            Lưu ý: Nếu bạn có vòng bụng lớn hoặc thích mặc rộng thoải mái, hãy chọn lớn hơn 1 size.
            """,
            "tags": ["size", "guide", "clothing", "kích thước"],
            "status": "published"
        },
        {
            "title": "Quy định về bảo mật thông tin",
            "category": "Policy",
            "content": """
            Chúng tôi cam kết bảo mật tuyệt đối thông tin cá nhân của khách hàng.
            
            - Thông tin thu thập: Tên, SĐT, Địa chỉ, Email (chỉ dùng để xử lý đơn hàng).
            - Không chia sẻ thông tin cho bên thứ 3 trừ các đơn vị vận chuyển.
            - Hệ thống thanh toán được mã hóa chuẩn quốc tế.
            """,
            "tags": ["privacy", "security", "bảo mật"],
            "status": "published"
        }
    ]
    
    logger.info(f"🚀 Bắt đầu tạo {len(samples)} nội dung mẫu cho Chatbot...")
    
    success_count = 0
    for item in samples:
        try:
            content_id = service.create_content(item)
            logger.info(f"✅ Đã tạo: {item['title']} (ID: {content_id})")
            success_count += 1
            time.sleep(0.05) 
        except Exception as e:
            logger.error(f"❌ Lỗi khi tạo {item['title']}: {e}")

    logger.info(f"🎉 Hoàn tất! Đã tạo {success_count}/{len(samples)} nội dung.")

if __name__ == "__main__":
    generate_sample_content()

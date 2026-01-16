# Luồng Hoạt Động Chatbot AI (Updated)

## Tổng Quan

Chatbot sử dụng kiến trúc RAG (Retrieval Augmented Generation) tiên tiến với Google GenAI (Gemini 2.0 Flash). Hệ thống được tối ưu hóa cho độ chính xác cao, khả năng tự sửa lỗi và xử lý linh hoạt các tình huống phức tạp.

**Capabilities:**
- **Thông tin sản phẩm**: Trả lời chi tiết, so sánh, thông số kỹ thuật.
- **Chính sách**: Giải thích rõ ràng quy định đổi trả, thanh toán, vận chuyển (liệt kê đầy đủ).
- **CSKH**: Hỗ trợ tự động, cung cấp thông tin liên hệ.
- **Realtime**: Kiểm tra tồn kho và giá bán theo thời gian thực.

---

## 1. Kiến Trúc Tổng Quan

```mermaid
graph TD
    User[User (Frontend)] -->|POST /chat| API[FastAPI Router]
    API --> Service[ChatbotService]
    
    subgraph "Chatbot Processing Pipeline"
        Service --> Security[SecurityUtils<br/>(Sanitize & Input Validation)]
        Security --> Coref[Coreference Resolution<br/>(Understand context)]
        Coref --> Intent[Intent Detection<br/>(LLM + Fallback)]
        Intent -->|Query| Retrieval[Data Retrieval]
        
        Retrieval -->|Candidates| Rerank[Context Reranking<br/>(LLM Based)]
        Rerank -->|Top K| Prompt[Dynamic Prompt Builder]
        Prompt -->|Context + Instructions| LLM[Google GenAI<br/>(Gemini 2.0 Flash)]
    end
    
    subgraph "Data & Caching"
        Retrieval <--> Redis[(Redis Cache)]
        Retrieval <--> VectorDB[(Pinecone/Vector Store)]
        Retrieval <--> DB[(Supabase/Postgres)]
    end
    
    LLM --> Response[Response Generation]
    Response --> User
```

---

## 2. Luồng Xử Lý Chi Tiết

### A. Intent Detection (Phân Loại Ý Định)
Hệ thống sử dụng LLM để phân tích ý định người dùng thay vì chỉ dựa vào từ khóa, giúp hiểu ngữ cảnh tốt hơn.

1.  **Input**: Câu hỏi thô của người dùng.
2.  **Coreference Resolution**: Thay thế đại từ (nó, cái đó, sản phẩm này) bằng tên sản phẩm được nhắc đến trước đó.
3.  **LLM Classification**: Gửi prompt yêu cầu trả về JSON định dạng chuẩn.
    -   *Logic xử lý lỗi*: Tự động sửa lỗi JSON (re-parsing) nếu LLM trả về format sai (preambles, markdown).
4.  **Fallback**: Nếu LLM thất bại, chuyển sang rule-based (keyword matching).

**Các Intent chính:**
-   `product_search`: Tìm kiếm sản phẩm
-   `product_info`: Hỏi thông tin chi tiết
-   `compare`: So sánh sản phẩm
-   `policy`: Chính sách (Thanh toán, Đổi trả, Vận chuyển...)
-   `support`: Hỗ trợ/Liên hệ
-   `stock_check`: Kiểm tra tồn kho

### B. Retrieval & Reranking (Truy Xuất & Sắp Xếp)
1.  **Hybrid Search**: Kết hợp tìm kiếm vector (semantic) và keyword.
2.  **Product & Content Handling**:
    -   *Product*: Lấy thông tin giá, thông số, biến thể.
    -   *Content (Policy)*: **Quan trọng** - Lấy toàn bộ nội dung từ metadata nếu field `data` null (Xử lý đặc biệt cho chính sách).
3.  **Reranking**: Sử dụng LLM để chấm điểm độ liên quan của các context tìm được với câu hỏi, lọc bỏ thông tin nhiễu.

### C. Prompt Engineering (Tạo Prompt Động)
Hệ thống xây dựng prompt động dựa trên Intent:

-   **Dynamic System Instructions**: Vai trò của bot thay đổi tùy intent (Chuyên gia sản phẩm vs Chuyên viên chính sách).
-   **Formatting Guides**:
    -   *Policy*: Yêu cầu liệt kê đầy đủ, dùng numbered list, không bỏ sót chi tiết (số tài khoản, hotline).
    -   *Compare*: Yêu cầu bảng so sánh hoặc bullet points.
    -   *Product Info*: Ngắn gọn, tập trung vào thông số chính.
-   **Context Injection**: Chèn thông tin đã được rerank vào prompt.

---

## 3. Data Flow Diagram

```
User Query "Bên mình có những phương thức thanh toán nào?"
       │
       ▼
┌─────────────────────────────────────────┐
│  1. Security & Coreference              │
│  - Sanitize input                       │
│  - "nó" -> "iPhone 15" (nếu có context) │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  2. Intent Detection (LLM)              │
│  - Output: Intent("policy", "payment")  │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  3. Retrieval (Vector + Cache)          │
│  - Search: "phương thức thanh toán"     │
│  - Result: [Guide Payment, Policy Ship] │
│  - *Fix*: Handle null data in Policies  │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  4. Reranking (LLM)                     │
│  - Filter: Keep only Payment Guide      │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  5. Prompt Build                        │
│  - Role: Policy Expert                  │
│  - Rule: "Liệt kê ĐẦY ĐỦ, numbered list"│
│  - Context: Full Payment Guide text     │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  6. Generation (Gemini 2.0 Flash)       │
│  - Generate final answer                │
└──────────────┬──────────────────────────┘
               │
               ▼
     "Chúng tôi hỗ trợ các phương thức:..."
```

---

## 4. Cấu Trúc Response

API trả về JSON với cấu trúc phong phú:

```json
{
  "answer": "Chúng tôi hỗ trợ thanh toán qua Ví điện tử (Momo, ZaloPay), Thẻ tín dụng và COD.",
  "contexts": [
    {
      "id": "content-123",
      "type": "product",
      "metadata": {
        "title": "Hướng dẫn thanh toán",
        "category": "Guide"
      }
    }
  ],
  "intent": {
    "primary": "policy",
    "confidence": 0.95
  }
}
```

---

## 5. Các Tính Năng Kỹ Thuật Nổi Bật

1.  **Robust JSON Parsing**: Module `SecurityUtils` có khả năng tự sửa lỗi JSON từ LLM (strip markdown, tìm object bằng regex), đảm bảo hệ thống không bị crash khi model trả về format lạ.
2.  **Context Aware Coreference**: Hiểu được ngữ cảnh hội thoại để xử lý các câu hỏi nối tiếp (VD: "Giá bao nhiêu?" sau khi hỏi về iPhone).
3.  **Circuit Breaker**: Bảo vệ hệ thống khi Google API gặp sự cố.
4.  **Redis Caching**: Cache kết quả Embedding, Intent và Search Result để tăng tốc độ phản hồi (Hit rate cao).
5.  **Offline Mode Fallback**: Tự động chuyển sang chế độ offline (trả về dữ liệu thô từ search) nếu LLM generation thất bại.

---

## 6. API Endpoints

### Chatbot
-   `POST /chatbot/chat`: Endpoint chính để chat.

### Content Management (Admin)
-   Hệ thống cho phép admin tạo/upload nội dung chính sách (Policy/Guide).
-   Dữ liệu được vector hóa và lưu vào Pinecone ngay lập tức để chatbot có thể tra cứu.

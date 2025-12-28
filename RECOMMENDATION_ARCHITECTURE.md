# 🎯 Recommendation Architecture: Product + Variant Strategy

## Tổng Quan

Hệ thống recommendation sử dụng **2-layer architecture** theo best practices của e-commerce:

1. **Layer 1 - Candidate Generation (PRODUCT level)**: Tìm sản phẩm phù hợp
2. **Layer 2 - Variant Selection (VARIANT level)**: Chọn variant tốt nhất cho mỗi sản phẩm

---

## 📊 Kiến Trúc 2-Layer

### Layer 1: Candidate Generation (PRODUCT)

**Mục đích**: Tìm top N products phù hợp với user

**Phương pháp**:
- ✅ **ALS** (Alternating Least Squares) - Collaborative Filtering
- ✅ **Vector Similarity** - Semantic search dựa trên embeddings
- ✅ **Session-based** - Dựa trên hành vi gần đây
- ✅ **Hybrid** - Kết hợp nhiều phương pháp

**Input**: `user_id` → `product_id`

**Output**: Top 100 `product_id` candidates

**Lý do dùng PRODUCT level**:
- ✅ Giảm sparsity (user tương tác với product, không phải từng variant)
- ✅ Model học tốt hơn (nhiều data hơn)
- ✅ Nhanh và hiệu quả

### Layer 2: Variant Selection (VARIANT)

**Mục đích**: Chọn variant tốt nhất cho mỗi product recommendation

**Scoring factors**:
- 🎨 **Color match** (20%): Màu user thường chọn
- 💾 **Storage match** (20%): Dung lượng user thường mua
- 💰 **Price similarity** (30%): Giá trong khoảng user thường mua
- 📦 **Stock availability** (10%): Còn hàng
- 🔥 **Popularity** (20%): Variant phổ biến

**Input**: `product_id` + `user_preferences` → `variant_id`

**Output**: `recommended_variant` cho mỗi product

---

## 📍 Mapping theo Vị Trí Trên Website

### 🏠 Trang Chủ / Discovery
- **Recommend**: PRODUCT
- **Hiển thị**: Default variant (phổ biến nhất)
- **Tracking**: `track_view(product_id)` - không cần variant_id

### 📦 Trang Danh Mục / Listing
- **Recommend**: PRODUCT
- **Sort**: Popularity / Relevance
- **Tracking**: `track_view(product_id)` hoặc `track_click(product_id)`

### 📱 Trang Chi Tiết Sản Phẩm
- **Recommend**: 
  - Similar PRODUCTs
  - Variant pre-selected theo user preferences
- **Tracking**: `track_view(product_id)` hoặc `track_click(product_id, variant_id)`

### 🛒 Cart / Checkout
- **Recommend**: VARIANT (phụ kiện tương thích, upsell)
- **Tracking**: `track_add_to_cart(product_id, variant_id)` ⚠️ **BẮT BUỘC variant_id**
- **Tracking**: `track_purchase(product_id, variant_id)` ⚠️ **BẮT BUỘC variant_id**

### 📧 Email / Push Notifications
- **Recommend**: PRODUCT → VARIANT
- Personalization dựa trên lịch sử mua hàng

---

## 📋 Interaction Tracking Rules

### Rule 1: View → product_id
```python
# Trang chủ, danh mục, product detail
track_view(user_id="user123", product_id="IP15-PRO")
# variant_id = None (không cần)
```

### Rule 2: Add to Cart / Order → variant_id
```python
# Khi user thêm vào giỏ hoặc mua
track_add_to_cart(
    user_id="user123", 
    product_id="IP15-PRO",
    variant_id="IP15P-256-BL"  # ⚠️ BẮT BUỘC
)

track_purchase(
    user_id="user123",
    product_id="IP15-PRO", 
    variant_id="IP15P-256-BL"  # ⚠️ BẮT BUỘC
)
```

### Rule 3: Train Model → product_id
- ALS model train trên `user_id × product_id`
- Không train trên variant level (quá sparse)

### Rule 4: Serve → variant_id
- API trả về `product_id` + `recommended_variant`
- Frontend hiển thị product với variant đã chọn

---

## 🔄 Flow Hoàn Chỉnh

```
1. User Request
   ↓
2. Layer 1: Candidate Generation
   - ALS / Vector / Session / Hybrid
   - Returns: [product_id_1, product_id_2, ...]
   ↓
3. Layer 2: Variant Selection
   - Get user preferences from history
   - Score each variant
   - Select best variant per product
   ↓
4. Response
   {
     "product_id": "IP15-PRO",
     "score": 0.95,
     "recommended_variant": {
       "sku": "IP15P-256-BL",
       "variantName": "256GB Blue",
       "color": "Blue",
       "price": 31990000
     }
   }
   ↓
5. Frontend
   - Display product with pre-selected variant
   - User can change variant if needed
```

---

## 💻 Implementation

### 1. Tracking với Variant

```python
# View (không cần variant)
POST /recommendations/track-view?product_id=IP15-PRO
Header: user_id: user123

# Add to Cart (CẦN variant)
POST /recommendations/track-add-to-cart?product_id=IP15-PRO&variant_id=IP15P-256-BL
Header: user_id: user123

# Purchase (CẦN variant)
POST /recommendations/track-purchase?product_id=IP15-PRO&variant_id=IP15P-256-BL
Header: user_id: user123
```

### 2. Get Recommendations

```python
GET /recommendations/personalized?limit=10
Header: user_id: user123

# Response
{
  "recommendations": [
    {
      "product_id": "IP15-PRO",
      "score": 0.95,
      "recommendation_type": "hybrid",
      "recommended_variant": {
        "sku": "IP15P-256-BL",
        "variantName": "256GB Blue",
        "color": "Blue",
        "price": 31990000
      }
    }
  ]
}
```

### 3. Variant Selection Logic

```python
from services.variant_selector import get_variant_selector

selector = get_variant_selector()

# Select best variant
best_variant = selector.select_best_variant(
    product_id="IP15-PRO",
    user_id="user123",
    user_history=user_history
)

# Enrich recommendations
enriched = selector.enrich_recommendations_with_variants(
    recommendations=product_recommendations,
    user_id="user123",
    user_history=user_history
)
```

---

## ✅ Lợi Ích

1. **Giảm Sparsity**: Train model ở product level (nhiều data hơn)
2. **Tăng Conversion**: Recommend variant phù hợp (màu, giá, storage)
3. **Personalization**: Học từ lịch sử mua hàng của user
4. **Flexibility**: User vẫn có thể đổi variant nếu muốn
5. **Scalability**: Dễ scale và maintain

---

## 📝 Notes

- **View/Click**: Không cần variant_id (product-level tracking)
- **Add to Cart/Purchase**: **BẮT BUỘC** variant_id (conversion tracking)
- **Model Training**: Chỉ dùng product_id (giảm sparsity)
- **Serving**: Trả về cả product_id và recommended_variant

---

## 🔧 Files Modified

1. `adapters/interfaces.py` - Thêm variant_id parameter
2. `adapters/database/mongodb_adapter.py` - Lưu variant_id trong interactions
3. `services/variant_selector.py` - **NEW** - Variant selection logic
4. `data/schemas.py` - Thêm RecommendedVariant model
5. `api/routes/recommend.py` - Enrich recommendations với variants

---

## 🚀 Next Steps

1. ✅ Update Postgres/Supabase adapters để hỗ trợ variant_id
2. ✅ Test variant selection với real data
3. ✅ A/B test: với/không có variant selection
4. ✅ Monitor conversion rate improvements


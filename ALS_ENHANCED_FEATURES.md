# 🚀 Tính Năng Nâng Cao Cho ALS Model

Tài liệu hướng dẫn sử dụng các tính năng mới: Data Quality Checks, Normalization, và Feature Engineering.

---

## 📋 Tổng Quan

Các tính năng đã được bổ sung:

1. ✅ **Data Quality Checks** - Kiểm tra và làm sạch dữ liệu
2. ✅ **Normalization** - Chuẩn hóa interaction counts
3. ✅ **Feature Engineering** - Temporal weighting, frequency, category features

---

## 1️⃣ Data Quality Checks

### Các Tính Năng

- ✅ **Remove Duplicates**: Loại bỏ duplicate user-product pairs (giữ count cao nhất)
- ✅ **Remove Outliers**: Loại bỏ interactions có count quá cao (có thể là bot/spam)
- ✅ **Remove Stale Data**: Chỉ lấy interactions trong N ngày gần đây
- ✅ **Remove Cold-Start**: Loại bỏ users/products có quá ít interactions

### Cấu Hình

Thêm vào file `.env`: 

```env
# Data Quality Settings
ALS_DATA_QUALITY_ENABLED=True
ALS_REMOVE_DUPLICATES=True
ALS_REMOVE_OUTLIERS=True
ALS_OUTLIER_THRESHOLD_STD=3.0
ALS_REMOVE_STALE=True
ALS_MAX_AGE_DAYS=90
ALS_REMOVE_COLD_START=True
ALS_MIN_USER_INTERACTIONS=2
ALS_MIN_PRODUCT_INTERACTIONS=2
```

### Giải Thích Các Tham Số

- `ALS_DATA_QUALITY_ENABLED`: Bật/tắt data quality checks
- `ALS_REMOVE_DUPLICATES`: Loại bỏ duplicate pairs
- `ALS_REMOVE_OUTLIERS`: Loại bỏ outliers (count > mean + N * std)
- `ALS_OUTLIER_THRESHOLD_STD`: Số standard deviations cho outlier detection (mặc định: 3.0)
- `ALS_REMOVE_STALE`: Loại bỏ dữ liệu cũ
- `ALS_MAX_AGE_DAYS`: Tuổi tối đa của interactions (mặc định: 90 ngày)
- `ALS_REMOVE_COLD_START`: Loại bỏ cold-start users/products
- `ALS_MIN_USER_INTERACTIONS`: Số interactions tối thiểu mỗi user (mặc định: 2)
- `ALS_MIN_PRODUCT_INTERACTIONS`: Số interactions tối thiểu mỗi product (mặc định: 2)

### Ví Dụ Sử Dụng

```python
from utils.data_quality import validate_interactions

interactions = [
    {"user_id": "user_1", "product_id": "prod_1", "count": 10},
    {"user_id": "user_1", "product_id": "prod_1", "count": 5},  # Duplicate
    {"user_id": "user_2", "product_id": "prod_1", "count": 1000},  # Outlier
    ...
]

cleaned, stats = validate_interactions(
    interactions,
    remove_duplicates=True,
    remove_outliers=True,
    outlier_threshold_std=3.0,
    remove_stale=True,
    max_age_days=90,
    remove_cold_start=True,
    min_user_interactions=2,
    min_product_interactions=2,
)

stats.log_summary()  # In ra thống kê
```

---

## 2️⃣ Normalization

### Các Phương Pháp

- **none**: Không normalize (mặc định)
- **log**: Log transformation `log(1 + x)` - Giảm ảnh hưởng của power users
- **minmax**: Min-max scaling về [0, 1]
- **zscore**: Z-score normalization (mean=0, std=1)
- **sqrt**: Square root transformation `sqrt(x)`

### Cấu Hình

Thêm vào file `.env`:

```env
# Normalization Settings
ALS_NORMALIZATION_METHOD=log
```

### Giải Thích

- **log**: Phù hợp khi có power users (users tương tác rất nhiều)
- **minmax**: Phù hợp khi muốn scale về [0, 1]
- **zscore**: Phù hợp khi muốn standardize distribution
- **sqrt**: Ít aggressive hơn log, vẫn giảm ảnh hưởng của outliers

### Ví Dụ Sử Dụng

```python
from utils.normalization import normalize_counts, apply_normalization_to_interactions

# Normalize một list counts
counts = [1, 5, 10, 50, 100]
normalized = normalize_counts(counts, method="log")
# Result: [0.693, 1.792, 2.398, 3.931, 4.615]

# Normalize interactions
interactions = [
    {"user_id": "user_1", "product_id": "prod_1", "count": 10},
    ...
]
normalized_interactions = apply_normalization_to_interactions(
    interactions,
    method="log",
    count_key="count",
)
```

---

## 3️⃣ Feature Engineering

### A. Temporal Weighting (Recency Weighting)

Áp dụng trọng số theo thời gian: interactions gần đây quan trọng hơn.

**Công thức**: `weight = 2^(-age / half_life)`

- Interactions mới (age=0): weight = 1.0
- Interactions ở half_life: weight = 0.5
- Interactions cũ hơn: weight < 0.5

### Cấu Hình

```env
# Temporal Weighting Settings
ALS_TEMPORAL_WEIGHTING_ENABLED=True
ALS_RECENCY_HALF_LIFE_DAYS=30.0
```

### Ví Dụ Sử Dụng

```python
from utils.feature_engineering import apply_temporal_weighting

interactions = [
    {
        "user_id": "user_1",
        "product_id": "prod_1",
        "count": 10,
        "timestamp": "2024-01-15T10:00:00Z",  # 30 ngày trước
    },
    {
        "user_id": "user_1",
        "product_id": "prod_2",
        "count": 10,
        "timestamp": "2024-02-14T10:00:00Z",  # Hôm nay
    },
]

weighted = apply_temporal_weighting(
    interactions,
    half_life_days=30.0,
    timestamp_key="timestamp",
)
# Interaction gần đây sẽ có count cao hơn sau khi weight
```

**Lưu ý**: Tính năng này yêu cầu timestamps trong interactions. Hiện tại `get_interaction_counts()` có thể không trả về timestamps. Cần cập nhật adapters để hỗ trợ.

### B. Frequency Features

Thêm features về tần suất tương tác trong một khoảng thời gian.

```python
from utils.feature_engineering import add_frequency_features

interactions = add_frequency_features(
    interactions,
    window_days=7,  # Tính frequency trong 7 ngày gần đây
    timestamp_key="timestamp",
)
# Mỗi interaction sẽ có thêm:
# - "user_frequency": Số interactions của user trong window
# - "product_frequency": Số interactions của product trong window
```

### C. Category Features

Thêm thông tin category của sản phẩm.

```python
from utils.feature_engineering import add_category_features
from adapters.factory import get_product_store

product_store = get_product_store()
interactions = add_category_features(
    interactions,
    product_store=product_store,
    category_key="category",
)
# Mỗi interaction sẽ có thêm:
# - "category": Category của product
```

---

## 🔧 Sử Dụng Trong Training

### Tự Động (Qua Config)

Các tính năng sẽ tự động được áp dụng khi train model:

```bash
# Train model với các tính năng mới
python -m services.model_trainer
```

Model trainer sẽ:
1. ✅ Áp dụng data quality checks (nếu `ALS_DATA_QUALITY_ENABLED=True`)
2. ✅ Áp dụng normalization (theo `ALS_NORMALIZATION_METHOD`)
3. ✅ Áp dụng feature engineering (nếu enabled)

### Thủ Công (Trong Code)

```python
from models.als_recommender import train_implicit_als, ALSSettings
from utils.data_quality import validate_interactions
from utils.normalization import apply_normalization_to_interactions
from utils.feature_engineering import apply_temporal_weighting

# 1. Load interactions
interactions = behavior.get_interaction_counts(limit=50000)

# 2. Apply feature engineering
if temporal_weighting_enabled:
    interactions = apply_temporal_weighting(
        interactions,
        half_life_days=30.0,
        timestamp_key="timestamp",
    )

# 3. Train với data quality và normalization
settings = ALSSettings(factors=64, iterations=15, ...)
model, matrix = train_implicit_als(
    interactions,
    settings=settings,
    apply_data_quality=True,
    apply_normalization=True,
    normalization_method="log",
    data_quality_config={
        "remove_duplicates": True,
        "remove_outliers": True,
        "outlier_threshold_std": 3.0,
        "remove_stale": True,
        "max_age_days": 90,
        "remove_cold_start": True,
        "min_user_interactions": 2,
        "min_product_interactions": 2,
    },
)
```

---

## 📊 Monitoring & Logging

### Data Quality Stats

Khi train model, bạn sẽ thấy log như sau:

```
============================================================
Data Quality Check Summary
============================================================
Total records: 50000
Removed - Invalid: 120
Removed - Duplicates: 350
Removed - Outliers: 45
Removed - Stale data: 1200
Removed - Cold-start users: 800
Removed - Cold-start products: 200
Final records: 47285
Unique users: 5000
Unique products: 2000
Count stats - Min: 1.00, Max: 50.00, Mean: 5.23, Median: 3.00
============================================================
```

### Normalization Logs

```
Applied log normalization: min=0.0000, max=4.6151
```

---

## 🎯 Best Practices

### 1. Data Quality

- **Bắt đầu với defaults**: Sử dụng giá trị mặc định trước, điều chỉnh sau
- **Monitor stats**: Xem log để hiểu dữ liệu bị loại bỏ
- **Điều chỉnh thresholds**: Nếu loại bỏ quá nhiều, giảm thresholds

### 2. Normalization

- **Dùng log cho power users**: Nếu có users tương tác rất nhiều
- **Dùng minmax cho scale**: Nếu muốn values trong [0, 1]
- **Test nhiều methods**: So sánh kết quả với các methods khác nhau

### 3. Feature Engineering

- **Temporal weighting**: Quan trọng nếu preferences thay đổi theo thời gian
- **Frequency features**: Có thể dùng để filter hoặc boost
- **Category features**: Có thể dùng cho category-based recommendations

---

## ⚠️ Lưu Ý

### Temporal Weighting

- **Yêu cầu timestamps**: Cần timestamps trong interactions
- **Adapter updates**: Có thể cần cập nhật adapters để trả về timestamps trong `get_interaction_counts()`

### Performance

- **Data quality checks**: Có thể chậm với dữ liệu lớn (>100K interactions)
- **Normalization**: Rất nhanh, không ảnh hưởng performance
- **Feature engineering**: Phụ thuộc vào số lượng products (category lookup)

---

## 📚 Tài Liệu Tham Khảo

- `utils/data_quality.py` - Data quality checks
- `utils/normalization.py` - Normalization methods
- `utils/feature_engineering.py` - Feature engineering
- `models/als_recommender.py` - Training với các tính năng mới
- `services/model_trainer.py` - Training entrypoint

---

## ✅ Checklist

- [ ] Đã cấu hình `.env` với các settings mới
- [ ] Đã test data quality checks với dữ liệu thật
- [ ] Đã chọn normalization method phù hợp
- [ ] Đã enable temporal weighting (nếu cần)
- [ ] Đã monitor logs để hiểu dữ liệu bị loại bỏ
- [ ] Đã so sánh kết quả với/không có các tính năng mới


# 📊 Pipeline ETL cho Model ALS

Tài liệu mô tả chi tiết quy trình Extract, Transform, Load (ETL) dữ liệu cho việc training ALS model.

---

## 🔄 Tổng Quan Pipeline

```
Raw Data (user_views table)
    ↓
[EXTRACT] - Lấy dữ liệu từ database
    ↓
[TRANSFORM] - Aggregate, weight, normalize
    ↓
[LOAD] - Build matrix và train model
    ↓
Trained ALS Model (.npz file)
```

---

## 1️⃣ EXTRACT (Trích Xuất Dữ Liệu)

### PostgreSQL Adapter (`adapters/postgres_adapter.py`)

**Method**: `get_interaction_counts(limit: int)`

**SQL Query**:
```sql
SELECT
    user_id,
    product_id,
    SUM(
        CASE event_type
            WHEN 'view' THEN 1
            WHEN 'click' THEN 2
            WHEN 'add_to_cart' THEN 3
            WHEN 'purchase' THEN 5
            ELSE 1
        END
    ) AS count
FROM user_views
GROUP BY user_id, product_id
ORDER BY count DESC
LIMIT %s;
```

**Đặc điểm**:
- ✅ **Transform được thực hiện ở SQL level** (hiệu quả hơn)
- ✅ Aggregate trực tiếp trong database
- ✅ Có giới hạn số lượng records (`LIMIT`)
- ✅ Sắp xếp theo count DESC (ưu tiên interactions quan trọng)

**Output**: `List[Dict[str, Any]]` với format:
```python
[
    {"user_id": "user_1", "product_id": "prod_1", "count": 15},
    {"user_id": "user_2", "product_id": "prod_1", "count": 8},
    ...
]
```

### Supabase Adapter (`adapters/supabase_adapter.py`)

**Method**: `get_interaction_counts(limit: int)`

**Approach**: Client-side aggregation (do Supabase limitations)

**Process**:
1. Lấy raw interactions qua pagination (`get_recent_interactions`)
2. Aggregate trong Python memory:
   ```python
   counts: Dict[tuple, int] = {}
   for row in batch:
       user_id = row.get("user_id")
       product_id = row.get("product_id")
       event_type = row.get("event_type", "view").lower()
       
       # Weight events
       if event_type == "click":
           w = 2
       elif event_type == "add_to_cart":
           w = 3
       elif event_type == "purchase":
           w = 5
       else:
           w = 1
       
       counts[(user_id, product_id)] = counts.get((user_id, product_id), 0) + w
   ```

**Đặc điểm**:
- ⚠️ **Transform ở client-side** (có thể chậm với dữ liệu lớn)
- ✅ Cùng weighting scheme như PostgreSQL
- ⚠️ Cần pagination để tránh memory overflow

---

## 2️⃣ TRANSFORM (Biến Đổi Dữ Liệu)

### A. Event Weighting (Trọng Số Hóa Events)

Các loại tương tác được gán trọng số khác nhau:

| Event Type | Weight | Ý Nghĩa |
|------------|--------|---------|
| `view` | 1 | Xem sản phẩm (tương tác yếu nhất) |
| `click` | 2 | Click vào sản phẩm (quan tâm hơn) |
| `add_to_cart` | 3 | Thêm vào giỏ hàng (ý định mua) |
| `purchase` | 5 | Mua hàng (tương tác mạnh nhất) |

**Lý do**: Purchase và add_to_cart thể hiện ý định mua rõ ràng hơn view/click.

### B. Aggregation (Tổng Hợp)

- **Group by**: `(user_id, product_id)`
- **Aggregation**: `SUM(weight)` - Tổng trọng số tất cả events của user với product
- **Result**: Mỗi cặp (user, product) có một `count` duy nhất

**Ví dụ**:
```
User A tương tác với Product X:
- 5 views (5 × 1 = 5)
- 2 clicks (2 × 2 = 4)
- 1 add_to_cart (1 × 3 = 3)
- 0 purchases (0 × 5 = 0)
→ Total count = 12
```

### C. Data Validation & Cleaning

Trong `train_implicit_als()` (`models/als_recommender.py`):

```python
for x in interactions:
    uid = x.get("user_id")
    pid = x.get("product_id")
    cnt = x.get("count", 0)
    
    # Validation
    if uid is None or pid is None:
        continue  # Skip invalid records
    
    try:
        cnt_f = float(cnt)
    except Exception:
        continue  # Skip non-numeric counts
    
    if cnt_f <= 0:
        continue  # Skip zero/negative counts
    
    # Build matrix indices
    rows.append(user_id_to_index[str(uid)])
    cols.append(product_id_to_index[str(pid)])
    vals.append(cnt_f)
```

**Các bước cleaning**:
1. ✅ Loại bỏ records thiếu `user_id` hoặc `product_id`
2. ✅ Loại bỏ `count` không phải số
3. ✅ Loại bỏ `count <= 0`
4. ✅ Normalize string IDs (convert sang string)

### D. Index Mapping

Tạo mapping từ ID sang index trong matrix:

```python
# Extract unique IDs
user_ids = sorted({str(x["user_id"]) for x in interactions if x.get("user_id") is not None})
product_ids = sorted({str(x["product_id"]) for x in interactions if x.get("product_id") is not None})

# Build index maps
user_id_to_index = {uid: i for i, uid in enumerate(user_ids)}
product_id_to_index = {pid: i for i, pid in enumerate(product_ids)}
```

**Lý do**: ALS model cần integer indices, không phải string IDs.

---

## 3️⃣ LOAD (Nạp Vào Model)

### A. Build Sparse Matrix

```python
# Build user-item matrix
user_item_matrix = sparse.csr_matrix(
    (vals, (rows, cols)), 
    shape=(n_users, n_items), 
    dtype=np.float32
)
```

**Format**: 
- **Rows**: User indices
- **Cols**: Product indices  
- **Values**: Interaction counts (weighted)

**Ví dụ Matrix**:
```
        prod_1  prod_2  prod_3
user_1    12      0       5
user_2     0      8       0
user_3     3      2      15
```

### B. Transpose for Implicit Library

```python
item_user_matrix = user_item_matrix.T.tocsr()
```

**Lý do**: Thư viện `implicit` yêu cầu item-user matrix (không phải user-item).

### C. Train Model

```python
model_impl = AlternatingLeastSquares(
    factors=settings.factors,          # 64 (default)
    regularization=settings.regularization,  # 0.1
    iterations=settings.iterations,     # 15
    alpha=settings.alpha,                # 40.0
    use_gpu=settings.use_gpu,
    random_state=seed,
)

model_impl.fit(item_user_matrix, show_progress=True)
```

### D. Save Model

```python
save_als_model(model, ALS_MODEL_PATH)
```

**Format**: `.npz` (NumPy compressed) chứa:
- `user_ids`: Array of user IDs
- `product_ids`: Array of product IDs
- `user_factors`: User embedding matrix (n_users × k)
- `item_factors`: Item embedding matrix (n_items × k)
- `trained_at`: Timestamp

---

## 📈 Điểm Mạnh của Pipeline Hiện Tại

### ✅ Đã Có ETL

1. **Extract**: 
   - ✅ Lấy dữ liệu từ database (PostgreSQL/Supabase)
   - ✅ Có pagination/limit để tránh memory overflow

2. **Transform**:
   - ✅ Event weighting (view=1, click=2, add_to_cart=3, purchase=5)
   - ✅ Aggregation (SUM per user-product pair)
   - ✅ Data validation (loại bỏ invalid records)
   - ✅ Index mapping (ID → matrix index)

3. **Load**:
   - ✅ Build sparse matrix (hiệu quả về memory)
   - ✅ Train ALS model
   - ✅ Save model artifact

### ✅ Tối Ưu Hóa

- **Sparse matrix**: Chỉ lưu non-zero values (tiết kiệm memory)
- **SQL-level aggregation**: PostgreSQL adapter aggregate trong DB (nhanh hơn)
- **Type conversion**: `np.float32` để tiết kiệm memory
- **Compressed storage**: `.npz` format để giảm kích thước file

---

## ⚠️ Điểm Cần Cải Thiện

### 1. Supabase Adapter - Client-Side Aggregation

**Vấn đề**: 
- Aggregate trong Python memory (chậm với dữ liệu lớn)
- Cần pagination nhiều lần

**Giải pháp đề xuất**:
- Tạo SQL function/view trong Supabase để aggregate ở server-side
- Hoặc dùng Supabase RPC (Remote Procedure Call)

### 2. Thiếu Data Quality Checks

**Hiện tại**: Chỉ validate cơ bản (None, non-numeric, <= 0)

**Có thể thêm**:
- ✅ Check duplicate user-product pairs
- ✅ Check outliers (count quá cao - có thể là bot/spam)
- ✅ Check data freshness (chỉ lấy interactions trong N ngày gần đây)
- ✅ Check minimum interactions per user/product (filter cold-start)

### 3. Thiếu Normalization

**Hiện tại**: Dùng raw weighted counts

**Có thể thêm**:
- **Log transformation**: `log(1 + count)` để giảm ảnh hưởng của power users
- **Min-max normalization**: Scale về [0, 1]
- **Z-score normalization**: Standardize distribution

### 4. Thiếu Feature Engineering

**Có thể thêm**:
- **Temporal features**: Recency weighting (events gần đây quan trọng hơn)
- **Frequency features**: Số lần tương tác trong khoảng thời gian
- **Category features**: Embed category information vào matrix

### 5. Thiếu Monitoring & Logging

**Có thể thêm**:
- Log số lượng interactions trước/sau cleaning
- Log distribution của counts (min, max, mean, median)
- Log số lượng users/products unique
- Metrics: sparsity ratio, average interactions per user/product

---

## 🔧 Đề Xuất Cải Thiện

### Option 1: Thêm Data Quality Module

```python
# utils/data_quality.py
def validate_interactions(interactions: List[Dict]) -> Tuple[List[Dict], Dict]:
    """
    Validate và clean interactions.
    Returns: (cleaned_interactions, stats)
    """
    stats = {
        "total": len(interactions),
        "removed_invalid": 0,
        "removed_duplicates": 0,
        "removed_outliers": 0,
    }
    
    # Validation logic...
    
    return cleaned_interactions, stats
```

### Option 2: Thêm Normalization

```python
# models/als_recommender.py
def normalize_counts(counts: List[float], method: str = "log") -> List[float]:
    """
    Normalize interaction counts.
    Methods: 'log', 'minmax', 'zscore', 'none'
    """
    if method == "log":
        return [math.log1p(c) for c in counts]
    elif method == "minmax":
        min_c, max_c = min(counts), max(counts)
        return [(c - min_c) / (max_c - min_c) if max_c > min_c else 0 for c in counts]
    # ...
```

### Option 3: Thêm ETL Pipeline Class

```python
# services/als_etl_pipeline.py
class ALSETLPipeline:
    def extract(self, limit: int) -> List[Dict]:
        """Extract raw interactions from database"""
        pass
    
    def transform(self, interactions: List[Dict]) -> List[Dict]:
        """Transform: weight, aggregate, validate, normalize"""
        pass
    
    def load(self, interactions: List[Dict]) -> ALSModel:
        """Load into model and train"""
        pass
    
    def run(self, limit: int) -> ALSModel:
        """Run full ETL pipeline"""
        raw = self.extract(limit)
        transformed = self.transform(raw)
        model = self.load(transformed)
        return model
```

---

## 📝 Kết Luận

### ✅ Pipeline Hiện Tại

**CÓ ETL**, nhưng ở mức cơ bản:
- ✅ Extract: Từ database với aggregation
- ✅ Transform: Weighting, aggregation, validation cơ bản
- ✅ Load: Build matrix và train model

### 🎯 Đề Xuất

1. **Ngắn hạn**: 
   - Thêm data quality checks
   - Thêm logging/metrics
   - Cải thiện Supabase aggregation (dùng SQL function)

2. **Dài hạn**:
   - Thêm normalization options
   - Thêm temporal/recency weighting
   - Tạo ETL pipeline class để dễ maintain

---

## 📚 Tài Liệu Tham Khảo

- `models/als_recommender.py` - Training logic
- `adapters/postgres_adapter.py` - PostgreSQL ETL
- `adapters/supabase_adapter.py` - Supabase ETL
- `services/model_trainer.py` - Training entrypoint


import random
import string
import requests
from uuid import uuid4
import time
import random

API_URL = "http://localhost:8000/products/"

# -----------------------------
# Base vocab for semantic search
# -----------------------------
CATEGORIES = {
    "Smartphone": {
        "names": ["iPhone 15 Pro", "Samsung Galaxy S24", "Xiaomi 14", "Pixel 8"],
        "keywords": [
            "5G",
            "OLED",
            "camera chất lượng cao",
            "pin lâu",
            "hiệu năng mạnh",
        ],
        "specifications": lambda: [
            {
                "key": "Phiên bản CPU",
                "value": random.choice(["A17 Pro", "Snapdragon 8 Gen 3"]),
                "group": "Performance",
            },
            {
                "key": "Dung lượng",
                "value": random.choice(["8GB", "12GB"]),
                "group": "RAM",
            },
            {
                "key": "Dung lượng",
                "value": random.choice(["256GB", "512GB"]),
                "group": "Storage",
            },
            {"key": "Kích thước", "value": "6.1 inch", "group": "Display"},
            {"key": "Công nghệ", "value": "OLED", "group": "Display"},
            {"key": "Độ phân giải", "value": "48MP", "group": "Camera"},
            {"key": "Dung lượng pin", "value": "4500mAh", "group": "Battery"},
            {
                "key": "Tên OS",
                "value": random.choice(["iOS", "Android"]),
                "group": "OperatingSystem",
            },
        ],
    },
    "Laptop": {
        "names": ["MacBook Air M2", "Dell XPS 15", "ThinkPad X1"],
        "keywords": ["mỏng nhẹ", "pin lâu", "hiệu năng cao", "SSD nhanh"],
        "specifications": lambda: [
            {
                "key": "Phiên bản CPU",
                "value": random.choice(["Intel i7", "Apple M2"]),
                "group": "Performance",
            },
            {
                "key": "Dung lượng",
                "value": random.choice(["16GB", "32GB"]),
                "group": "RAM",
            },
            {"key": "Dung lượng", "value": "1TB SSD", "group": "Storage"},
            {"key": "Kích thước", "value": "15.6 inch", "group": "Display"},
            {"key": "Công nghệ", "value": "IPS", "group": "Display"},
            {"key": "Chip đồ họa", "value": "Intel Iris Xe", "group": "Graphic"},
            {"key": "Tên OS", "value": "Windows 11", "group": "OperatingSystem"},
        ],
    },
    "Tablet": {
        "names": ["iPad Pro", "Galaxy Tab S9"],
        "keywords": ["giải trí", "học tập", "màn hình lớn"],
        "specifications": lambda: [
            {"key": "Phiên bản CPU", "value": "Apple M2", "group": "Performance"},
            {"key": "Dung lượng", "value": "8GB", "group": "RAM"},
            {"key": "Dung lượng", "value": "256GB", "group": "Storage"},
            {"key": "Kích thước", "value": "11 inch", "group": "Display"},
            {"key": "Độ phân giải", "value": "12MP", "group": "Camera"},
            {"key": "Dung lượng pin", "value": "7500mAh", "group": "Battery"},
        ],
    },
    "Accessories": {
        "names": ["Tai nghe Bluetooth", "Loa di động"],
        "keywords": ["bluetooth", "không dây", "âm thanh tốt"],
        "specifications": lambda: [
            {"key": "Thời lượng pin", "value": "30h", "group": "Battery"},
            {"key": "Chuẩn kết nối", "value": "Bluetooth 5.3", "group": "Connectivity"},
        ],
    },
}


def random_price(category):
    if category == "Laptops":
        return round(random.uniform(800, 2500), 2)
    if category == "Smartphones":
        return round(random.uniform(500, 1500), 2)
    if category == "Desktop Computers":
        return round(random.uniform(1000, 4000), 2)
    if category == "Electronics":
        return round(random.uniform(80, 300), 2)
    if category == "Gaming Accessories":
        return round(random.uniform(50, 200), 2)
    if category == "Wearables":
        return round(random.uniform(100, 250), 2)
    return round(random.uniform(60, 150), 2)


def generate_description(name, keywords):
    selected = random.sample(keywords, k=min(3, len(keywords)))
    return (
        f"{name} là sản phẩm điện tử hiện đại. "
        f"Tính năng nổi bật: {', '.join(selected)}. "
        f"Phù hợp cho học tập, làm việc và giải trí."
    )


def generate_product():
    category = random.choice(list(CATEGORIES.keys()))
    config = CATEGORIES[category]

    name = random.choice(config["names"])
    description = generate_description(name, config["keywords"])
    specs = config["specifications"]()

    brand = random.choice(["Apple", "Samsung", "Xiaomi", "Dell", "Lenovo"])

    price = random_price(category)

    return {
        "name": name,
        "brand": brand,
        "description": description,
        "listPrice": price,
        "currency": "VND",
        "inStock": True,
        "warranty": "12 tháng",
        "categories": [{"id": category.lower(), "name": category}],
        "images": ["https://via.placeholder.com/300x300?text=Product"],
        "videoUrl": "",
        "specifications": specs,
        "productVariants": [
            {
                "sku": "SKU-" + uuid4().hex[:8].upper(),
                "variantName": f"{name} - Standard",
                "color": random.choice(["Black", "White", "Silver"]),
                "price": price,
                "inStock": True,
                "bestSpecifications": [],
            }
        ],
    }


def post_product(product, delay_range=(0.3, 1.2)):
    start_time = time.time()

    try:
        response = requests.post(API_URL, json=product, timeout=5)
        elapsed = time.time() - start_time

        if response.status_code not in (200, 201):
            print(
                f"[FAILED] {response.status_code} | "
                f"time={elapsed:.2f}s | {response.text}"
            )
        else:
            print(
                f"[OK] product_id={response.json().get('product_id')} | "
                f"time={elapsed:.2f}s"
            )

    except Exception as e:
        print(f"[ERROR] {str(e)}")

    # 🔥 Delay để consumer xử lý kịp
    sleep_time = random.uniform(*delay_range)
    time.sleep(sleep_time)


def main(total=50):
    print(f"Generating {total} products with throttling...\n")

    for i in range(total):
        print(f"Sending product {i + 1}/{total}")
        product = generate_product()
        post_product(product)


if __name__ == "__main__":
    try:
        # Generate 100 items as requested (mostly new categories now included)
        main(total=30)
    except KeyboardInterrupt:
        print("\nStopped.")

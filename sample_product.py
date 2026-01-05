import random
import string
import requests
from uuid import uuid4

API_URL = "http://localhost:8000/products/"

# -----------------------------
# Base vocab for semantic search
# -----------------------------
CATEGORIES = {
    "Electronics": {
        "names": [
            "Wireless Headphones",
            "Bluetooth Earbuds",
            "Noise Cancelling Headphones",
            "Portable Speaker",
        ],
        "keywords": [
            "wireless",
            "bluetooth",
            "noise cancelling",
            "deep bass",
            "high quality sound",
            "long battery life",
        ],
        "specifications": lambda: [
            {
                "key": "brand",
                "value": random.choice(["SoundMax", "AudioPro", "BeatX"]),
                "type": "TEXT",
                "group": "GENERAL",
            },
            {
                "key": "battery_life",
                "value": random.choice(["20h", "24h", "30h"]),
                "type": "TEXT",
                "group": "TECHNICAL",
            },
            {
                "key": "connectivity",
                "value": "Bluetooth",
                "type": "TEXT",
                "group": "TECHNICAL",
            },
        ],
    },
    "Gaming Accessories": {
        "names": ["Gaming Mouse", "Mechanical Keyboard", "Gaming Headset"],
        "keywords": [
            "gaming",
            "rgb lighting",
            "high precision",
            "ergonomic design",
            "fast response",
        ],
        "specifications": lambda: [
            {
                "key": "brand",
                "value": random.choice(["ProGamer", "HyperPlay"]),
                "type": "TEXT",
                "group": "GENERAL",
            },
            {"key": "rgb", "value": "Yes", "type": "TEXT", "group": "TECHNICAL"},
            {
                "key": "dpi",
                "value": str(random.choice([8000, 12000, 16000])),
                "type": "NUMBER",
                "group": "TECHNICAL",
            },
        ],
    },
    "Wearables": {
        "names": ["Smart Watch", "Fitness Tracker"],
        "keywords": [
            "heart rate monitoring",
            "sleep tracking",
            "fitness",
            "gps",
            "waterproof",
        ],
        "specifications": lambda: [
            {
                "key": "brand",
                "value": random.choice(["FitLife", "HealthPlus"]),
                "type": "TEXT",
                "group": "GENERAL",
            },
            {
                "key": "gps",
                "value": str(random.choice([True, False])),
                "type": "TEXT",
                "group": "TECHNICAL",
            },
            {"key": "waterproof", "value": "Yes", "type": "TEXT", "group": "TECHNICAL"},
        ],
    },
    "Sportswear": {
        "names": ["Running Shoes", "Training Shoes"],
        "keywords": ["lightweight", "breathable mesh", "comfortable", "durable sole"],
        "specifications": lambda: [
            {
                "key": "brand",
                "value": random.choice(["RunFast", "ActiveWear"]),
                "type": "TEXT",
                "group": "GENERAL",
            },
            {"key": "material", "value": "Mesh", "type": "TEXT", "group": "MATERIAL"},
            {
                "key": "gender",
                "value": random.choice(["Men", "Women"]),
                "type": "TEXT",
                "group": "GENERAL",
            },
        ],
    },
}


def random_price(category):
    if category == "Electronics":
        return round(random.uniform(80, 300), 2)
    if category == "Gaming Accessories":
        return round(random.uniform(50, 200), 2)
    if category == "Wearables":
        return round(random.uniform(100, 250), 2)
    return round(random.uniform(60, 150), 2)


def generate_description(name, keywords):
    category = random.choice(list(CATEGORIES.keys()))

    selected = random.sample(keywords, k=3)
    return (
        f"{name} designed for modern users. "
        f"Features {', '.join(selected)}. "
        f"Perfect for everyday use and long-term comfort."
    )


def generate_product():
    category = random.choice(list(CATEGORIES.keys()))
    config = CATEGORIES[category]

    name = random.choice(config["names"])
    description = generate_description(name, config["keywords"])

    specs = config["specifications"]()
    brand = next((s["value"] for s in specs if s["key"] == "brand"), "Generic")

    return {
        "name": name,
        "description": description,
        "category": category,
        "categoryId": [category],
        "price": random_price(category),
        "brandName": brand,
        "sku": "SKU-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8)),
        "specifications": specs,
        "productVariants": [
            {
                "sku": "SKU-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8)),
                "variantName": f"{name} - Standard",
                "color": random.choice(["Red", "Black", "White"]),
                "price": random_price(category),
                "bestSpecifications": []
            }
        ],
        "videoUrl": "",
        "avgRating": 0,
        "listPrice": None,
        "sold": 0,
        "thumbnail": "",
        "imageList": []
    }


def post_product(product):
    response = requests.post(API_URL, json=product)
    if response.status_code not in (200, 201):
        print("❌ Failed:", response.status_code, response.text)
    else:
        print("✅ Created:", response.json().get("product_id"))


def main(total=50):
    print(f"🚀 Generating {total} products...\n")
    for _ in range(total):
        product = generate_product()
        post_product(product)


if __name__ == "__main__":
    main(total=100)

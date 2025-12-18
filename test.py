# import json
# import requests

# endpoint = "http://localhost:8000/products/"
# headers = {
#     "Content-Type": "application/json",
#     # "Authorization": "Bearer <token>"  # if the API requires auth
# }

# # Sample product list with ids from 1 to 10
# # products = [
# #     { "id": "15", "name": "Unisex Cotton T-Shirt", "category": "Fashion", "price": 199000, "tags": ["cotton", "unisex", "tshirt", "casual"], "attributes": {"color": "White", "size": "M", "material": "Cotton"}, "popularity": 95, "rating": 4.6, "like": 120 },
# #     { "id": "16", "name": "Wireless Bluetooth Headphones", "category": "Electronics", "price": 890000, "tags": ["bluetooth", "audio", "wireless", "headset"], "attributes": {"color": "Black", "battery_hours": 30}, "popularity": 120, "rating": 4.4, "like": 210 },
# #     { "id": "17", "name": "500ml Insulated Water Bottle", "category": "Home Goods", "price": 249000, "tags": ["stainless", "insulated", "water-bottle"], "attributes": {"material": "304 Stainless Steel", "capacity_ml": 500}, "popularity": 80, "rating": 4.2, "like": 90 },
# #     { "id": "18", "name": "15.6 Inch Laptop Backpack", "category": "Accessories", "price": 399000, "tags": ["bag", "laptop", "waterproof", "travel"], "attributes": {"fits_laptop": "15.6 inch", "material": "Polyester"}, "popularity": 110, "rating": 4.5, "like": 150 },
# #     { "id": "19", "name": "Gentle Facial Cleanser 120ml", "category": "Cosmetics", "price": 149000, "tags": ["skincare", "cleanser", "gentle"], "attributes": {"volume_ml": 120, "skin_type": "sensitive"}, "popularity": 70, "rating": 4.1, "like": 75 },
# #     { "id": "20", "name": "Adjustable Brightness LED Desk Lamp", "category": "Electrical Goods", "price": 299000, "tags": ["lighting", "LED", "desk"], "attributes": {"modes": 3, "power_w": 8}, "popularity": 60, "rating": 4.0, "like": 60 },
# #     { "id": "21", "name": "Ceramic Dinner Set for 6", "category": "Kitchen", "price": 599000, "tags": ["dinnerware", "ceramic", "dishware"], "attributes": {"pieces": 24}, "popularity": 85, "rating": 4.3, "like": 105 },
# #     { "id": "22", "name": "Wireless Gaming Mouse", "category": "Computer Accessories", "price": 450000, "tags": ["gaming", "mouse", "RGB", "wireless"], "attributes": {"dpi_max": 16000}, "popularity": 150, "rating": 4.6, "like": 300 },
# #     { "id": "23", "name": "Non-Slip Yoga Mat", "category": "Sports", "price": 229000, "tags": ["yoga", "fitness", "mat"], "attributes": {"thickness_mm": 6}, "popularity": 90, "rating": 4.2, "like": 120 },
# #     { "id": "24", "name": "3-Socket Extension Cord + 2 USB", "category": "Household Electrical", "price": 179000, "tags": ["extension", "power", "usb"], "attributes": {"outlets": 3, "usb_ports": 2}, "popularity": 100, "rating": 4.4, "like": 140 },
# #     { "id": "25", "name": "Mint Oil Breath Mints", "category": "Snacks", "price": 49000, "tags": ["snack", "mint", "breath"], "attributes": {"flavor": "Mint"}, "popularity": 50, "rating": 4.0, "like": 40 },
# #     { "id": "26", "name": "Mini Coffee Maker", "category": "Kitchen", "price": 990000, "tags": ["coffee", "kitchen", "appliance"], "attributes": {"watts": 600}, "popularity": 160, "rating": 4.7, "like": 420 }
# # ]

# products= [
#     {
#         "id": "31",
#         "name": "Unisex Cotton T-Shirt",
#         "description": "A comfortable cotton t-shirt suitable for all occasions.",
#         "category": "Fashion",
#         "price": 199000,
#         "sku": "Tshirt001",
#         "attributes": {
#             "color": "White",
#             "size": "M",
#             "material": "Cotton"
#         }
#     },
#     {
#         "id": "32",
#         "name": "Wireless Bluetooth Headphones",
#         "description": "High-quality wireless headphones with noise cancellation.",
#         "category": "Electronics",
#         "price": 890000,
#         "sku": "Headphone001",
#         "attributes": {
#             "color": "Black",
#             "battery_hours": 30
#         }
#     },
#     {
#         "id": "33",
#         "name": "500ml Insulated Water Bottle",
#         "description": "Keeps your drinks hot or cold for hours.",
#         "category": "Home Goods",
#         "price": 249000,
#         "sku": "Bottle001",
#         "attributes": {
#             "material": "Stainless Steel",
#             "capacity_ml": 500
#         }
#     },
#     {
#         "id": "34",
#         "name": "15.6 Inch Laptop Backpack",
#         "description": "Stylish and durable backpack for laptops.",
#         "category": "Accessories",
#         "price": 399000,
#         "sku": "Backpack001",
#         "attributes": {
#             "fits_laptop": "15.6 inch",
#             "material": "Polyester"
#         }
#     },
#     {
#         "id": "35",
#         "name": "Gentle Facial Cleanser 120ml",
#         "description": "A gentle cleanser suitable for sensitive skin.",
#         "category": "Cosmetics",
#         "price": 149000,
#         "sku": "Cleanser001",
#         "attributes": {
#             "volume_ml": 120,
#             "skin_type": "sensitive"
#         }
#     },
#     {
#         "id": "36",
#         "name": "Adjustable Brightness LED Desk Lamp",
#         "description": "A modern desk lamp with adjustable brightness.",
#         "category": "Electrical Goods",
#         "price": 299000,
#         "sku": "Lamp001",
#         "attributes": {
#             "modes": 3,
#             "power_w": 8
#         }
#     },
#     {
#         "id": "37",
#         "name": "Ceramic Dinner Set for 6",
#         "description": "Elegant dinnerware set for family gatherings.",
#         "category": "Kitchen",
#         "price": 599000,
#         "sku": "DinnerSet001",
#         "attributes": {
#             "pieces": 24
#         }
#     },
#     {
#         "id": "38",
#         "name": "Wireless Gaming Mouse",
#         "description": "High precision gaming mouse with RGB lighting.",
#         "category": "Computer Accessories",
#         "price": 450000,
#         "sku": "Mouse001",
#         "attributes": {
#             "dpi_max": 16000
#         }
#     },
#     {
#         "id": "39",
#         "name": "Non-Slip Yoga Mat",
#         "description": "Perfect for yoga and fitness enthusiasts.",
#         "category": "Sports",
#         "price": 229000,
#         "sku": "YogaMat001",
#         "attributes": {
#             "thickness_mm": 6
#         }
#     },
#     {
#         "id": "40",
#         "name": "3-Socket Extension Cord + 2 USB",
#         "description": "Convenient extension cord with USB ports.",
#         "category": "Household Electrical",
#         "price": 179000,
#         "sku": "ExtensionCord001",
#         "attributes": {
#             "outlets": 3,
#             "usb_ports": 2
#         }
#     },
#     {
#         "id": "41",
#         "name": "Mint Oil Breath Mints",
#         "description": "Refreshing mints with mint oil flavor.",
#         "category": "Snacks",
#         "price": 49000,
#         "sku": "Mint001",
#         "attributes": {
#             "flavor": "Mint"
#         }
#     },
#     {
#         "id": "42",
#         "name": "Mini Coffee Maker",
#         "description": "Compact coffee maker for quick brews.",
#         "category": "Kitchen",
#         "price": 990000,
#         "sku": "CoffeeMaker001",
#         "attributes": {
#             "watts": 600
#         }
#     },
#     {
#         "id": "43",
#         "name": "Portable Phone Charger",
#         "description": "High-capacity power bank for on-the-go charging.",
#         "category": "Electronics",
#         "price": 299000,
#         "sku": "PowerBank001",
#         "attributes": {
#             "capacity_mAh": 10000
#         }
#     },
#     {
#         "id": "44",
#         "name": "Smartwatch with Heart Rate Monitor",
#         "description": "Stylish smartwatch with fitness tracking features.",
#         "category": "Wearables",
#         "price": 1490000,
#         "sku": "Smartwatch001",
#         "attributes": {
#             "features": ["heart_rate", "step_count", "notifications"]
#         }
#     },
#     {
#         "id": "45",
#         "name": "Electric Toothbrush",
#         "description": "Rechargeable electric toothbrush for effective cleaning.",
#         "category": "Health & Beauty",
#         "price": 799000,
#         "sku": "Toothbrush001",
#         "attributes": {
#             "mode": "clean",
#             "battery_life_hours": 10
#         }
#     },
#     {
#         "id": "46",
#         "name": "Yoga Block",
#         "description": "Supportive block for yoga practice.",
#         "category": "Fitness",
#         "price": 99000,
#         "sku": "YogaBlock001",
#         "attributes": {
#             "material": "Foam",
#             "dimensions": "23x15x10 cm"
#         }
#     }
# ]


# # Send POST requests one by one
# for idx, product in enumerate(products, start=1):
#     resp = requests.post(endpoint, headers=headers, data=json.dumps(product))
#     print(f"POST #{idx}: status={resp.status_code}, body={resp.text}")


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
            "Portable Speaker"
        ],
        "keywords": [
            "wireless", "bluetooth", "noise cancelling",
            "deep bass", "high quality sound", "long battery life"
        ],
        "attributes": lambda: {
            "brand": random.choice(["SoundMax", "AudioPro", "BeatX"]),
            "battery_life": random.choice(["20h", "24h", "30h"]),
            "connectivity": "Bluetooth"
        }
    },
    "Gaming Accessories": {
        "names": [
            "Gaming Mouse",
            "Mechanical Keyboard",
            "Gaming Headset"
        ],
        "keywords": [
            "gaming", "rgb lighting", "high precision",
            "ergonomic design", "fast response"
        ],
        "attributes": lambda: {
            "brand": random.choice(["ProGamer", "HyperPlay"]),
            "rgb": True,
            "dpi": random.choice([8000, 12000, 16000])
        }
    },
    "Wearables": {
        "names": [
            "Smart Watch",
            "Fitness Tracker"
        ],
        "keywords": [
            "heart rate monitoring", "sleep tracking",
            "fitness", "gps", "waterproof"
        ],
        "attributes": lambda: {
            "brand": random.choice(["FitLife", "HealthPlus"]),
            "gps": random.choice([True, False]),
            "waterproof": True
        }
    },
    "Sportswear": {
        "names": [
            "Running Shoes",
            "Training Shoes"
        ],
        "keywords": [
            "lightweight", "breathable mesh",
            "comfortable", "durable sole"
        ],
        "attributes": lambda: {
            "brand": random.choice(["RunFast", "ActiveWear"]),
            "material": "Mesh",
            "gender": random.choice(["Men", "Women"])
        }
    }
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

    return {
        "id": str(uuid4()),
        "name": name,
        "description": description,
        "category": category,
        "price": random_price(category),
        "sku": "SKU-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8)),
        "attributes": config["attributes"]()
    }


def post_product(product):
    response = requests.post(API_URL, json=product)
    if response.status_code not in (200, 201):
        print("❌ Failed:", response.status_code, response.text)
    else:
        print("✅ Created:", product["name"], "|", product["id"])


def main(total=50):
    print(f"🚀 Generating {total} products...\n")
    for _ in range(total):
        product = generate_product()
        post_product(product)


if __name__ == "__main__":
    main(total=100)

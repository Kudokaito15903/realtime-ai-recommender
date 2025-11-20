"""
Simple UI for AI Recommendation System using pure Python
Alternative to Streamlit for testing the system
"""

import sys
import os
import json
import time
from typing import Dict, List, Any

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def load_backend_services():
    """Load backend services"""
    try:
        from adapters.factory import get_vector_store, get_event_processor, get_backend_info
        from models.embeddings import get_embedding_model

        print("Loading backend services...")

        services = {
            'vector_store': get_vector_store(),
            'event_processor': get_event_processor(),
            'embedding_model': get_embedding_model(),
            'backend_info': get_backend_info()
        }

        print("SUCCESS: Backend services loaded successfully!")
        return services

    except Exception as e:
        print(f"ERROR: Failed to load backend services: {e}")
        return None

def display_backend_status(services):
    """Display backend service status"""
    if not services:
        return False

    print("\n" + "="*50)
    print("🔧 BACKEND STATUS")
    print("="*50)

    info = services['backend_info']

    # Status indicators
    statuses = {
        "Vector Store": "✅" if services['vector_store'] else "❌",
        "Event Processor": "✅" if services['event_processor'] else "❌",
        "Embedding Model": "✅" if services['embedding_model'] else "❌"
    }

    for service, status in statuses.items():
        print(f"{status} {service}")

    print("\n📋 Configuration:")
    print(f"   Backend Type: {info.get('backend_type', 'Unknown')}")
    print(f"   Vector Store: {info.get('vector_store', 'Unknown')}")
    print(f"   Event Processor: {info.get('event_processor', 'Unknown')}")

    cloud_services = info.get('cloud_services', {})
    print(f"   Pinecone Configured: {cloud_services.get('pinecone_configured', False)}")
    print(f"   Supabase Configured: {cloud_services.get('supabase_configured', False)}")

    return True

def create_sample_products():
    """Create sample product data"""
    return [
        {
            "id": "demo-001",
            "name": "Wireless Bluetooth Headphones",
            "description": "High-quality wireless headphones with noise cancellation",
            "category": "electronics",
            "price": 299.99
        },
        {
            "id": "demo-002",
            "name": "Smart Fitness Tracker",
            "description": "Advanced fitness tracker with heart rate monitoring",
            "category": "electronics",
            "price": 199.99
        },
        {
            "id": "demo-003",
            "name": "Ergonomic Office Chair",
            "description": "Professional office chair with lumbar support",
            "category": "furniture",
            "price": 449.99
        }
    ]

def add_product_interactive(services):
    """Interactive product addition"""
    print("\n" + "="*50)
    print("➕ ADD NEW PRODUCT")
    print("="*50)

    try:
        product_id = input("Product ID: ").strip()
        if not product_id:
            print("❌ Product ID is required!")
            return

        product_name = input("Product Name: ").strip()
        if not product_name:
            print("❌ Product name is required!")
            return

        product_description = input("Description: ").strip()
        product_category = input("Category (electronics/furniture/clothing/books): ").strip() or "electronics"

        try:
            product_price = float(input("Price: ") or "0.00")
        except ValueError:
            product_price = 0.00

        # Create product data
        product_data = {
            "id": product_id,
            "name": product_name,
            "description": product_description,
            "category": product_category,
            "price": product_price,
            "created_at": time.time()
        }

        print("\n🔄 Processing product...")

        # Generate embedding
        print("   Generating AI embedding...")
        embedding = services['embedding_model'].get_product_embedding(product_data)
        print(f"   ✅ Generated {len(embedding)}-dimensional embedding")

        # Store in vector database
        print("   Storing in vector database...")
        metadata = {
            'name': product_name,
            'category': product_category,
            'price': str(product_price)
        }

        success = services['vector_store'].store_product_embedding(
            product_id, embedding, metadata
        )

        if success:
            print(f"✅ Product '{product_name}' added successfully!")

            # Try to publish event
            try:
                event_id = services['event_processor'].publish_product_created(product_data)
                if event_id:
                    print(f"📡 Event published: {event_id}")
            except Exception as e:
                print(f"⚠️ Product added but event publishing failed: {e}")

        else:
            print("❌ Failed to store product in vector database")

    except KeyboardInterrupt:
        print("\n❌ Operation cancelled")
    except Exception as e:
        print(f"❌ Error adding product: {e}")

def search_products_interactive(services):
    """Interactive product search"""
    print("\n" + "="*50)
    print("🔍 PRODUCT SEARCH")
    print("="*50)

    print("Search Options:")
    print("1. Text Search")
    print("2. Product Similarity")
    print("3. Load Sample Products")

    choice = input("Choose option (1-3): ").strip()

    try:
        if choice == "1":
            # Text search
            query = input("Enter search query: ").strip()
            if not query:
                print("❌ Search query is required!")
                return

            max_results = int(input("Max results (default 10): ") or "10")
            min_similarity = float(input("Min similarity 0.0-1.0 (default 0.3): ") or "0.3")

            print(f"\n🔍 Searching for '{query}'...")

            # Generate embedding for search query
            query_embedding = services['embedding_model'].get_text_embedding(query)

            # Search similar products
            results = services['vector_store'].find_similar_products(
                embedding=query_embedding,
                limit=max_results,
                min_score=min_similarity
            )

            display_search_results(results, f"Text search: '{query}'")

        elif choice == "2":
            # Product similarity
            product_id = input("Enter product ID: ").strip()
            if not product_id:
                print("❌ Product ID is required!")
                return

            max_results = int(input("Max results (default 5): ") or "5")
            min_similarity = float(input("Min similarity 0.0-1.0 (default 0.7): ") or "0.7")

            print(f"\n🔍 Finding products similar to '{product_id}'...")

            # Get product embedding
            product_embedding = services['vector_store'].get_product_embedding(product_id)

            if product_embedding is not None:
                # Find similar products
                results = services['vector_store'].find_similar_products(
                    embedding=product_embedding,
                    limit=max_results + 1,
                    min_score=min_similarity
                )

                # Filter out the original product
                results = [r for r in results if r['product_id'] != product_id][:max_results]
                display_search_results(results, f"Similar to: '{product_id}'")
            else:
                print(f"❌ Product '{product_id}' not found in vector database")

        elif choice == "3":
            # Load sample products
            print("\n📦 Loading sample products...")
            sample_products = create_sample_products()
            success_count = 0

            for product in sample_products:
                try:
                    print(f"   Adding {product['name']}...")

                    # Generate embedding
                    embedding = services['embedding_model'].get_product_embedding(product)

                    # Store in vector database
                    metadata = {
                        'name': product['name'],
                        'category': product['category'],
                        'price': str(product['price'])
                    }

                    success = services['vector_store'].store_product_embedding(
                        product['id'], embedding, metadata
                    )

                    if success:
                        success_count += 1
                        print(f"   ✅ {product['name']} added")

                except Exception as e:
                    print(f"   ❌ Failed to add {product['name']}: {e}")

            print(f"\n✅ Loaded {success_count}/{len(sample_products)} sample products!")

            if success_count > 0:
                print("\nSample products loaded:")
                for product in sample_products:
                    print(f"   • {product['id']}: {product['name']} (${product['price']})")

    except KeyboardInterrupt:
        print("\n❌ Operation cancelled")
    except Exception as e:
        print(f"❌ Search failed: {e}")

def display_search_results(results: List[Dict], search_info: str):
    """Display search results"""
    print(f"\n📊 SEARCH RESULTS - {search_info}")
    print("="*50)

    if not results:
        print("❌ No products found matching your criteria")
        return

    print(f"Found {len(results)} products:")
    print()

    for i, result in enumerate(results, 1):
        metadata = result.get('metadata', {})
        print(f"{i}. 🏷️  Product ID: {result['product_id']}")
        print(f"   📦 Name: {metadata.get('name', 'Unknown')}")
        print(f"   🏷️  Category: {metadata.get('category', 'Unknown')}")
        print(f"   💰 Price: ${metadata.get('price', 'N/A')}")
        print(f"   📊 Similarity: {result['similarity_score']:.2%}")
        print()

def show_analytics(services):
    """Show analytics and database stats"""
    print("\n" + "="*50)
    print("📊 ANALYTICS & DATABASE STATS")
    print("="*50)

    # Vector store stats
    if hasattr(services['vector_store'], 'get_index_stats'):
        try:
            print("🔄 Loading database statistics...")
            stats = services['vector_store'].get_index_stats()

            print("📈 Database Statistics:")
            print(f"   Total Vectors: {stats.get('total_vector_count', 'N/A')}")
            print(f"   Dimensions: {stats.get('dimension', 'N/A')}")
            print(f"   Index Fullness: {stats.get('index_fullness', 0):.1%}")
            print(f"   Namespaces: {len(stats.get('namespaces', {}))}")

            print("\n🔍 Detailed Stats:")
            print(json.dumps(stats, indent=2))

        except Exception as e:
            print(f"❌ Failed to load statistics: {e}")
    else:
        print("ℹ️  Vector database statistics not available for this backend")

    # Backend info
    print("\n🔧 Backend Configuration:")
    backend_info = services['backend_info']
    print(json.dumps(backend_info, indent=2))

def main_menu():
    """Display main menu"""
    print("\n" + "="*50)
    print("🛍️  AI RECOMMENDATION ENGINE - MAIN MENU")
    print("="*50)
    print("1. ➕ Add New Product")
    print("2. 🔍 Search & Recommend")
    print("3. 📊 Analytics & Stats")
    print("4. 🔧 Backend Status")
    print("5. ❌ Exit")
    print()

def main():
    """Main application"""
    print("AI RECOMMENDATION ENGINE")
    print("Modern Product Recommendations powered by Pinecone + Supabase")
    print("="*60)

    # Load backend services
    services = load_backend_services()
    if not display_backend_status(services):
        print("\n❌ Cannot proceed without backend services. Please check your configuration.")
        return

    while True:
        try:
            main_menu()
            choice = input("Choose option (1-5): ").strip()

            if choice == "1":
                add_product_interactive(services)
            elif choice == "2":
                search_products_interactive(services)
            elif choice == "3":
                show_analytics(services)
            elif choice == "4":
                display_backend_status(services)
            elif choice == "5":
                print("\n👋 Thanks for using the AI Recommendation Engine!")
                break
            else:
                print("❌ Invalid option. Please choose 1-5.")

        except KeyboardInterrupt:
            print("\n\n👋 Thanks for using the AI Recommendation Engine!")
            break
        except Exception as e:
            print(f"\n❌ An error occurred: {e}")

if __name__ == "__main__":
    main()
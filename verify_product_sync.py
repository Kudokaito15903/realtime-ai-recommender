import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.getcwd())

# Mock sentence_transformers before importing modules that need it
sys.modules["sentence_transformers"] = MagicMock()

from consumers.modern_product_event_consumer import ModernProductEventConsumer


class TestModernProductEventConsumer(unittest.TestCase):
    def setUp(self):
        # Mocks
        self.mock_event_processor = MagicMock()
        self.mock_vector_store = MagicMock()
        self.mock_product_store = MagicMock()
        self.mock_embedding_model = MagicMock()

        # Patch the factory methods
        self.patcher1 = patch(
            "consumers.modern_product_event_consumer.get_event_processor",
            return_value=self.mock_event_processor,
        )
        self.patcher2 = patch(
            "consumers.modern_product_event_consumer.get_vector_store",
            return_value=self.mock_vector_store,
        )
        self.patcher3 = patch(
            "consumers.modern_product_event_consumer.get_product_store",
            return_value=self.mock_product_store,
        )
        self.patcher4 = patch(
            "consumers.modern_product_event_consumer.get_embedding_model",
            return_value=self.mock_embedding_model,
        )

        self.patcher1.start()
        self.patcher2.start()
        self.patcher3.start()
        self.patcher4.start()

        # Mock embedding return value
        self.mock_embedding_model.get_product_embedding.return_value = [0.1, 0.2, 0.3]
        self.mock_vector_store.store_product_embedding.return_value = True
        self.mock_vector_store.delete_product_embedding.return_value = True
        self.mock_product_store.store_product.return_value = True
        self.mock_product_store.delete_product.return_value = True

        self.consumer = ModernProductEventConsumer(consumer_id="test-consumer")

    def tearDown(self):
        self.patcher1.stop()
        self.patcher2.stop()
        self.patcher3.stop()
        self.patcher4.stop()

    def test_product_upsert_syncs_to_store(self):
        product_id = "test_product_123"
        product_data = {
            "id": product_id,
            "name": "Test Product",
            "category": "Electronics",
            "price": 100.0,
        }
        event = {
            "event_type": "create",
            "product_id": product_id,
            "data": product_data,
            "timestamp": "2023-01-01T00:00:00Z",
        }

        self.consumer._handle_event(event)

        # Verify product store sync
        self.mock_product_store.store_product.assert_called_with(product_data)

        # Verify vector store sync
        self.mock_vector_store.store_product_embedding.assert_called()
        args, kwargs = self.mock_vector_store.store_product_embedding.call_args
        self.assertEqual(kwargs["product_id"], product_id)
        self.assertEqual(kwargs["metadata"]["name"], "Test Product")

    def test_product_delete_syncs_to_store(self):
        product_id = "test_product_123"
        event = {
            "event_type": "delete",
            "product_id": product_id,
            "timestamp": "2023-01-01T00:00:00Z",
        }

        self.consumer._handle_event(event)

        # Verify product store delete
        self.mock_product_store.delete_product.assert_called_with(product_id)

        # Verify vector store delete
        self.mock_vector_store.delete_product_embedding.assert_called_with(product_id)


if __name__ == "__main__":
    unittest.main()

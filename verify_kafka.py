import sys
import os
import unittest
import json
import time
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.getcwd())

# Mock kafka first
mock_kafka = MagicMock()
sys.modules["kafka"] = mock_kafka
sys.modules["kafka.errors"] = MagicMock()

# Now import the adapter which will use the mock
from adapters.messaging.kafka_adapter import KafkaEventProcessor


class TestKafkaEventProcessor(unittest.TestCase):
    def setUp(self):
        # Reset mocks
        mock_kafka.KafkaProducer.reset_mock()
        mock_kafka.KafkaConsumer.reset_mock()

        self.processor = KafkaEventProcessor(
            bootstrap_servers="localhost:9092",
            topic="test-topic",
            group_id="test-group",
        )
        # Verify producer init
        mock_kafka.KafkaProducer.assert_called()
        self.producer_instance = self.processor.producer

    def test_publish_event(self):
        product_data = {"id": "123", "name": "Test"}

        # Test publish
        self.processor.publish_product_created(product_data)

        # Verify producer.send called
        # The call is producer.send(topic, event)
        self.producer_instance.send.assert_called()
        args, kwargs = self.producer_instance.send.call_args

        # Args[0] is topic, Args[1] is event (if positional)
        # OR kwargs['topic'] and kwargs['value']?
        # The code is: self.producer.send(self.topic, event) -> positional

        call_topic = args[0]
        call_event = args[1]

        self.assertEqual(call_topic, "test-topic")
        self.assertEqual(call_event["event_type"], "create")
        self.assertEqual(call_event["product_id"], "123")
        self.assertEqual(call_event["data"], product_data)

    def test_consume_event(self):
        # Mock consumer instance
        mock_consumer_instance = MagicMock()
        mock_kafka.KafkaConsumer.return_value = mock_consumer_instance

        # Mock message
        mock_message = MagicMock()
        mock_message.value = {
            "event_type": "create",
            "product_id": "123",
            "data": {"id": "123"},
            "timestamp": 1234567890,
        }

        # Mock poll return (one batch then exception to break loop)
        # poll returns Dict[TopicPartition, List[ConsumerRecord]]
        mock_consumer_instance.poll.side_effect = [
            {MagicMock(): [mock_message]},
            Exception("Stop Loop"),
        ]

        # Handler
        handler = MagicMock()
        self.processor.set_event_handler(handler)

        # Start consumer loop directly to catch exception
        try:
            self.processor._consume_loop("test-consumer")
        except Exception as e:
            if str(e) != "Stop Loop":
                raise

        # Verify handler called
        handler.assert_called_with(mock_message.value)


if __name__ == "__main__":
    unittest.main()

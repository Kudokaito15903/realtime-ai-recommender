import time
from pymongo import MongoClient
from kafka import KafkaProducer, KafkaConsumer, KafkaAdminClient
from kafka.admin import NewTopic

# --- Configuration ---
KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
KAFKA_TOPIC = "product-events"
MONGODB_URI = "mongodb://root:root@localhost:27017/"
MONGODB_DB = "realtime_ai"


def check_mongodb():
    print("--- 1. Kiểm tra MongoDB ---")
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        db = client[MONGODB_DB]
        client.admin.command("ping")
        print(f"✅ Kết nối MongoDB thành công!")
        print(f"✅ Database: {MONGODB_DB}\n")
    except Exception as e:
        print(f"❌ Lỗi kết nối MongoDB: {e}\n")


def check_kafka():
    print("--- 2. Kiểm tra Kafka ---")

    # 2.1. Kiểm tra & Tạo Topic nếu chưa có
    try:
        admin_client = KafkaAdminClient(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS, request_timeout_ms=5000
        )
        existing_topics = admin_client.list_topics()
        if KAFKA_TOPIC not in existing_topics:
            print(f"⚠️  Topic '{KAFKA_TOPIC}' chưa tồn tại. Đang khởi tạo...")
            topic_list = [
                NewTopic(name=KAFKA_TOPIC, num_partitions=1, replication_factor=1)
            ]
            admin_client.create_topics(new_topics=topic_list, validate_only=False)
            print(f"✅ Đã tạo topic '{KAFKA_TOPIC}'")
        else:
            print(f"✅ Topic '{KAFKA_TOPIC}' đã sẵn sàng.")
        admin_client.close()
    except Exception as e:
        print(f"❌ Lỗi Admin Client (Có thể Kafka chưa up xong): {e}")
        return

    # 2.2. Kiểm tra Producer
    try:
        # Xóa 'timeout_ms' ở đây, dùng 'request_timeout_ms' nếu cần
        producer = KafkaProducer(
            bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS], request_timeout_ms=5000
        )
        test_msg = b"Test message: " + str(time.time()).encode()
        future = producer.send(KAFKA_TOPIC, test_msg)
        future.get(timeout=10)  # Chờ xác nhận gửi thành công
        print(f"✅ Kafka Producer: Đã gửi tin nhắn test thành công.")
        producer.close()
    except Exception as e:
        print(f"❌ Lỗi Kafka Producer: {e}")
        return

    # 2.3. Kiểm tra Consumer
    try:
        consumer = KafkaConsumer(
            KAFKA_TOPIC,
            bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
            auto_offset_reset="earliest",
            consumer_timeout_ms=5000,  # Thời gian đợi tin nhắn trước khi tự đóng
        )
        print(f"✅ Kafka Consumer: Đang kiểm tra dữ liệu...")

        received = False
        for message in consumer:
            if message.value == test_msg:
                print(f"✅ Kafka Consumer: Đã nhận đúng tin nhắn vừa gửi!")
                received = True
                break

        if not received:
            print(
                "⚠️ Kafka Consumer: Kết nối được nhưng không tìm thấy tin nhắn vừa gửi."
            )
        consumer.close()
    except Exception as e:
        print(f"❌ Lỗi Kafka Consumer: {e}")


if __name__ == "__main__":
    check_mongodb()
    check_kafka()
    print("\n--- Hoàn tất kiểm tra ---")

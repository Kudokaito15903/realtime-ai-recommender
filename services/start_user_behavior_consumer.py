# import os
# import time
# import signal
# import sys
# import threading
# from loguru import logger

# # Add project root to path
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# def start_user_behavior_consumer(consumer_id: str = None):
#     consumer = UserBehaviorConsumer(consumer_id)

#     def shutdown_handler(sig, frame):
#         logger.info("Shutting down UserBehaviorConsumer")
#         consumer.stop()
#         sys.exit(0)

#     signal.signal(signal.SIGINT, shutdown_handler)
#     signal.signal(signal.SIGTERM, shutdown_handler)

#     consumer.start()

#     logger.info("UserBehaviorConsumer is running")
#     while True:
#         time.sleep(1)


# if __name__ == "__main__":
#     import argparse

#     parser = argparse.ArgumentParser("User Behavior Consumer")
#     parser.add_argument("--consumer-id", type=str)
#     args = parser.parse_args()

#     start_user_behavior_consumer(args.consumer_id)

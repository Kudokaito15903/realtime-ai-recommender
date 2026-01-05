import os
import sys
import time
import signal
from loguru import logger

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from consumers.product_event_handler import ProductEventHandler
from consumers.content_event_handler import ContentEventHandler


class VectorWorkerApp:
    """
    Vector Worker App
    - Starts product & content Kafka consumers
    - Handles graceful shutdown
    """

    def __init__(self):
        self.product_handler = ProductEventHandler(worker_name="product-vector-worker")
        self.content_handler = ContentEventHandler(worker_name="content-vector-worker")

        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self):
        if self._running:
            return

        logger.info("Starting Vector Worker Application...")

        self.product_handler.start()
        self.content_handler.start()

        self._running = True
        logger.info("Vector Worker Application started")

    def stop(self):
        if not self._running:
            return

        logger.info("Stopping Vector Worker Application...")

        try:
            self.product_handler.stop()
        except Exception:
            logger.exception("Error stopping product handler")

        try:
            self.content_handler.stop()
        except Exception:
            logger.exception("Error stopping content handler")

        self._running = False
        logger.info("Vector Worker Application stopped")

    # ------------------------------------------------------------------
    # Blocking loop
    # ------------------------------------------------------------------
    def run_forever(self):
        self.start()

        logger.info("Vector workers running... Press Ctrl+C to stop.")
        while self._running:
            time.sleep(1)


# ----------------------------------------------------------------------
# Process bootstrap
# ----------------------------------------------------------------------
def main():
    app = VectorWorkerApp()

    def shutdown_handler(sig, frame):
        logger.info(f"Shutdown signal received ({sig})")
        app.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    app.run_forever()


if __name__ == "__main__":
    main()

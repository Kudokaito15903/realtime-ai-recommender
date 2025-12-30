import os
import sys
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import uvicorn

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import API_HOST, API_PORT, DEBUG_MODE
from api.routes import modern_products, recommend, chatbot, content
from services.product_event_handler import get_product_event_handler
from services.content_event_handler import get_content_event_handler

# from api.middleware.logging import LoggingMiddleware


# Initialize FastAPI app
app = FastAPI(
    title="E-commerce Real-time AI API (Pinecone stack)",
    description="API for real-time product analysis and recommendations powered by Pinecone",
    version="2.0.0",
    debug=DEBUG_MODE,
)

# Add CORS middleware (optional - keep disabled by default)
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],  # In production, restrict this to your frontend domain
#     allow_credentials=False,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )
#
# # Add custom logging middleware
# app.add_middleware(LoggingMiddleware)

# Include routers
app.include_router(modern_products.router, prefix="/products", tags=["products"])
app.include_router(
    recommend.router, prefix="/recommendations", tags=["recommendations"]
)
app.include_router(chatbot.router, prefix="/chatbot", tags=["chatbot"])
app.include_router(content.router, prefix="/content", tags=["content"])


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": time.time()}


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Middleware to track processing time for each request"""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


if __name__ == "__main__":
    # Configure logger
    logger.info(f"Starting API server on {API_HOST}:{API_PORT}")

    # Start server
    uvicorn.run("api.app:app", host=API_HOST, port=API_PORT, reload=DEBUG_MODE)


# Start background event handler when app starts


@app.on_event("startup")
async def startup_event():
    try:
        # Start product event handler
        product_handler = get_product_event_handler()
        product_handler.start()
        logger.info("Product event handler started on app startup")

        # Start content event handler
        content_handler = get_content_event_handler()
        content_handler.start()
        logger.info("Content event handler started on app startup")
    except Exception as e:
        logger.error(f"Failed to start event handlers on startup: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    try:
        handler = get_product_event_handler()
        handler.stop()
        logger.info("Product event handler stopped on shutdown")
    except Exception as e:
        logger.error(f"Error stopping product event handler on shutdown: {e}")

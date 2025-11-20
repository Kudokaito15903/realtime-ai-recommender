 
import os
import sys
import time
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import uvicorn

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import API_HOST, API_PORT, DEBUG_MODE
from api.routes import products, recommendations
from api.middleware.logging import LoggingMiddleware


# Initialize FastAPI app
app = FastAPI(
    title="E-commerce Real-time AI API",
    description="API for real-time product analysis and recommendations",
    version="1.0.0",
    debug=DEBUG_MODE
)

# Add CORS middleware
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],  # In production, restrict this to your frontend domain
#     allow_credentials=False,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # Add custom logging middleware
# app.add_middleware(LoggingMiddleware)

# Include routers
app.include_router(products.router, prefix="/products", tags=["products"])
app.include_router(recommendations.router, prefix="/recommendations", tags=["recommendations"])


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
    uvicorn.run(
        "api.app:app",
        host=API_HOST,
        port=API_PORT,
        reload=DEBUG_MODE
    )
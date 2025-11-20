 
import time
import json
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from loguru import logger
import uuid


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging requests and responses"""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable):
        # Generate a unique request ID
        request_id = str(uuid.uuid4())
        
        # Set request ID in headers for correlation
        request.state.request_id = request_id
        
        # Log request
        await self._log_request(request, request_id)
        
        # Process request and measure time
        start_time = time.time()
        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            
            # Add custom headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = str(process_time)
            
            # Log response
            self._log_response(request, response, process_time, request_id)
            
            return response
            
        except Exception as exc:
            process_time = time.time() - start_time
            logger.error(
                f"Request failed: {request.method} {request.url.path} "
                f"- Error: {str(exc)} - Request ID: {request_id} "
                f"- Took: {process_time:.4f}s"
            )
            raise
    
    async def _log_request(self, request: Request, request_id: str):
        """Log incoming request details"""
        # Get client IP
        host = request.client.host if request.client else "unknown"
        
        # Get path and query params
        path = request.url.path
        query_params = str(request.query_params) if request.query_params else ""
        
        # Get headers (excluding sensitive ones)
        headers = {
            k.lower(): v for k, v in request.headers.items() 
            if k.lower() not in ("authorization", "cookie", "x-api-key")
        }
        
        # Try to read body for specific content types
        body = None
        if request.method in ("POST", "PUT", "PATCH"):
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    body_bytes = await request.body()
                    if body_bytes:
                        body = body_bytes.decode()
                        # Truncate if too long
                        if len(body) > 1000:
                            body = body[:1000] + "... [truncated]"
                except Exception:
                    body = "[Error reading body]"
        
        # Log the request
        logger.info(
            f"Request: {request.method} {path}{query_params} "
            f"- Client: {host} - Request ID: {request_id} "
            f"- UA: {request.headers.get('user-agent', 'unknown')}"
        )
        
        # Log body if available (debug level)
        if body:
            try:
                # Try to parse as JSON for nicer formatting
                parsed_body = json.loads(body)
                logger.debug(f"Request Body (ID: {request_id}): {json.dumps(parsed_body, indent=2)}")
            except json.JSONDecodeError:
                logger.debug(f"Request Body (ID: {request_id}): {body}")
    
    def _log_response(self, request: Request, response: Response, process_time: float, request_id: str):
        """Log outgoing response details"""
        logger.info(
            f"Response: {request.method} {request.url.path} "
            f"- Status: {response.status_code} - Request ID: {request_id} "
            f"- Took: {process_time:.4f}s"
        )
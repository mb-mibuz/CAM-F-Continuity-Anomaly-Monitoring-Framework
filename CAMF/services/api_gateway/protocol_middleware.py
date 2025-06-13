"""
Protocol negotiation middleware for API Gateway.

Handles automatic protocol detection and conversion between JSON and MessagePack
for internal service communication while maintaining JSON for client communication.
"""

from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

from CAMF.common.protocol import (
    ProtocolType, 
    protocol_manager
)


class ProtocolNegotiationMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle protocol negotiation and conversion.
    
    - Accepts both JSON and MessagePack from clients
    - Uses MessagePack for internal Python service communication
    - Always returns JSON to clients (frontend compatibility)
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Detect incoming protocol from Content-Type header
        content_type = request.headers.get("content-type", "").lower()
        
        # Parse request body if present
        if request.method in ["POST", "PUT", "PATCH"] and content_type:
            # Store original body for later use
            body = await request.body()
            
            if body:
                try:
                    # Deserialize based on content type
                    if "msgpack" in content_type:
                        data = protocol_manager.deserialize(body, ProtocolType.MSGPACK)
                    else:
                        data = protocol_manager.deserialize(body, ProtocolType.JSON)
                    
                    # Store parsed data for endpoints to use
                    request.state.parsed_body = data
                    request.state.original_body = body
                except Exception as e:
                    # Log error but continue - let endpoint handle invalid data
                    request.state.parse_error = str(e)
        
        # Check Accept header to determine response format
        accept_header = request.headers.get("accept", "").lower()
        "msgpack" in accept_header and "json" not in accept_header
        
        # Process request
        response = await call_next(request)
        
        # Handle response conversion
        if isinstance(response, StarletteResponse):
            # For internal communication, we might want to use MessagePack
            # But for now, keep JSON for frontend compatibility
            # The internal service-to-service communication will use the
            # protocol abstraction layer directly
            pass
        
        return response


def setup_protocol_middleware(app):
    """Setup protocol negotiation middleware."""
    app.add_middleware(ProtocolNegotiationMiddleware)
    
    # Enable debug mode if configured
    import os
    if os.getenv("CAMF_PROTOCOL_DEBUG", "").lower() == "true":
        protocol_manager.enable_debug(True)
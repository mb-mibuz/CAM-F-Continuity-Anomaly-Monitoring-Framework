# CAMF/services/api_gateway/main.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
import uvicorn
import os
import logging

logger = logging.getLogger(__name__)

from starlette.middleware.base import BaseHTTPMiddleware

from CAMF.common.config import get_config
from CAMF.services.detector_framework import get_detector_framework_service
from pathlib import Path

from CAMF.services.storage.main import get_storage_service
from CAMF.services.capture.main import get_capture_service

# Import consolidated endpoints
from .endpoints.crud import router as crud_router
from .endpoints.detectors import router as detectors_router
from .endpoints.capture import router as capture_router
from .endpoints.monitoring import router as monitoring_router
from .endpoints.export import router as export_router

# Import remaining individual endpoints (to be deprecated)
from .error_recovery import error_recovery_middleware, setup_recovery_callbacks, start_health_monitoring, health_tracker
from .protocol_middleware import setup_protocol_middleware
from .sse_integration import setup_sse_integrations

# Individual endpoints have been consolidated into endpoint modules

class LimitUploadSize(BaseHTTPMiddleware):
    def __init__(self, app, max_upload_size: int):
        super().__init__(app)
        self.max_upload_size = max_upload_size

    async def dispatch(self, request: Request, call_next):
        if request.method == "POST":
            # Skip check for file upload endpoints which handle their own size limits
            if "/upload/" in request.url.path:
                response = await call_next(request)
                return response
                
            # Check content-length header for other POST requests
            content_length = request.headers.get("content-length")
            if content_length:
                content_length = int(content_length)
                if content_length > self.max_upload_size:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": f"File too large. Maximum size is {self.max_upload_size} bytes"},
                        headers={
                            "Access-Control-Allow-Origin": "*",
                            "Access-Control-Allow-Methods": "*",
                            "Access-Control-Allow-Headers": "*"
                        }
                    )
        
        response = await call_next(request)
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    # Startup
    print("Starting up API Gateway...")
    
    # Register API Gateway with service discovery (with protocol support)
    try:
        from CAMF.common.service_discovery import register_service
        from CAMF.common.config import env_config
        register_service(
            name="api_gateway",
            port=env_config.api_port,
            health_endpoint="/",
            supported_protocols=["json", "msgpack"]
        )
        print("✓ API Gateway registered with service discovery")
    except Exception as e:
        print(f"⚠ Failed to register with service discovery: {e}")
    
    # Set up SSE integrations
    try:
        setup_sse_integrations()
        print("✓ SSE integrations setup successfully")
    except Exception as e:
        print(f"⚠ Failed to setup SSE integrations: {e}")
        # Continue anyway - system can work without real-time events
        
    # Setup error recovery
    try:
        setup_recovery_callbacks()
        print("✓ Error recovery callbacks setup")
    except Exception as e:
        print(f"⚠ Failed to setup error recovery: {e}")
        
    # Start health monitoring
    try:
        start_health_monitoring()
        print("✓ Health monitoring started")
    except Exception as e:
        print(f"⚠ Failed to start health monitoring: {e}")
    
    yield
    
    # Shutdown
    print("Shutting down API Gateway...")
    
    # Stop health monitoring
    try:
        health_tracker.stop()
    except Exception as e:
        logger.warning(f"Failed to stop health monitoring: {e}")
    
    # Cleanup services
    storage = get_storage_service()
    if storage:
        storage.cleanup()
        
    capture_service = get_capture_service()
    if capture_service:
        capture_service.cleanup()
        
    detector_framework = get_detector_framework_service()
    if detector_framework:
        detector_framework.cleanup()
        
    print("API Gateway shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="CAMF API Gateway",
        description="Continuity Anomaly Monitoring Framework API",
        version="1.0.0",
        lifespan=lifespan
    )
    
    # Add middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add error recovery middleware using the proper pattern
    @app.middleware("http")
    async def add_error_recovery(request: Request, call_next):
        return await error_recovery_middleware(request, call_next)
    
    # Add request size limiting middleware (500MB limit)
    app.add_middleware(LimitUploadSize, max_upload_size=500 * 1024 * 1024)
    
    # Setup protocol middleware (MessagePack support)
    setup_protocol_middleware(app)
    
    # Include consolidated routers
    app.include_router(crud_router)
    app.include_router(detectors_router)
    app.include_router(capture_router)
    app.include_router(monitoring_router)
    app.include_router(export_router)
    
    # Root endpoint
    @app.get("/")
    async def root():
        return {
            "message": "CAMF API Gateway",
            "version": "1.0.0",
            "endpoints": {
                "crud": "/api/projects, /api/scenes, /api/angles, /api/takes",
                "detectors": "/api/detectors",
                "capture": "/api/capture, /api/frames, /api/upload",
                "monitoring": "/api/sse, /api/monitoring, /api/processing, /api/errors",
                "export": "/api/export, /api/notes"
            }
        }
    
    # Serve static files from frontend build
    get_config()
    frontend_path = Path(__file__).parent.parent.parent / "frontend" / "dist"
    if frontend_path.exists():
        app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="static")
        
    return app


# Create app instance for module-level access
app = create_app()


def main():
    """Run the API Gateway service."""
    # Get configuration
    get_config()
    # Use environment config or defaults
    host = os.getenv('API_HOST', '0.0.0.0')
    port = int(os.getenv('API_PORT', '8000'))
    
    # Run server
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )


if __name__ == "__main__":
    main()
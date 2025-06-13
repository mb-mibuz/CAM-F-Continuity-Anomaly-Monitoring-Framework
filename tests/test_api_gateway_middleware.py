"""
Comprehensive tests for API Gateway middleware components.
Tests protocol negotiation, error recovery, request validation, and other middleware.
"""

import pytest
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import msgpack
import json
import gzip
import time
from datetime import datetime, timedelta
import asyncio

from CAMF.services.api_gateway.protocol_middleware import ProtocolNegotiationMiddleware
from CAMF.services.api_gateway.error_recovery import error_recovery_middleware
from CAMF.common.models import Project, Scene
from CAMF.common.protocol import ProtocolType, protocol_manager


class TestProtocolNegotiationMiddleware:
    """Test protocol negotiation middleware."""
    
    @pytest.fixture
    def app(self):
        """Create test FastAPI app with middleware."""
        app = FastAPI()
        app.add_middleware(ProtocolNegotiationMiddleware)
        
        @app.post("/test")
        async def test_endpoint(request: Request):
            body = await request.body()
            return {"received": len(body), "message": "ok"}
        
        @app.get("/health")
        async def health():
            return {"status": "healthy"}
        
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)
    
    def test_json_request_handling(self, client):
        """Test handling JSON requests."""
        data = {"test": "data", "number": 42}
        
        response = client.post(
            "/test",
            json=data,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        assert response.json()["message"] == "ok"
    
    def test_msgpack_request_handling(self, client):
        """Test handling MessagePack requests."""
        data = {"test": "msgpack", "number": 123}
        packed_data = msgpack.packb(data)
        
        response = client.post(
            "/test",
            content=packed_data,
            headers={"Content-Type": "application/x-msgpack"}
        )
        
        assert response.status_code == 200
        assert response.json()["message"] == "ok"
    
    def test_default_content_type(self, client):
        """Test default content type handling."""
        # Send request without Content-Type header
        data = {"test": "default"}
        
        response = client.post("/test", json=data)
        
        assert response.status_code == 200
        assert response.json()["message"] == "ok"
    
    def test_get_request_passthrough(self, client):
        """Test GET requests pass through middleware."""
        response = client.get("/health")
        
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_invalid_msgpack(self, client):
        """Test handling invalid MessagePack data."""
        # Send invalid msgpack data
        response = client.post(
            "/test",
            content=b"invalid msgpack data",
            headers={"Content-Type": "application/x-msgpack"}
        )
        
        # Should still process the request
        assert response.status_code == 200
    
    def test_empty_body(self, client):
        """Test handling empty request body."""
        response = client.post(
            "/test",
            content=b"",
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
    
    def test_large_payload(self, client):
        """Test handling large payloads."""
        # Create large data structure
        large_data = {
            "items": [{"id": i, "data": "x" * 1000} for i in range(100)]
        }
        
        response = client.post("/test", json=large_data)
        
        assert response.status_code == 200
        assert response.json()["received"] > 100000  # Should be > 100KB


class TestErrorRecoveryMiddleware:
    """Test error recovery middleware."""
    
    @pytest.fixture
    def app(self):
        """Create test app with error recovery middleware."""
        app = FastAPI()
        
        # Add error recovery middleware
        @app.middleware("http")
        async def add_error_recovery(request: Request, call_next):
            return await error_recovery_middleware(request, call_next)
        
        @app.get("/success")
        async def success_endpoint():
            return {"status": "success"}
        
        @app.get("/error")
        async def error_endpoint():
            raise HTTPException(status_code=400, detail="Test error")
        
        @app.get("/exception")
        async def exception_endpoint():
            raise Exception("Unhandled exception")
        
        @app.get("/timeout")
        async def timeout_endpoint():
            await asyncio.sleep(10)  # Simulate long operation
            return {"status": "complete"}
        
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)
    
    def test_success_request(self, client):
        """Test successful request passes through."""
        response = client.get("/success")
        
        assert response.status_code == 200
        assert response.json()["status"] == "success"
    
    def test_http_exception_handling(self, client):
        """Test HTTP exception is handled properly."""
        response = client.get("/error")
        
        assert response.status_code == 400
        assert "Test error" in response.json()["detail"]
    
    def test_unhandled_exception(self, client):
        """Test unhandled exceptions are caught."""
        response = client.get("/exception")
        
        # Should return 500 with error details
        assert response.status_code == 500
        assert "error" in response.json()
    
    def test_request_logging(self, client):
        """Test request logging functionality."""
        with patch('logging.Logger.info') as mock_log:
            response = client.get("/success")
            
            # Should log request details
            assert mock_log.called
    
    def test_error_logging(self, client):
        """Test error logging functionality."""
        with patch('logging.Logger.error') as mock_log:
            response = client.get("/exception")
            
            # Should log error details
            assert mock_log.called
    
    def test_recovery_after_error(self, client):
        """Test system recovers after error."""
        # Cause an error
        error_response = client.get("/exception")
        assert error_response.status_code == 500
        
        # Next request should work fine
        success_response = client.get("/success")
        assert success_response.status_code == 200
    
    def test_concurrent_error_handling(self, client):
        """Test handling multiple concurrent errors."""
        import concurrent.futures
        
        def make_error_request():
            return client.get("/exception")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_error_request) for _ in range(5)]
            responses = [f.result() for f in futures]
        
        # All should return 500
        assert all(r.status_code == 500 for r in responses)
        
        # System should still be operational
        assert client.get("/success").status_code == 200


class TestMiddlewareIntegration:
    """Test multiple middleware working together."""
    
    @pytest.fixture
    def app(self):
        """Create app with multiple middleware."""
        app = FastAPI()
        
        # Add protocol middleware
        app.add_middleware(ProtocolNegotiationMiddleware)
        
        # Add error recovery middleware
        @app.middleware("http")
        async def add_error_recovery(request: Request, call_next):
            return await error_recovery_middleware(request, call_next)
        
        @app.post("/echo")
        async def echo_endpoint(request: Request):
            body = await request.body()
            return {"size": len(body), "echo": "ok"}
        
        @app.post("/error")
        async def error_endpoint():
            raise ValueError("Test error")
        
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)
    
    def test_middleware_chain_success(self, client):
        """Test successful request through middleware chain."""
        data = {"test": "chain"}
        
        response = client.post("/echo", json=data)
        
        assert response.status_code == 200
        assert response.json()["echo"] == "ok"
    
    def test_middleware_chain_error(self, client):
        """Test error handling through middleware chain."""
        response = client.post("/error", json={})
        
        # Error recovery should catch and return 500
        assert response.status_code == 500
    
    def test_msgpack_with_error_recovery(self, client):
        """Test MessagePack request with error recovery."""
        data = {"test": "msgpack"}
        packed = msgpack.packb(data)
        
        # Success case
        response = client.post(
            "/echo",
            content=packed,
            headers={"Content-Type": "application/x-msgpack"}
        )
        
        assert response.status_code == 200
        
        # Error case
        error_response = client.post(
            "/error",
            content=packed,
            headers={"Content-Type": "application/x-msgpack"}
        )
        
        assert error_response.status_code == 500


class TestRequestSizeLimit:
    """Test request size limiting."""
    
    @pytest.fixture
    def app(self):
        """Create app with size limit."""
        app = FastAPI()
        
        # Add custom size limit middleware
        @app.middleware("http")
        async def limit_request_size(request: Request, call_next):
            # Check content length
            content_length = request.headers.get("content-length")
            if content_length:
                if int(content_length) > 1024 * 1024:  # 1MB limit
                    return Response(
                        content=json.dumps({"error": "Request too large"}),
                        status_code=413,
                        media_type="application/json"
                    )
            return await call_next(request)
        
        @app.post("/upload")
        async def upload_endpoint():
            return {"status": "uploaded"}
        
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)
    
    def test_small_request(self, client):
        """Test small request passes."""
        data = {"small": "data"}
        response = client.post("/upload", json=data)
        
        assert response.status_code == 200
    
    def test_large_request_blocked(self, client):
        """Test large request is blocked."""
        # Create data larger than 1MB
        large_data = {"data": "x" * (1024 * 1024 + 1)}
        
        response = client.post("/upload", json=large_data)
        
        assert response.status_code == 413
        assert "too large" in response.json()["error"]


class TestCORSMiddleware:
    """Test CORS middleware configuration."""
    
    @pytest.fixture
    def app(self):
        """Create app with CORS."""
        from fastapi.middleware.cors import CORSMiddleware
        
        app = FastAPI()
        
        # Add CORS middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        @app.get("/data")
        async def get_data():
            return {"data": "test"}
        
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)
    
    def test_cors_headers(self, client):
        """Test CORS headers are added."""
        response = client.get(
            "/data",
            headers={"Origin": "http://localhost:3000"}
        )
        
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    
    def test_preflight_request(self, client):
        """Test CORS preflight request."""
        response = client.options(
            "/data",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET"
            }
        )
        
        assert response.status_code == 200
        assert "access-control-allow-methods" in response.headers


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
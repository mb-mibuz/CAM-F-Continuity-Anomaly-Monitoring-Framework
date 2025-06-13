"""
Backward compatibility layer for HTTP-based services.

Provides transparent IPC optimization while maintaining HTTP API compatibility.
"""

import os
import logging
from typing import Any, Dict, Optional
from urllib.parse import urlparse
import requests

from .patterns import RequestReplyBroker
from .registry import discover_service

logger = logging.getLogger(__name__)


class IPCCompatibilityLayer:
    """
    Provides HTTP-compatible interface over ZeroMQ IPC.
    
    Automatically uses IPC when available, falls back to HTTP.
    """
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.rpc_broker = RequestReplyBroker(service_name)
        self._ipc_enabled = True
        self._http_fallback_urls: Dict[str, str] = {}
    
    def register_http_fallback(self, service: str, base_url: str):
        """Register HTTP fallback URL for a service."""
        self._http_fallback_urls[service] = base_url
    
    def get(self, service: str, path: str, params: Optional[Dict] = None) -> Any:
        """HTTP GET compatible method."""
        return self._request(service, "GET", path, params=params)
    
    def post(self, service: str, path: str, json: Optional[Dict] = None) -> Any:
        """HTTP POST compatible method."""
        return self._request(service, "POST", path, json=json)
    
    def put(self, service: str, path: str, json: Optional[Dict] = None) -> Any:
        """HTTP PUT compatible method."""
        return self._request(service, "PUT", path, json=json)
    
    def delete(self, service: str, path: str) -> Any:
        """HTTP DELETE compatible method."""
        return self._request(service, "DELETE", path)
    
    def _request(self, service: str, method: str, path: str,
                 params: Optional[Dict] = None, json: Optional[Dict] = None) -> Any:
        """Make a request using IPC or HTTP."""
        
        # Try IPC first
        if self._ipc_enabled:
            try:
                # Check if service is available via IPC
                ipc_url = discover_service(service, "rpc")
                
                if ipc_url:
                    # Use IPC
                    request_data = {
                        "method": method,
                        "path": path,
                        "params": params,
                        "json": json
                    }
                    
                    response = self.rpc_broker.call(
                        service, "http_request", request_data
                    )
                    
                    return response
            
            except Exception as e:
                logger.debug(f"IPC failed for {service}, falling back to HTTP: {e}")
        
        # Fall back to HTTP
        return self._http_request(service, method, path, params, json)
    
    def _http_request(self, service: str, method: str, path: str,
                     params: Optional[Dict] = None, json: Optional[Dict] = None) -> Any:
        """Make HTTP request (fallback)."""
        base_url = self._http_fallback_urls.get(service)
        
        if not base_url:
            # Try service discovery
            from CAMF.common.service_discovery import discover_service as http_discover
            service_info = http_discover(service)
            if service_info:
                base_url = service_info['url']
            else:
                raise ValueError(f"No HTTP endpoint found for service: {service}")
        
        url = f"{base_url}{path}"
        
        # Make HTTP request
        response = requests.request(
            method, url, params=params, json=json,
            timeout=30
        )
        response.raise_for_status()
        
        if response.headers.get('content-type', '').startswith('application/json'):
            return response.json()
        else:
            return response.content


class IPCOptimizedClient:
    """
    Drop-in replacement for HTTP clients with IPC optimization.
    
    Usage:
        # Instead of:
        # client = requests
        
        # Use:
        client = IPCOptimizedClient("my_service")
        
        # Same API as requests
        response = client.get("http://storage:8001/api/projects")
    """
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.compat = IPCCompatibilityLayer(service_name)
    
    def get(self, url: str, **kwargs) -> requests.Response:
        """GET request with IPC optimization."""
        service, path = self._parse_url(url)
        
        try:
            # Try IPC
            data = self.compat.get(service, path, params=kwargs.get('params'))
            return self._make_response(data, 200)
        except:
            # Fall back to real HTTP
            return requests.get(url, **kwargs)
    
    def post(self, url: str, **kwargs) -> requests.Response:
        """POST request with IPC optimization."""
        service, path = self._parse_url(url)
        
        try:
            # Try IPC
            data = self.compat.post(service, path, json=kwargs.get('json'))
            return self._make_response(data, 200)
        except:
            # Fall back to real HTTP
            return requests.post(url, **kwargs)
    
    def _parse_url(self, url: str) -> tuple[str, str]:
        """Parse URL to extract service name and path."""
        parsed = urlparse(url)
        
        # Extract service name from hostname
        # e.g., "http://storage:8001/api/projects" -> "storage", "/api/projects"
        service = parsed.hostname or parsed.netloc.split(':')[0]
        path = parsed.path
        
        return service, path
    
    def _make_response(self, data: Any, status_code: int) -> requests.Response:
        """Create a fake Response object for compatibility."""
        response = requests.Response()
        response.status_code = status_code
        response._content = data if isinstance(data, bytes) else str(data).encode()
        
        if isinstance(data, (dict, list)):
            response.headers['content-type'] = 'application/json'
            response.json = lambda: data
        
        return response


# Service-side compatibility
class IPCServiceAdapter:
    """
    Adapter to expose existing HTTP services via IPC.
    
    Wraps FastAPI/Flask apps to handle IPC requests.
    """
    
    def __init__(self, service_name: str, app: Any):
        self.service_name = service_name
        self.app = app
        self.broker = RequestReplyBroker(service_name)
        
        # Register HTTP request handler
        self.broker.register_handler("http_request", self._handle_http_request)
    
    def start(self):
        """Start IPC server."""
        self.broker.start_server()
        logger.info(f"IPC adapter started for {self.service_name}")
    
    def _handle_http_request(self, request_data: Dict) -> Any:
        """Handle HTTP-style request via IPC."""
        method = request_data.get('method', 'GET')
        path = request_data.get('path', '/')
        params = request_data.get('params')
        json_data = request_data.get('json')
        
        # Create test client for the app
        if hasattr(self.app, 'test_client'):
            # Flask app
            client = self.app.test_client()
        else:
            # FastAPI app
            from fastapi.testclient import TestClient
            client = TestClient(self.app)
        
        # Make request
        if method == 'GET':
            response = client.get(path, params=params)
        elif method == 'POST':
            response = client.post(path, json=json_data)
        elif method == 'PUT':
            response = client.put(path, json=json_data)
        elif method == 'DELETE':
            response = client.delete(path)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        # Return response data
        if hasattr(response, 'json'):
            try:
                return response.json()
            except:
                return response.text
        else:
            return response.data.decode()


# Monkey-patch requests for transparent IPC
_original_request = requests.request
_ipc_clients: Dict[str, IPCOptimizedClient] = {}


def _ipc_optimized_request(method: str, url: str, **kwargs):
    """Replacement for requests.request with IPC optimization."""
    # Check if this looks like an internal service URL
    parsed = urlparse(url)
    
    if parsed.hostname and parsed.hostname in ['localhost', '127.0.0.1'] or \
       not parsed.hostname or parsed.hostname.endswith('.local'):
        # Could be internal service
        service = parsed.hostname or 'unknown'
        
        # Get or create IPC client
        if service not in _ipc_clients:
            _ipc_clients[service] = IPCOptimizedClient(f"client_{os.getpid()}")
        
        # Try IPC-optimized request
        try:
            client = _ipc_clients[service]
            if method.upper() == 'GET':
                return client.get(url, **kwargs)
            elif method.upper() == 'POST':
                return client.post(url, **kwargs)
        except:
            pass  # Fall back to HTTP
    
    # Use original requests
    return _original_request(method, url, **kwargs)


def enable_ipc_optimization():
    """Enable transparent IPC optimization for requests library."""
    requests.request = _ipc_optimized_request
    logger.info("IPC optimization enabled for requests library")


def disable_ipc_optimization():
    """Disable IPC optimization."""
    requests.request = _original_request
    logger.info("IPC optimization disabled")
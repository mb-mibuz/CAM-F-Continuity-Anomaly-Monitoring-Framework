"""
Protocol abstraction layer for dual JSON/MessagePack support.

This module provides seamless protocol switching between JSON (for detectors)
and MessagePack (for internal Python services) with auto-detection capabilities.
"""

import json
import msgpack
import asyncio
import time
import logging
from typing import Any, Dict, Optional, Callable, TypeVar
from enum import Enum
from functools import wraps
import aiohttp
import httpx

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ProtocolType(Enum):
    """Supported serialization protocols."""
    JSON = "json"
    MSGPACK = "msgpack"


class SerializationMetrics:
    """Track serialization performance metrics."""
    
    def __init__(self):
        self.json_ops = 0
        self.msgpack_ops = 0
        self.json_time = 0.0
        self.msgpack_time = 0.0
        self.json_bytes = 0
        self.msgpack_bytes = 0
    
    def record_operation(self, protocol: ProtocolType, duration: float, size: int):
        """Record a serialization operation."""
        if protocol == ProtocolType.JSON:
            self.json_ops += 1
            self.json_time += duration
            self.json_bytes += size
        else:
            self.msgpack_ops += 1
            self.msgpack_time += duration
            self.msgpack_bytes += size
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics."""
        return {
            "json": {
                "operations": self.json_ops,
                "total_time": self.json_time,
                "avg_time": self.json_time / self.json_ops if self.json_ops > 0 else 0,
                "total_bytes": self.json_bytes,
                "avg_bytes": self.json_bytes / self.json_ops if self.json_ops > 0 else 0
            },
            "msgpack": {
                "operations": self.msgpack_ops,
                "total_time": self.msgpack_time,
                "avg_time": self.msgpack_time / self.msgpack_ops if self.msgpack_ops > 0 else 0,
                "total_bytes": self.msgpack_bytes,
                "avg_bytes": self.msgpack_bytes / self.msgpack_ops if self.msgpack_ops > 0 else 0
            }
        }


# Global metrics instance
metrics = SerializationMetrics()


class ProtocolHandler:
    """Base protocol handler interface."""
    
    def serialize(self, data: Any) -> bytes:
        """Serialize data to bytes."""
        raise NotImplementedError
    
    def deserialize(self, data: bytes) -> Any:
        """Deserialize bytes to data."""
        raise NotImplementedError
    
    @property
    def content_type(self) -> str:
        """Get HTTP content type for this protocol."""
        raise NotImplementedError


class JSONHandler(ProtocolHandler):
    """JSON protocol handler."""
    
    def serialize(self, data: Any) -> bytes:
        """Serialize data to JSON bytes."""
        start = time.time()
        result = json.dumps(data).encode('utf-8')
        metrics.record_operation(ProtocolType.JSON, time.time() - start, len(result))
        return result
    
    def deserialize(self, data: bytes) -> Any:
        """Deserialize JSON bytes to data."""
        return json.loads(data.decode('utf-8'))
    
    @property
    def content_type(self) -> str:
        return "application/json"


class MessagePackHandler(ProtocolHandler):
    """MessagePack protocol handler."""
    
    def serialize(self, data: Any) -> bytes:
        """Serialize data to MessagePack bytes."""
        start = time.time()
        result = msgpack.packb(data, use_bin_type=True)
        metrics.record_operation(ProtocolType.MSGPACK, time.time() - start, len(result))
        return result
    
    def deserialize(self, data: bytes) -> Any:
        """Deserialize MessagePack bytes to data."""
        return msgpack.unpackb(data, raw=False)
    
    @property
    def content_type(self) -> str:
        return "application/msgpack"


class ProtocolManager:
    """Manages protocol selection and switching."""
    
    def __init__(self):
        self.handlers = {
            ProtocolType.JSON: JSONHandler(),
            ProtocolType.MSGPACK: MessagePackHandler()
        }
        self._service_protocols: Dict[str, ProtocolType] = {}
        self._debug_mode = False
    
    def enable_debug(self, enabled: bool = True):
        """Enable/disable debug mode for protocol monitoring."""
        self._debug_mode = enabled
    
    def get_handler(self, protocol: ProtocolType) -> ProtocolHandler:
        """Get handler for specified protocol."""
        return self.handlers[protocol]
    
    def auto_detect_protocol(self, content_type: Optional[str]) -> ProtocolType:
        """Auto-detect protocol from content type header."""
        if content_type:
            if "msgpack" in content_type.lower():
                return ProtocolType.MSGPACK
        return ProtocolType.JSON
    
    def get_protocol_for_service(self, service_name: str) -> ProtocolType:
        """Get the preferred protocol for a service."""
        # Detectors always use JSON
        if "detector" in service_name.lower():
            return ProtocolType.JSON
        
        # Check cached preference
        if service_name in self._service_protocols:
            return self._service_protocols[service_name]
        
        # Default to MessagePack for Python services
        return ProtocolType.MSGPACK
    
    def set_service_protocol(self, service_name: str, protocol: ProtocolType):
        """Set the preferred protocol for a service."""
        self._service_protocols[service_name] = protocol
        if self._debug_mode:
            logger.info(f"Set protocol for {service_name}: {protocol.value}")
    
    def serialize(self, data: Any, protocol: Optional[ProtocolType] = None) -> bytes:
        """Serialize data using specified or default protocol."""
        if protocol is None:
            protocol = ProtocolType.JSON
        
        handler = self.get_handler(protocol)
        result = handler.serialize(data)
        
        if self._debug_mode:
            logger.debug(f"Serialized {len(result)} bytes using {protocol.value}")
        
        return result
    
    def deserialize(self, data: bytes, protocol: Optional[ProtocolType] = None, 
                    content_type: Optional[str] = None) -> Any:
        """Deserialize data using specified or auto-detected protocol."""
        if protocol is None:
            protocol = self.auto_detect_protocol(content_type)
        
        handler = self.get_handler(protocol)
        result = handler.deserialize(data)
        
        if self._debug_mode:
            logger.debug(f"Deserialized {len(data)} bytes using {protocol.value}")
        
        return result
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get serialization metrics."""
        return metrics.get_stats()


# Global protocol manager instance
protocol_manager = ProtocolManager()


def with_protocol(protocol: Optional[ProtocolType] = None):
    """Decorator to handle protocol serialization for function results."""
    def decorator(func: Callable[..., T]) -> Callable[..., bytes]:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> bytes:
            result = await func(*args, **kwargs)
            return protocol_manager.serialize(result, protocol)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> bytes:
            result = func(*args, **kwargs)
            return protocol_manager.serialize(result, protocol)
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator


class HTTPClient:
    """HTTP client with automatic protocol negotiation."""
    
    def __init__(self, base_url: str, service_name: str):
        self.base_url = base_url.rstrip('/')
        self.service_name = service_name
        self.protocol = protocol_manager.get_protocol_for_service(service_name)
        self.handler = protocol_manager.get_handler(self.protocol)
    
    async def request(self, method: str, endpoint: str, data: Any = None, **kwargs) -> Any:
        """Make HTTP request with automatic serialization."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = kwargs.pop('headers', {})
        
        if data is not None:
            headers['Content-Type'] = self.handler.content_type
            body = self.handler.serialize(data)
        else:
            body = None
        
        # Set Accept header to indicate supported protocols
        headers['Accept'] = f"{self.handler.content_type}, application/json"
        
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, data=body, headers=headers, **kwargs) as response:
                response.raise_for_status()
                
                # Auto-detect response protocol
                content_type = response.headers.get('Content-Type', '')
                response_data = await response.read()
                
                if response_data:
                    return protocol_manager.deserialize(response_data, content_type=content_type)
                return None
    
    async def get(self, endpoint: str, **kwargs) -> Any:
        """Make GET request."""
        return await self.request('GET', endpoint, **kwargs)
    
    async def post(self, endpoint: str, data: Any = None, **kwargs) -> Any:
        """Make POST request."""
        return await self.request('POST', endpoint, data, **kwargs)
    
    async def put(self, endpoint: str, data: Any = None, **kwargs) -> Any:
        """Make PUT request."""
        return await self.request('PUT', endpoint, data, **kwargs)
    
    async def delete(self, endpoint: str, **kwargs) -> Any:
        """Make DELETE request."""
        return await self.request('DELETE', endpoint, **kwargs)


class SyncHTTPClient:
    """Synchronous HTTP client with automatic protocol negotiation."""
    
    def __init__(self, base_url: str, service_name: str):
        self.base_url = base_url.rstrip('/')
        self.service_name = service_name
        self.protocol = protocol_manager.get_protocol_for_service(service_name)
        self.handler = protocol_manager.get_handler(self.protocol)
        self.client = httpx.Client()
    
    def request(self, method: str, endpoint: str, data: Any = None, **kwargs) -> Any:
        """Make HTTP request with automatic serialization."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = kwargs.pop('headers', {})
        
        if data is not None:
            headers['Content-Type'] = self.handler.content_type
            body = self.handler.serialize(data)
        else:
            body = None
        
        # Set Accept header to indicate supported protocols
        headers['Accept'] = f"{self.handler.content_type}, application/json"
        
        response = self.client.request(method, url, content=body, headers=headers, **kwargs)
        response.raise_for_status()
        
        # Auto-detect response protocol
        content_type = response.headers.get('Content-Type', '')
        
        if response.content:
            return protocol_manager.deserialize(response.content, content_type=content_type)
        return None
    
    def get(self, endpoint: str, **kwargs) -> Any:
        """Make GET request."""
        return self.request('GET', endpoint, **kwargs)
    
    def post(self, endpoint: str, data: Any = None, **kwargs) -> Any:
        """Make POST request."""
        return self.request('POST', endpoint, data, **kwargs)
    
    def put(self, endpoint: str, data: Any = None, **kwargs) -> Any:
        """Make PUT request."""
        return self.request('PUT', endpoint, data, **kwargs)
    
    def delete(self, endpoint: str, **kwargs) -> Any:
        """Make DELETE request."""
        return self.request('DELETE', endpoint, **kwargs)
    
    def close(self):
        """Close the HTTP client."""
        self.client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Export main components
__all__ = [
    'ProtocolType',
    'ProtocolManager',
    'protocol_manager',
    'HTTPClient',
    'SyncHTTPClient',
    'with_protocol',
    'SerializationMetrics',
    'encode_message',
    'decode_message'
]


# Compatibility functions for legacy code
def encode_message(data: Any, protocol: str = 'json') -> bytes:
    """Legacy encode function for backward compatibility."""
    protocol_type = ProtocolType.JSON if protocol == 'json' else ProtocolType.MSGPACK
    handler = protocol_manager.get_handler(protocol_type)
    return handler.serialize(data)


def decode_message(data: bytes, protocol: str = 'json') -> Any:
    """Legacy decode function for backward compatibility."""
    protocol_type = ProtocolType.JSON if protocol == 'json' else ProtocolType.MSGPACK
    handler = protocol_manager.get_handler(protocol_type)
    return handler.deserialize(data)
"""
Service registry for IPC endpoints.

Provides service discovery and endpoint management for ZeroMQ IPC.
"""

import os
import json
import time
import threading
from typing import Dict, List, Optional, Set
from pathlib import Path
from dataclasses import dataclass, asdict
import logging

from .transport import get_ipc_directory, TransportType

logger = logging.getLogger(__name__)


@dataclass
class ServiceEndpoint:
    """Information about a service endpoint."""
    service_name: str
    endpoint_name: str
    url: str
    transport: TransportType
    pid: int
    socket_type: str  # PUB, SUB, REQ, REP, PUSH, PULL
    registered_at: float = 0.0
    last_seen: float = 0.0
    
    def is_alive(self, timeout: float = 30.0) -> bool:
        """Check if endpoint is still alive."""
        return (time.time() - self.last_seen) < timeout


class IPCServiceRegistry:
    """
    Registry for IPC service endpoints.
    
    Provides service discovery without network overhead.
    """
    
    def __init__(self, registry_name: str = "camf_ipc_registry"):
        self.registry_name = registry_name
        self.registry_path = self._get_registry_path()
        self.endpoints: Dict[str, ServiceEndpoint] = {}
        self._lock = threading.Lock()
        self._running = False
        self._cleanup_thread = None
        
        # Ensure registry directory exists
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing registry
        self._load_registry()
        
        # Start cleanup thread
        self._start_cleanup_thread()
    
    def _get_registry_path(self) -> Path:
        """Get path to registry file."""
        ipc_dir = get_ipc_directory()
        return ipc_dir / f"{self.registry_name}.json"
    
    def _load_registry(self):
        """Load registry from disk."""
        if self.registry_path.exists():
            try:
                with open(self.registry_path, 'r') as f:
                    data = json.load(f)
                    
                # Convert back to ServiceEndpoint objects
                for key, endpoint_data in data.items():
                    endpoint_data['transport'] = TransportType(endpoint_data['transport'])
                    self.endpoints[key] = ServiceEndpoint(**endpoint_data)
                    
                logger.info(f"Loaded {len(self.endpoints)} endpoints from registry")
            except Exception as e:
                logger.error(f"Failed to load registry: {e}")
                self.endpoints = {}
    
    def _save_registry(self):
        """Save registry to disk."""
        try:
            # Convert to JSON-serializable format
            data = {}
            for key, endpoint in self.endpoints.items():
                endpoint_dict = asdict(endpoint)
                endpoint_dict['transport'] = endpoint.transport.value
                data[key] = endpoint_dict
            
            # Write atomically
            tmp_path = self.registry_path.with_suffix('.tmp')
            with open(tmp_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            # Atomic rename
            tmp_path.replace(self.registry_path)
            
        except Exception as e:
            logger.error(f"Failed to save registry: {e}")
    
    def register_endpoint(self, service_name: str, endpoint_name: str,
                         url: str, transport: TransportType,
                         socket_type: str) -> str:
        """
        Register a service endpoint.
        
        Returns:
            Endpoint key for future reference
        """
        endpoint_key = f"{service_name}:{endpoint_name}"
        
        with self._lock:
            endpoint = ServiceEndpoint(
                service_name=service_name,
                endpoint_name=endpoint_name,
                url=url,
                transport=transport,
                pid=os.getpid(),
                socket_type=socket_type,
                registered_at=time.time(),
                last_seen=time.time()
            )
            
            self.endpoints[endpoint_key] = endpoint
            self._save_registry()
            
        logger.info(f"Registered endpoint: {endpoint_key} -> {url}")
        return endpoint_key
    
    def unregister_endpoint(self, endpoint_key: str):
        """Unregister a service endpoint."""
        with self._lock:
            if endpoint_key in self.endpoints:
                del self.endpoints[endpoint_key]
                self._save_registry()
                logger.info(f"Unregistered endpoint: {endpoint_key}")
    
    def get_endpoint(self, service_name: str, endpoint_name: str) -> Optional[ServiceEndpoint]:
        """Get a specific endpoint."""
        endpoint_key = f"{service_name}:{endpoint_name}"
        
        with self._lock:
            endpoint = self.endpoints.get(endpoint_key)
            if endpoint and endpoint.is_alive():
                return endpoint
            elif endpoint:
                # Dead endpoint, remove it
                del self.endpoints[endpoint_key]
                self._save_registry()
            
        return None
    
    def get_service_endpoints(self, service_name: str) -> List[ServiceEndpoint]:
        """Get all endpoints for a service."""
        endpoints = []
        
        with self._lock:
            for key, endpoint in list(self.endpoints.items()):
                if endpoint.service_name == service_name and endpoint.is_alive():
                    endpoints.append(endpoint)
                elif not endpoint.is_alive():
                    # Clean up dead endpoint
                    del self.endpoints[key]
        
        return endpoints
    
    def find_endpoints(self, socket_type: Optional[str] = None,
                      transport: Optional[TransportType] = None) -> List[ServiceEndpoint]:
        """Find endpoints matching criteria."""
        endpoints = []
        
        with self._lock:
            for endpoint in self.endpoints.values():
                if not endpoint.is_alive():
                    continue
                    
                if socket_type and endpoint.socket_type != socket_type:
                    continue
                    
                if transport and endpoint.transport != transport:
                    continue
                
                endpoints.append(endpoint)
        
        return endpoints
    
    def heartbeat(self, endpoint_key: str):
        """Update heartbeat for an endpoint."""
        with self._lock:
            if endpoint_key in self.endpoints:
                self.endpoints[endpoint_key].last_seen = time.time()
    
    def _cleanup_dead_endpoints(self):
        """Remove dead endpoints from registry."""
        with self._lock:
            dead_keys = []
            
            for key, endpoint in self.endpoints.items():
                if not endpoint.is_alive(timeout=60.0):
                    dead_keys.append(key)
            
            if dead_keys:
                for key in dead_keys:
                    del self.endpoints[key]
                
                self._save_registry()
                logger.info(f"Cleaned up {len(dead_keys)} dead endpoints")
    
    def _start_cleanup_thread(self):
        """Start background thread to clean up dead endpoints."""
        def cleanup_loop():
            self._running = True
            while self._running:
                try:
                    time.sleep(30)  # Check every 30 seconds
                    self._cleanup_dead_endpoints()
                except Exception as e:
                    logger.error(f"Error in cleanup thread: {e}")
        
        self._cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
        self._cleanup_thread.start()
    
    def close(self):
        """Close the registry."""
        self._running = False
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=1.0)
    
    def get_optimal_endpoint(self, service_name: str, endpoint_name: str,
                           prefer_inproc: bool = True) -> Optional[ServiceEndpoint]:
        """
        Get optimal endpoint for communication.
        
        Prefers in-process if available, then IPC, then TCP.
        """
        endpoints = []
        
        # Get all matching endpoints
        with self._lock:
            for key, endpoint in self.endpoints.items():
                if (endpoint.service_name == service_name and 
                    endpoint.endpoint_name == endpoint_name and
                    endpoint.is_alive()):
                    endpoints.append(endpoint)
        
        if not endpoints:
            return None
        
        # Sort by preference
        def transport_priority(ep: ServiceEndpoint) -> int:
            if prefer_inproc and ep.transport == TransportType.INPROC and ep.pid == os.getpid():
                return 0  # Highest priority
            elif ep.transport == TransportType.IPC:
                return 1
            elif ep.transport == TransportType.TCP:
                return 2
            else:
                return 3
        
        endpoints.sort(key=transport_priority)
        return endpoints[0]
    
    def list_all_services(self) -> Set[str]:
        """Get set of all registered service names."""
        services = set()
        
        with self._lock:
            for endpoint in self.endpoints.values():
                if endpoint.is_alive():
                    services.add(endpoint.service_name)
        
        return services


# Global registry instance
_global_registry: Optional[IPCServiceRegistry] = None


def get_registry() -> IPCServiceRegistry:
    """Get global IPC service registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = IPCServiceRegistry()
    return _global_registry


def discover_service(service_name: str, endpoint_name: str,
                    prefer_inproc: bool = True) -> Optional[str]:
    """
    Discover service endpoint URL.
    
    Args:
        service_name: Name of the service
        endpoint_name: Name of the endpoint
        prefer_inproc: Prefer in-process transport if available
    
    Returns:
        Endpoint URL or None if not found
    """
    registry = get_registry()
    endpoint = registry.get_optimal_endpoint(service_name, endpoint_name, prefer_inproc)
    
    if endpoint:
        return endpoint.url
    return None
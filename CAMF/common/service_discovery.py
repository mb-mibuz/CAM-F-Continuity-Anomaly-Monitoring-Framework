"""
Service discovery and health monitoring utilities.
Uses a simple file-based registry for local development and can be extended
to use Consul, etcd, or Kubernetes service discovery for production.
"""

import json
import time
import threading
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
import os
from .protocol import ProtocolType, protocol_manager

@dataclass
class ServiceInfo:
    """Information about a registered service."""
    name: str
    host: str
    port: int
    health_endpoint: str
    metadata: Dict[str, any] = field(default_factory=dict)
    last_heartbeat: float = 0
    status: str = "unknown"  # healthy, unhealthy, unknown
    protocol: str = "json"  # Default protocol for backward compatibility
    supported_protocols: List[str] = field(default_factory=lambda: ["json"])
    
    def to_dict(self):
        return asdict(self)
    
    def supports_protocol(self, protocol: ProtocolType) -> bool:
        """Check if service supports a given protocol."""
        return protocol.value in self.supported_protocols

class ServiceRegistry:
    """
    Simple service registry for service discovery.
    Can be extended to use Consul, etcd, or other service discovery tools.
    """
    
    def __init__(self, registry_path: str = "./data/service_registry.json"):
        self.registry_path = Path(registry_path)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.services: Dict[str, ServiceInfo] = {}
        self.lock = threading.RLock()
        self._load_registry()
        
        # Start health check thread
        from CAMF.common.config import get_config
        self.health_check_interval = get_config().service.health_check_interval
        self.health_check_thread = threading.Thread(target=self._health_check_loop)
        self.health_check_thread.daemon = True
        self.health_check_thread.start()
    
    def register(self, service: ServiceInfo) -> bool:
        """Register a service."""
        with self.lock:
            service.last_heartbeat = time.time()
            service.status = "unknown"
            self.services[service.name] = service
            self._save_registry()
            return True
    
    def unregister(self, service_name: str) -> bool:
        """Unregister a service."""
        with self.lock:
            if service_name in self.services:
                del self.services[service_name]
                self._save_registry()
                return True
            return False
    
    def get_service(self, service_name: str) -> Optional[ServiceInfo]:
        """Get service info by name."""
        with self.lock:
            return self.services.get(service_name)
    
    def get_healthy_service(self, service_name: str) -> Optional[ServiceInfo]:
        """Get service info only if healthy."""
        service = self.get_service(service_name)
        if service and service.status == "healthy":
            return service
        return None
    
    def list_services(self, only_healthy: bool = False) -> List[ServiceInfo]:
        """List all services."""
        with self.lock:
            services = list(self.services.values())
            if only_healthy:
                services = [s for s in services if s.status == "healthy"]
            return services
    
    def _health_check_loop(self):
        """Background thread for health checking."""
        while True:
            try:
                self._check_all_services()
                time.sleep(self.health_check_interval)
            except Exception as e:
                print(f"Health check error: {e}")
                time.sleep(self.health_check_interval)
    
    def _check_all_services(self):
        """Check health of all registered services."""
        with self.lock:
            services = list(self.services.values())
        
        for service in services:
            self._check_service_health(service)
    
    def _check_service_health(self, service: ServiceInfo):
        """Check health of a single service."""
        try:
            url = f"http://{service.host}:{service.port}{service.health_endpoint}"
            response = requests.get(url, timeout=5)
            
            with self.lock:
                if service.name in self.services:
                    if response.status_code == 200:
                        self.services[service.name].status = "healthy"
                        self.services[service.name].last_heartbeat = time.time()
                    else:
                        self.services[service.name].status = "unhealthy"
                    self._save_registry()
                    
        except Exception:
            with self.lock:
                if service.name in self.services:
                    self.services[service.name].status = "unhealthy"
                    self._save_registry()
    
    def _save_registry(self):
        """Save registry to disk."""
        try:
            data = {
                name: service.to_dict() 
                for name, service in self.services.items()
            }
            with open(self.registry_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Failed to save registry: {e}")
    
    def _load_registry(self):
        """Load registry from disk."""
        try:
            if self.registry_path.exists():
                with open(self.registry_path, 'r') as f:
                    data = json.load(f)
                    for name, info in data.items():
                        self.services[name] = ServiceInfo(**info)
        except Exception as e:
            print(f"Failed to load registry: {e}")

# Global registry instance
_registry = None

def get_service_registry() -> ServiceRegistry:
    """Get the service registry singleton."""
    global _registry
    if _registry is None:
        _registry = ServiceRegistry()
    return _registry

def register_service(name: str, port: int, health_endpoint: str = "/health", 
                    metadata: Dict = None, 
                    supported_protocols: List[str] = None) -> bool:
    """Register current service with protocol support."""
    registry = get_service_registry()
    
    # Auto-detect host
    host = os.getenv("SERVICE_HOST", "127.0.0.1")
    
    # Determine supported protocols
    if supported_protocols is None:
        # Detectors only support JSON
        if "detector" in name.lower():
            supported_protocols = ["json"]
        else:
            # Python services support both JSON and MessagePack
            supported_protocols = ["json", "msgpack"]
    
    # Set preferred protocol for the service
    preferred_protocol = "msgpack" if "msgpack" in supported_protocols and "detector" not in name.lower() else "json"
    
    service = ServiceInfo(
        name=name,
        host=host,
        port=port,
        health_endpoint=health_endpoint,
        metadata=metadata or {},
        protocol=preferred_protocol,
        supported_protocols=supported_protocols
    )
    
    # Update protocol manager with service preference
    if preferred_protocol == "msgpack":
        protocol_manager.set_service_protocol(name, ProtocolType.MSGPACK)
    
    return registry.register(service)

def get_service_url(service_name: str, path: str = "") -> Optional[str]:
    """Get URL for a healthy service."""
    registry = get_service_registry()
    service = registry.get_healthy_service(service_name)
    
    if service:
        return f"http://{service.host}:{service.port}{path}"
    return None

def get_service_info_with_protocol(service_name: str) -> Optional[Tuple[str, ProtocolType]]:
    """Get service URL and preferred protocol."""
    registry = get_service_registry()
    service = registry.get_healthy_service(service_name)
    
    if service:
        url = f"http://{service.host}:{service.port}"
        protocol = ProtocolType.MSGPACK if service.protocol == "msgpack" else ProtocolType.JSON
        return url, protocol
    return None
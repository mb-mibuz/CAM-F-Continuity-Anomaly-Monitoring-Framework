import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional
import logging
from .protocol import SyncHTTPClient, HTTPClient, ProtocolType
from .service_discovery import get_service_info_with_protocol

def generate_id() -> str:
    """Generate a unique ID."""
    return str(uuid.uuid4())

def ensure_directory(directory: Path):
    """Ensure that a directory exists."""
    os.makedirs(directory, exist_ok=True)

def get_timestamp() -> float:
    """Get current timestamp in seconds."""
    return time.time()

def format_timestamp(timestamp: float, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format a timestamp into a human-readable string."""
    import datetime
    dt = datetime.datetime.fromtimestamp(timestamp)
    return dt.strftime(format_str)

def get_project_path(base_dir: str, project_id: int) -> Path:
    """Get the path to a project directory."""
    return Path(base_dir) / str(project_id)

def get_scene_path(base_dir: str, project_id: int, scene_id: int) -> Path:
    """Get the path to a scene directory."""
    return get_project_path(base_dir, project_id) / str(scene_id)

def get_angle_path(base_dir: str, project_id: int, scene_id: int, angle_id: int) -> Path:
    """Get the path to an angle directory."""
    return get_scene_path(base_dir, project_id, scene_id) / str(angle_id)

def get_take_path(base_dir: str, project_id: int, scene_id: int, angle_id: int, take_id: int) -> Path:
    """Get the path to a take directory."""
    return get_angle_path(base_dir, project_id, scene_id, angle_id) / str(take_id)

def get_frame_path(base_dir: str, project_id: int, scene_id: int, angle_id: int, take_id: int, frame_id: int) -> Path:
    """Get the path to a frame file."""
    take_path = get_take_path(base_dir, project_id, scene_id, angle_id, take_id)
    return take_path / f"frame_{frame_id:08d}.jpg"


class ServiceClient:
    """Base class for service clients with automatic protocol selection."""
    
    def __init__(self, service_name: str, fallback_url: Optional[str] = None):
        """
        Initialize service client.
        
        Args:
            service_name: Name of the service to connect to
            fallback_url: Fallback URL if service discovery fails
        """
        self.service_name = service_name
        self.logger = logging.getLogger(f"{self.__class__.__name__}")
        
        # Try to get service info from discovery
        service_info = get_service_info_with_protocol(service_name)
        
        if service_info:
            self.base_url, self.protocol = service_info
            self.logger.info(f"Connected to {service_name} at {self.base_url} using {self.protocol.value}")
        elif fallback_url:
            self.base_url = fallback_url
            self.protocol = ProtocolType.JSON  # Default to JSON for fallback
            self.logger.warning(f"Using fallback URL for {service_name}: {fallback_url}")
        else:
            raise RuntimeError(f"Service {service_name} not found and no fallback URL provided")
        
        # Create HTTP client with protocol support
        self.client = SyncHTTPClient(self.base_url, service_name)
    
    def _handle_response(self, response: Any) -> Any:
        """Handle service response, checking for errors."""
        if isinstance(response, dict) and "error" in response:
            raise Exception(f"Service error: {response['error']}")
        return response
    
    def close(self):
        """Close the HTTP client."""
        if hasattr(self.client, 'close'):
            self.client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class AsyncServiceClient:
    """Async base class for service clients with automatic protocol selection."""
    
    def __init__(self, service_name: str, fallback_url: Optional[str] = None):
        """
        Initialize async service client.
        
        Args:
            service_name: Name of the service to connect to
            fallback_url: Fallback URL if service discovery fails
        """
        self.service_name = service_name
        self.logger = logging.getLogger(f"{self.__class__.__name__}")
        
        # Try to get service info from discovery
        service_info = get_service_info_with_protocol(service_name)
        
        if service_info:
            self.base_url, self.protocol = service_info
            self.logger.info(f"Connected to {service_name} at {self.base_url} using {self.protocol.value}")
        elif fallback_url:
            self.base_url = fallback_url
            self.protocol = ProtocolType.JSON  # Default to JSON for fallback
            self.logger.warning(f"Using fallback URL for {service_name}: {fallback_url}")
        else:
            raise RuntimeError(f"Service {service_name} not found and no fallback URL provided")
        
        # Create async HTTP client with protocol support
        self.client = HTTPClient(self.base_url, service_name)
    
    async def _handle_response(self, response: Any) -> Any:
        """Handle service response, checking for errors."""
        if isinstance(response, dict) and "error" in response:
            raise Exception(f"Service error: {response['error']}")
        return response
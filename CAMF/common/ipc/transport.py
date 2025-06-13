"""
Transport layer for ZeroMQ IPC.

Provides different transport mechanisms optimized for various scenarios:
- In-process (inproc://) - Zero-copy, fastest
- Inter-process (ipc://) - Unix domain sockets
- TCP (tcp://) - For network communication (backward compatibility)
"""

import os
import sys
import tempfile
from enum import Enum
from pathlib import Path
from typing import Optional

class TransportType(Enum):
    """Available transport types for IPC."""
    INPROC = "inproc"  # In-process, zero-copy
    IPC = "ipc"        # Unix domain sockets / named pipes
    TCP = "tcp"        # Network sockets (compatibility)


def get_ipc_directory() -> Path:
    """Get platform-appropriate directory for IPC sockets."""
    if sys.platform == "win32":
        # Windows doesn't support Unix domain sockets well
        # Use named pipes instead (ZeroMQ handles this)
        return Path(tempfile.gettempdir()) / "camf_ipc"
    else:
        # Unix-like systems
        # Try to use /run/user/UID for better performance
        runtime_dir = os.environ.get('XDG_RUNTIME_DIR')
        if runtime_dir:
            return Path(runtime_dir) / "camf_ipc"
        else:
            # Fallback to /tmp
            return Path("/tmp") / f"camf_ipc_{os.getuid()}"


def ensure_ipc_directory() -> Path:
    """Ensure IPC directory exists with proper permissions."""
    ipc_dir = get_ipc_directory()
    ipc_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return ipc_dir


def get_transport_url(service_name: str, endpoint: str, 
                     transport: TransportType = TransportType.IPC,
                     port: Optional[int] = None) -> str:
    """
    Generate transport URL for a service endpoint.
    
    Args:
        service_name: Name of the service
        endpoint: Endpoint identifier (e.g., "commands", "frames", "results")
        transport: Transport type to use
        port: Port number for TCP transport
    
    Returns:
        Transport URL string
    """
    if transport == TransportType.INPROC:
        # In-process transport
        return f"inproc://{service_name}_{endpoint}"
    
    elif transport == TransportType.IPC:
        # Inter-process transport
        if sys.platform == "win32":
            # Windows named pipes
            return f"ipc:////{service_name}_{endpoint}"
        else:
            # Unix domain sockets
            ipc_dir = ensure_ipc_directory()
            socket_path = ipc_dir / f"{service_name}_{endpoint}.sock"
            return f"ipc://{socket_path}"
    
    elif transport == TransportType.TCP:
        # TCP transport for network/compatibility
        if port is None:
            # Use deterministic port based on service name
            # This is just for demo - in production use proper port allocation
            port = 50000 + hash(f"{service_name}_{endpoint}") % 10000
        return f"tcp://127.0.0.1:{port}"
    
    else:
        raise ValueError(f"Unknown transport type: {transport}")


def cleanup_transport(url: str):
    """Clean up transport resources (e.g., socket files)."""
    if url.startswith("ipc://") and not sys.platform == "win32":
        # Extract socket path and remove file
        socket_path = url[6:]  # Remove "ipc://"
        if os.path.exists(socket_path):
            try:
                os.unlink(socket_path)
            except OSError:
                pass


def get_optimal_transport() -> TransportType:
    """
    Determine optimal transport for current platform.
    
    Returns:
        Best transport type for the platform
    """
    if sys.platform == "win32":
        # Windows: Use TCP as IPC support is limited
        # Note: ZeroMQ does support Windows named pipes but with limitations
        return TransportType.TCP
    else:
        # Unix-like: Use IPC (Unix domain sockets)
        return TransportType.IPC


def is_same_process(pid: int) -> bool:
    """Check if given PID is same as current process."""
    return pid == os.getpid()


def can_use_inproc(service_pid: int) -> bool:
    """
    Check if inproc transport can be used with a service.
    
    Args:
        service_pid: Process ID of the service
    
    Returns:
        True if inproc can be used
    """
    return is_same_process(service_pid)


# Transport URLs for well-known services
WELL_KNOWN_ENDPOINTS = {
    # Storage service
    "storage_queries": "storage_queries",
    "storage_commands": "storage_commands",
    
    # Frame provider
    "frames_pub": "frames_pub",
    "frames_req": "frames_req",
    
    # Capture service  
    "capture_commands": "capture_commands",
    "capture_status": "capture_status",
    "capture_frames": "capture_frames",
    
    # Detector framework
    "detector_commands": "detector_commands",
    "detector_results": "detector_results",
    "detector_requests": "detector_requests",
    
    # Processing service
    "processing_commands": "processing_commands",
    "processing_status": "processing_status",
    
    # Session management
    "session_events": "session_events",
    "session_commands": "session_commands"
}


def get_service_endpoints(service_name: str, 
                         transport: Optional[TransportType] = None) -> dict[str, str]:
    """
    Get all endpoint URLs for a service.
    
    Args:
        service_name: Name of the service
        transport: Transport type (auto-detect if None)
    
    Returns:
        Dictionary of endpoint_name -> URL
    """
    if transport is None:
        transport = get_optimal_transport()
    
    endpoints = {}
    
    # Get endpoints for the service
    for endpoint_key, endpoint_name in WELL_KNOWN_ENDPOINTS.items():
        if endpoint_key.startswith(service_name + "_"):
            endpoint_type = endpoint_key[len(service_name) + 1:]
            url = get_transport_url(service_name, endpoint_type, transport)
            endpoints[endpoint_type] = url
    
    return endpoints
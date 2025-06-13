"""
Mock service implementations for testing.
Provides lightweight mock versions of services for unit testing.
"""

import asyncio
import json
import os
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
import numpy as np
import threading
import queue
from dataclasses import dataclass, asdict
from unittest.mock import MagicMock

# Mock models
@dataclass
class MockProject:
    id: int
    name: str
    created_at: datetime
    updated_at: datetime
    
    def dict(self):
        return asdict(self)


@dataclass
class MockScene:
    id: int
    project_id: int
    name: str
    detector_configs: Dict[str, Any]
    created_at: datetime
    
    def dict(self):
        return asdict(self)


@dataclass
class MockFrame:
    id: int
    take_id: int
    frame_number: int
    timestamp: float
    file_path: str
    detector_results: Optional[Dict] = None
    
    def dict(self):
        return asdict(self)


class MockStorageService:
    """Mock storage service for testing."""
    
    def __init__(self):
        self.projects = {}
        self.scenes = {}
        self.angles = {}
        self.takes = {}
        self.frames = {}
        self._id_counter = 1
        
    def _next_id(self):
        """Get next ID."""
        id_val = self._id_counter
        self._id_counter += 1
        return id_val
        
    async def create_project(self, data: dict) -> MockProject:
        """Create mock project."""
        project = MockProject(
            id=self._next_id(),
            name=data["name"],
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        self.projects[project.id] = project
        return project
        
    async def get_project(self, project_id: int) -> Optional[MockProject]:
        """Get project by ID."""
        return self.projects.get(project_id)
        
    async def get_projects(self) -> List[MockProject]:
        """Get all projects."""
        return list(self.projects.values())
        
    async def create_scene(self, data: dict) -> MockScene:
        """Create mock scene."""
        scene = MockScene(
            id=self._next_id(),
            project_id=data["project_id"],
            name=data["name"],
            detector_configs=data.get("detector_configs", {}),
            created_at=datetime.now()
        )
        self.scenes[scene.id] = scene
        return scene
        
    async def get_scenes(self, project_id: int) -> List[MockScene]:
        """Get scenes for project."""
        return [s for s in self.scenes.values() if s.project_id == project_id]
        
    async def create_frame(self, data: dict) -> MockFrame:
        """Create mock frame."""
        frame = MockFrame(
            id=self._next_id(),
            take_id=data["take_id"],
            frame_number=data["frame_number"],
            timestamp=data["timestamp"],
            file_path=data.get("file_path", f"/frames/frame_{data['frame_number']}.jpg")
        )
        self.frames[frame.id] = frame
        return frame
        
    async def get_frames(self, take_id: int) -> List[MockFrame]:
        """Get frames for take."""
        return [f for f in self.frames.values() if f.take_id == take_id]


class MockCaptureService:
    """Mock capture service for testing."""
    
    def __init__(self):
        self.is_capturing = False
        self.capture_thread = None
        self.frame_queue = queue.Queue()
        self.frame_count = 0
        self.mock_source = None
        
    def start_capture(self, source_config: dict):
        """Start mock capture."""
        self.is_capturing = True
        self.frame_count = 0
        
        # Create mock capture thread
        self.capture_thread = threading.Thread(target=self._capture_loop)
        self.capture_thread.start()
        
        return {"status": "started", "source": source_config}
        
    def stop_capture(self):
        """Stop mock capture."""
        self.is_capturing = False
        if self.capture_thread:
            self.capture_thread.join()
            
        return {"status": "stopped", "frames_captured": self.frame_count}
        
    def _capture_loop(self):
        """Mock capture loop."""
        while self.is_capturing:
            # Generate mock frame
            frame = self._generate_mock_frame()
            self.frame_queue.put(frame)
            self.frame_count += 1
            
            # Simulate capture rate
            time.sleep(1/30)  # 30 FPS
            
    def _generate_mock_frame(self):
        """Generate mock frame data."""
        return {
            "frame_number": self.frame_count,
            "timestamp": self.frame_count / 30.0,
            "data": np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        }
        
    def get_frame(self):
        """Get captured frame."""
        try:
            return self.frame_queue.get_nowait()
        except queue.Empty:
            return None
            
    def get_status(self):
        """Get capture status."""
        return {
            "is_capturing": self.is_capturing,
            "frame_count": self.frame_count,
            "queue_size": self.frame_queue.qsize()
        }


class MockDetectorFramework:
    """Mock detector framework for testing."""
    
    def __init__(self):
        self.detectors = {}
        self.processing_queue = queue.Queue()
        self.results = {}
        
    def register_detector(self, name: str, config: dict):
        """Register mock detector."""
        self.detectors[name] = {
            "config": config,
            "status": "ready",
            "processed_count": 0
        }
        return {"detector": name, "status": "registered"}
        
    async def process_frame(self, frame_id: int, detector_name: str):
        """Process frame with mock detector."""
        # Simulate processing time
        await asyncio.sleep(0.01)
        
        # Generate mock result
        result = {
            "frame_id": frame_id,
            "detector": detector_name,
            "detected": np.random.random() > 0.3,  # 70% detection rate
            "confidence": np.random.uniform(0.7, 0.99),
            "timestamp": time.time()
        }
        
        self.results[f"{frame_id}_{detector_name}"] = result
        return result
        
    async def process_batch(self, frames: List[dict], detector_name: str):
        """Process batch of frames."""
        results = []
        for frame in frames:
            result = await self.process_frame(frame["id"], detector_name)
            results.append(result)
        return results
        
    def get_detector_status(self, detector_name: str):
        """Get detector status."""
        return self.detectors.get(detector_name, {"status": "not_found"})


class MockExportService:
    """Mock export service for testing."""
    
    def __init__(self, temp_dir: str):
        self.temp_dir = Path(temp_dir)
        self.exports = {}
        
    async def export_pdf(self, take_id: int, options: dict):
        """Mock PDF export."""
        # Simulate export time
        await asyncio.sleep(0.1)
        
        # Create mock PDF path
        pdf_path = self.temp_dir / f"take_{take_id}_report.pdf"
        
        # Create empty file
        pdf_path.touch()
        
        export_id = f"export_{take_id}_{int(time.time())}"
        self.exports[export_id] = {
            "id": export_id,
            "take_id": take_id,
            "path": str(pdf_path),
            "status": "completed",
            "created_at": datetime.now()
        }
        
        return self.exports[export_id]
        
    def get_export(self, export_id: str):
        """Get export by ID."""
        return self.exports.get(export_id)


class MockSSEHandler:
    """Mock SSE handler for testing."""
    
    def __init__(self):
        self.events = []
        self.clients = {}
        
    async def broadcast(self, event: dict):
        """Mock broadcast event."""
        self.events.append({
            "timestamp": time.time(),
            "event": event
        })
        
        # Simulate sending to clients
        for client_id, client_info in self.clients.items():
            if event.get("channel") in client_info.get("channels", []):
                # Would send to client
                pass
                
    def add_client(self, client_id: str, channels: List[str]):
        """Add mock client."""
        self.clients[client_id] = {
            "channels": channels,
            "connected_at": time.time()
        }
        
    def remove_client(self, client_id: str):
        """Remove client."""
        self.clients.pop(client_id, None)
        
    def get_events(self, since: float = 0):
        """Get events since timestamp."""
        return [e for e in self.events if e["timestamp"] > since]


class MockDockerClient:
    """Mock Docker client for testing."""
    
    def __init__(self):
        self.containers = {}
        self.images = {}
        self._container_id_counter = 1
        
    def ping(self):
        """Mock ping."""
        return True
        
    def create_container(self, image: str, **kwargs):
        """Create mock container."""
        container_id = f"mock_container_{self._container_id_counter}"
        self._container_id_counter += 1
        
        container = MagicMock()
        container.id = container_id
        container.status = "created"
        container.image = image
        container.attrs = {
            "State": {"Status": "created", "Running": False},
            "Config": {"Image": image}
        }
        
        self.containers[container_id] = container
        return container
        
    def get_container(self, container_id: str):
        """Get container by ID."""
        return self.containers.get(container_id)
        
    def list_containers(self, **filters):
        """List containers."""
        return list(self.containers.values())


def create_mock_services(temp_dir: str) -> dict:
    """Create all mock services."""
    return {
        "storage": MockStorageService(),
        "capture": MockCaptureService(),
        "detector_framework": MockDetectorFramework(),
        "export": MockExportService(temp_dir),
        "sse_handler": MockSSEHandler(),
        "docker_client": MockDockerClient()
    }


# Test fixtures using mocks
def mock_api_app():
    """Create mock FastAPI app for testing."""
    from fastapi import FastAPI
    
    app = FastAPI()
    
    # Add mock services
    app.state.services = create_mock_services("/tmp/test")
    
    # Add test routes
    @app.get("/test/health")
    async def health():
        return {"status": "healthy", "mock": True}
        
    @app.post("/test/projects")
    async def create_project(data: dict):
        service = app.state.services["storage"]
        project = await service.create_project(data)
        return project.dict()
        
    return app


# Utility functions for tests
def create_test_frame_data(count: int = 10) -> List[np.ndarray]:
    """Create test frame data."""
    frames = []
    for i in range(count):
        frame = np.full((480, 640, 3), i * 25, dtype=np.uint8)
        frames.append(frame)
    return frames


def create_test_detector_result(detected: bool = True, confidence: float = 0.9) -> dict:
    """Create test detector result."""
    return {
        "detected": detected,
        "confidence": confidence,
        "details": {
            "objects": [
                {"type": "test_object", "bbox": [100, 100, 200, 200]}
            ] if detected else []
        },
        "timestamp": time.time()
    }


# Environment setup helper
class TestEnvironment:
    """Test environment context manager."""
    
    def __init__(self, temp_dir: str):
        self.temp_dir = Path(temp_dir)
        self.services = None
        self.original_env = {}
        
    def __enter__(self):
        """Set up test environment."""
        # Save original environment
        self.original_env = dict(os.environ)
        
        # Set test environment variables
        os.environ["CAMF_TEST_MODE"] = "true"
        os.environ["CAMF_TEST_TEMP_DIR"] = str(self.temp_dir)
        
        # Create mock services
        self.services = create_mock_services(str(self.temp_dir))
        
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up test environment."""
        # Restore environment
        os.environ.clear()
        os.environ.update(self.original_env)
        
        # Clean up services
        if self.services:
            # Stop any running services
            if hasattr(self.services["capture"], "stop_capture"):
                self.services["capture"].stop_capture()


# Example usage in tests
"""
def test_with_mock_services():
    with TestEnvironment("/tmp/test") as env:
        # Access mock services
        storage = env.services["storage"]
        
        # Use in test
        project = await storage.create_project({"name": "Test"})
        assert project.id == 1
"""
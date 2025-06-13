"""
Basic functionality tests that should work with minimal setup.
These tests use mocks and don't require the full application to be running.
"""

import pytest
import asyncio
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import mocks
from tests.mock_services import (
    MockStorageService, MockCaptureService, MockDetectorFramework,
    MockExportService, create_test_frame_data, create_test_detector_result,
    TestEnvironment
)

# Try to import actual models, fall back to mocks if not available
try:
    from CAMF.common.models import CaptureStatus, ProcessingStatus
except ImportError:
    # Define minimal enums for testing
    class CaptureStatus:
        IDLE = "idle"
        RECORDING = "recording"
        PROCESSING = "processing"
        COMPLETED = "completed"
        ERROR = "error"
    
    class ProcessingStatus:
        PENDING = "pending"
        PROCESSING = "processing"
        COMPLETED = "completed"
        ERROR = "error"


class TestBasicWorkflow:
    """Test basic workflow with mock services."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory."""
        with tempfile.TemporaryDirectory() as td:
            yield td
    
    @pytest.fixture
    def mock_services(self, temp_dir):
        """Create mock services."""
        return {
            "storage": MockStorageService(),
            "capture": MockCaptureService(),
            "detector": MockDetectorFramework(),
            "export": MockExportService(temp_dir)
        }
    
    @pytest.mark.asyncio
    async def test_create_project_hierarchy(self, mock_services):
        """Test creating project hierarchy."""
        storage = mock_services["storage"]
        
        # Create project
        project = await storage.create_project({"name": "Test Project"})
        assert project.id == 1
        assert project.name == "Test Project"
        
        # Create scene
        scene = await storage.create_scene({
            "project_id": project.id,
            "name": "Test Scene",
            "detector_configs": {"TestDetector": {"enabled": True}}
        })
        assert scene.id == 2
        assert scene.project_id == project.id
        
        # Verify retrieval
        projects = await storage.get_projects()
        assert len(projects) == 1
        assert projects[0].name == "Test Project"
    
    def test_capture_frames(self, mock_services):
        """Test frame capture."""
        capture = mock_services["capture"]
        
        # Start capture
        result = capture.start_capture({"source": "test"})
        assert result["status"] == "started"
        
        # Wait for some frames
        import time
        time.sleep(0.2)  # Capture ~6 frames at 30fps
        
        # Check frames
        frames = []
        while True:
            frame = capture.get_frame()
            if frame is None:
                break
            frames.append(frame)
        
        assert len(frames) >= 5
        assert all(f["frame_number"] >= 0 for f in frames)
        
        # Stop capture
        result = capture.stop_capture()
        assert result["status"] == "stopped"
        assert result["frames_captured"] >= 5
    
    @pytest.mark.asyncio
    async def test_detector_processing(self, mock_services):
        """Test detector processing."""
        detector = mock_services["detector"]
        
        # Register detector
        result = detector.register_detector("TestDetector", {
            "threshold": 0.8
        })
        assert result["status"] == "registered"
        
        # Process frames
        results = []
        for i in range(5):
            result = await detector.process_frame(i, "TestDetector")
            results.append(result)
        
        assert len(results) == 5
        assert all(r["detector"] == "TestDetector" for r in results)
        assert all(0.7 <= r["confidence"] <= 0.99 for r in results)
    
    @pytest.mark.asyncio
    async def test_export_generation(self, mock_services, temp_dir):
        """Test export generation."""
        export_service = mock_services["export"]
        
        # Generate export
        result = await export_service.export_pdf(
            take_id=1,
            options={"include_frames": True}
        )
        
        assert result["status"] == "completed"
        assert result["take_id"] == 1
        assert Path(result["path"]).exists()
    
    @pytest.mark.asyncio
    async def test_end_to_end_workflow(self, mock_services):
        """Test complete workflow with mocks."""
        storage = mock_services["storage"]
        capture = mock_services["capture"]
        detector = mock_services["detector"]
        
        # 1. Create project structure
        project = await storage.create_project({"name": "E2E Test"})
        scene = await storage.create_scene({
            "project_id": project.id,
            "name": "Scene 1",
            "detector_configs": {"ClockDetector": {"enabled": True}}
        })
        
        # 2. Start capture
        capture.start_capture({"source": "test"})
        
        # 3. Capture frames
        import time
        time.sleep(0.1)
        
        frames = []
        while True:
            frame = capture.get_frame()
            if frame is None:
                break
            
            # Store frame
            stored_frame = await storage.create_frame({
                "take_id": 1,
                "frame_number": frame["frame_number"],
                "timestamp": frame["timestamp"]
            })
            frames.append(stored_frame)
        
        capture.stop_capture()
        
        # 4. Process with detector
        detector.register_detector("ClockDetector", {})
        
        for frame in frames:
            result = await detector.process_frame(frame.id, "ClockDetector")
            assert result is not None
        
        # 5. Verify stored frames
        stored_frames = await storage.get_frames(take_id=1)
        assert len(stored_frames) == len(frames)


class TestMockBehavior:
    """Test mock service behavior."""
    
    def test_mock_storage_persistence(self):
        """Test that mock storage persists data."""
        storage = MockStorageService()
        
        # Create items
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        project1 = loop.run_until_complete(
            storage.create_project({"name": "Project 1"})
        )
        project2 = loop.run_until_complete(
            storage.create_project({"name": "Project 2"})
        )
        
        # Verify persistence
        projects = loop.run_until_complete(storage.get_projects())
        assert len(projects) == 2
        assert projects[0].name == "Project 1"
        assert projects[1].name == "Project 2"
        
        # Verify IDs are unique
        assert project1.id != project2.id
    
    def test_mock_capture_timing(self):
        """Test mock capture frame timing."""
        capture = MockCaptureService()
        
        capture.start_capture({})
        
        # Capture for specific duration
        import time
        start_time = time.time()
        time.sleep(0.5)  # Half second
        
        capture.stop_capture()
        duration = time.time() - start_time
        
        # Should have ~15 frames at 30fps
        status = capture.get_status()
        expected_frames = int(duration * 30)
        assert abs(status["frame_count"] - expected_frames) <= 2
    
    def test_test_environment_context(self, tmp_path):
        """Test TestEnvironment context manager."""
        original_env = os.environ.get("CAMF_TEST_MODE")
        
        with TestEnvironment(str(tmp_path)) as env:
            # Environment should be set
            assert os.environ.get("CAMF_TEST_MODE") == "true"
            assert os.environ.get("CAMF_TEST_TEMP_DIR") == str(tmp_path)
            
            # Services should be available
            assert env.services is not None
            assert "storage" in env.services
            assert "capture" in env.services
        
        # Environment should be restored
        assert os.environ.get("CAMF_TEST_MODE") == original_env


class TestUtilityFunctions:
    """Test utility functions."""
    
    def test_create_test_frame_data(self):
        """Test frame data generation."""
        frames = create_test_frame_data(count=5)
        
        assert len(frames) == 5
        assert all(f.shape == (480, 640, 3) for f in frames)
        # Each frame should have different intensity
        assert frames[0][0, 0, 0] != frames[4][0, 0, 0]
    
    def test_create_test_detector_result(self):
        """Test detector result generation."""
        # Positive detection
        result = create_test_detector_result(detected=True, confidence=0.95)
        assert result["detected"] is True
        assert result["confidence"] == 0.95
        assert len(result["details"]["objects"]) > 0
        
        # Negative detection
        result = create_test_detector_result(detected=False)
        assert result["detected"] is False
        assert len(result["details"]["objects"]) == 0


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])
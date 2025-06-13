"""
Comprehensive integration tests for complete workflows.
Tests end-to-end scenarios with multiple services interacting.
"""

import pytest
import asyncio
import tempfile
import os
import shutil
import time
from datetime import datetime
import json
import cv2
import numpy as np
from unittest.mock import Mock, patch, MagicMock
import threading
import multiprocessing

from CAMF.services.api_gateway.main import app as api_app
from CAMF.services.storage.main import StorageService
from CAMF.services.capture.main import CaptureService
from CAMF.services.detector_framework.main import DetectorFramework
from CAMF.services.export.main import ExportService
from CAMF.common.models import (
    Project, Scene, Angle, Take, Frame,
    CaptureStatus, ProcessingStatus
)
from fastapi.testclient import TestClient


class TestCompleteWorkflow:
    """Test complete production workflow from project creation to export."""
    
    @pytest.fixture
    def test_environment(self):
        """Set up test environment with all services."""
        # Create temporary directories
        base_dir = tempfile.mkdtemp()
        storage_dir = os.path.join(base_dir, "storage")
        frames_dir = os.path.join(base_dir, "frames")
        export_dir = os.path.join(base_dir, "exports")
        
        os.makedirs(storage_dir)
        os.makedirs(frames_dir)
        os.makedirs(export_dir)
        
        # Initialize services
        storage_service = StorageService(db_path=os.path.join(storage_dir, "test.db"))
        capture_service = CaptureService()
        detector_framework = DetectorFramework()
        export_service = ExportService()
        
        # Create API client
        client = TestClient(api_app)
        
        yield {
            "base_dir": base_dir,
            "storage": storage_service,
            "capture": capture_service,
            "detectors": detector_framework,
            "export": export_service,
            "client": client,
            "dirs": {
                "storage": storage_dir,
                "frames": frames_dir,
                "export": export_dir
            }
        }
        
        # Cleanup
        shutil.rmtree(base_dir)
    
    def test_production_workflow(self, test_environment):
        """Test complete production workflow."""
        client = test_environment["client"]
        
        # Step 1: Create project
        project_response = client.post("/api/projects", json={
            "name": "Test Production"
        })
        assert project_response.status_code == 200
        project = project_response.json()
        project_id = project["id"]
        
        # Step 2: Create scene with detector configuration
        scene_response = client.post("/api/scenes", json={
            "project_id": project_id,
            "name": "Opening Scene",
            "detector_configs": {
                "ClockDetector": {
                    "enabled": True,
                    "threshold": 0.8
                },
                "ContinuityDetector": {
                    "enabled": True,
                    "sensitivity": "high"
                }
            }
        })
        assert scene_response.status_code == 200
        scene = scene_response.json()
        scene_id = scene["id"]
        
        # Step 3: Create angle
        angle_response = client.post("/api/angles", json={
            "scene_id": scene_id,
            "name": "Wide Shot",
            "description": "Main establishing shot"
        })
        assert angle_response.status_code == 200
        angle = angle_response.json()
        angle_id = angle["id"]
        
        # Step 4: Create reference take
        take_response = client.post("/api/takes", json={
            "angle_id": angle_id,
            "name": "Take 1",
            "is_reference": True
        })
        assert take_response.status_code == 200
        take = take_response.json()
        take_id = take["id"]
        
        # Step 5: Start capture
        capture_response = client.post(f"/api/takes/{take_id}/capture/start", json={
            "source_type": "screen",
            "source_config": {
                "monitor_index": 0,
                "capture_region": {
                    "x": 0, "y": 0,
                    "width": 1920, "height": 1080
                }
            }
        })
        assert capture_response.status_code == 200
        
        # Simulate capture for 2 seconds
        time.sleep(2)
        
        # Step 6: Stop capture
        stop_response = client.post(f"/api/takes/{take_id}/capture/stop")
        assert stop_response.status_code == 200
        
        # Step 7: Wait for processing
        max_wait = 10
        start_time = time.time()
        while time.time() - start_time < max_wait:
            status_response = client.get(f"/api/takes/{take_id}/status")
            status = status_response.json()
            if status["capture_status"] == "completed":
                break
            time.sleep(0.5)
        
        # Step 8: Verify frames were captured and processed
        frames_response = client.get(f"/api/frames?take_id={take_id}")
        assert frames_response.status_code == 200
        frames = frames_response.json()
        assert len(frames) > 0
        
        # Step 9: Check detector results
        detections_response = client.get(f"/api/takes/{take_id}/detections")
        assert detections_response.status_code == 200
        detections = detections_response.json()
        
        # Step 10: Export report
        export_response = client.post(f"/api/takes/{take_id}/export", json={
            "format": "pdf",
            "include_frames": True,
            "include_detections": True
        })
        assert export_response.status_code == 200
        export_result = export_response.json()
        assert "export_path" in export_result
    
    def test_multi_take_comparison_workflow(self, test_environment):
        """Test workflow comparing multiple takes."""
        client = test_environment["client"]
        
        # Create project structure
        project = client.post("/api/projects", json={"name": "Comparison Test"}).json()
        scene = client.post("/api/scenes", json={
            "project_id": project["id"],
            "name": "Test Scene"
        }).json()
        angle = client.post("/api/angles", json={
            "scene_id": scene["id"],
            "name": "Angle 1"
        }).json()
        
        # Create reference take
        ref_take = client.post("/api/takes", json={
            "angle_id": angle["id"],
            "name": "Reference Take",
            "is_reference": True
        }).json()
        
        # Simulate reference capture with mock frames
        ref_frames = self._create_mock_frames(ref_take["id"], 30)
        
        # Create comparison takes
        comparison_takes = []
        for i in range(2):
            take = client.post("/api/takes", json={
                "angle_id": angle["id"],
                "name": f"Take {i+2}",
                "is_reference": False
            }).json()
            
            # Create frames with slight differences
            frames = self._create_mock_frames(take["id"], 30, variation=i+1)
            comparison_takes.append(take)
        
        # Run comparison analysis
        comparison_response = client.post("/api/analysis/compare", json={
            "reference_take_id": ref_take["id"],
            "comparison_take_ids": [t["id"] for t in comparison_takes],
            "detector": "ContinuityDetector"
        })
        
        assert comparison_response.status_code == 200
        comparison_result = comparison_response.json()
        assert "differences" in comparison_result
        assert len(comparison_result["differences"]) > 0
    
    def _create_mock_frames(self, take_id, count, variation=0):
        """Helper to create mock frames for testing."""
        frames = []
        for i in range(count):
            # Create frame with variation
            frame_data = np.full((480, 640, 3), 100 + variation * 20, dtype=np.uint8)
            
            # Add some visual elements
            cv2.rectangle(frame_data, (100 + variation * 10, 100), 
                         (200 + variation * 10, 200), (255, 255, 255), -1)
            
            frames.append({
                "take_id": take_id,
                "frame_number": i,
                "timestamp": i / 30.0,
                "data": frame_data
            })
        return frames


class TestServiceIntegration:
    """Test integration between different services."""
    
    @pytest.mark.asyncio
    async def test_storage_capture_integration(self, test_environment):
        """Test integration between storage and capture services."""
        storage = test_environment["storage"]
        capture = test_environment["capture"]
        
        # Create take in storage
        project = await storage.create_project({"name": "Integration Test"})
        scene = await storage.create_scene({
            "project_id": project.id,
            "name": "Scene 1"
        })
        angle = await storage.create_angle({
            "scene_id": scene.id,
            "name": "Angle 1"
        })
        take = await storage.create_take({
            "angle_id": angle.id,
            "name": "Take 1"
        })
        
        # Configure capture to store frames
        capture.configure_storage(storage, take.id)
        
        # Mock capture source
        mock_source = MagicMock()
        mock_source.get_frame.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Start capture
        await capture.start_capture(mock_source)
        
        # Capture some frames
        for _ in range(10):
            frame = await capture.capture_frame()
            assert frame is not None
        
        await capture.stop_capture()
        
        # Verify frames in storage
        stored_frames = await storage.get_frames(take_id=take.id)
        assert len(stored_frames) == 10
    
    @pytest.mark.asyncio
    async def test_detector_storage_integration(self, test_environment):
        """Test integration between detector framework and storage."""
        storage = test_environment["storage"]
        detectors = test_environment["detectors"]
        
        # Create test data
        project = await storage.create_project({"name": "Detector Test"})
        scene = await storage.create_scene({
            "project_id": project.id,
            "name": "Scene 1",
            "detector_configs": {
                "TestDetector": {"enabled": True}
            }
        })
        angle = await storage.create_angle({"scene_id": scene.id, "name": "Angle 1"})
        take = await storage.create_take({"angle_id": angle.id, "name": "Take 1"})
        
        # Create frames
        frame_ids = []
        for i in range(5):
            frame = await storage.create_frame({
                "take_id": take.id,
                "frame_number": i,
                "timestamp": i / 30.0,
                "file_path": f"/frames/frame_{i}.jpg"
            })
            frame_ids.append(frame.id)
        
        # Mock detector
        mock_detector = MagicMock()
        mock_detector.process_frame = AsyncMock(return_value={
            "detected": True,
            "confidence": 0.9
        })
        
        # Register detector
        detectors.register_detector("TestDetector", mock_detector)
        
        # Process frames
        results = await detectors.process_take(
            take_id=take.id,
            frame_ids=frame_ids,
            detector_configs=scene.detector_configs
        )
        
        assert len(results) == 5
        
        # Verify results stored
        for frame_id in frame_ids:
            frame = await storage.get_frame(frame_id)
            assert frame.detector_results is not None
            assert "TestDetector" in frame.detector_results
    
    @pytest.mark.asyncio
    async def test_sse_real_time_updates(self, test_environment):
        """Test real-time updates via SSE during capture."""
        client = test_environment["client"]
        
        # Create project structure
        project = client.post("/api/projects", json={"name": "SSE Test"}).json()
        scene = client.post("/api/scenes", json={
            "project_id": project["id"],
            "name": "Scene 1"
        }).json()
        angle = client.post("/api/angles", json={
            "scene_id": scene["id"],
            "name": "Angle 1"
        }).json()
        take = client.post("/api/takes", json={
            "angle_id": angle["id"],
            "name": "Take 1"
        }).json()
        
        # Connect to SSE endpoint
        events = []
        
        def sse_listener():
            with client.stream("GET", f"/api/sse?channels=take:{take['id']}") as response:
                for line in response.iter_lines():
                    if line.startswith("data:"):
                        event_data = json.loads(line[5:])
                        events.append(event_data)
                        if len(events) >= 5:  # Collect 5 events
                            break
        
        # Start SSE listener in thread
        sse_thread = threading.Thread(target=sse_listener)
        sse_thread.start()
        
        # Simulate capture events
        time.sleep(0.5)  # Let SSE connect
        
        # Start capture
        client.post(f"/api/takes/{take['id']}/capture/start", json={
            "source_type": "test"
        })
        
        # Simulate frame captures
        for i in range(5):
            client.post(f"/api/takes/{take['id']}/frames", json={
                "frame_number": i,
                "timestamp": i / 30.0
            })
            time.sleep(0.1)
        
        # Stop capture
        client.post(f"/api/takes/{take['id']}/capture/stop")
        
        # Wait for events
        sse_thread.join(timeout=5)
        
        # Verify events received
        assert len(events) >= 5
        event_types = [e.get("type") for e in events]
        assert "capture:started" in event_types
        assert any("frame:captured" in t for t in event_types)


class TestConcurrentOperations:
    """Test concurrent operations across services."""
    
    @pytest.mark.asyncio
    async def test_concurrent_detector_processing(self, test_environment):
        """Test processing multiple takes concurrently."""
        storage = test_environment["storage"]
        detectors = test_environment["detectors"]
        
        # Create multiple takes
        project = await storage.create_project({"name": "Concurrent Test"})
        scene = await storage.create_scene({
            "project_id": project.id,
            "name": "Scene 1"
        })
        
        takes = []
        for i in range(3):
            angle = await storage.create_angle({
                "scene_id": scene.id,
                "name": f"Angle {i}"
            })
            take = await storage.create_take({
                "angle_id": angle.id,
                "name": f"Take {i}"
            })
            
            # Create frames for each take
            for j in range(10):
                await storage.create_frame({
                    "take_id": take.id,
                    "frame_number": j,
                    "timestamp": j / 30.0
                })
            
            takes.append(take)
        
        # Process all takes concurrently
        tasks = []
        for take in takes:
            task = detectors.process_take(
                take_id=take.id,
                detector_configs={"TestDetector": {"enabled": True}}
            )
            tasks.append(task)
        
        # Wait for all to complete
        results = await asyncio.gather(*tasks)
        
        # Verify all processed
        assert len(results) == 3
        for result in results:
            assert len(result) == 10  # 10 frames each
    
    def test_concurrent_api_requests(self, test_environment):
        """Test handling concurrent API requests."""
        client = test_environment["client"]
        
        # Create base data
        project = client.post("/api/projects", json={"name": "Concurrent API"}).json()
        
        # Function to create scene
        def create_scene(index):
            response = client.post("/api/scenes", json={
                "project_id": project["id"],
                "name": f"Scene {index}"
            })
            return response.json()
        
        # Create scenes concurrently
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(create_scene, i) for i in range(10)]
            scenes = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # Verify all created
        assert len(scenes) == 10
        
        # Verify no duplicates
        scene_ids = [s["id"] for s in scenes]
        assert len(set(scene_ids)) == 10


class TestErrorRecovery:
    """Test error recovery across service boundaries."""
    
    @pytest.mark.asyncio
    async def test_capture_failure_recovery(self, test_environment):
        """Test recovery from capture failures."""
        storage = test_environment["storage"]
        capture = test_environment["capture"]
        
        # Create take
        project = await storage.create_project({"name": "Recovery Test"})
        scene = await storage.create_scene({
            "project_id": project.id,
            "name": "Scene 1"
        })
        angle = await storage.create_angle({
            "scene_id": scene.id,
            "name": "Angle 1"
        })
        take = await storage.create_take({
            "angle_id": angle.id,
            "name": "Take 1"
        })
        
        # Mock failing capture source
        mock_source = MagicMock()
        mock_source.get_frame.side_effect = [
            np.zeros((480, 640, 3), dtype=np.uint8),  # Success
            Exception("Camera disconnected"),          # Failure
            np.zeros((480, 640, 3), dtype=np.uint8),  # Recovery
        ]
        
        # Configure with recovery
        capture.configure_storage(storage, take.id)
        capture.enable_auto_recovery()
        
        # Start capture
        await capture.start_capture(mock_source)
        
        # Capture with failure and recovery
        frames_captured = 0
        errors = 0
        
        for _ in range(3):
            try:
                frame = await capture.capture_frame()
                if frame is not None:
                    frames_captured += 1
            except Exception:
                errors += 1
        
        await capture.stop_capture()
        
        # Should have captured 2 frames (1st and 3rd)
        assert frames_captured == 2
        assert errors == 1
        
        # Verify take status reflects recovery
        take = await storage.get_take(take.id)
        assert take.status != CaptureStatus.ERROR
    
    @pytest.mark.asyncio
    async def test_detector_failure_isolation(self, test_environment):
        """Test that detector failures don't affect other detectors."""
        detectors = test_environment["detectors"]
        
        # Register multiple detectors
        good_detector = MagicMock()
        good_detector.process_frame = AsyncMock(return_value={
            "detected": True,
            "confidence": 0.9
        })
        
        bad_detector = MagicMock()
        bad_detector.process_frame = AsyncMock(
            side_effect=Exception("Detector crashed")
        )
        
        detectors.register_detector("GoodDetector", good_detector)
        detectors.register_detector("BadDetector", bad_detector)
        
        # Process frame with both detectors
        results = await detectors.process_frame(
            frame_id=1,
            frame_data={"path": "/frame.jpg"},
            detector_configs={
                "GoodDetector": {"enabled": True},
                "BadDetector": {"enabled": True}
            }
        )
        
        # Good detector should succeed
        assert "GoodDetector" in results
        assert results["GoodDetector"]["detected"] is True
        
        # Bad detector should have error result
        assert "BadDetector" in results
        assert results["BadDetector"].get("error") is True
    
    def test_api_transaction_rollback(self, test_environment):
        """Test transaction rollback on API errors."""
        client = test_environment["client"]
        
        # Create project
        project = client.post("/api/projects", json={"name": "Transaction Test"}).json()
        
        # Try to create scene with invalid data that will fail after partial processing
        response = client.post("/api/scenes", json={
            "project_id": project["id"],
            "name": "Test Scene",
            "detector_configs": {
                "InvalidDetector": {
                    "enabled": True,
                    "invalid_param": "will_cause_error"
                }
            }
        })
        
        # Should fail
        assert response.status_code == 400
        
        # Verify no partial data was saved
        scenes_response = client.get(f"/api/scenes?project_id={project['id']}")
        scenes = scenes_response.json()
        assert len(scenes) == 0
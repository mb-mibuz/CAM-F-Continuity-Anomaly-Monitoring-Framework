"""
Comprehensive tests for camera capture functionality.
Tests camera detection, initialization, frame capture, and error handling.
"""

import pytest
import cv2
import numpy as np
from unittest.mock import Mock, patch, MagicMock, PropertyMock
import time
import threading
import queue
from datetime import datetime

from CAMF.services.capture.camera import CameraCapture, CameraManager
from CAMF.services.capture.source import CaptureSource, SourceType, SourceStatus


class TestCameraCapture:
    """Test camera capture functionality."""
    
    @pytest.fixture
    def mock_video_capture(self):
        """Create mock VideoCapture object."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
        mock_cap.get.side_effect = lambda prop: {
            cv2.CAP_PROP_FRAME_WIDTH: 640,
            cv2.CAP_PROP_FRAME_HEIGHT: 480,
            cv2.CAP_PROP_FPS: 30,
            cv2.CAP_PROP_FRAME_COUNT: 0,
            cv2.CAP_PROP_FOURCC: cv2.VideoWriter_fourcc(*'MJPG')
        }.get(prop, 0)
        return mock_cap
    
    @pytest.fixture
    def camera_capture(self, mock_video_capture):
        """Create camera capture instance with mocked VideoCapture."""
        with patch('cv2.VideoCapture', return_value=mock_video_capture):
            capture = CameraCapture(camera_index=0)
            return capture
    
    def test_camera_initialization(self, mock_video_capture):
        """Test camera initialization."""
        with patch('cv2.VideoCapture', return_value=mock_video_capture):
            capture = CameraCapture(camera_index=0)
            
            assert capture.camera_index == 0
            assert capture.source_type == SourceType.CAMERA
            assert capture.status == SourceStatus.INITIALIZED
            assert capture.get_resolution() == (640, 480)
            assert capture.get_fps() == 30
    
    def test_camera_initialization_failure(self):
        """Test handling of camera initialization failure."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        
        with patch('cv2.VideoCapture', return_value=mock_cap):
            with pytest.raises(RuntimeError, match="Failed to open camera"):
                CameraCapture(camera_index=0)
    
    def test_start_capture(self, camera_capture, mock_video_capture):
        """Test starting camera capture."""
        # Start capture
        success = camera_capture.start()
        
        assert success is True
        assert camera_capture.status == SourceStatus.ACTIVE
        assert camera_capture._capture_thread is not None
        assert camera_capture._capture_thread.is_alive()
        
        # Stop capture
        camera_capture.stop()
    
    def test_capture_frame(self, camera_capture, mock_video_capture):
        """Test capturing individual frames."""
        camera_capture.start()
        
        # Wait for frames to be captured
        time.sleep(0.1)
        
        # Get frame
        frame = camera_capture.get_frame()
        
        assert frame is not None
        assert frame.shape == (480, 640, 3)
        assert camera_capture.frame_count > 0
        
        camera_capture.stop()
    
    def test_capture_frame_queue(self, camera_capture, mock_video_capture):
        """Test frame queue management."""
        camera_capture.start()
        
        # Let it capture some frames
        time.sleep(0.2)
        
        # Check queue size
        assert camera_capture.get_queue_size() > 0
        
        # Drain queue
        frames = []
        while camera_capture.get_queue_size() > 0:
            frame = camera_capture.get_frame()
            if frame is not None:
                frames.append(frame)
        
        assert len(frames) > 0
        
        camera_capture.stop()
    
    def test_capture_with_frame_skip(self, camera_capture):
        """Test frame skipping for performance."""
        camera_capture.set_frame_skip(2)  # Skip every other frame
        camera_capture.start()
        
        time.sleep(0.3)
        
        # Frame count should be roughly half of what it would be
        frame_count = camera_capture.frame_count
        
        camera_capture.stop()
        
        # Verify frame skipping worked (approximate due to timing)
        assert frame_count < 15  # Would be ~30 without skipping
    
    def test_camera_disconnection_handling(self, camera_capture, mock_video_capture):
        """Test handling of camera disconnection."""
        camera_capture.start()
        
        # Simulate camera disconnection
        mock_video_capture.read.return_value = (False, None)
        
        # Wait for error detection
        time.sleep(0.2)
        
        assert camera_capture.status == SourceStatus.ERROR
        assert camera_capture.get_error() is not None
    
    def test_camera_reconnection(self, camera_capture, mock_video_capture):
        """Test camera reconnection after disconnection."""
        camera_capture.start()
        
        # Simulate disconnection
        mock_video_capture.read.return_value = (False, None)
        time.sleep(0.1)
        
        # Simulate reconnection
        mock_video_capture.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
        mock_video_capture.isOpened.return_value = True
        
        # Try to reconnect
        success = camera_capture.reconnect()
        
        assert success is True
        assert camera_capture.status == SourceStatus.ACTIVE
        
        camera_capture.stop()
    
    def test_camera_properties(self, camera_capture, mock_video_capture):
        """Test getting and setting camera properties."""
        # Get properties
        props = camera_capture.get_properties()
        assert "width" in props
        assert "height" in props
        assert "fps" in props
        assert "codec" in props
        
        # Set properties
        success = camera_capture.set_property("width", 1920)
        mock_video_capture.set.assert_called_with(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        
        success = camera_capture.set_property("fps", 60)
        mock_video_capture.set.assert_called_with(cv2.CAP_PROP_FPS, 60)
    
    def test_frame_timestamp_accuracy(self, camera_capture):
        """Test frame timestamp accuracy."""
        camera_capture.start()
        
        timestamps = []
        for _ in range(10):
            frame = camera_capture.get_frame()
            if frame is not None:
                timestamps.append(camera_capture.get_last_frame_timestamp())
            time.sleep(0.033)  # ~30fps
        
        camera_capture.stop()
        
        # Check timestamps are increasing
        for i in range(1, len(timestamps)):
            assert timestamps[i] > timestamps[i-1]
        
        # Check timestamp intervals (approximately 33ms for 30fps)
        intervals = [timestamps[i] - timestamps[i-1] for i in range(1, len(timestamps))]
        avg_interval = sum(intervals) / len(intervals)
        assert 0.02 < avg_interval < 0.05  # Allow some variance


class TestCameraManager:
    """Test camera manager for multiple cameras."""
    
    @pytest.fixture
    def mock_cameras(self):
        """Create mock cameras."""
        cameras = []
        for i in range(3):
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
            mock_cap.get.side_effect = lambda prop: {
                cv2.CAP_PROP_FRAME_WIDTH: 640,
                cv2.CAP_PROP_FRAME_HEIGHT: 480,
                cv2.CAP_PROP_FPS: 30,
            }.get(prop, 0)
            cameras.append(mock_cap)
        return cameras
    
    @pytest.fixture
    def camera_manager(self, mock_cameras):
        """Create camera manager with mocked cameras."""
        with patch('cv2.VideoCapture', side_effect=mock_cameras):
            manager = CameraManager()
            return manager
    
    def test_enumerate_cameras(self, camera_manager):
        """Test camera enumeration."""
        with patch.object(camera_manager, '_test_camera', return_value=True):
            cameras = camera_manager.enumerate_cameras()
            
            # Should find at least one camera
            assert len(cameras) > 0
            assert all('index' in cam for cam in cameras)
            assert all('name' in cam for cam in cameras)
    
    def test_add_camera(self, camera_manager, mock_cameras):
        """Test adding camera to manager."""
        with patch('cv2.VideoCapture', return_value=mock_cameras[0]):
            camera_id = camera_manager.add_camera(0, name="Main Camera")
            
            assert camera_id is not None
            assert camera_manager.get_camera(camera_id) is not None
            assert camera_manager.get_camera_count() == 1
    
    def test_remove_camera(self, camera_manager, mock_cameras):
        """Test removing camera from manager."""
        with patch('cv2.VideoCapture', return_value=mock_cameras[0]):
            camera_id = camera_manager.add_camera(0)
            
            # Remove camera
            success = camera_manager.remove_camera(camera_id)
            
            assert success is True
            assert camera_manager.get_camera(camera_id) is None
            assert camera_manager.get_camera_count() == 0
    
    def test_multiple_cameras(self, camera_manager, mock_cameras):
        """Test managing multiple cameras."""
        camera_ids = []
        
        # Add multiple cameras
        for i in range(3):
            with patch('cv2.VideoCapture', return_value=mock_cameras[i]):
                camera_id = camera_manager.add_camera(i, name=f"Camera {i}")
                camera_ids.append(camera_id)
        
        assert camera_manager.get_camera_count() == 3
        
        # Start all cameras
        for cam_id in camera_ids:
            camera = camera_manager.get_camera(cam_id)
            camera.start()
        
        # Get frames from all cameras
        frames = camera_manager.get_frames_from_all()
        assert len(frames) == 3
        assert all(frame is not None for _, frame in frames.items())
        
        # Stop all cameras
        camera_manager.stop_all_cameras()
    
    def test_camera_synchronization(self, camera_manager, mock_cameras):
        """Test synchronized capture from multiple cameras."""
        # Add cameras
        cam_ids = []
        for i in range(2):
            with patch('cv2.VideoCapture', return_value=mock_cameras[i]):
                cam_id = camera_manager.add_camera(i)
                cam_ids.append(cam_id)
        
        # Enable synchronization
        camera_manager.enable_sync_mode()
        
        # Start synchronized capture
        camera_manager.start_all_cameras()
        
        # Capture synchronized frames
        time.sleep(0.1)
        sync_frames = camera_manager.capture_synchronized()
        
        assert len(sync_frames) == 2
        # Timestamps should be very close
        timestamps = [camera_manager.get_camera(cam_id).get_last_frame_timestamp() 
                     for cam_id in cam_ids]
        assert abs(timestamps[0] - timestamps[1]) < 0.01  # Within 10ms
        
        camera_manager.stop_all_cameras()
    
    def test_camera_health_monitoring(self, camera_manager, mock_cameras):
        """Test camera health monitoring."""
        with patch('cv2.VideoCapture', return_value=mock_cameras[0]):
            cam_id = camera_manager.add_camera(0)
            camera = camera_manager.get_camera(cam_id)
            camera.start()
        
        # Get health status
        health = camera_manager.get_camera_health(cam_id)
        
        assert health["status"] == "healthy"
        assert health["fps"] > 0
        assert health["frame_count"] >= 0
        assert health["error_count"] == 0
        
        # Simulate errors
        mock_cameras[0].read.return_value = (False, None)
        time.sleep(0.2)
        
        health = camera_manager.get_camera_health(cam_id)
        assert health["status"] == "error"
        assert health["error_count"] > 0
        
        camera_manager.stop_all_cameras()


class TestCameraConfiguration:
    """Test camera configuration and settings."""
    
    @pytest.fixture
    def camera_config(self):
        """Create camera configuration."""
        return {
            "resolution": (1920, 1080),
            "fps": 60,
            "exposure": -5,
            "gain": 10,
            "white_balance": 5000,
            "focus": 100,
            "codec": "MJPG"
        }
    
    def test_apply_camera_config(self, camera_capture, mock_video_capture, camera_config):
        """Test applying camera configuration."""
        # Apply configuration
        success = camera_capture.apply_configuration(camera_config)
        
        # Verify settings were applied
        assert mock_video_capture.set.call_count >= len(camera_config)
        mock_video_capture.set.assert_any_call(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        mock_video_capture.set.assert_any_call(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        mock_video_capture.set.assert_any_call(cv2.CAP_PROP_FPS, 60)
    
    def test_save_load_camera_config(self, camera_capture, camera_config, tmp_path):
        """Test saving and loading camera configuration."""
        config_file = tmp_path / "camera_config.json"
        
        # Save configuration
        camera_capture.save_configuration(str(config_file), camera_config)
        assert config_file.exists()
        
        # Load configuration
        loaded_config = camera_capture.load_configuration(str(config_file))
        assert loaded_config == camera_config
    
    def test_auto_exposure_adjustment(self, camera_capture, mock_video_capture):
        """Test automatic exposure adjustment."""
        # Create frames with different brightness
        dark_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        bright_frame = np.full((480, 640, 3), 200, dtype=np.uint8)
        
        # Test auto exposure
        mock_video_capture.read.return_value = (True, dark_frame)
        camera_capture.enable_auto_exposure()
        camera_capture.start()
        
        time.sleep(0.1)
        
        # Should attempt to adjust exposure
        calls = [call for call in mock_video_capture.set.call_args_list 
                if call[0][0] == cv2.CAP_PROP_EXPOSURE]
        assert len(calls) > 0
        
        camera_capture.stop()
    
    def test_resolution_validation(self, camera_capture):
        """Test resolution validation."""
        # Valid resolutions
        valid_resolutions = [
            (640, 480), (1280, 720), (1920, 1080), (3840, 2160)
        ]
        
        for res in valid_resolutions:
            assert camera_capture.is_valid_resolution(res) is True
        
        # Invalid resolutions
        invalid_resolutions = [
            (0, 0), (-1, 480), (640, -1), (999999, 999999)
        ]
        
        for res in invalid_resolutions:
            assert camera_capture.is_valid_resolution(res) is False


class TestCameraPerformance:
    """Test camera capture performance."""
    
    @pytest.fixture
    def performance_monitor(self):
        """Create performance monitor."""
        return {
            "frame_times": [],
            "dropped_frames": 0,
            "total_frames": 0
        }
    
    def test_capture_frame_rate(self, camera_capture, mock_video_capture, performance_monitor):
        """Test actual vs target frame rate."""
        target_fps = 30
        camera_capture.set_property("fps", target_fps)
        camera_capture.start()
        
        # Capture for 1 second
        start_time = time.time()
        frame_count = 0
        
        while time.time() - start_time < 1.0:
            frame = camera_capture.get_frame()
            if frame is not None:
                frame_count += 1
                performance_monitor["frame_times"].append(time.time())
        
        camera_capture.stop()
        
        # Check frame rate (allow 10% variance)
        actual_fps = frame_count
        assert abs(actual_fps - target_fps) / target_fps < 0.1
    
    def test_frame_dropping_under_load(self, camera_capture, mock_video_capture):
        """Test frame dropping when processing is slow."""
        camera_capture.enable_frame_dropping()
        camera_capture.start()
        
        dropped_before = camera_capture.get_dropped_frame_count()
        
        # Simulate slow processing
        for _ in range(10):
            time.sleep(0.1)  # Slow processing
            frame = camera_capture.get_frame()
        
        dropped_after = camera_capture.get_dropped_frame_count()
        
        # Should have dropped some frames
        assert dropped_after > dropped_before
        
        camera_capture.stop()
    
    def test_memory_usage(self, camera_capture, mock_video_capture):
        """Test memory usage during capture."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        memory_before = process.memory_info().rss
        
        camera_capture.start()
        
        # Capture many frames
        for _ in range(100):
            frame = camera_capture.get_frame()
            # Don't keep references
        
        camera_capture.stop()
        
        memory_after = process.memory_info().rss
        memory_increase = memory_after - memory_before
        
        # Memory increase should be reasonable (< 100MB)
        assert memory_increase < 100 * 1024 * 1024
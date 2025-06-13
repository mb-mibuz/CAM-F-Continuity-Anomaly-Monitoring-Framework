"""
Comprehensive tests for screen and window capture functionality.
Tests screen capture, window detection, capture modes, and multi-monitor support.
"""

import pytest
import numpy as np
from unittest.mock import Mock, patch, MagicMock, PropertyMock
import time
import platform
from PIL import Image
import io

from CAMF.services.capture.screen import ScreenCapture, Monitor
from CAMF.services.capture.window import WindowCapture, Window
from CAMF.services.capture.source import SourceType, SourceStatus


class TestScreenCapture:
    """Test screen capture functionality."""
    
    @pytest.fixture
    def mock_screenshot(self):
        """Create mock screenshot."""
        # Create a test image
        img = Image.new('RGB', (1920, 1080), color='red')
        return img
    
    @pytest.fixture
    def mock_mss(self, mock_screenshot):
        """Create mock mss instance."""
        mock_sct = MagicMock()
        mock_monitor = {
            "left": 0,
            "top": 0,
            "width": 1920,
            "height": 1080
        }
        
        # Mock screenshot data
        screenshot_data = io.BytesIO()
        mock_screenshot.save(screenshot_data, format='PNG')
        mock_sct.grab.return_value.rgb = screenshot_data.getvalue()
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 1920, "height": 1080},  # Combined
            {"left": 0, "top": 0, "width": 1920, "height": 1080},  # Primary
            {"left": 1920, "top": 0, "width": 1920, "height": 1080}  # Secondary
        ]
        
        return mock_sct
    
    @pytest.fixture
    def screen_capture(self, mock_mss):
        """Create screen capture instance with mocked mss."""
        with patch('mss.mss', return_value=mock_mss):
            capture = ScreenCapture(monitor_index=1)
            capture._sct = mock_mss
            return capture
    
    def test_screen_initialization(self, mock_mss):
        """Test screen capture initialization."""
        with patch('mss.mss', return_value=mock_mss):
            capture = ScreenCapture(monitor_index=1)
            
            assert capture.monitor_index == 1
            assert capture.source_type == SourceType.SCREEN
            assert capture.status == SourceStatus.INITIALIZED
            assert capture.get_resolution() == (1920, 1080)
    
    def test_enumerate_monitors(self, screen_capture, mock_mss):
        """Test monitor enumeration."""
        monitors = screen_capture.enumerate_monitors()
        
        assert len(monitors) == 2  # Excluding combined monitor
        assert monitors[0].index == 1
        assert monitors[0].width == 1920
        assert monitors[0].height == 1080
        assert monitors[0].is_primary is True
    
    def test_capture_full_screen(self, screen_capture, mock_mss):
        """Test capturing full screen."""
        screen_capture.start()
        
        # Wait for capture
        time.sleep(0.1)
        
        frame = screen_capture.get_frame()
        assert frame is not None
        assert frame.shape == (1080, 1920, 3)
        
        screen_capture.stop()
    
    def test_capture_screen_region(self, screen_capture, mock_mss):
        """Test capturing specific screen region."""
        # Set capture region
        region = {"left": 100, "top": 100, "width": 800, "height": 600}
        screen_capture.set_capture_region(region)
        
        screen_capture.start()
        time.sleep(0.1)
        
        # Mock should be called with region
        mock_mss.grab.assert_called_with({
            "left": 100,
            "top": 100,
            "width": 800,
            "height": 600
        })
        
        screen_capture.stop()
    
    def test_multi_monitor_capture(self, mock_mss):
        """Test capturing from multiple monitors."""
        captures = []
        
        # Create capture for each monitor
        for i in [1, 2]:
            with patch('mss.mss', return_value=mock_mss):
                capture = ScreenCapture(monitor_index=i)
                capture._sct = mock_mss
                captures.append(capture)
        
        # Start all captures
        for capture in captures:
            capture.start()
        
        time.sleep(0.1)
        
        # Get frames from all monitors
        frames = [capture.get_frame() for capture in captures]
        assert all(frame is not None for frame in frames)
        
        # Stop all captures
        for capture in captures:
            capture.stop()
    
    def test_capture_performance_mode(self, screen_capture):
        """Test different capture performance modes."""
        # High quality mode
        screen_capture.set_capture_mode("quality")
        assert screen_capture.capture_quality == 100
        assert screen_capture.capture_interval == 0
        
        # Performance mode
        screen_capture.set_capture_mode("performance")
        assert screen_capture.capture_quality < 100
        assert screen_capture.capture_interval > 0
        
        # Balanced mode
        screen_capture.set_capture_mode("balanced")
        assert 50 <= screen_capture.capture_quality <= 90
    
    def test_screen_change_detection(self, screen_capture, mock_mss):
        """Test screen change detection for efficiency."""
        screen_capture.enable_change_detection(threshold=0.05)
        screen_capture.start()
        
        # First frame should always be captured
        frame1 = screen_capture.get_frame()
        assert frame1 is not None
        
        # Without changes, might skip frames
        frame2 = screen_capture.get_frame()
        
        # Simulate screen change
        new_img = Image.new('RGB', (1920, 1080), color='blue')
        screenshot_data = io.BytesIO()
        new_img.save(screenshot_data, format='PNG')
        mock_mss.grab.return_value.rgb = screenshot_data.getvalue()
        
        # Should detect change and capture
        frame3 = screen_capture.get_frame()
        assert frame3 is not None
        
        screen_capture.stop()
    
    def test_cursor_capture(self, screen_capture):
        """Test cursor capture options."""
        # Enable cursor capture
        screen_capture.set_capture_cursor(True)
        assert screen_capture.capture_cursor is True
        
        # Disable cursor capture
        screen_capture.set_capture_cursor(False)
        assert screen_capture.capture_cursor is False
    
    def test_screen_capture_error_handling(self, screen_capture, mock_mss):
        """Test error handling during screen capture."""
        screen_capture.start()
        
        # Simulate capture error
        mock_mss.grab.side_effect = Exception("Screen capture failed")
        
        time.sleep(0.1)
        
        assert screen_capture.status == SourceStatus.ERROR
        assert screen_capture.get_error() is not None
        assert "Screen capture failed" in str(screen_capture.get_error())


class TestWindowCapture:
    """Test window capture functionality."""
    
    @pytest.fixture
    def mock_windows(self):
        """Create mock window list."""
        return [
            Window(id=1, title="Application 1", process="app1.exe", 
                  x=100, y=100, width=800, height=600),
            Window(id=2, title="Application 2", process="app2.exe",
                  x=200, y=200, width=1024, height=768),
            Window(id=3, title="Background App", process="bg.exe",
                  x=0, y=0, width=400, height=300, visible=False)
        ]
    
    @pytest.fixture
    def mock_window_manager(self, mock_windows):
        """Create mock window manager."""
        mock_wm = MagicMock()
        mock_wm.enumerate_windows.return_value = mock_windows
        mock_wm.get_window_by_id.side_effect = lambda id: next(
            (w for w in mock_windows if w.id == id), None
        )
        mock_wm.capture_window.return_value = np.zeros((600, 800, 3), dtype=np.uint8)
        return mock_wm
    
    @pytest.fixture
    def window_capture(self, mock_window_manager):
        """Create window capture instance."""
        with patch('CAMF.services.capture.window.WindowManager', return_value=mock_window_manager):
            capture = WindowCapture(window_id=1)
            capture._window_manager = mock_window_manager
            return capture
    
    def test_window_enumeration(self, window_capture, mock_windows):
        """Test window enumeration."""
        windows = window_capture.enumerate_windows()
        
        assert len(windows) == 3
        assert windows[0].title == "Application 1"
        assert windows[1].title == "Application 2"
        assert windows[2].visible is False
    
    def test_window_capture_by_id(self, window_capture):
        """Test capturing window by ID."""
        window_capture.start()
        
        time.sleep(0.1)
        
        frame = window_capture.get_frame()
        assert frame is not None
        assert frame.shape == (600, 800, 3)
        
        window_capture.stop()
    
    def test_window_capture_by_title(self, mock_window_manager, mock_windows):
        """Test capturing window by title."""
        with patch('CAMF.services.capture.window.WindowManager', return_value=mock_window_manager):
            capture = WindowCapture(window_title="Application 2")
            capture._window_manager = mock_window_manager
            
            # Should find window by title
            assert capture.window_id == 2
            assert capture.get_resolution() == (1024, 768)
    
    def test_window_capture_by_process(self, mock_window_manager, mock_windows):
        """Test capturing window by process name."""
        with patch('CAMF.services.capture.window.WindowManager', return_value=mock_window_manager):
            capture = WindowCapture(process_name="app1.exe")
            capture._window_manager = mock_window_manager
            
            # Should find window by process
            assert capture.window_id == 1
    
    def test_window_focus_tracking(self, window_capture, mock_window_manager):
        """Test window focus change tracking."""
        window_capture.enable_focus_tracking()
        window_capture.start()
        
        # Simulate window losing focus
        mock_window_manager.is_window_focused.return_value = False
        time.sleep(0.1)
        
        assert window_capture.is_focused() is False
        
        # Simulate window gaining focus
        mock_window_manager.is_window_focused.return_value = True
        time.sleep(0.1)
        
        assert window_capture.is_focused() is True
        
        window_capture.stop()
    
    def test_window_minimized_handling(self, window_capture, mock_window_manager):
        """Test handling of minimized windows."""
        window_capture.start()
        
        # Simulate window being minimized
        mock_window_manager.is_window_visible.return_value = False
        mock_window_manager.capture_window.return_value = None
        
        time.sleep(0.1)
        
        frame = window_capture.get_frame()
        assert frame is None  # No frame when minimized
        
        # Restore window
        mock_window_manager.is_window_visible.return_value = True
        mock_window_manager.capture_window.return_value = np.zeros((600, 800, 3), dtype=np.uint8)
        
        time.sleep(0.1)
        
        frame = window_capture.get_frame()
        assert frame is not None
        
        window_capture.stop()
    
    def test_window_resize_handling(self, window_capture, mock_window_manager):
        """Test handling of window resize."""
        window_capture.start()
        
        # Initial size
        assert window_capture.get_resolution() == (800, 600)
        
        # Simulate window resize
        resized_window = Window(id=1, title="Application 1", process="app1.exe",
                               x=100, y=100, width=1024, height=768)
        mock_window_manager.get_window_by_id.return_value = resized_window
        mock_window_manager.capture_window.return_value = np.zeros((768, 1024, 3), dtype=np.uint8)
        
        # Trigger resize detection
        window_capture._update_window_info()
        
        # Check new resolution
        assert window_capture.get_resolution() == (1024, 768)
        
        window_capture.stop()
    
    def test_window_closed_handling(self, window_capture, mock_window_manager):
        """Test handling of window being closed."""
        window_capture.start()
        
        # Simulate window being closed
        mock_window_manager.get_window_by_id.return_value = None
        mock_window_manager.capture_window.side_effect = Exception("Window not found")
        
        time.sleep(0.1)
        
        assert window_capture.status == SourceStatus.ERROR
        assert "Window not found" in str(window_capture.get_error())
        
        window_capture.stop()
    
    def test_window_capture_with_borders(self, window_capture):
        """Test window capture with/without borders."""
        # Capture with borders (default)
        window_capture.set_include_borders(True)
        assert window_capture.include_borders is True
        
        # Capture without borders
        window_capture.set_include_borders(False)
        assert window_capture.include_borders is False
    
    def test_window_capture_child_windows(self, window_capture):
        """Test capturing child windows."""
        # Enable child window capture
        window_capture.set_capture_child_windows(True)
        assert window_capture.capture_child_windows is True
        
        # This would affect the actual capture behavior
        # Implementation would merge child windows into parent capture


class TestPlatformSpecific:
    """Test platform-specific capture features."""
    
    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows-specific test")
    def test_windows_dwm_capture(self):
        """Test Windows DWM (Desktop Window Manager) capture."""
        from CAMF.services.capture.window import WindowsDWMCapture
        
        capture = WindowsDWMCapture(window_handle=12345)
        assert capture.capture_method == "DWM"
        # Would test actual DWM capture functionality
    
    @pytest.mark.skipif(platform.system() != "Darwin", reason="macOS-specific test")
    def test_macos_window_capture(self):
        """Test macOS window capture permissions."""
        from CAMF.services.capture.window import MacOSWindowCapture
        
        capture = MacOSWindowCapture(window_id=12345)
        # Check screen recording permission
        assert capture.check_screen_recording_permission() in [True, False]
    
    @pytest.mark.skipif(platform.system() != "Linux", reason="Linux-specific test")
    def test_linux_x11_capture(self):
        """Test Linux X11 window capture."""
        from CAMF.services.capture.window import X11WindowCapture
        
        capture = X11WindowCapture(window_id=12345)
        assert capture.display_protocol in ["X11", "Wayland"]


class TestCaptureIntegration:
    """Test integration between screen and window capture."""
    
    def test_capture_window_from_screen_region(self, screen_capture, window_capture, mock_windows):
        """Test capturing window area from screen."""
        # Get window position
        window = mock_windows[0]  # Application 1
        
        # Set screen capture region to window area
        screen_capture.set_capture_region({
            "left": window.x,
            "top": window.y,
            "width": window.width,
            "height": window.height
        })
        
        screen_capture.start()
        window_capture.start()
        
        time.sleep(0.1)
        
        # Both should capture the same area
        screen_frame = screen_capture.get_frame()
        window_frame = window_capture.get_frame()
        
        assert screen_frame is not None
        assert window_frame is not None
        # In real scenario, frames would be similar
        
        screen_capture.stop()
        window_capture.stop()
    
    def test_multi_source_capture(self, screen_capture, window_capture):
        """Test capturing from multiple sources simultaneously."""
        sources = [screen_capture, window_capture]
        
        # Start all sources
        for source in sources:
            source.start()
        
        time.sleep(0.1)
        
        # Capture from all sources
        frames = {}
        for source in sources:
            frame = source.get_frame()
            frames[source.source_type] = frame
        
        assert len(frames) == 2
        assert all(frame is not None for frame in frames.values())
        
        # Stop all sources
        for source in sources:
            source.stop()


class TestCapturePerformance:
    """Test capture performance and optimization."""
    
    def test_screen_capture_fps(self, screen_capture):
        """Test screen capture frame rate."""
        target_fps = 30
        screen_capture.set_target_fps(target_fps)
        screen_capture.start()
        
        # Capture for 1 second
        start_time = time.time()
        frames = []
        
        while time.time() - start_time < 1.0:
            frame = screen_capture.get_frame()
            if frame is not None:
                frames.append((frame, time.time()))
        
        screen_capture.stop()
        
        # Check actual FPS
        actual_fps = len(frames)
        assert abs(actual_fps - target_fps) < 5  # Allow some variance
        
        # Check frame timing
        if len(frames) > 1:
            intervals = [frames[i][1] - frames[i-1][1] for i in range(1, len(frames))]
            avg_interval = sum(intervals) / len(intervals)
            expected_interval = 1.0 / target_fps
            assert abs(avg_interval - expected_interval) < 0.01
    
    def test_capture_gpu_acceleration(self, screen_capture):
        """Test GPU-accelerated capture when available."""
        # Check if GPU acceleration is available
        if screen_capture.is_gpu_acceleration_available():
            screen_capture.enable_gpu_acceleration()
            assert screen_capture.gpu_accelerated is True
            
            # Performance should be better with GPU
            # Would measure actual performance difference
    
    def test_capture_memory_efficiency(self, screen_capture):
        """Test memory efficiency during long captures."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        memory_before = process.memory_info().rss
        
        screen_capture.start()
        
        # Capture many frames
        for _ in range(100):
            frame = screen_capture.get_frame()
            # Don't keep references
        
        screen_capture.stop()
        
        memory_after = process.memory_info().rss
        memory_increase = memory_after - memory_before
        
        # Memory increase should be minimal
        assert memory_increase < 50 * 1024 * 1024  # Less than 50MB
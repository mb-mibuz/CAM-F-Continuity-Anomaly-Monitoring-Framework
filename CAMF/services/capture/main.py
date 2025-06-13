# CAMF/services/capture/main.py - Thread-safe version
import base64
from typing import Dict, Any, Optional, List, Tuple, Callable, Union
import threading
import time

import numpy as np

# Try to import cv2, but don't fail if not available
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    import logging
    logging.warning("OpenCV (cv2) not available - some features will be disabled")

from CAMF.services.storage import get_storage_service
from CAMF.common.resolution_utils import downscale_frame, should_downscale
from .camera import CameraSource
from .screen import ScreenSource
from .window import WindowSource
from .upload import VideoUploadProcessor

# Resolution presets
RESOLUTION_PRESETS = {
    "4K": (3840, 2160),
    "1080p": (1920, 1080),
    "720p": (1280, 720),
    "480p": (854, 480)
}

class CaptureService:
    """Service for capturing frames from various sources with thread safety."""
    
    def __init__(self):
        """Initialize the capture service with thread-safe state management."""
        self.storage = get_storage_service()
        self.source = None
        self.source_type = None
        
        # Thread-safe state management
        self._state_lock = threading.RLock()
        self._capturing = False
        self._active_take_id = None
        self._frame_count = 0
        self._stop_requested = False
        self._capture_start_time = None
        self._source_error = None
        
        # Settings
        self.frame_rate = 1.0  # Default to 1 FPS
        self.max_resolution = None  # No resolution limit by default
        self.scene_resolution = "1080p"  # Default scene resolution
        
        # Preview
        self.preview_callbacks = []
        
        # Error handling
        self.error_callbacks = []

        # Video upload support
        self.video_processor = VideoUploadProcessor()

        self._preview_frame = None  
        self._preview_lock = threading.Lock()
        
        # SSE callback for real-time streaming
        self.sse_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        
        # Status update thread
        self._status_update_thread = None
        self._last_status_update = 0
        self.status_update_interval = 0.1  # 100ms updates
        
        # Frame count limit
        self.frame_count_limit = None
        
        # Detector processing context
        self.is_monitoring_mode = False  # True when in take monitoring page
        self.reference_take_id = None  # Reference take for comparison
        
        # Cache for camera list to avoid enumeration during capture
        self._cached_cameras = []
        self._camera_cache_time = 0
    
    # Thread-safe property accessors
    @property
    def capturing(self):
        with self._state_lock:
            return self._capturing
    
    @capturing.setter
    def capturing(self, value):
        with self._state_lock:
            self._capturing = value
    
    @property
    def active_take_id(self):
        with self._state_lock:
            return self._active_take_id
    
    @active_take_id.setter
    def active_take_id(self, value):
        with self._state_lock:
            self._active_take_id = value
    
    @property
    def is_capturing(self):
        """Public property to check if capture is in progress."""
        with self._state_lock:
            return self._capturing
    
    @property
    def frame_count(self):
        with self._state_lock:
            return self._frame_count
    
    @frame_count.setter
    def frame_count(self, value):
        with self._state_lock:
            self._frame_count = value
    
    @property
    def capture_start_time(self):
        with self._state_lock:
            return self._capture_start_time
    
    def increment_frame_count(self):
        """Thread-safe frame count increment."""
        with self._state_lock:
            self._frame_count += 1
            return self._frame_count
    
    def get_capture_state(self):
        """Get current capture state atomically."""
        with self._state_lock:
            return {
                'capturing': self._capturing,
                'active_take_id': self._active_take_id,
                'frame_count': self._frame_count,
                'stop_requested': self._stop_requested
            }
    
    def set_frame_rate(self, frame_rate: float):
        """Set the capture frame rate.
        
        Args:
            frame_rate: Frames per second (can be fractional, e.g., 0.2 for 1 frame every 5 seconds)
        """
        self.frame_rate = frame_rate
        
        # Update source if it exists
        if self.source:
            self.source.frame_rate = frame_rate
    
    def set_monitoring_mode(self, enabled: bool, reference_take_id: Optional[int] = None):
        """Set whether we're in take monitoring mode (enables detector processing).
        
        Args:
            enabled: Whether monitoring mode is enabled
            reference_take_id: ID of the reference take for comparison
        """
        self.is_monitoring_mode = enabled
        self.reference_take_id = reference_take_id
        
        # Cache reference frame count for processing limit
        self._reference_frame_count = None
        if reference_take_id:
            try:
                reference_frames = self.storage.get_frames_for_take(reference_take_id)
                if reference_frames:
                    self._reference_frame_count = len(reference_frames)
                    print(f"[CaptureService] Cached reference frame count: {self._reference_frame_count}")
            except Exception as e:
                print(f"[CaptureService] Error getting reference frame count: {e}")
        
        print(f"[CaptureService] Monitoring mode set to: {enabled}, reference take: {reference_take_id}")
        print(f"[CaptureService] is_monitoring_mode = {self.is_monitoring_mode}")
        print(f"[CaptureService] reference_take_id = {self.reference_take_id}")
    
    def set_max_resolution(self, resolution: Union[str, Tuple[int, int], None]):
        """Set the maximum resolution for captured frames.
        
        Args:
            resolution: Either a preset name ("4K", "1080p", etc.), a tuple (width, height),
                        or None for no limit
        """
        if isinstance(resolution, str):
            if resolution in RESOLUTION_PRESETS:
                self.max_resolution = RESOLUTION_PRESETS[resolution]
            else:
                raise ValueError(f"Unknown resolution preset: {resolution}")
        else:
            self.max_resolution = resolution
        
        # Update source if it exists
        if self.source:
            self.source.max_resolution = self.max_resolution
    
    def set_camera_source(self, camera_id: int) -> bool:
        """Set a camera as the capture source.
        
        Args:
            camera_id: ID of the camera to use
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Clean up existing source
            self._cleanup_source()
            
            # Create and connect to new source
            self.source = CameraSource(
                camera_id=camera_id,
                frame_rate=self.frame_rate,
                max_resolution=self.max_resolution
            )
            
            if not self.source.connect():
                self.source = None
                return False
            
            self.source_type = "camera"
            self.source.add_frame_callback(self._handle_frame)
            self.source.add_error_callback(self._handle_source_error)
            return True
        except Exception as e:
            error_msg = f"Error setting camera source: {e}"
            print(error_msg)
            self._notify_error(error_msg)
            self.source = None
            return False
    
    def set_screen_source(self, monitor_id: int = 1, region: Optional[Tuple[int, int, int, int]] = None) -> bool:
        """Set a screen as the capture source.
        
        Args:
            monitor_id: ID of the monitor to capture
            region: Optional region to capture as (left, top, width, height)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Clean up existing source
            self._cleanup_source()
            
            # Create and connect to new source
            self.source = ScreenSource(
                monitor_id=monitor_id,
                region=region,
                frame_rate=self.frame_rate,
                max_resolution=self.max_resolution
            )
            
            if not self.source.connect():
                self.source = None
                return False
            
            self.source_type = "screen"
            self.source.add_frame_callback(self._handle_frame)
            self.source.add_error_callback(self._handle_source_error)
            return True
        except Exception as e:
            error_msg = f"Error setting screen source: {e}"
            print(error_msg)
            self._notify_error(error_msg)
            self.source = None
            return False
    
    def set_source(self, source_type: str, source_id: int, **kwargs) -> bool:
        """Set the capture source based on type and ID.
        
        Args:
            source_type: Type of source ('camera', 'screen', 'window')
            source_id: ID of the source
            **kwargs: Additional arguments (e.g., region for screen capture)
            
        Returns:
            True if source was set successfully, False otherwise
        """
        if source_type == "camera":
            return self.set_camera_source(source_id)
        elif source_type == "screen":
            region = kwargs.get('region')
            return self.set_screen_source(source_id, region)
        elif source_type == "window":
            return self.set_window_source(source_id)
        else:
            print(f"Unknown source type: {source_type}")
            return False
    
    def set_window_source(self, window_handle: int) -> bool:
        """Set a window as the capture source.
        
        Args:
            window_handle: Handle of the window to capture
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Clean up existing source
            self._cleanup_source()
            
            # Create and connect to new source
            self.source = WindowSource(
                window_handle=window_handle,
                frame_rate=self.frame_rate,
                max_resolution=self.max_resolution
            )
            
            if not self.source.connect():
                self.source = None
                return False
            
            self.source_type = "window"
            self.source.add_frame_callback(self._handle_frame)
            self.source.add_error_callback(self._handle_source_error)
            return True
        except Exception as e:
            error_msg = f"Error setting window source: {e}"
            print(error_msg)
            self._notify_error(error_msg)
            self.source = None
            return False

    def start_capture(self, take_id: int, frame_count_limit: Optional[int] = None, 
                     scene_settings: Optional[Dict[str, Any]] = None) -> bool:
        """Start capturing frames and saving them to the specified take.
        
        Args:
            take_id: ID of the take to save frames to
            frame_count_limit: Optional limit on number of frames to capture
            scene_settings: Optional scene settings including resolution and frame_rate
        """
        with self._state_lock:
            if not self.source:
                print("No capture source set")
                return False
                
            if self._capturing:
                print("Already capturing")
                return False
            
            # Apply scene settings if provided
            if scene_settings:
                self.frame_rate = scene_settings.get('frame_rate', 1.0)
                self.scene_resolution = scene_settings.get('resolution', '1080p')
                print(f"Using scene settings: FPS={self.frame_rate}, Resolution={self.scene_resolution}")
            
            self._active_take_id = take_id
            self._frame_count = 0
            self._capturing = True
            self._stop_requested = False
            self._capture_start_time = time.time()
            self.frame_count_limit = frame_count_limit  # Store the limit
            self._last_status_update = 0
                
            # Update session frame count
            try:
                from CAMF.services.session_management import get_session_manager
                session_manager = get_session_manager()
                session_manager.update_frame_count(0)
            except:
                pass
                
            print(f"Starting capture for take {take_id} with limit: {frame_count_limit}")
                
        # Ensure frame callback is registered
        if self._handle_frame not in self.source._frame_callbacks:
            self.source.add_frame_callback(self._handle_frame)
            print(f"Added frame callback, total callbacks: {len(self.source._frame_callbacks)}")
                
        # Start capture outside of lock
        success = self.source.start_capture()
        
        if not success:
            print("Source failed to start capture")
            with self._state_lock:
                self._capturing = False
                self._active_take_id = None
            return False
        
        # Start status update thread
        self._status_update_thread = threading.Thread(
            target=self._status_update_loop,
            daemon=True,
            name="CaptureStatusUpdate"
        )
        self._status_update_thread.start()
            
        return True

    def stop_capture(self) -> bool:
        """Stop capturing frames with immediate effect."""
        print(f"Stop capture called. Current state: capturing={self.capturing}")
        
        # Atomically update state
        with self._state_lock:
            if not self._capturing:
                print("Not currently capturing")
                return False
            
            # Immediately set flags to stop frame processing
            self._stop_requested = True
            self._capturing = False
            
            # Store values before clearing
            take_id = self._active_take_id
            frame_count = self._frame_count
            self._active_take_id = None
            
            # Clear monitoring mode
            if self.is_monitoring_mode:
                print(f"[CaptureService] Clearing monitoring mode")
                self.is_monitoring_mode = False
                self.reference_take_id = None
        
        try:
            # Stop status update thread
            if self._status_update_thread and self._status_update_thread.is_alive():
                # Thread will exit on next iteration due to self._capturing = False
                self._status_update_thread.join(timeout=1.0)
            
            # Stop the source capture
            if self.source:
                # Clear callbacks first to stop new frames immediately
                if hasattr(self.source, '_frame_callbacks'):
                    self.source._frame_callbacks = [
                        cb for cb in self.source._frame_callbacks 
                        if cb != self._handle_frame
                    ]
                
                # Stop the source capture thread
                self.source.stop_capture()
            
            print(f"Capture stopped successfully for take {take_id}, captured {frame_count} frames")
            return True
            
        except Exception as e:
            print(f"Error during stop capture: {e}")
            return True  # Still return True since we updated the state
        finally:
            with self._state_lock:
                self._stop_requested = False

    def _status_update_loop(self):
        """Send periodic status updates instead of per-frame events."""
        print("Status update loop started")
        last_frame_count = -1
        
        while True:
            # Get state atomically
            state = self.get_capture_state()
            
            if not state['capturing'] or state['stop_requested']:
                break
                
            try:
                current_time = time.time()
                
                # Send update more frequently - every frame change or every 100ms
                if (state['frame_count'] != last_frame_count or 
                    current_time - self._last_status_update >= 0.1):
                    
                    status_data = {
                        'type': 'capture_status',
                        'data': {
                            'take_id': state['active_take_id'],
                            'frame_count': state['frame_count'],
                            'frame_index': state['frame_count'] - 1 if state['frame_count'] > 0 else 0,
                            'is_capturing': state['capturing'],
                            'frame_count_limit': getattr(self, 'frame_count_limit', None),
                            'timestamp': current_time
                        }
                    }
                    
                    # Only log significant changes
                    if state['frame_count'] != last_frame_count:
                        print(f"Status update: take_id={state['active_take_id']}, frames={state['frame_count']}")
                    
                    # Send via WebSocket callbacks (only for major events)
                    if state['frame_count'] != last_frame_count:
                        for callback in self.sse_callbacks:
                            try:
                                callback(status_data)
                            except Exception as e:
                                print(f"Error in WebSocket callback: {e}")
                    
                    last_frame_count = state['frame_count']
                    self._last_status_update = current_time
                
                time.sleep(0.25)  # Check every 250ms
                
            except Exception as e:
                print(f"Error in status update loop: {e}")
                time.sleep(0.5)
        
        print("Status update loop ended")
    
    def add_preview_callback(self, callback: Callable[[np.ndarray], None]):
        """Add a callback to receive preview frames.
        
        Args:
            callback: Function to call with the frame
        """
        self.preview_callbacks.append(callback)
    
    def add_error_callback(self, callback: Callable[[str], None]):
        """Add a callback to receive error notifications.
        
        Args:
            callback: Function to call with the error message
        """
        self.error_callbacks.append(callback)
    
    def get_available_cameras(self) -> List[Dict[str, Any]]:
        """Get a list of available cameras.
        
        Returns:
            List of dictionaries with camera information
        """
        # If we're capturing, return cached cameras to avoid disrupting capture
        if self._capturing:
            # Return cached list if available and recent (within 30 seconds)
            if self._cached_cameras and (time.time() - self._camera_cache_time < 30):
                return self._cached_cameras
            # Return empty list during capture to prevent enumeration
            return []
        
        # Clear cache to ensure fresh detection when not capturing
        CameraSource.clear_camera_cache()
        cameras = CameraSource.list_cameras()
        
        # Update cache
        self._cached_cameras = cameras
        self._camera_cache_time = time.time()
        
        return cameras
    
    def get_available_monitors(self) -> List[Dict[str, Any]]:
        """Get a list of available monitors.
        
        Returns:
            List of dictionaries with monitor information
        """
        return ScreenSource.list_monitors()
    
    def get_available_screens(self) -> List[Dict[str, Any]]:
        """Get a list of available screens (alias for monitors).
        
        Returns:
            List of dictionaries with screen information
        """
        return ScreenSource.list_monitors()
    
    def get_available_windows(self) -> List[Dict[str, Any]]:
        """Get a list of available windows.
        
        Returns:
            List of dictionaries with window information
        """
        try:
            return WindowSource.list_windows()
        except Exception:
            return []
    
    def get_capture_status(self) -> Dict[str, Any]:
        """Get current capture status.
        
        Returns:
            Dictionary with capture status information
        """
        with self._state_lock:
            return {
                "is_capturing": self._capturing,
                "active_take_id": self._active_take_id,
                "frame_count": self._frame_count,
                "source_type": self.source_type,
                "frame_rate": self.frame_rate
            }
    
    def get_current_source_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the current capture source.
        
        Returns:
            Dictionary with source information or None if no source is set
        """
        if not self.source:
            return None
        
        source_info = {
            "type": self.source_type,
            "id": None,
            "name": None
        }
        
        # Get source-specific info
        if self.source_type == "camera" and hasattr(self.source, 'camera_id'):
            source_info["id"] = self.source.camera_id
            source_info["name"] = f"Camera {self.source.camera_id}"
        elif self.source_type == "screen" and hasattr(self.source, 'monitor_id'):
            source_info["id"] = self.source.monitor_id
            source_info["name"] = f"Monitor {self.source.monitor_id}"
        elif self.source_type == "window" and hasattr(self.source, 'window_handle'):
            source_info["id"] = self.source.window_handle
            if hasattr(self.source, 'window_title'):
                source_info["name"] = self.source.window_title
            else:
                source_info["name"] = f"Window {self.source.window_handle}"
        
        return source_info
        
    def get_preview_frame_from_source(self, source_type: str, source_id: int) -> Optional[np.ndarray]:
        """Get a single preview frame from a specific source without setting it as active."""
        try:
            if source_type == "camera":
                # If we're capturing from this camera, use cached frame instead
                if (self.capturing and 
                    self.source_type == "camera" and 
                    hasattr(self.source, 'camera_id') and 
                    self.source.camera_id == source_id):
                    # Try to get cached frame from camera manager
                    from .camera_manager import get_camera_manager
                    manager = get_camera_manager()
                    frame = manager.get_cached_frame()
                    if frame is not None:
                        with self._preview_lock:
                            self._preview_frame = frame.copy()
                        return frame
                    # Fall back to stored preview frame
                    with self._preview_lock:
                        if self._preview_frame is not None:
                            return self._preview_frame.copy()
                    return None
                
                # Otherwise, use camera manager for single-shot capture
                from .camera_manager import get_camera_manager
                manager = get_camera_manager()
                frame = manager.capture_single_frame(source_id, owner="preview")
                if frame is not None:
                    # Store it as preview frame
                    with self._preview_lock:
                        self._preview_frame = frame.copy()
                return frame
                
            elif source_type == "screen" or source_type == "monitor":
                # Create temporary screen source
                from .screen import ScreenSource
                source = ScreenSource(monitor_id=source_id, frame_rate=self.frame_rate, max_resolution=self.max_resolution)
                if source.connect():
                    # Get the capture method directly
                    frame = source._capture_frame()
                    source.disconnect()
                    if frame is not None:
                        # Store it as preview frame
                        with self._preview_lock:
                            self._preview_frame = frame.copy()
                    return frame
                    
            elif source_type == "window":
                # Create temporary window source
                from .window import WindowSource
                source = WindowSource(window_handle=source_id, frame_rate=self.frame_rate, max_resolution=self.max_resolution)
                if source.connect():
                    # Get the capture method directly
                    frame = source._capture_frame()
                    source.disconnect()
                    if frame is not None:
                        # Store it as preview frame
                        with self._preview_lock:
                            self._preview_frame = frame.copy()
                    return frame
                    
        except Exception as e:
            print(f"Error getting preview frame from {source_type} {source_id}: {e}")
            import traceback
            traceback.print_exc()
            
        return None

    def get_current_preview_frame(self) -> Optional[np.ndarray]:
        """Get preview frame from current source or last captured frame."""
        # For camera sources, use the manager's preview method
        if self.source and self.source_type == "camera" and hasattr(self.source, 'camera_id'):
            from .camera_manager import get_camera_manager
            manager = get_camera_manager()
            frame = manager.get_preview_frame(self.source.camera_id)
            if frame is not None:
                with self._preview_lock:
                    self._preview_frame = frame.copy()
                return frame
        
        # If we have a stored preview frame, return it
        with self._preview_lock:
            if self._preview_frame is not None:
                return self._preview_frame.copy()
        
        # For other sources, try to get a frame
        if self.source and hasattr(self.source, '_capture_frame'):
            try:
                frame = self.source._capture_frame()
                if frame is not None:
                    with self._preview_lock:
                        self._preview_frame = frame.copy()
                    return frame
            except:
                pass
                
        return None
    
    def cleanup(self):
        """Clean up resources."""
        # Clean up source
        self._cleanup_source()

    def _cleanup_source(self):
        """Enhanced cleanup with preview clearing."""
        # Clear preview frame
        with self._preview_lock:
            self._preview_frame = None
        
        if self.source:
            # Always stop capture if active
            if self.capturing:
                try:
                    self.stop_capture()
                except Exception as e:
                    print(f"Error stopping capture during cleanup: {e}")
                    # Force state reset
                    with self._state_lock:
                        self._capturing = False
                        self._active_take_id = None
            
            try:
                self.source.disconnect()
            except Exception as e:
                print(f"Error disconnecting source: {e}")
            
            self.source = None
            self.source_type = None
        
        # Clean up video processor if needed
        if self.source_type == "video":
            self.video_processor.cleanup()
            self.source_type = None
    
    def _handle_frame(self, frame: np.ndarray, relative_time: float):
        """Handle captured frame - only save to storage, no processing."""
        print(f"[CaptureService] _handle_frame called with frame shape: {frame.shape}, time: {relative_time:.2f}")
        
        # CRITICAL: Atomic frame limit check and increment
        # This prevents ANY race condition with frame limits
        with self._state_lock:
            # Check all stop conditions first
            if self._stop_requested or not self._capturing:
                print(f"Frame handler: Stop requested or not capturing, ignoring frame")
                return
                
            if self._active_take_id is None:
                print("Frame handler: No active take ID, ignoring frame")
                return
            
            # Always allow capture - no auto-stop based on frame limit
            # Just increment the frame counter
            current_frame_index = self._frame_count
            self._frame_count += 1
            frame_count_after = self._frame_count
            
            # Copy values we need outside the lock
            active_take_id = self._active_take_id
        
        try:
            # Apply resolution downscaling if needed
            original_shape = frame.shape
            if should_downscale((frame.shape[1], frame.shape[0]), self.scene_resolution):
                print(f"Downscaling from {frame.shape[1]}x{frame.shape[0]} to {self.scene_resolution}")
                frame = downscale_frame(frame, self.scene_resolution)
                print(f"Downscaled to {frame.shape[1]}x{frame.shape[0]}")
            
            # Store frame for preview
            with self._preview_lock:
                self._preview_frame = frame.copy()
            
            # Encode frame preview for SSE (resize for performance)
            preview_frame = frame
            if CV2_AVAILABLE and (frame.shape[0] > 240 or frame.shape[1] > 320):
                # Resize for preview
                scale = min(240/frame.shape[0], 320/frame.shape[1])
                new_h = int(frame.shape[0] * scale)
                new_w = int(frame.shape[1] * scale)
                preview_frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
            
            # Encode preview as base64
            if CV2_AVAILABLE:
                _, buffer = cv2.imencode('.jpg', preview_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                preview_b64 = base64.b64encode(buffer).decode('utf-8')
            else:
                preview_b64 = ""  # No preview without cv2
            
            # Save frame to storage using the reserved index
            print(f"Saving frame {current_frame_index} to take {active_take_id}")
            stored_frame = self.storage.add_frame(
                take_id=active_take_id,
                frame=frame,
                frame_id=current_frame_index,
                timestamp=relative_time,
                metadata={
                    'original_resolution': f"{original_shape[1]}x{original_shape[0]}",
                    'capture_resolution': f"{frame.shape[1]}x{frame.shape[0]}",
                    'scene_resolution': self.scene_resolution
                }
            )
            
            if stored_frame:
                print(f"Frame {current_frame_index} saved successfully, total frames: {frame_count_after}")
                
                # Update session if available
                try:
                    from CAMF.services.session_management import get_session_manager
                    session_manager = get_session_manager()
                    session_manager.update_frame_count(frame_count_after)
                except:
                    pass
                
                # Send frame update via SSE callbacks with preview
                for callback in self.sse_callbacks:
                    try:
                        callback({
                            'type': 'frame_captured',
                            'data': {
                                'frameIndex': current_frame_index,
                                'frame_count': frame_count_after,
                                'take_id': active_take_id,
                                'timestamp': relative_time,
                                'preview': f'data:image/jpeg;base64,{preview_b64}'
                            }
                        })
                    except Exception as e:
                        print(f"Error in SSE callback: {e}")
                
                # If in monitoring mode, queue frame pair for detector processing
                # Only process frames up to reference take's frame count
                print(f"[CaptureService] Checking monitoring mode: is_monitoring_mode={self.is_monitoring_mode}, reference_take_id={self.reference_take_id}")
                if self.is_monitoring_mode and self.reference_take_id:
                    print(f"[CaptureService] In monitoring mode, processing frame {current_frame_index}")
                    # Get reference take frame count
                    if hasattr(self, '_reference_frame_count') and self._reference_frame_count is not None:
                        if current_frame_index < self._reference_frame_count:
                            print(f"[CaptureService] Frame {current_frame_index} within reference limit ({self._reference_frame_count}), queuing for processing")
                            self._queue_frame_for_processing(active_take_id, current_frame_index)
                        else:
                            print(f"[CaptureService] Frame {current_frame_index} beyond reference limit ({self._reference_frame_count}), skipping processing")
                    else:
                        # No reference frame count cached, queue anyway
                        print(f"[CaptureService] No reference frame count cached, queuing frame {current_frame_index} anyway")
                        self._queue_frame_for_processing(active_take_id, current_frame_index)
                else:
                    print(f"[CaptureService] Not in monitoring mode or no reference take, skipping detector processing")
            else:
                print(f"Failed to store frame {current_frame_index}")
                # Decrement counter since we didn't actually store the frame
                with self._state_lock:
                    self._frame_count -= 1
        
        except Exception as e:
            print(f"Error handling frame {self.frame_count}: {e}")
            import traceback
            traceback.print_exc()

    # Removed _delayed_stop_capture - no longer needed since we don't auto-stop
    
    def _queue_frame_for_processing(self, current_take_id: int, frame_id: int):
        """Queue a frame pair for detector processing.
        
        Args:
            current_take_id: ID of the current take being captured
            frame_id: ID of the frame to process
        """
        print(f"[CaptureService] _queue_frame_for_processing called - current_take_id: {current_take_id}, frame_id: {frame_id}, reference_take_id: {self.reference_take_id}")
        try:
            from CAMF.services.detector_framework import get_detector_framework_service
            detector_framework = get_detector_framework_service()
            
            # Queue the frame pair for processing
            result = detector_framework.process_frame_pair(
                reference_take_id=self.reference_take_id,
                current_take_id=current_take_id,
                frame_id=frame_id
            )
            
            print(f"[CaptureService] Queued frame {frame_id} for detector processing, result: {result}")
            
        except Exception as e:
            print(f"[CaptureService] Error queuing frame for processing: {e}")
            import traceback
            traceback.print_exc()

    def _send_websocket_frame_captured(self, frame_id: int, timestamp: float):
        """DEPRECATED - No longer send individual frame events, use status updates instead."""

    def _notify_error(self, error_message: str):
        """Notify error callbacks of an error.
        
        Args:
            error_message: The error message
        """
        for callback in self.error_callbacks:
            try:
                callback(error_message)
            except Exception as e:
                print(f"Error in error callback: {e}")
    
    def _handle_source_error(self, error_message: str):
        """Handle errors from the capture source.
        
        Args:
            error_message: Error message from the source
        """
        print(f"[CaptureService] Source error: {error_message}")
        
        # Check if it's a critical error (disconnection, repeated failures)
        is_critical = any(keyword in error_message.lower() for keyword in [
            "disconnect", "failed after", "too many", "not opened", "camera disconnected"
        ])
        
        if is_critical and self.capturing:
            print("[CaptureService] CRITICAL: Source disconnected during capture")
            
            # Store the error state
            with self._state_lock:
                self._source_error = error_message
            
            # Stop capture immediately to prevent further errors
            self.stop_capture()
            
            # Send disconnection event via WebSocket
            for callback in self.sse_callbacks:
                try:
                    callback({
                        'type': 'source_disconnected',
                        'data': {
                            'source_type': self.source_type,
                            'message': error_message,
                            'take_id': self._active_take_id,
                            'frame_count': self._frame_count
                        }
                    })
                except Exception as e:
                    print(f"Error in disconnection callback: {e}")
            
            # Stop capture
            self.stop_capture()
        
        # Always notify error callbacks
        self._notify_error(error_message)
    
    def load_video_file(self, video_path: str) -> Dict[str, Any]:
        """Load a video file for processing.
        
        Args:
            video_path: Path to the video file
            
        Returns:
            Dictionary with success status and metadata
        """
        # Clean up any existing source
        self._cleanup_source()
        
        # Load video
        result = self.video_processor.load_video(video_path)
        
        if result['success']:
            self.source_type = "video"
            # Add frame callback
            self.video_processor.add_frame_callback(self._handle_frame)
        
        return result
    
    def set_video_source(self, video_path: str) -> bool:
        """Set a video file as the capture source.
        
        Args:
            video_path: Path to the video file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            result = self.load_video_file(video_path)
            return result['success']
        except Exception as e:
            error_msg = f"Error setting video source: {e}"
            print(error_msg)
            self._notify_error(error_msg)
            return False
    
    def start_video_capture(self, take_id: int, target_fps: Optional[float] = None) -> bool:
        """Start capturing from video file.
        
        Args:
            take_id: ID of the take to save frames to
            target_fps: Target frame rate for processing (None = use video's FPS)
            
        Returns:
            True if capture started successfully
        """
        with self._state_lock:
            if self.source_type != "video" or self._capturing:
                return False
            
            self._active_take_id = take_id
            self._frame_count = 0
            self._capturing = True
            self._stop_requested = False
        
        # Start status update thread for video capture too
        self._last_status_update = 0
        self._status_update_thread = threading.Thread(
            target=self._status_update_loop,
            daemon=True,
            name="VideoStatusUpdate"
        )
        self._status_update_thread.start()
        
        return self.video_processor.start_processing(target_fps)
    
    def seek_video(self, frame_index: int) -> bool:
        """Seek to a specific frame in the video.
        
        Args:
            frame_index: Frame index to seek to
            
        Returns:
            True if successful
        """
        if self.source_type != "video":
            return False
        
        return self.video_processor.seek_to_frame(frame_index)
    
    def get_video_progress(self) -> Dict[str, Any]:
        """Get video processing progress."""
        if self.source_type != "video":
            return {'error': 'Not using video source'}
        
        return self.video_processor.get_progress()
    
    def get_video_upload_status(self, take_id: int) -> Optional[Dict[str, Any]]:
        """Get the status of a video upload for a take.
        
        Args:
            take_id: ID of the take to check
            
        Returns:
            Status dictionary or None if no upload in progress
        """
        return self.video_processor.get_upload_status(take_id)
    
    def process_video_upload(self, take_id: int, video_path: str) -> int:
        """Process an uploaded video file and extract frames.
        
        Args:
            take_id: ID of the take to save frames to
            video_path: Path to the uploaded video file
            
        Returns:
            Number of frames extracted
        """
        return self.video_processor.process_upload(take_id, video_path, self.storage)
    
    def add_sse_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Add a callback for SSE updates.
        
        Args:
            callback: Function to call with updates
        """
        self.sse_callbacks.append(callback)
    
    # Compatibility alias for backward compatibility
    def add_websocket_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Compatibility alias for add_sse_callback."""
        self.add_sse_callback(callback)
    
    def remove_sse_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Remove an SSE callback."""
        if callback in self.sse_callbacks:
            self.sse_callbacks.remove(callback)
    
    # Compatibility alias for backward compatibility  
    def remove_websocket_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Compatibility alias for remove_sse_callback."""
        self.remove_sse_callback(callback)
    
    def _send_sse_preview(self, frame: np.ndarray):
        """Send preview frame via SSE."""
        try:
            if not CV2_AVAILABLE:
                return  # Can't send preview without cv2
                
            # Resize frame for preview (to reduce bandwidth)
            preview_height = 360  # 360p for preview
            height, width = frame.shape[:2]
            scale = preview_height / height
            preview_width = int(width * scale)
            
            preview_frame = cv2.resize(frame, (preview_width, preview_height))
            
            # Convert to JPEG
            _, buffer = cv2.imencode('.jpg', preview_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            frame_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # Send via WebSocket callbacks
            for callback in self.sse_callbacks:
                try:
                    callback({
                        'type': 'preview_frame',
                        'data': {
                            'frame': f"data:image/jpeg;base64,{frame_base64}",
                            'timestamp': time.time()
                        }
                    })
                except Exception as e:
                    print(f"Error in WebSocket callback: {e}")
                    
        except Exception as e:
            print(f"Error sending WebSocket preview: {e}")


# Singleton instance
_capture_service = None
_service_lock = threading.Lock()

def get_capture_service():
    """Get the capture service singleton with thread safety."""
    global _capture_service
    if _capture_service is None:
        with _service_lock:
            if _capture_service is None:
                _capture_service = CaptureService()
    return _capture_service
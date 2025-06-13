import numpy as np
from typing import List, Dict, Any, Optional, Tuple
import time
import logging
import threading

from .source import CaptureSource
from .camera_manager import get_camera_manager

logger = logging.getLogger(__name__)

class CameraSource(CaptureSource):
    """Camera source using the camera manager for conflict-free access."""
    
    # Class-level cache for camera list
    _camera_list_cache = None
    _cache_timestamp = 0
    _cache_lock = threading.Lock()
    
    # Cache duration from config
    @classmethod
    def _get_cache_duration(cls):
        from CAMF.common.config import get_config
        return get_config().frame.cache_duration_seconds
    
    def __init__(self, camera_id: int = 0, frame_rate: float = 24, max_resolution: Optional[Tuple[int, int]] = None):
        self._last_frame_hash = None
        self._duplicate_count = 0
        super().__init__(frame_rate=frame_rate, max_resolution=max_resolution)
        self.camera_id = camera_id
        self.name = f"Camera {camera_id}"
        self._manager = get_camera_manager()
        self._connected = False
        self._capture_owner = f"camera_source_{camera_id}_{id(self)}"  # Unique owner ID
        
    def _notify_error(self, error_msg: str):
        """Notify all error callbacks about an error."""
        for callback in self._error_callbacks:
            try:
                callback(error_msg)
            except Exception as e:
                logger.error(f"Error in error callback: {e}")
        
    def connect(self) -> bool:
        """Connect to the camera."""
        try:
            # For camera sources, we don't hold a connection during idle
            # We'll acquire it when we start capture
            self._connected = True
            logger.info(f"Camera source {self.camera_id} ready")
            return True
        except Exception as e:
            logger.error(f"Error connecting camera source: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the camera."""
        try:
            self.stop_capture()
            self._connected = False
            # Make sure camera is released
            self._manager.release_camera(self._capture_owner)
        except Exception as e:
            logger.error(f"Error disconnecting camera: {e}")
    
    def start_capture(self) -> bool:
        """Start capturing frames at the specified frame rate."""
        if not self._connected:
            logger.error("Camera source not connected")
            return False
        
        logger.info(f"Starting capture for camera {self.camera_id}")
        
        try:
            # Acquire camera before starting the capture thread
            if not self._manager.acquire_camera(self.camera_id, owner=self._capture_owner):
                logger.error(f"Failed to acquire camera {self.camera_id}")
                # FAILPROOF: Try to force release and re-acquire
                logger.info("Attempting force release and re-acquire")
                self._manager.force_release_all()
                time.sleep(0.5)
                if not self._manager.acquire_camera(self.camera_id, owner=self._capture_owner):
                    return False
            
            logger.info(f"Camera {self.camera_id} acquired successfully")
            
            # Reset failure counter
            self._consecutive_failures = 0
            
            # Start the capture loop
            result = super().start_capture()
            
            if not result:
                # Release camera if start failed
                self._manager.release_camera(self._capture_owner)
                
            return result
            
        except Exception as e:
            logger.error(f"Failed to start capture: {e}")
            # Make sure to release camera on failure
            self._manager.release_camera(self._capture_owner)
            return False
    
    def stop_capture(self):
        """Stop capturing frames."""
        try:
            super().stop_capture()
        finally:
            # Always release camera when stopping capture
            try:
                self._manager.release_camera(self._capture_owner)
            except Exception as e:
                logger.error(f"Error releasing camera during stop: {e}")
    
    
    def _capture_frame(self) -> Optional[np.ndarray]:
        """Capture a single frame during continuous capture."""
        try:
            frame = self._manager.get_frame_continuous()
            if frame is None:
                # Track consecutive failures
                if not hasattr(self, '_consecutive_failures'):
                    self._consecutive_failures = 0
                self._consecutive_failures += 1
                
                # Log every 10 failures to reduce spam
                if self._consecutive_failures % 10 == 1:
                    logger.warning(f"Camera capture failing (failure #{self._consecutive_failures})")
                
                # Only notify error after many failures
                if self._consecutive_failures > 20:
                    logger.error("Camera appears to be disconnected")
                    self._notify_error("Camera disconnected")
                    # Try one more force reconnect
                    try:
                        self._manager.force_release_all()
                        time.sleep(0.5)
                        if self._manager.acquire_camera(self.camera_id, owner=self._capture_owner):
                            logger.info("Emergency reconnect successful")
                            self._consecutive_failures = 0
                    except:
                        pass
                
                return None
            else:
                # Success - reset failure counter
                if hasattr(self, '_consecutive_failures') and self._consecutive_failures > 0:
                    logger.info(f"Camera recovered after {self._consecutive_failures} failures")
                self._consecutive_failures = 0
                return frame
                
        except Exception as e:
            logger.error(f"Error capturing frame: {e}")
            # Try to recover silently
            return None
    
    def get_preview_frame(self) -> Optional[np.ndarray]:
        """Get a single frame for preview (doesn't start continuous capture)."""
        if not self._connected:
            return None
        
        try:
            # Use single-shot capture for preview with unique owner tracking
            preview_owner = f"preview_{self.camera_id}_{time.time()}"
            return self._manager.capture_single_frame(self.camera_id, owner=preview_owner)
        except Exception as e:
            logger.error(f"Error getting preview frame: {e}")
            return None
    
    @staticmethod
    def list_cameras() -> List[Dict[str, Any]]:
        """List available cameras with caching to reduce repeated access."""
        with CameraSource._cache_lock:
            # Check if cache is still valid
            current_time = time.time()
            if (CameraSource._camera_list_cache is not None and 
                current_time - CameraSource._cache_timestamp < CameraSource._get_cache_duration()):
                logger.debug("Returning cached camera list")
                return CameraSource._camera_list_cache
            
            logger.info("Enumerating cameras...")
            cameras = []
            manager = get_camera_manager()
            
            # Check first N cameras
            max_cameras_to_check = 5
            for i in range(max_cameras_to_check):
                try:
                    # Use quick check first
                    resolution = manager.quick_camera_check(i)
                    if resolution:
                        width, height = resolution
                        cameras.append({
                            "id": i,
                            "name": f"Camera {i}",
                            "resolution": (width, height)
                        })
                        logger.info(f"Found camera {i}: {width}x{height}")
                    else:
                        # No more cameras found
                        break
                        
                except Exception as e:
                    logger.debug(f"Error checking camera {i}: {e}")
                    break
            
            # Update cache
            CameraSource._camera_list_cache = cameras
            CameraSource._cache_timestamp = current_time
            
            logger.info(f"Camera enumeration complete. Found {len(cameras)} camera(s)")
            return cameras
    
    @staticmethod
    def clear_camera_cache():
        """Clear the camera list cache."""
        with CameraSource._cache_lock:
            CameraSource._camera_list_cache = None
            CameraSource._cache_timestamp = 0
            logger.debug("Camera cache cleared")
    
    def __del__(self):
        """Cleanup when object is destroyed."""
        try:
            if hasattr(self, '_connected') and self._connected:
                self.disconnect()
        except:
            pass
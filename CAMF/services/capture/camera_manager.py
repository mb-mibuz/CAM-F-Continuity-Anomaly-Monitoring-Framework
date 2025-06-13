"""
Simplified camera manager with minimal locking for single-source capture.
Since we only capture from one source at a time, complex locking is unnecessary.
"""

import time
import cv2
import numpy as np
from typing import Optional, Dict, Any, Tuple
import logging
import atexit

logger = logging.getLogger(__name__)

class CameraManager:
    """Simplified camera manager for single-source capture."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        
        # Simple state tracking - no complex locking needed
        self._current_camera_id = None
        self._capture = None
        self._is_capturing = False  # Simple flag instead of complex locks
        self._owner = None
        
        # Frame reading state
        self._last_read_time = 0
        self._last_frame = None
        
        # Register cleanup on exit
        atexit.register(self._cleanup_on_exit)
        
    def _cleanup_on_exit(self):
        """Ensure camera is released on program exit."""
        try:
            if self._capture:
                self._capture.release()
                self._capture = None
        except:
            pass
    
    def quick_camera_check(self, camera_id: int) -> Optional[Tuple[int, int]]:
        """Quick check if camera exists without full initialization.
        Returns (width, height) if camera exists, None otherwise.
        """
        cap = None
        try:
            # Use DirectShow on Windows for faster enumeration
            import os
            if os.name == 'nt':
                cap = cv2.VideoCapture(camera_id, cv2.CAP_DSHOW)
            else:
                cap = cv2.VideoCapture(camera_id)
            
            if cap.isOpened():
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                
                if width > 0 and height > 0:
                    return (width, height)
            
            return None
            
        except Exception as e:
            logger.debug(f"Quick check failed for camera {camera_id}: {e}")
            return None
            
        finally:
            # Always release the camera
            if cap is not None:
                try:
                    cap.release()
                except:
                    pass
    
    def acquire_camera(self, camera_id: int, timeout: float = 2.0, owner: str = "unknown") -> bool:
        """Acquire access to a camera.
        
        Simplified: Since we only capture from one source at a time,
        we just need to check if camera is already in use.
        """
        logger.info(f"[{owner}] Camera acquisition requested for camera {camera_id}")
        
        # Simple check - are we already capturing?
        if self._is_capturing and self._owner != owner:
            logger.error(f"[{owner}] Camera already in use by {self._owner}")
            return False
        
        # If same owner re-acquires, that's fine
        if self._is_capturing and self._owner == owner and self._current_camera_id == camera_id:
            logger.info(f"[{owner}] Re-acquiring same camera {camera_id}")
            return True
        
        # Release any different camera
        if self._current_camera_id != camera_id and self._capture:
            logger.info(f"[{owner}] Releasing different camera {self._current_camera_id}")
            try:
                self._capture.release()
            except:
                pass
            self._capture = None
            self._current_camera_id = None
        
        # If we already have this camera open, just update owner
        if self._current_camera_id == camera_id and self._capture and self._capture.isOpened():
            logger.info(f"[{owner}] Camera {camera_id} already open, updating owner")
            self._owner = owner
            self._is_capturing = True
            return True
        
        # Open the camera
        logger.info(f"[{owner}] Opening camera {camera_id}")
        
        try:
            # Try DirectShow first on Windows
            if cv2.os.name == 'nt':
                self._capture = cv2.VideoCapture(camera_id, cv2.CAP_DSHOW)
            else:
                self._capture = cv2.VideoCapture(camera_id)
            
            if not self._capture.isOpened():
                logger.error(f"[{owner}] Failed to open camera {camera_id}")
                self._capture = None
                return False
            
            # Configure for low latency
            try:
                self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                logger.debug(f"[{owner}] Set camera buffer size to 1")
            except:
                logger.debug(f"[{owner}] Could not set buffer size (not supported by camera)")
            
            # SIMPLIFIED: Just test that camera works with one read
            logger.debug(f"[{owner}] Testing camera {camera_id}")
            
            ret, frame = self._capture.read()
            if not ret or frame is None:
                logger.error(f"[{owner}] Failed to read test frame from camera {camera_id}")
                self._capture.release()
                self._capture = None
                return False
            
            # Success - update state
            self._current_camera_id = camera_id
            self._owner = owner
            self._is_capturing = True
            self._last_read_time = time.time()
            
            logger.info(f"[{owner}] Successfully opened camera {camera_id}")
            return True
            
        except Exception as e:
            logger.error(f"[{owner}] Error acquiring camera: {e}")
            if self._capture:
                try:
                    self._capture.release()
                except:
                    pass
                self._capture = None
            return False
    
    def release_camera(self, owner: str = "unknown"):
        """Release camera access."""
        logger.info(f"[{owner}] Releasing camera")
        
        # Only the owner or a force release can release the camera
        if self._owner and self._owner != owner:
            logger.warning(f"[{owner}] Attempted to release camera held by {self._owner}")
            return
        
        self._is_capturing = False
        self._owner = None
        # Note: We keep the camera open for reliability
        # It will be closed when a different camera is requested or on exit
    
    def _reconnect_camera(self) -> bool:
        """Attempt to reconnect a disconnected camera - SIMPLIFIED."""
        try:
            if not hasattr(self, '_current_camera_id') or self._current_camera_id is None:
                return False
                
            camera_id = self._current_camera_id
            logger.info(f"Reconnecting camera {camera_id}")
            
            # Release current capture
            if self._capture:
                try:
                    self._capture.release()
                except:
                    pass
                self._capture = None
                time.sleep(0.2)  # Brief delay
            
            # Try multiple backends if first fails
            backends = [cv2.CAP_DSHOW, cv2.CAP_ANY] if cv2.os.name == 'nt' else [cv2.CAP_ANY]
            
            for backend in backends:
                try:
                    self._capture = cv2.VideoCapture(camera_id, backend)
                    if self._capture.isOpened():
                        # Just set buffer size
                        try:
                            self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        except:
                            pass
                        
                        # Quick test read
                        ret, frame = self._capture.read()
                        if ret and frame is not None:
                            logger.info(f"Camera {camera_id} reconnected successfully with backend {backend}")
                            self._consecutive_failures = 0
                            return True
                except:
                    pass
            
            logger.error(f"Failed to reconnect camera {camera_id}")
            return False
            
        except Exception as e:
            logger.error(f"Error reconnecting camera: {e}")
            return False
    
    def force_release_all(self):
        """Force release camera resources."""
        logger.warning("Force releasing all camera resources")
        
        self._is_capturing = False
        self._owner = None
        
        if self._capture:
            try:
                self._capture.release()
            except:
                pass
            self._capture = None
            self._current_camera_id = None
    
    def capture_single_frame(self, camera_id: int, owner: str = "preview") -> Optional[np.ndarray]:
        """Capture a single frame."""
        # For preview, we can share the camera if it's already open
        if self._current_camera_id == camera_id and self._capture and self._capture.isOpened():
            # Just read a frame without changing ownership
            try:
                # Grab a few frames to get fresh data
                for _ in range(2):
                    ret, frame = self._capture.read()
                    if ret and frame is not None:
                        self._last_frame = frame.copy()
                return self._last_frame
            except Exception as e:
                logger.error(f"Error reading preview frame: {e}")
                return None
        
        # Otherwise, acquire camera temporarily
        if not self.acquire_camera(camera_id, timeout=2.0, owner=owner):
            return None
        
        try:
            if self._capture and self._capture.isOpened():
                # Grab multiple frames to ensure fresh data
                for _ in range(2):
                    ret, frame = self._capture.read()
                    if ret and frame is not None:
                        self._last_frame = frame.copy()
                return self._last_frame
        except Exception as e:
            logger.error(f"Error capturing single frame: {e}")
        finally:
            # Release for single frame capture
            self.release_camera(owner)
        
        return None
    
    def get_frame_continuous(self) -> Optional[np.ndarray]:
        """Get a frame during continuous capture - SIMPLIFIED VERSION."""
        if not self._is_capturing:
            logger.error("Camera not acquired for continuous capture")
            return None
        
        if not self._capture or not self._capture.isOpened():
            logger.error("Camera not opened for continuous capture")
            # Try to reconnect immediately
            if self._current_camera_id is not None:
                logger.info("Attempting immediate reconnection")
                if self._reconnect_camera():
                    logger.info("Reconnection successful")
                else:
                    return None
            else:
                return None
        
        try:
            # SIMPLIFIED: Just read the latest frame, minimal buffer flushing
            # Grab 1-2 frames to get fresh data
            self._capture.grab()  # Discard one frame
            
            # Read the fresh frame
            ret, frame = self._capture.read()
            if ret and frame is not None:
                self._last_frame = frame.copy()
                self._consecutive_failures = 0
                return frame
            else:
                # Frame read failed
                logger.warning(f"Camera read failed")
                self._consecutive_failures = getattr(self, '_consecutive_failures', 0) + 1
                
                # Try reconnect after 3 failures
                if self._consecutive_failures >= 3:
                    logger.info(f"Attempting reconnect after {self._consecutive_failures} failures")
                    if self._reconnect_camera():
                        # Try one more read
                        ret, frame = self._capture.read()
                        if ret and frame is not None:
                            self._consecutive_failures = 0
                            return frame
                
                return None
                
        except Exception as e:
            logger.error(f"Error reading frame: {e}")
            # Try to recover
            try:
                if self._reconnect_camera():
                    ret, frame = self._capture.read()
                    if ret and frame is not None:
                        return frame
            except:
                pass
            return None
    
    def get_preview_frame(self, camera_id: int) -> Optional[np.ndarray]:
        """Get a preview frame only when not capturing.
        When capturing is active, preview should come from saved frames instead.
        """
        # If camera is in use for capture, don't allow preview access
        if self._is_capturing:
            logger.warning(f"[preview] Camera {camera_id} is in use for capture - preview should use saved frames")
            return None
        
        # Otherwise, capture single frame for preview
        return self.capture_single_frame(camera_id, owner="preview")
    
    def is_camera_available(self, camera_id: int) -> bool:
        """Check if a camera is available."""
        # If it's the current camera and it's open, it's available
        if self._current_camera_id == camera_id and self._capture and self._capture.isOpened():
            return True
        
        # Otherwise, do a quick check
        return self.quick_camera_check(camera_id) is not None
    
    def get_health(self) -> Dict[str, Any]:
        """Get camera manager health information."""
        return {
            'current_camera_id': self._current_camera_id,
            'is_capturing': self._is_capturing,
            'owner': self._owner,
            'has_capture': self._capture is not None,
            'capture_opened': self._capture.isOpened() if self._capture else False
        }

# Global instance getter
_camera_manager = None

def get_camera_manager() -> CameraManager:
    """Get the camera manager singleton."""
    global _camera_manager
    if _camera_manager is None:
        _camera_manager = CameraManager()
    return _camera_manager
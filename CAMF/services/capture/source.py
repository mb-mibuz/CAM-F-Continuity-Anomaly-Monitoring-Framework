# source.py
import time
import threading
from abc import ABC, abstractmethod
from typing import Optional, Callable
import logging

import numpy as np

logger = logging.getLogger(__name__)

class CaptureSource(ABC):
    """Base class for all capture sources."""
    
    def __init__(self, frame_rate=24, max_resolution=None):
        """Initialize the capture source.
        
        Args:
            frame_rate: Frames per second to capture (can be fractional)
            max_resolution: Maximum resolution as (width, height) or None for no limit
        """
        # Validate inputs
        if frame_rate <= 0 or frame_rate > 240:
            raise ValueError(f"frame_rate must be between 0 and 240, got {frame_rate}")
        if max_resolution is not None:
            if not isinstance(max_resolution, tuple) or len(max_resolution) != 2:
                raise ValueError("max_resolution must be a tuple of (width, height)")
                
        self.frame_rate = frame_rate
        self.max_resolution = max_resolution
        self._running = False
        self._frame_callbacks = []
        self._error_callbacks = []
        self._thread = None
        self._last_frame = None
        self._start_time = None
        self._frames_captured = 0
    
    def add_error_callback(self, callback):
        """Add a callback to be called when errors occur.
        
        Args:
            callback: Function to call with error message
        """
        self._error_callbacks.append(callback)
        
    @abstractmethod
    def connect(self) -> bool:
        """Connect to the source."""
    
    @abstractmethod
    def disconnect(self):
        """Disconnect from the source."""
    
    @abstractmethod
    def _capture_frame(self) -> Optional[np.ndarray]:
        """Capture a single frame from the source.
        
        Returns:
            Frame as numpy array or None if capture failed
        """
    
    def start_capture(self) -> bool:
        """Start capturing frames at the specified frame rate."""
        if self._running:
            return False
        
        self._running = True
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._capture_loop)
        self._thread.daemon = True
        self._thread.start()
        return True
    
    def stop_capture(self):
        """Stop capturing frames immediately."""
        self._running = False  # Set flag first
        
        if self._thread and self._thread != threading.current_thread():
            # Only join if we're not in the same thread (avoids "cannot join current thread" error)
            try:
                self._thread.join(timeout=1.0)  # Reduced from 2.0
                if self._thread.is_alive():
                    print(f"Warning: Capture thread for {self.__class__.__name__} did not stop quickly")
                    # Thread will eventually stop due to _running flag
            except RuntimeError as e:
                print(f"Error during stop capture: {e}")
            finally:
                self._thread = None
        else:
            self._thread = None
    
    def add_frame_callback(self, callback: Callable[[np.ndarray, float], None]):
        """Add a callback to be called for each new frame.
        
        Args:
            callback: Function to call with (frame, relative_time)
        """
        self._frame_callbacks.append(callback)
    
    def get_last_frame(self) -> Optional[np.ndarray]:
        """Get the most recently captured frame."""
        return self._last_frame
    
    def _downscale_if_needed(self, frame: np.ndarray) -> np.ndarray:
        """Downscale the frame if its resolution exceeds the maximum."""
        if self.max_resolution is None:
            return frame
        
        max_width, max_height = self.max_resolution
        height, width = frame.shape[:2]
        
        if width <= max_width and height <= max_height:
            return frame
        
        # Calculate new dimensions while maintaining aspect ratio
        ratio = min(max_width / width, max_height / height)
        new_width = int(width * ratio)
        new_height = int(height * ratio)
        
        import cv2
        return cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)
    
    def _capture_loop(self):
        """Capture loop that runs in a separate thread with accurate timing."""
        frame_interval = 1.0 / self.frame_rate if self.frame_rate > 0 else float('inf')
        consecutive_failures = 0
        max_consecutive_failures = 10
        frames_captured = 0
        
        logger.info(f"Starting capture loop for {self.__class__.__name__} at {self.frame_rate} FPS")
        logger.debug(f"Frame callbacks registered: {len(self._frame_callbacks)}")
        
        # Use absolute timing for accurate frame rate
        next_frame_time = time.time()
        
        while self._running:
            # Check at the beginning of each iteration
            if not self._running:
                break
                
            current_time = time.time()
            
            # Wait until it's time for the next frame
            if current_time >= next_frame_time:
                # Double-check before capturing
                if not self._running:
                    break
                    
                # Capture frame
                capture_start = time.time()
                frame = self._capture_frame()
                capture_duration = time.time() - capture_start
                
                if frame is not None and self._running:
                    consecutive_failures = 0  # Reset failure counter
                    frames_captured += 1
                    
                    # Downscale if needed
                    frame = self._downscale_if_needed(frame)
                    
                    # Store the frame
                    self._last_frame = frame
                    self._frames_captured = frames_captured
                    
                    # Calculate relative time from start
                    relative_time = current_time - self._start_time
                    
                    # Debug: log every 30th frame to reduce spam
                    if frames_captured % 30 == 1:
                        logger.debug(f"Frame {frames_captured} captured at {relative_time:.2f}s")
                    
                    # Call all callbacks
                    callback_start = time.time()
                    for idx, callback in enumerate(self._frame_callbacks):
                        try:
                            callback(frame.copy(), relative_time)
                            if frames_captured == 1:  # Log first frame callback
                                logger.debug(f"Callback {idx} executed successfully")
                        except Exception as e:
                            logger.error(f"Error in frame callback {idx}: {e}")
                    
                    time.time() - callback_start
                    
                    # Calculate next frame time based on fixed interval
                    # This ensures consistent frame rate regardless of processing time
                    next_frame_time += frame_interval
                    
                    # If we're running behind, catch up
                    if next_frame_time < current_time:
                        # Skip frames if we're more than 2 intervals behind
                        frames_behind = int((current_time - next_frame_time) / frame_interval)
                        if frames_behind > 2:
                            logger.warning(f"Running {frames_behind} frames behind, skipping to catch up")
                            next_frame_time = current_time + frame_interval
                else:
                    consecutive_failures += 1
                    
                    # Check if too many failures
                    if consecutive_failures >= max_consecutive_failures:
                        error_msg = f"Source failed after {consecutive_failures} consecutive capture failures"
                        logger.error(f"CRITICAL: {error_msg}")
                        
                        # Notify error callbacks
                        for callback in self._error_callbacks:
                            try:
                                callback(error_msg)
                            except Exception as e:
                                logger.error(f"Error in error callback: {e}")
                        
                        # FAILPROOF: Don't stop immediately, try to continue
                        # Reset counter to give it more chances
                        if hasattr(self, '_total_failure_resets'):
                            self._total_failure_resets += 1
                            if self._total_failure_resets > 3:
                                # OK, really stop now
                                break
                        else:
                            self._total_failure_resets = 1
                        
                        consecutive_failures = 0  # Reset to try again
                        time.sleep(1.0)  # Wait a second before retrying
                    
                    elif consecutive_failures % 10 == 1:
                        logger.warning(f"Frame capture failed ({consecutive_failures} consecutive failures)")
                            
                # Check if we should stop after processing
                if not self._running:
                    break
            
            # Sleep to avoid CPU thrashing
            sleep_time = min(0.001, frame_interval / 20)  # Check 20x per frame interval
            time.sleep(sleep_time)
        
        logger.info(f"Capture loop ended for {self.__class__.__name__} - captured {frames_captured} frames")
    
    def get_status(self) -> dict:
        """Get capture source status."""
        status = {
            "is_capturing": self._running,
            "frame_rate": self.frame_rate,
            "frames_captured": getattr(self, '_frames_captured', 0)
        }
        if self._start_time and self._running:
            duration = time.time() - self._start_time
            status["duration"] = duration
            status["actual_fps"] = status["frames_captured"] / duration if duration > 0 else 0
        return status
    
    def __enter__(self):
        """Context manager entry."""
        if not self.connect():
            raise RuntimeError(f"Failed to connect to {self.__class__.__name__}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop_capture()
        self.disconnect()
        return False
# screen.py
import numpy as np
from typing import List, Dict, Any, Optional

from .source import CaptureSource

try:
    import mss
    import mss.tools
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False

class ScreenSource(CaptureSource):
    """Screen-based capture source with fixed threading support."""
    
    def __init__(self, monitor_id=1, region=None, frame_rate=24, max_resolution=None):
        """Initialize a screen source.
        
        Args:
            monitor_id: ID of the monitor to capture (0 = all monitors combined)
            region: Region to capture as (left, top, width, height) or None for full monitor
            frame_rate: Frames per second to capture
            max_resolution: Maximum resolution as (width, height) or None
        """
        # Call parent WITHOUT name parameter
        super().__init__(frame_rate, max_resolution)
        self.monitor_id = monitor_id
        self.region = region
        self.monitor_info = None
        # Set name after initialization
        self.name = f"Monitor {monitor_id}"
        
        if not MSS_AVAILABLE:
            raise ImportError("mss library is required for screen capture. Install with: pip install mss")
        
    def connect(self) -> bool:
        """Connect to the screen source."""
        try:
            # Create a temporary MSS instance just for validation
            with mss.mss() as sct:
                monitors = sct.monitors
                
                # Ensure monitor ID is valid
                if self.monitor_id >= len(monitors):
                    print(f"Monitor ID {self.monitor_id} not found. Available: {len(monitors)-1}")
                    return False
                
                # Get monitor information
                self.monitor_info = monitors[self.monitor_id]
                
                # If region is specified, validate it
                if self.region:
                    left, top, width, height = self.region
                    
                    # Check if region is within monitor bounds
                    if (left < self.monitor_info["left"] or 
                        top < self.monitor_info["top"] or
                        left + width > self.monitor_info["left"] + self.monitor_info["width"] or
                        top + height > self.monitor_info["top"] + self.monitor_info["height"]):
                        print("Region is outside monitor bounds")
                        return False
            
            return True
        except Exception as e:
            print(f"Error connecting to screen: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the screen source."""
        self.stop_capture()
        self.monitor_info = None
    
    def _capture_frame(self) -> Optional[np.ndarray]:
        """Capture a single frame from the screen.
        
        Returns:
            Frame as numpy array or None if capture failed
        """
        if not self.monitor_info:
            print("No monitor info available")
            return None
        
        try:
            # Create MSS instance in the capture thread
            with mss.mss() as sct:
                # Refresh monitors list in case of changes
                monitors = sct.monitors
                
                # Validate monitor still exists
                if self.monitor_id >= len(monitors):
                    print(f"Monitor {self.monitor_id} no longer available")
                    return None
                
                # Update monitor info
                self.monitor_info = monitors[self.monitor_id]
                
                # Set capture region
                if self.region:
                    left, top, width, height = self.region
                    region = {
                        "left": left,
                        "top": top,
                        "width": width,
                        "height": height
                    }
                else:
                    region = self.monitor_info
                
                # Capture screenshot
                screenshot = sct.grab(region)
                
                # Convert to numpy array
                frame = np.array(screenshot)
                
                # Convert from BGRA to BGR (OpenCV format)
                import cv2
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                
                print(f"Captured frame from monitor {self.monitor_id}: {frame.shape}")
                
                return frame
        except Exception as e:
            print(f"Error capturing screen: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    @staticmethod
    def list_monitors() -> List[Dict[str, Any]]:
        """List available monitors on the system."""
        if not MSS_AVAILABLE:
            return []
        
        monitors = []
        with mss.mss() as sct:
            for i, monitor in enumerate(sct.monitors):
                # Skip the "all monitors" entry which is first
                if i == 0:
                    continue
                
                monitors.append({
                    "id": i,
                    "name": f"Monitor {i}",
                    "resolution": (monitor["width"], monitor["height"]),
                    "position": (monitor["left"], monitor["top"])
                })
        
        return monitors
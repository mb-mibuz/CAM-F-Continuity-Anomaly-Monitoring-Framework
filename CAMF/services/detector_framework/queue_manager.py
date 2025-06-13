"""
Queue-based detector manager for the new push-based architecture.
"""
import logging
import threading
from typing import Dict, Any, List, Optional
import importlib.util
import sys
from pathlib import Path

from CAMF.services.detector_framework.interface import QueueBasedDetector, FramePair
from CAMF.services.detector_framework.detector_wrapper import QueueBasedDetectorWrapper
from CAMF.common.models import DetectorInfo, DetectorStatus, DetectorResult

logger = logging.getLogger(__name__)


class QueueBasedDetectorManager:
    """Manager for queue-based detectors in the push architecture."""
    
    def __init__(self, detector_path: Path, detector_info: DetectorInfo):
        self.detector_path = detector_path
        self.info = detector_info
        self.detector: Optional[QueueBasedDetector] = None
        self.wrapper: Optional[QueueBasedDetectorWrapper] = None
        self.is_loaded = False
        self._lock = threading.RLock()
        
    def load_detector(self) -> bool:
        """Load the detector module and create instance."""
        try:
            # Load the detector module
            detector_py = self.detector_path / "detector.py"
            if not detector_py.exists():
                logger.error(f"Detector file not found: {detector_py}")
                return False
                
            # Import the detector module
            spec = importlib.util.spec_from_file_location(
                f"detector_{self.info.name}", 
                detector_py
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            
            # Find the detector class
            detector_class = None
            for item_name in dir(module):
                item = getattr(module, item_name)
                if (isinstance(item, type) and 
                    issubclass(item, QueueBasedDetector) and 
                    item != QueueBasedDetector):
                    detector_class = item
                    break
                    
            if not detector_class:
                logger.error(f"No QueueBasedDetector subclass found in {detector_py}")
                return False
                
            # Create detector instance
            self.detector = detector_class()
            self.wrapper = QueueBasedDetectorWrapper(self.detector, self.info)
            self.is_loaded = True
            
            logger.info(f"Successfully loaded detector: {self.info.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load detector {self.info.name}: {e}", exc_info=True)
            return False
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize the detector with configuration."""
        if not self.is_loaded:
            if not self.load_detector():
                return False
                
        if self.wrapper:
            return self.wrapper.initialize(config)
        return False
    
    def add_frame_pair(self, frame_pair: FramePair, take_frame_count: int = 0) -> bool:
        """Add a frame pair to the detector's queue."""
        if self.wrapper:
            return self.wrapper.add_frame_pair(frame_pair, take_frame_count)
        return False
    
    def get_results(self, timeout: float = 0.1) -> List[DetectorResult]:
        """Get results from the detector."""
        if self.wrapper:
            return self.wrapper.get_results(timeout)
        return []
    
    def get_all_results(self) -> List[DetectorResult]:
        """Get all available results."""
        if self.wrapper:
            return self.wrapper.get_all_results()
        return []
    
    def get_status(self) -> DetectorStatus:
        """Get detector status."""
        if self.wrapper:
            return self.wrapper.status
        return DetectorStatus(
            name=self.info.name,
            enabled=False,
            running=False,
            last_error="Detector not loaded"
        )
    
    def cleanup(self):
        """Clean up detector resources."""
        if self.wrapper:
            self.wrapper.cleanup()
        self.detector = None
        self.wrapper = None
        self.is_loaded = False
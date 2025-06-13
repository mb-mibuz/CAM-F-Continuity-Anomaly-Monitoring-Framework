"""
Wrapper to adapt detectors to the queue-based interface for the framework.
"""
import logging
import threading
import time
from typing import Dict, Any, List

from CAMF.services.detector_framework.interface import QueueBasedDetector, FramePair
from CAMF.common.models import DetectorResult, DetectorInfo, DetectorStatus, ErrorConfidence

logger = logging.getLogger(__name__)


class QueueBasedDetectorWrapper:
    """Wraps a QueueBasedDetector instance for use in the detector framework."""
    
    def __init__(self, detector: QueueBasedDetector, detector_info: DetectorInfo):
        self.detector = detector
        self.info = detector_info
        self.status = DetectorStatus(
            name=detector_info.name,
            enabled=False,
            running=False
        )
        self._lock = threading.RLock()
        
    def initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize the detector."""
        try:
            success = self.detector.initialize(config)
            if success:
                self.detector.start_processing()
                with self._lock:
                    self.status.enabled = True
                    self.status.last_error = None
                    self.status.last_error_time = None
            return success
        except Exception as e:
            logger.error(f"Failed to initialize detector {self.info.name}: {e}")
            with self._lock:
                self.status.last_error = str(e)
                self.status.last_error_time = time.time()
            return False
    
    def add_frame_pair(self, frame_pair: FramePair, take_frame_count: int = 0) -> bool:
        """Add a frame pair to the detector's queue."""
        if not self.status.enabled:
            return False
            
        with self._lock:
            self.status.running = True
            
        try:
            success = self.detector.add_frame_pair(frame_pair, take_frame_count)
            if success:
                with self._lock:
                    self.status.total_processed += 1
            return success
        except Exception as e:
            logger.error(f"Error adding frame pair to detector {self.info.name}: {e}")
            with self._lock:
                self.status.last_error = str(e)
                self.status.last_error_time = time.time()
            return False
        finally:
            with self._lock:
                self.status.running = False
    
    def get_results(self, timeout: float = 0.1) -> List[DetectorResult]:
        """Get results from the detector."""
        try:
            results = self.detector.get_results(timeout=timeout)
            if results:
                # Update error count
                error_results = [r for r in results if r.confidence in [ErrorConfidence.CONFIRMED_ERROR, ErrorConfidence.LIKELY_ERROR]]
                with self._lock:
                    self.status.total_errors_found += len(error_results)
                return results
            return []
        except Exception as e:
            logger.error(f"Error getting results from detector {self.info.name}: {e}")
            return []
    
    def get_all_results(self) -> List[DetectorResult]:
        """Get all available results from the detector."""
        all_results = []
        try:
            result_batches = self.detector.get_all_results()
            for batch in result_batches:
                if isinstance(batch, list):
                    all_results.extend(batch)
                else:
                    all_results.append(batch)
                    
            # Update error count
            error_results = [r for r in all_results if r.confidence in [ErrorConfidence.CONFIRMED_ERROR, ErrorConfidence.LIKELY_ERROR]]
            with self._lock:
                self.status.total_errors_found += len(error_results)
                
            return all_results
        except Exception as e:
            logger.error(f"Error getting all results from detector {self.info.name}: {e}")
            return []
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get detector statistics."""
        try:
            stats = self.detector.get_stats()
            # Update status with stats
            with self._lock:
                if 'average_processing_time' in stats:
                    self.status.average_processing_time = stats['average_processing_time']
            return stats
        except Exception as e:
            logger.error(f"Error getting statistics from detector {self.info.name}: {e}")
            return {}
    
    def cleanup(self):
        """Clean up detector resources."""
        try:
            self.detector.stop_processing()
            if hasattr(self.detector, 'cleanup'):
                self.detector.cleanup()
            with self._lock:
                self.status.enabled = False
                self.status.running = False
        except Exception as e:
            logger.error(f"Error cleaning up detector {self.info.name}: {e}")
            with self._lock:
                self.status.last_error = f"Cleanup failed: {str(e)}"
                self.status.last_error_time = time.time()
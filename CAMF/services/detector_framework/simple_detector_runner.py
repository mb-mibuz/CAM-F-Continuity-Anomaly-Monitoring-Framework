"""
Simple Detector Runner - Direct execution without Docker or complex process management
This is a minimal implementation for testing when Docker is not available.
"""

import sys
import os
import json
import time
import logging
import importlib.util
from pathlib import Path
from typing import Dict, Any, Optional, List

from CAMF.common.models import DetectorResult
from CAMF.services.storage import get_storage_service

logger = logging.getLogger(__name__)


class SimpleDetectorRunner:
    """Run detectors directly in the main process for testing."""
    
    def __init__(self, detector_name: str, detector_path: Path):
        self.detector_name = detector_name
        self.detector_path = detector_path
        self.detector_module = None
        self.detector_instance = None
        self.is_initialized = False
        self.storage = get_storage_service()
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        """Load and initialize the detector."""
        try:
            # Load detector module dynamically
            detector_file = self.detector_path / "detector.py"
            if not detector_file.exists():
                logger.error(f"Detector file not found: {detector_file}")
                return False
            
            # Add detector path to sys.path temporarily
            sys.path.insert(0, str(self.detector_path))
            
            try:
                # Load the module
                spec = importlib.util.spec_from_file_location("detector", detector_file)
                self.detector_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(self.detector_module)
                
                # Get the detector class (usually named after the detector)
                detector_class = None
                for name in dir(self.detector_module):
                    obj = getattr(self.detector_module, name)
                    if (isinstance(obj, type) and 
                        hasattr(obj, 'process_frame') and 
                        name != 'BaseDetector'):
                        detector_class = obj
                        break
                
                if not detector_class:
                    logger.error(f"No detector class found in {detector_file}")
                    return False
                
                # Create instance
                self.detector_instance = detector_class()
                
                # Initialize with config and frame provider
                if hasattr(self.detector_instance, 'initialize'):
                    # Create a simple frame provider
                    frame_provider = SimpleFrameProvider(self.storage)
                    success = self.detector_instance.initialize(config, frame_provider)
                    if not success:
                        logger.error(f"Detector initialization failed")
                        return False
                
                self.is_initialized = True
                logger.info(f"Successfully initialized detector: {self.detector_name}")
                return True
                
            finally:
                # Remove from sys.path
                sys.path.remove(str(self.detector_path))
                
        except Exception as e:
            logger.error(f"Failed to initialize detector {self.detector_name}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def process_frame(self, frame_id: int, take_id: int) -> List[DetectorResult]:
        """Process a frame directly."""
        if not self.is_initialized or not self.detector_instance:
            return []
        
        try:
            # Call the detector's process_frame method
            results = self.detector_instance.process_frame(frame_id, take_id)
            
            if results:
                # Ensure results have detector name
                for result in results:
                    if not hasattr(result, 'detector_name') or not result.detector_name:
                        result.detector_name = self.detector_name
            
            return results or []
            
        except Exception as e:
            logger.error(f"Error processing frame in detector {self.detector_name}: {e}")
            import traceback
            traceback.print_exc()
            
            # Return error result
            return [DetectorResult(
                confidence=-1.0,
                description=f"Detector error: {str(e)}",
                frame_id=frame_id,
                detector_name=self.detector_name
            )]
    
    def cleanup(self):
        """Clean up detector resources."""
        if self.detector_instance and hasattr(self.detector_instance, 'cleanup'):
            try:
                self.detector_instance.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up detector {self.detector_name}: {e}")


class SimpleFrameProvider:
    """Simple frame provider for detectors."""
    
    def __init__(self, storage):
        self.storage = storage
    
    def get_frame_pair(self, current_frame_id: int, reference_frame_id: int, 
                      current_take_id: int, reference_take_id: int) -> Optional[tuple]:
        """Get a pair of frames for comparison."""
        try:
            # Get current frame
            current_frame = self.storage.get_frame_array(current_take_id, current_frame_id)
            if current_frame is None:
                return None
            
            # Get reference frame
            reference_frame = self.storage.get_frame_array(reference_take_id, reference_frame_id)
            if reference_frame is None:
                return None
            
            return (current_frame, reference_frame)
            
        except Exception as e:
            logger.error(f"Error getting frame pair: {e}")
            return None
    
    def get_frame(self, frame_id: int, take_id: int):
        """Get a single frame."""
        try:
            return self.storage.get_frame_array(take_id, frame_id)
        except Exception as e:
            logger.error(f"Error getting frame: {e}")
            return None
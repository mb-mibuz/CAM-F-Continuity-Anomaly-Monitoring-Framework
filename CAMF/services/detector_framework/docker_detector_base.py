"""
Base class for Docker-based detectors
Provides secure communication interface for detector implementations
"""

import json
import sys
import time
import logging
import base64
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod
import numpy as np
import cv2
from datetime import datetime


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DockerDetector(ABC):
    """
    Base class for Docker-based detectors
    
    Handles secure communication with the framework through filesystem-based IPC
    Detectors should inherit from this class and implement process_frame_pair()
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.name = self.config.get('name', 'UnknownDetector')
        self.version = self.config.get('version', '1.0.0')
        self.initialized = False
        
        # Only parse command line arguments if running as main script
        if hasattr(sys, 'argv') and ('--docker-mode' in sys.argv or len(sys.argv) > 2):
            # Parse command line arguments
            parser = argparse.ArgumentParser()
            parser.add_argument('--docker-mode', action='store_true', 
                              help='Running in Docker container')
            parser.add_argument('input_dir', help='Input directory for messages')
            parser.add_argument('output_dir', help='Output directory for results')
            
            self.args = parser.parse_args()
            
            if not self.args.docker_mode:
                raise RuntimeError("This detector must be run in Docker mode")
                
            self.input_dir = Path(self.args.input_dir)
            self.output_dir = Path(self.args.output_dir)
            
            # Validate directories
            if not self.input_dir.exists() or not self.output_dir.exists():
                raise RuntimeError(f"Communication directories do not exist")
        else:
            # For testing/import - don't validate paths
            self.input_dir = Path("/comm/input")
            self.output_dir = Path("/comm/output")
            self.args = argparse.Namespace(docker_mode=False, 
                                         input_dir=str(self.input_dir), 
                                         output_dir=str(self.output_dir))
            
        logger.info(f"Initializing {self.name} v{self.version} in Docker mode")
        
    def run(self):
        """Main detector loop - polls for input and processes frames"""
        try:
            # Initialize detector
            self.initialize()
            self.initialized = True
            logger.info("Detector initialized successfully")
            
            # Main processing loop
            while True:
                try:
                    # Check for input files
                    input_files = sorted(self.input_dir.glob("*.json"))
                    
                    for input_file in input_files:
                        try:
                            # Read and process message
                            with open(input_file, 'r') as f:
                                message = json.load(f)
                                
                            # Process based on message type
                            if message.get('type') == 'process_frame_pair':
                                self._handle_frame_pair(message)
                            elif message.get('type') == 'shutdown':
                                logger.info("Received shutdown signal")
                                return
                            else:
                                logger.warning(f"Unknown message type: {message.get('type')}")
                                
                            # Remove processed input file
                            input_file.unlink()
                            
                        except Exception as e:
                            logger.error(f"Error processing input file {input_file}: {e}")
                            # Remove corrupted file
                            try:
                                input_file.unlink()
                            except Exception as unlink_error:
                                logger.debug(f"Failed to remove corrupted file {input_file}: {unlink_error}")
                                
                    # Brief sleep to prevent CPU spinning
                    time.sleep(0.1)
                    
                except KeyboardInterrupt:
                    logger.info("Detector interrupted")
                    break
                except Exception as e:
                    logger.error(f"Error in main loop: {e}")
                    time.sleep(1)
                    
        finally:
            # Cleanup
            try:
                self.cleanup()
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")
            logger.info("Detector shutdown complete")
            
    def _handle_frame_pair(self, message: Dict[str, Any]):
        """Handle frame pair processing request"""
        message_id = message.get('id', 'unknown')
        
        try:
            # Deserialize frames
            current_frame = self._deserialize_frame(message['current_frame'])
            reference_frame = self._deserialize_frame(message['reference_frame'])
            metadata = message.get('metadata', {})
            
            # Process frames
            start_time = time.time()
            results = self.process_frame_pair(current_frame, reference_frame, metadata)
            processing_time = time.time() - start_time
            
            # Prepare response
            response = {
                'id': message_id,
                'type': 'result',
                'timestamp': time.time(),
                'processing_time': processing_time,
                'detector_name': self.name,
                'detector_version': self.version,
                'results': results
            }
            
            # Write response
            output_file = self.output_dir / f"{message_id}.json"
            with open(output_file, 'w') as f:
                json.dump(response, f)
                
        except Exception as e:
            logger.error(f"Error processing frame pair: {e}")
            
            # Send error response
            error_response = {
                'id': message_id,
                'type': 'error',
                'timestamp': time.time(),
                'error': str(e),
                'detector_name': self.name
            }
            
            output_file = self.output_dir / f"{message_id}.json"
            with open(output_file, 'w') as f:
                json.dump(error_response, f)
                
    def _deserialize_frame(self, frame_data: Dict[str, Any]) -> np.ndarray:
        """Deserialize frame from base64 PNG data"""
        # Decode base64
        png_bytes = base64.b64decode(frame_data['data'])
        
        # Decode PNG
        nparr = np.frombuffer(png_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            raise ValueError("Failed to decode frame")
            
        return frame
        
    @abstractmethod
    def initialize(self):
        """
        Initialize the detector
        Load models, set up resources, etc.
        """
        
    @abstractmethod
    def process_frame_pair(self, current_frame: np.ndarray, 
                          reference_frame: np.ndarray,
                          metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Process a frame pair and return detected anomalies
        
        Args:
            current_frame: Current frame as numpy array (BGR)
            reference_frame: Reference frame as numpy array (BGR)
            metadata: Additional metadata about the frames
            
        Returns:
            List of detection results, each containing:
            - error_type: Type of continuity error detected
            - confidence: Confidence score (0-1)
            - location: Bounding box or region of interest
            - description: Human-readable description
            - details: Additional detection-specific details
        """
        
    def cleanup(self):
        """
        Cleanup resources
        Override if detector needs special cleanup
        """
        

class ContinuityError:
    """Standard continuity error format"""
    
    def __init__(self, error_type: str, confidence: float, 
                 location: Optional[Dict[str, int]] = None,
                 description: str = "", details: Optional[Dict[str, Any]] = None):
        self.error_type = error_type
        self.confidence = confidence
        self.location = location  # {"x": int, "y": int, "w": int, "h": int}
        self.description = description
        self.details = details or {}
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'error_type': self.error_type,
            'confidence': self.confidence,
            'location': self.location,
            'description': self.description,
            'details': self.details,
            'timestamp': datetime.utcnow().isoformat()
        }


if __name__ == "__main__":
    # Example usage - this should be overridden by actual detectors
    class ExampleDetector(DockerDetector):
        def initialize(self):
            logger.info("Example detector initialized")
            
        def process_frame_pair(self, current_frame: np.ndarray, 
                              reference_frame: np.ndarray,
                              metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
            # Example: Simple difference detection
            diff = cv2.absdiff(current_frame, reference_frame)
            gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            
            # Threshold to find significant changes
            _, thresh = cv2.threshold(gray_diff, 30, 255, cv2.THRESH_BINARY)
            
            # Find contours
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            results = []
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > 100:  # Minimum area threshold
                    x, y, w, h = cv2.boundingRect(contour)
                    
                    error = ContinuityError(
                        error_type="object_change",
                        confidence=min(area / 1000, 1.0),  # Simple confidence based on area
                        location={"x": int(x), "y": int(y), "w": int(w), "h": int(h)},
                        description=f"Detected change in region ({x}, {y}, {w}x{h})"
                    )
                    
                    results.append(error.to_dict())
                    
            return results
            
    # Run example detector
    detector = ExampleDetector()
    detector.run()
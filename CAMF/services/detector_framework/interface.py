# CAMF/services/detector_framework/interface.py
"""
Detector Framework Interface - Queue-based Push System
Provides the core interfaces for detector plugins using a push-based queue model.
Detectors receive frame pairs directly and process them independently.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from abc import abstractmethod
import numpy as np
import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import logging
import time

from CAMF.common.models import (
    BaseDetector, DetectorInfo, DetectorResult, 
    ErrorConfidence
)


@dataclass
class FramePair:
    """A pair of frames for comparison - passed directly to detectors."""
    current_frame: np.ndarray  # Current take frame as numpy array
    reference_frame: np.ndarray  # Reference take frame as numpy array
    current_frame_id: int
    reference_frame_id: int
    take_id: int
    scene_id: int
    angle_id: int
    project_id: int
    timestamp: float = field(default_factory=time.time)
    metadata: Optional[Dict[str, Any]] = None
    
    def get_hash(self) -> str:
        """Get a unique hash for this frame pair."""
        current_hash = hashlib.md5(self.current_frame.tobytes()).hexdigest()
        reference_hash = hashlib.md5(self.reference_frame.tobytes()).hexdigest()
        return f"{current_hash}_{reference_hash}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (excluding frame data)."""
        return {
            'current_frame_id': self.current_frame_id,
            'reference_frame_id': self.reference_frame_id,
            'take_id': self.take_id,
            'scene_id': self.scene_id,
            'angle_id': self.angle_id,
            'project_id': self.project_id,
            'timestamp': self.timestamp,
            'metadata': self.metadata
        }


@dataclass
class FalsePositive:
    """Represents a false positive detection."""
    detector_name: str
    frame_id: int
    take_id: int
    scene_id: int
    angle_id: int
    error_description: str
    error_metadata: Dict[str, Any]
    marked_at: datetime = field(default_factory=datetime.now)
    marked_by: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            'detector_name': self.detector_name,
            'frame_id': self.frame_id,
            'take_id': self.take_id,
            'scene_id': self.scene_id,
            'angle_id': self.angle_id,
            'error_description': self.error_description,
            'error_metadata': self.error_metadata,
            'marked_at': self.marked_at.isoformat(),
            'marked_by': self.marked_by
        }


class QueueBasedDetector(BaseDetector):
    """Base class for queue-based detectors with push-based frame processing."""
    
    def __init__(self):
        super().__init__()
        # Queue configuration with intelligent management
        from CAMF.services.detector_framework.priority_queue_manager import IntelligentFrameQueue
        self._frame_queue = IntelligentFrameQueue(maxsize=100, high_water_mark=0.8)
        self._result_queue = queue.Queue()
        
        # Processing state
        self._processing = False
        self._worker_thread = None
        self._frame_count = 0
        self._processed_count = 0
        self._last_process_time = 0
        
        # Error tracking
        self._error_count = 0
        self._consecutive_errors = 0
        
        # Take tracking for frame count info
        self._take_frame_counts = {}
        self._current_take_id = None
        
        # Logger
        self.logger = logging.getLogger(f"detector.{self.__class__.__name__}")
        
    @abstractmethod
    def process_frame_pair(self, frame_pair: FramePair) -> List[DetectorResult]:
        """Process a single frame pair and return results.
        This method should be implemented by each detector.
        """
    
    def start_processing(self):
        """Start the processing thread."""
        if not self._processing:
            self._processing = True
            self._worker_thread = threading.Thread(target=self._process_queue, daemon=True)
            self._worker_thread.start()
    
    def stop_processing(self):
        """Stop the processing thread."""
        self._processing = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5.0)
    
    def add_frame_pair(self, frame_pair: FramePair, take_frame_count: int = 0) -> bool:
        """Add a frame pair to the processing queue with intelligent management.
        
        Args:
            frame_pair: FramePair object containing current and reference frames
            take_frame_count: Total frames in the take (for prioritization)
            
        Returns:
            True if successfully added/handled, False if rejected
        """
        # Update take info if needed
        if frame_pair.take_id != self._current_take_id:
            self._current_take_id = frame_pair.take_id
            self._take_frame_counts[frame_pair.take_id] = take_frame_count
            self.logger.debug(f"New take {frame_pair.take_id} started, frame count: {take_frame_count}")
        
        # Use intelligent queue's put method
        success = self._frame_queue.put(frame_pair, take_frame_count)
        if success:
            self._frame_count += 1
            
        return success
    
    def get_results(self, timeout: float = 0.1) -> Optional[List[DetectorResult]]:
        """Get processed results from the result queue.
        
        Args:
            timeout: Maximum time to wait for results
            
        Returns:
            List of detector results or None if timeout
        """
        try:
            return self._result_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def get_all_results(self) -> List[List[DetectorResult]]:
        """Get all available results without blocking.
        
        Returns:
            List of result batches
        """
        all_results = []
        while True:
            try:
                results = self._result_queue.get_nowait()
                all_results.append(results)
            except queue.Empty:
                break
        return all_results
    
    def get_queue_size(self) -> int:
        """Get the current queue size."""
        return self._frame_queue.qsize()
    
    def get_processed_count(self) -> int:
        """Get the number of frames processed."""
        return self._processed_count
    
    def get_total_frame_count(self) -> int:
        """Get the total number of frames added to queue."""
        return self._frame_count
    
    def get_stats(self) -> Dict[str, Any]:
        """Get detector statistics including queue performance."""
        base_stats = {
            'name': self.get_info().name if hasattr(self, 'get_info') else self.__class__.__name__,
            'is_processing': self._processing,
            'frames_added': self._frame_count,
            'frames_processed': self._processed_count,
            'frames_pending': self._frame_count - self._processed_count,
            'error_count': self._error_count,
            'consecutive_errors': self._consecutive_errors,
            'last_process_time': self._last_process_time
        }
        
        # Add intelligent queue stats
        queue_stats = self._frame_queue.get_stats()
        base_stats.update({
            'queue_size': queue_stats['current_size'],
            'queue_max_size': queue_stats['max_size'],
            'frames_dropped': queue_stats['frames_dropped'],
            'drop_rate': queue_stats['drop_rate'],
            'queue_utilization': queue_stats['utilization']
        })
        
        return base_stats
    
    def clear_queue(self):
        """Clear all pending frames from the queue."""
        cleared = self._frame_queue.clear()
        self.logger.info(f"Cleared {cleared} frames from intelligent queue")
        return cleared
    
    def _process_queue(self):
        """Worker thread that processes frames from the queue."""
        self.logger.info("Processing thread started with intelligent queue management")
        
        while self._processing:
            try:
                # Get frame pair from intelligent queue with timeout
                frame_pair = self._frame_queue.get(timeout=0.5)
                
                if frame_pair is None:
                    continue
                
                # Process the frame pair
                start_time = time.time()
                try:
                    # Call process_frame_pair with proper arguments
                    result_dict = self.process_frame_pair(
                        frame_pair.current_frame, 
                        frame_pair.reference_frame,
                        frame_pair
                    )
                    process_time = time.time() - start_time
                    self._last_process_time = process_time
                    
                    # Extract results from the returned dictionary
                    if isinstance(result_dict, dict):
                        results = result_dict.get('results', [])
                    else:
                        # Backward compatibility - if detector returns list directly
                        results = result_dict if isinstance(result_dict, list) else []
                    
                    # Add timing metadata to results
                    for result in results:
                        if not result.metadata:
                            result.metadata = {}
                        result.metadata['process_time'] = process_time
                    
                    # Add results to result queue
                    if results:
                        self._result_queue.put(results)
                    
                    self._processed_count += 1
                    self._consecutive_errors = 0  # Reset error counter on success
                    
                    self.logger.debug(f"Processed frame pair in {process_time:.3f}s")
                    
                    # Log stats periodically
                    if self._processed_count % 100 == 0:
                        stats = self._frame_queue.get_stats()
                        self.logger.info(f"Queue stats after {self._processed_count} frames: "
                                       f"size={stats['current_size']}/{stats['max_size']}, "
                                       f"dropped={stats['frames_dropped']} ({stats['drop_rate']:.1%})")
                    
                except Exception as e:
                    self._error_count += 1
                    self._consecutive_errors += 1
                    
                    self.logger.error(f"Error processing frame pair: {e}", exc_info=True)
                    
                    # Create error result
                    error_result = DetectorResult(
                        confidence=ErrorConfidence.DETECTOR_FAILED,
                        description=f"Processing error: {str(e)}",
                        frame_id=frame_pair.current_frame_id,
                        detector_name=self.get_info().name if hasattr(self, 'get_info') else self.__class__.__name__,
                        metadata={'error': str(e), 'error_type': type(e).__name__}
                    )
                    self._result_queue.put([error_result])
                    
                    # If too many consecutive errors, pause briefly
                    if self._consecutive_errors > 5:
                        self.logger.warning(f"Too many consecutive errors ({self._consecutive_errors}), pausing...")
                        time.sleep(1.0)
                
            except queue.Empty:
                # No frames to process, continue
                continue
            except Exception as e:
                self.logger.error(f"Unexpected error in processing thread: {e}", exc_info=True)
                time.sleep(0.1)  # Brief pause on unexpected errors
        
        self.logger.info("Processing thread stopped")
        
        # Log final statistics
        final_stats = self._frame_queue.get_stats()
        self.logger.info(f"Final queue statistics: {final_stats}")


class DetectorRegistry:
    """Registry for managing available detectors."""
    
    def __init__(self):
        self.detector_metadata: Dict[str, Dict[str, Any]] = {}
        self.detector_info: Dict[str, DetectorInfo] = {}
    
    def register_detector_from_metadata(self, detector_name: str, metadata: Dict[str, Any]) -> bool:
        """Register a detector from its metadata."""
        try:
            print(f"Registering detector from metadata: {detector_name}")
            
            # Create DetectorInfo from metadata
            info = DetectorInfo(
                name=metadata['name'],
                description=metadata.get('description', ''),
                version=metadata.get('version', '1.0.0'),
                author=metadata.get('author', 'Unknown'),
                requires_reference=metadata.get('requires_reference', True),
                min_frames_required=metadata.get('min_frames_required', 1)
            )
            
            self.detector_metadata[detector_name] = metadata
            self.detector_info[detector_name] = info
            
            print(f"Successfully registered detector: {detector_name}")
            return True
            
        except Exception as e:
            print(f"Failed to register detector from metadata: {e}")
            return False
    
    def get_detector_metadata(self, name: str) -> Optional[Dict[str, Any]]:
        """Get detector metadata by name."""
        return self.detector_metadata.get(name)
    
    def get_detector_info(self, name: str) -> Optional[DetectorInfo]:
        """Get detector info by name."""
        return self.detector_info.get(name)
    
    def list_detectors(self) -> List[str]:
        """List all registered detector names."""
        return list(self.detector_metadata.keys())


class DetectorLoader:
    """Loads detectors from the detectors directory."""
    
    def __init__(self, detectors_path: str):
        self.detectors_path = Path(detectors_path)
        self.registry = DetectorRegistry()
        # Map display names to directory names
        self.name_to_dir_map = {}
        # Map display names to directory names for easier lookup
        self.display_name_to_dir_map = {}
    
    def discover_detectors(self) -> List[str]:
        """Discover all available detectors."""
        discovered = []
        
        if not self.detectors_path.exists():
            print(f"Detectors path does not exist: {self.detectors_path}")
            return discovered
        
        print(f"Scanning detectors directory: {self.detectors_path}")
        
        for detector_dir in self.detectors_path.iterdir():
            if detector_dir.is_dir() and not detector_dir.name.startswith('_'):
                print(f"Found detector directory: {detector_dir.name}")
                detector_name = self._load_detector_metadata(detector_dir)
                if detector_name:
                    discovered.append(detector_name)
                    # Store the mapping
                    self.name_to_dir_map[detector_name] = detector_dir.name
                else:
                    print(f"Failed to load detector from directory: {detector_dir.name}")
        
        print(f"Registry contains detectors: {self.registry.list_detectors()}")
        
        return discovered
    
    def get_detector_directory(self, detector_name: str) -> Optional[str]:
        """Get the directory name for a detector display name."""
        # First try as directory name
        if detector_name in self.name_to_dir_map:
            return self.name_to_dir_map.get(detector_name)
        # Then try as display name
        dir_name = self.display_name_to_dir_map.get(detector_name)
        if dir_name:
            return dir_name
        return None
    
    def find_detector_by_name(self, name: str) -> Optional[str]:
        """Find detector directory name by either directory name or display name."""
        # Check if it's already a directory name
        if name in self.registry.detector_metadata:
            return name
        # Check if it's a display name
        return self.display_name_to_dir_map.get(name)
    
    def _load_detector_metadata(self, detector_dir: Path) -> Optional[str]:
        """Load detector metadata from JSON file."""
        print(f"\n=== Loading detector metadata from: {detector_dir} ===")
        
        try:
            # Look for detector.json
            metadata_file = detector_dir / "detector.json"
            
            if not metadata_file.exists():
                # Try legacy metadata.json
                metadata_file = detector_dir / "metadata.json"
                
            if not metadata_file.exists():
                print(f"ERROR: No detector.json found in {detector_dir}")
                return None
            
            # Read metadata
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            # Validate required fields
            required_fields = ['name', 'version']
            for field in required_fields:
                if field not in metadata:
                    print(f"ERROR: Missing required field '{field}' in {metadata_file}")
                    return None
            
            # Use directory name as the primary key for consistency
            detector_name = detector_dir.name
            
            # Register with metadata using directory name as key
            if self.registry.register_detector_from_metadata(detector_name, metadata):
                print(f"Successfully loaded detector metadata: {detector_name} (display name: {metadata['name']})")
                # Store mapping from display name to directory name
                self.display_name_to_dir_map[metadata['name']] = detector_name
                return detector_name
            else:
                print(f"ERROR: Failed to register detector: {detector_name}")
                return None
                
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid JSON in {metadata_file}: {e}")
        except Exception as e:
            print(f"ERROR loading detector metadata from {detector_dir}: {e}")
            import traceback
            traceback.print_exc()
        
        return None


class ConfigurationManager:
    """Manages detector configurations."""
    
    def __init__(self, storage_service):
        self.storage = storage_service
    
    def save_detector_config(self, scene_id: int, detector_name: str, config: Dict[str, Any]) -> bool:
        """Save detector configuration for a scene."""
        try:
            # Get current scene
            scene = self.storage.get_scene(scene_id)
            if not scene:
                return False
            
            # Update detector settings
            if not scene.detector_settings:
                scene.detector_settings = {}
            
            scene.detector_settings[detector_name] = config
            
            # Save back to storage
            self.storage.update_scene(
                scene_id=scene_id,
                detector_settings=scene.detector_settings
            )
            
            return True
        
        except Exception as e:
            print(f"Failed to save detector config: {e}")
            return False
    
    def load_detector_config(self, scene_id: int, detector_name: str) -> Dict[str, Any]:
        """Load detector configuration for a scene."""
        try:
            scene = self.storage.get_scene(scene_id)
            if not scene or not scene.detector_settings:
                return {}
            
            return scene.detector_settings.get(detector_name, {})
        
        except Exception as e:
            print(f"Failed to load detector config: {e}")
            return {}
    
    def get_enabled_detectors(self, scene_id: int) -> List[str]:
        """Get list of enabled detectors for a scene."""
        try:
            scene = self.storage.get_scene(scene_id)
            if not scene:
                return []
            
            return scene.enabled_detectors or []
        
        except Exception as e:
            print(f"Failed to get enabled detectors: {e}")
            return []
    
    def set_enabled_detectors(self, scene_id: int, detector_names: List[str]) -> bool:
        """Set enabled detectors for a scene."""
        try:
            self.storage.update_scene(
                scene_id=scene_id,
                enabled_detectors=detector_names
            )
            return True
        
        except Exception as e:
            print(f"Failed to set enabled detectors: {e}")
            return False


class FalsePositiveManager:
    """Manages false positive detections with persistent storage."""
    
    def __init__(self, storage_service=None):
        self.storage = storage_service
        self._false_positives: Dict[str, List[FalsePositive]] = {}
        self._false_positives_lock = threading.Lock()
        self._storage_path = Path("data/storage/false_positives.json")
        self.logger = logging.getLogger("FalsePositiveManager")
        self._load_false_positives()
    
    def mark_as_false_positive(self, detector_name: str, frame_id: int, take_id: int,
                               scene_id: int, angle_id: int, error_description: str,
                               error_metadata: Dict[str, Any], marked_by: Optional[str] = None) -> bool:
        """Mark a detection as false positive and remove it from frame results."""
        try:
            fp = FalsePositive(
                detector_name=detector_name,
                frame_id=frame_id,
                take_id=take_id,
                scene_id=scene_id,
                angle_id=angle_id,
                error_description=error_description,
                error_metadata=error_metadata,
                marked_by=marked_by
            )
            
            # Store in memory with thread safety
            with self._false_positives_lock:
                key = self._get_key(detector_name, frame_id, take_id)
                if key not in self._false_positives:
                    self._false_positives[key] = []
                self._false_positives[key].append(fp)
            
            # Persist to storage
            self._save_false_positives()
            
            # Remove from frame results in storage
            if self.storage:
                self._remove_from_frame_results(detector_name, frame_id, take_id, error_description)
            
            self.logger.info(f"Marked false positive: {detector_name} - frame {frame_id} - {error_description}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to mark as false positive: {e}", exc_info=True)
            return False
    
    def is_false_positive(self, detector_name: str, frame_id: int, take_id: int,
                         error_description: str) -> bool:
        """Check if a detection is marked as false positive."""
        with self._false_positives_lock:
            key = self._get_key(detector_name, frame_id, take_id)
            if key in self._false_positives:
                for fp in self._false_positives[key]:
                    if fp.error_description == error_description:
                        return True
        return False
    
    def filter_results(self, results: List[DetectorResult], take_id: int) -> List[DetectorResult]:
        """Filter out false positives from a list of detector results."""
        filtered = []
        for result in results:
            if not self.is_false_positive(
                result.detector_name, 
                result.frame_id, 
                take_id,
                result.description
            ):
                filtered.append(result)
        return filtered
    
    def get_false_positives(self, take_id: Optional[int] = None,
                           scene_id: Optional[int] = None,
                           detector_name: Optional[str] = None) -> List[FalsePositive]:
        """Get false positives filtered by criteria."""
        results = []
        for fps in self._false_positives.values():
            for fp in fps:
                if take_id and fp.take_id != take_id:
                    continue
                if scene_id and fp.scene_id != scene_id:
                    continue
                if detector_name and fp.detector_name != detector_name:
                    continue
                results.append(fp)
        return results
    
    def clear_false_positives(self, take_id: Optional[int] = None,
                             scene_id: Optional[int] = None,
                             detector_name: Optional[str] = None):
        """Clear false positives based on criteria."""
        keys_to_remove = []
        for key, fps in self._false_positives.items():
            fps_to_keep = []
            for fp in fps:
                if take_id and fp.take_id == take_id:
                    continue
                if scene_id and fp.scene_id == scene_id:
                    continue
                if detector_name and fp.detector_name == detector_name:
                    continue
                fps_to_keep.append(fp)
            
            if fps_to_keep:
                self._false_positives[key] = fps_to_keep
            else:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self._false_positives[key]
        
        self._save_false_positives()
    
    def _get_key(self, detector_name: str, frame_id: int, take_id: int) -> str:
        """Generate a unique key for false positive storage."""
        return f"{detector_name}_{frame_id}_{take_id}"
    
    def _load_false_positives(self):
        """Load false positives from storage."""
        try:
            if self._storage_path.exists():
                with open(self._storage_path, 'r') as f:
                    data = json.load(f)
                    with self._false_positives_lock:
                        for key, fps_data in data.items():
                            self._false_positives[key] = [
                                FalsePositive(
                                    detector_name=fp['detector_name'],
                                    frame_id=fp['frame_id'],
                                    take_id=fp['take_id'],
                                    scene_id=fp['scene_id'],
                                    angle_id=fp['angle_id'],
                                    error_description=fp['error_description'],
                                    error_metadata=fp['error_metadata'],
                                    marked_at=datetime.fromisoformat(fp['marked_at']),
                                    marked_by=fp.get('marked_by')
                                )
                                for fp in fps_data
                            ]
                self.logger.info(f"Loaded {sum(len(v) for v in self._false_positives.values())} false positives")
        except Exception as e:
            self.logger.error(f"Failed to load false positives: {e}", exc_info=True)
    
    def _save_false_positives(self):
        """Save false positives to storage."""
        try:
            # Ensure directory exists
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Prepare data with thread safety
            with self._false_positives_lock:
                data = {}
                for key, fps in self._false_positives.items():
                    data[key] = [fp.to_dict() for fp in fps]
            
            # Write atomically
            temp_file = self._storage_path.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            # Replace original file
            temp_file.replace(self._storage_path)
                
        except Exception as e:
            self.logger.error(f"Failed to save false positives: {e}", exc_info=True)
    
    def _remove_from_frame_results(self, detector_name: str, frame_id: int,
                                  take_id: int, error_description: str):
        """Remove false positive from frame results in storage."""
        try:
            # Get frame from storage
            frame = self.storage.get_frame(frame_id)
            if frame and frame.detector_results:
                # Filter out the false positive
                original_count = len(frame.detector_results)
                updated_results = []
                
                for result in frame.detector_results:
                    # Skip the false positive
                    if (result.detector_name == detector_name and
                        result.description == error_description):
                        continue
                    updated_results.append(result)
                
                # Only update if we actually removed something
                if len(updated_results) < original_count:
                    # Update frame with filtered results
                    self.storage.update_frame(
                        frame_id=frame_id,
                        detector_results=updated_results
                    )
                    self.logger.info(f"Removed false positive from frame {frame_id} results")
                    
        except Exception as e:
            self.logger.error(f"Failed to remove from frame results: {e}", exc_info=True)


class DetectorTemplate:
    """Provides template for creating new detectors with queue-based processing."""
    
    @staticmethod
    def generate_template(detector_name: str, output_path: str) -> bool:
        """Generate a queue-based detector template."""
        try:
            # Create detector.json metadata file
            metadata = {
                "name": detector_name,
                "version": "1.0.0",
                "description": f"Checks for {detector_name.lower()} continuity issues",
                "author": "Your Name",
                "requires_reference": True,
                "min_frames_required": 1,
                "schema": {
                    "fields": {
                        "sensitivity": {
                            "field_type": "number",
                            "title": "Detection Sensitivity",
                            "description": "How sensitive the detector should be (0.1 - 1.0)",
                            "required": False,
                            "default": 0.7,
                            "minimum": 0.1,
                            "maximum": 1.0
                        },
                        "enable_logging": {
                            "field_type": "boolean",
                            "title": "Enable Logging",
                            "description": "Enable detailed logging for debugging",
                            "required": False,
                            "default": False
                        }
                    }
                }
            }
            
            # Create Python template with queue-based processing
            template_content = f'''# {detector_name} Detector
"""
{detector_name} - A detector for continuity monitoring.
Author: Your Name
Version: 1.0.0
"""

import numpy as np
import cv2
from typing import List, Dict, Any, Optional
import logging

from CAMF.services.detector_framework.interface import QueueBasedDetector, FramePair
from CAMF.common.models import (
    DetectorInfo, DetectorConfigurationSchema, 
    DetectorResult, ErrorConfidence, ConfigurationField
)


class {detector_name.replace(" ", "")}Detector(QueueBasedDetector):
    """Detector for {detector_name.lower()} continuity checking.
    
    Uses queue-based processing for frame pairs.
    """
    
    def __init__(self):
        """Initialize the detector."""
        super().__init__()
        self.name = "{detector_name}"
        self.config = {{}}
        self.is_initialized = False
    
    def get_info(self) -> DetectorInfo:
        """Return detector information."""
        return DetectorInfo(
            name="{detector_name}",
            description="Checks for {detector_name.lower()} continuity issues",
            version="1.0.0",
            author="Your Name",
            requires_reference=True,
            min_frames_required=1
        )
    
    def get_configuration_schema(self) -> DetectorConfigurationSchema:
        """Return configuration schema."""
        return DetectorConfigurationSchema(
            fields={{
                "sensitivity": ConfigurationField(
                    field_type="number",
                    title="Detection Sensitivity",
                    description="How sensitive the detector should be (0.1 - 1.0)",
                    required=False,
                    default=0.7,
                    minimum=0.1,
                    maximum=1.0
                ),
                "enable_logging": ConfigurationField(
                    field_type="boolean",
                    title="Enable Logging",
                    description="Enable detailed logging for debugging",
                    required=False,
                    default=False
                ),
                "detection_threshold": ConfigurationField(
                    field_type="number",
                    title="Detection Threshold",
                    description="Minimum confidence threshold for reporting errors",
                    required=False,
                    default=0.5,
                    minimum=0.0,
                    maximum=1.0
                )
            }}
        )
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize the detector.
        
        Args:
            config: Configuration dictionary from the UI
            
        Returns:
            True if initialization successful
        """
        try:
            self.config = config
            self.sensitivity = config.get("sensitivity", 0.7)
            self.enable_logging = config.get("enable_logging", False)
            self.detection_threshold = config.get("detection_threshold", 0.5)
            
            # Set up logging if enabled
            if self.enable_logging:
                self.logger.setLevel(logging.DEBUG)
            
            # TODO: Add your initialization logic here
            # Examples:
            # - Load ML models
            # - Initialize image processing pipelines
            # - Set up any required resources
            
            self.is_initialized = True
            
            # Start the processing thread
            self.start_processing()
            self.logger.info(f"{{self.get_info().name}} initialized successfully")
            
            return True
        
        except Exception as e:
            self.logger.error(f"Failed to initialize: {{e}}", exc_info=True)
            return False
    
    def process_frame_pair(self, frame_pair: FramePair) -> List[DetectorResult]:
        """Process a frame pair.
        
        This method is called automatically by the processing thread for each
        frame pair in the queue.
        
        Args:
            frame_pair: FramePair object containing current and reference frames
            
        Returns:
            List of DetectorResult objects for any issues found
        """
        results = []
        
        if not self.is_initialized:
            return [DetectorResult(
                confidence=ErrorConfidence.DETECTOR_FAILED,
                description="Detector not initialized",
                frame_id=frame_pair.current_frame_id,
                detector_name=self.name
            )]
        
        try:
            # Extract frames from the pair
            current_frame = frame_pair.current_frame
            reference_frame = frame_pair.reference_frame
            
            # Get metadata
            metadata = frame_pair.metadata or {{}}
            
            # TODO: Implement your detection logic here
            # This is just an example - replace with your actual detection algorithm
            
            # Example: Simple pixel difference detection
            if reference_frame is not None:
                diff = cv2.absdiff(current_frame, reference_frame)
                gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY) if len(diff.shape) == 3 else diff
                mean_diff = np.mean(gray_diff)
                
                # Calculate confidence based on difference and sensitivity
                normalized_diff = min(mean_diff / 255.0, 1.0)
                confidence = normalized_diff * self.sensitivity
                
                # Only report if above threshold
                if confidence > self.detection_threshold:
                    # Find regions of change (example)
                    _, thresh = cv2.threshold(gray_diff, 30, 255, cv2.THRESH_BINARY)
                    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    
                    # Get bounding boxes for changed regions
                    bounding_boxes = []
                    for contour in contours[:5]:  # Limit to top 5 regions
                        x, y, w, h = cv2.boundingRect(contour)
                        if w * h > 100:  # Minimum area threshold
                            bounding_boxes.append({{
                                "x": int(x),
                                "y": int(y),
                                "width": int(w),
                                "height": int(h)
                            }})
                    
                    # Determine error level
                    if confidence > 0.8:
                        error_level = ErrorConfidence.LIKELY_ERROR
                    elif confidence > 0.6:
                        error_level = ErrorConfidence.POTENTIAL_ERROR
                    else:
                        error_level = ErrorConfidence.POTENTIAL_ERROR
                    
                    results.append(DetectorResult(
                        confidence=error_level,
                        description=f"{{self.name}} detected changes (confidence: {{confidence:.2f}})",
                        frame_id=frame_pair.current_frame_id,
                        detector_name=self.name,
                        bounding_boxes=bounding_boxes,
                        metadata={{
                            "mean_difference": float(mean_diff),
                            "confidence": float(confidence),
                            "threshold": float(self.detection_threshold),
                            "sensitivity": float(self.sensitivity),
                            "take_id": frame_pair.take_id,
                            "reference_frame_id": frame_pair.reference_frame_id,
                            "regions_found": len(bounding_boxes)
                        }}
                    ))
            
            if self.enable_logging:
                self.logger.debug(
                    f"Processed frame pair: current={{frame_pair.current_frame_id}}, "
                    f"reference={{frame_pair.reference_frame_id}}"
                )
            
        except Exception as e:
            self.logger.error(f"Error processing frame pair: {{e}}", exc_info=True)
            results.append(DetectorResult(
                confidence=ErrorConfidence.DETECTOR_FAILED,
                description=f"Processing failed: {{str(e)}}",
                frame_id=frame_pair.current_frame_id,
                detector_name=self.name,
                metadata={{"error": str(e), "error_type": type(e).__name__}}
            ))
        
        return results
    
    def cleanup(self):
        """Clean up detector resources."""
        try:
            # Stop the processing thread
            self.stop_processing()
            
            # TODO: Add your cleanup logic here
            # Examples:
            # - Release ML models
            # - Close file handles
            # - Free GPU memory
            # - Save state if needed
            
            self.is_initialized = False
            self.logger.info(f"{{self.name}} cleaned up successfully")
            
        except Exception as e:
            self.logger.error(f"Error during cleanup: {{e}}", exc_info=True)


# Example usage
if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.DEBUG)
    
    # Create detector instance
    detector = {detector_name.replace(" ", "")}Detector()
    
    # Initialize with config
    config = {{
        "sensitivity": 0.7,
        "enable_logging": True,
        "detection_threshold": 0.5
    }}
    
    if detector.initialize(config):
        print("Detector initialized successfully")
        print(f"Stats: {{detector.get_stats()}}")
        
        # The detector will process frames pushed to its queue
        # In production, frames are pushed by the detector framework
        
        # Clean up when done
        detector.cleanup()
    else:
        print("Failed to initialize detector")
'''
            
            # Create output directory if it doesn't exist
            Path(output_path).mkdir(parents=True, exist_ok=True)
            
            # Write metadata file
            metadata_file = Path(output_path) / "detector.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
            
            # Write template file
            template_file = Path(output_path) / "detector.py"
            with open(template_file, 'w', encoding='utf-8') as f:
                f.write(template_content)
            
            # Create requirements.txt
            requirements_file = Path(output_path) / "requirements.txt"
            with open(requirements_file, 'w', encoding='utf-8') as f:
                f.write("""# Add your detector dependencies here
# Example:
# opencv-python>=4.5.0
# numpy>=1.20.0
# pillow>=8.0.0
""")
            
            # Create README.md
            readme_file = Path(output_path) / "README.md"
            with open(readme_file, 'w', encoding='utf-8') as f:
                f.write(f"""# {detector_name} Detector

## Description
{detector_name} detector for continuity monitoring.

## Configuration
- **sensitivity**: Detection sensitivity (0.1 - 1.0)
- **enable_logging**: Enable detailed logging
- **detection_threshold**: Minimum confidence for reporting (0.0 - 1.0)

## Implementation
1. Modify the detection logic in `process_frame_pair` method
2. Update configuration schema in both `detector.json` and the Python code
3. Add any dependencies to requirements.txt

## Queue-Based Processing
This detector uses a queue-based processing model:
- Frame pairs are pushed to the detector's queue
- A background thread processes frame pairs independently
- Results are collected asynchronously

## Development
1. Edit `detector.py` to implement your detection logic
2. The main processing happens in `process_frame_pair()` method
3. Use `initialize()` for one-time setup (loading models, etc.)
4. Use `cleanup()` to release resources

## Testing
```bash
python -m CAMF.detector_framework validate .
python -m CAMF.detector_framework test . --frame path/to/test/image.jpg
```

## Performance Monitoring
- Monitor `get_queue_size()` to track backlog
- Use `get_processed_count()` to track progress
- Configure detection_threshold to balance accuracy vs performance
""")
            
            print(f"Queue-based template generated at: {output_path}")
            return True
            
        except Exception as e:
            print(f"Failed to generate template: {e}")
            return False
# CAMF/services/detector_framework/deduplication.py

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from dataclasses import dataclass
from typing import List, Optional

from CAMF.common.models import DetectorResult


@dataclass
class BoundingBox:
    x: int
    y: int
    width: int
    height: int
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            x=data.get('x', 0),
            y=data.get('y', 0),
            width=data.get('width', 0),
            height=data.get('height', 0)
        )
    
    def to_dict(self):
        return {
            'x': self.x,
            'y': self.y,
            'width': self.width,
            'height': self.height
        }
    
    def center(self) -> Tuple[float, float]:
        """Get center point of bounding box."""
        return (self.x + self.width / 2, self.y + self.height / 2)
    
    def iou(self, other: 'BoundingBox') -> float:
        """Calculate Intersection over Union."""
        # Calculate intersection
        x_left = max(self.x, other.x)
        y_top = max(self.y, other.y)
        x_right = min(self.x + self.width, other.x + other.width)
        y_bottom = min(self.y + self.height, other.y + other.height)
        
        if x_right < x_left or y_bottom < y_top:
            return 0.0
        
        intersection_area = (x_right - x_left) * (y_bottom - y_top)
        
        # Calculate union
        self_area = self.width * self.height
        other_area = other.width * other.height
        union_area = self_area + other_area - intersection_area
        
        return intersection_area / union_area if union_area > 0 else 0.0

class ErrorDeduplicationService:
    """Service for detecting and grouping continuous errors."""
    
    def __init__(self, storage_service):
        self.storage = storage_service
        self.active_errors: Dict[int, List[dict]] = {}  # take_id -> list of active errors
        
        # Thresholds for similarity detection
        self.IOU_THRESHOLD = 0.5  # 50% overlap
        self.POSITION_THRESHOLD = 100  # pixels
        self.DESCRIPTION_SIMILARITY_THRESHOLD = 0.8
    
    def process_detector_result(self, result: 'DetectorResult', take_id: int, 
                              timestamp: float) -> Optional[int]:
        """
        Process a detector result and determine if it's part of a continuous error.
        
        Returns:
            continuous_error_id if created or updated, None otherwise
        """
        if result.confidence <= 0.0:  # No error or detector failure
            return None
        
        # Get active errors for this take
        if take_id not in self.active_errors:
            self._load_active_errors(take_id)
        
        # Check if this is a continuation of an existing error
        continuous_error = self._find_matching_error(result, take_id)
        
        if continuous_error:
            # Update existing error
            self._update_continuous_error(continuous_error, result, timestamp)
            return continuous_error['id']
        else:
            # Create new continuous error
            continuous_error_id = self._create_continuous_error(result, take_id, timestamp)
            return continuous_error_id
    
    def _find_matching_error(self, result: 'DetectorResult', take_id: int) -> Optional[dict]:
        """Find if this result matches any active continuous error."""
        active_errors = self.active_errors.get(take_id, [])
        
        for error in active_errors:
            # Check if same detector
            if error['detector_name'] != result.detector_name:
                continue
            
            # Check if consecutive frame
            if result.frame_id != error['last_frame_id'] + 1:
                continue
            
            # Check spatial similarity
            if self._check_spatial_similarity(error, result):
                return error
            
            # Check if detector provided error signature matches
            if (hasattr(result, 'error_signature') and 
                error.get('error_signature') == result.error_signature):
                return error
        
        return None
    
    def _check_spatial_similarity(self, error: dict, result: 'DetectorResult') -> bool:
        """Check if error and result are spatially similar."""
        # If no bounding boxes, check description similarity
        if not result.bounding_boxes or not error.get('spatial_info'):
            return self._check_description_similarity(error['description'], result.description)
        
        # Compare bounding boxes
        error_boxes = [BoundingBox.from_dict(box) for box in error['spatial_info'].get('boxes', [])]
        result_boxes = [BoundingBox.from_dict(box) for box in result.bounding_boxes]
        
        # Check if any boxes have sufficient overlap
        for e_box in error_boxes:
            for r_box in result_boxes:
                iou = e_box.iou(r_box)
                if iou > self.IOU_THRESHOLD:
                    return True
                
                # Also check relative position (for camera movement)
                e_center = e_box.center()
                r_center = r_box.center()
                distance = np.sqrt((e_center[0] - r_center[0])**2 + 
                                 (e_center[1] - r_center[1])**2)
                
                if distance < self.POSITION_THRESHOLD:
                    return True
        
        return False
    
    def _check_description_similarity(self, desc1: str, desc2: str) -> bool:
        """Simple description similarity check."""
        # For now, exact match. Could implement fuzzy matching later
        return desc1.lower().strip() == desc2.lower().strip()
    
    def _create_continuous_error(self, result: 'DetectorResult', take_id: int, 
                           timestamp: float) -> int:
        """Create a new continuous error."""
        # Store spatial info for future comparisons
        spatial_info = {
            'boxes': result.bounding_boxes,
            'frame_size': getattr(result, 'frame_size', None)  # If detector provides
        }
        
        # Create continuous error in database
        continuous_error_id = self.storage.create_continuous_error(
            take_id=take_id,
            detector_name=result.detector_name,
            first_frame_id=result.frame_id,
            last_frame_id=result.frame_id,
            description=result.description,
            confidence=result.confidence.value,  # Convert enum to integer value
            error_signature=getattr(result, 'error_signature', None),
            spatial_info=spatial_info
        )
        
        # Add first occurrence
        self.storage.add_error_occurrence(
            continuous_error_id=continuous_error_id,
            frame_id=result.frame_id,
            confidence=result.confidence.value,  # Convert enum to integer value
            bounding_boxes=result.bounding_boxes,
            timestamp=timestamp
        )
        
        # Add to active errors cache
        if take_id not in self.active_errors:
            self.active_errors[take_id] = []
        
        self.active_errors[take_id].append({
            'id': continuous_error_id,
            'detector_name': result.detector_name,
            'last_frame_id': result.frame_id,
            'description': result.description,
            'spatial_info': spatial_info,
            'error_signature': getattr(result, 'error_signature', None)
        })
        
        return continuous_error_id
    
    def _update_continuous_error(self, error: dict, result: 'DetectorResult', 
                           timestamp: float):
        """Update existing continuous error with new occurrence."""
        # Update last frame
        error['last_frame_id'] = result.frame_id
        
        # Update spatial info with latest position
        error['spatial_info'] = {
            'boxes': result.bounding_boxes,
            'frame_size': getattr(result, 'frame_size', None)
        }
        
        # Update in database
        self.storage.update_continuous_error_last_frame(
            continuous_error_id=error['id'],
            last_frame_id=result.frame_id,
            spatial_info=error['spatial_info']
        )
        
        # Add occurrence
        self.storage.add_error_occurrence(
            continuous_error_id=error['id'],
            frame_id=result.frame_id,
            confidence=result.confidence.value,  # Convert enum to integer value
            bounding_boxes=result.bounding_boxes,
            timestamp=timestamp
        )
    
    def _load_active_errors(self, take_id: int):
        """Load active errors for a take from database."""
        active_errors = self.storage.get_active_continuous_errors(take_id)
        self.active_errors[take_id] = [
            {
                'id': error.id,
                'detector_name': error.detector_name,
                'last_frame_id': error.last_frame_id,
                'description': error.description,
                'spatial_info': error.spatial_info,
                'error_signature': error.error_signature
            }
            for error in active_errors
        ]
    
    def mark_inactive_errors(self, take_id: int, current_frame_id: int):
        """Mark errors as inactive if they haven't appeared in recent frames."""
        if take_id not in self.active_errors:
            return
        
        # Threshold: if error hasn't appeared in last 5 frames, mark as inactive
        INACTIVE_THRESHOLD = 5
        
        inactive_errors = []
        for error in self.active_errors[take_id]:
            if current_frame_id - error['last_frame_id'] > INACTIVE_THRESHOLD:
                self.storage.mark_continuous_error_inactive(error['id'])
                inactive_errors.append(error)
        
        # Remove from active cache
        for error in inactive_errors:
            self.active_errors[take_id].remove(error)



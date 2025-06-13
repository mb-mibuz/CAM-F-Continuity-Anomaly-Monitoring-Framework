"""
Detector result grouping for continuous error detection.
Groups detector results into continuous errors based on spatial and temporal proximity.
"""
import uuid
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class DetectorResultGrouping:
    """Groups detector results into continuous errors."""
    
    # Thresholds for grouping
    IOU_THRESHOLD = 0.5  # 50% bounding box overlap
    POSITION_THRESHOLD = 100  # pixels distance
    FRAME_GAP_THRESHOLD = 5  # max frames between occurrences
    
    @staticmethod
    def calculate_iou(box1: Dict[str, float], box2: Dict[str, float]) -> float:
        """Calculate Intersection over Union for two bounding boxes."""
        if not (box1 and box2):
            return 0.0
            
        # Extract coordinates
        x1_min, y1_min = box1.get('x', 0), box1.get('y', 0)
        x1_max = x1_min + box1.get('width', 0)
        y1_max = y1_min + box1.get('height', 0)
        
        x2_min, y2_min = box2.get('x', 0), box2.get('y', 0)
        x2_max = x2_min + box2.get('width', 0)
        y2_max = y2_min + box2.get('height', 0)
        
        # Calculate intersection
        intersect_xmin = max(x1_min, x2_min)
        intersect_ymin = max(y1_min, y2_min)
        intersect_xmax = min(x1_max, x2_max)
        intersect_ymax = min(y1_max, y2_max)
        
        if intersect_xmax < intersect_xmin or intersect_ymax < intersect_ymin:
            return 0.0
            
        intersect_area = (intersect_xmax - intersect_xmin) * (intersect_ymax - intersect_ymin)
        
        # Calculate union
        area1 = (x1_max - x1_min) * (y1_max - y1_min)
        area2 = (x2_max - x2_min) * (y2_max - y2_min)
        union_area = area1 + area2 - intersect_area
        
        return intersect_area / union_area if union_area > 0 else 0.0
    
    @staticmethod
    def calculate_position_distance(box1: Dict[str, float], box2: Dict[str, float]) -> float:
        """Calculate distance between bounding box centers."""
        if not (box1 and box2):
            return float('inf')
            
        # Calculate centers
        center1_x = box1.get('x', 0) + box1.get('width', 0) / 2
        center1_y = box1.get('y', 0) + box1.get('height', 0) / 2
        center2_x = box2.get('x', 0) + box2.get('width', 0) / 2
        center2_y = box2.get('y', 0) + box2.get('height', 0) / 2
        
        # Euclidean distance
        return ((center2_x - center1_x) ** 2 + (center2_y - center1_y) ** 2) ** 0.5
    
    @classmethod
    def group_detector_results(cls, results: List[Dict[str, Any]], 
                             use_spatial: bool = True) -> List[Dict[str, Any]]:
        """
        Group detector results into continuous errors.
        
        Args:
            results: List of detector results sorted by frame_id
            use_spatial: Whether to use spatial grouping (True) or just text (False)
            
        Returns:
            List of grouped results with error_group_id assigned
        """
        if not results:
            return []
            
        # Sort by detector and frame
        sorted_results = sorted(results, key=lambda x: (x['detector_name'], x['frame_id']))
        
        # Track active groups
        active_groups = {}  # group_id -> last_result
        grouped_results = []
        
        for result in sorted_results:
            detector = result['detector_name']
            frame_id = result['frame_id']
            
            # Find matching group
            matched_group_id = None
            
            for group_id, last_result in active_groups.items():
                # Must be same detector
                if last_result['detector_name'] != detector:
                    continue
                    
                # Check frame gap
                frame_gap = frame_id - last_result['frame_id']
                if frame_gap > cls.FRAME_GAP_THRESHOLD:
                    continue
                    
                # Check if error matches
                if cls._errors_match(result, last_result, use_spatial):
                    matched_group_id = group_id
                    break
            
            # Assign group
            if matched_group_id:
                result['error_group_id'] = matched_group_id
                result['is_continuous_start'] = False
                result['is_continuous_end'] = False  # Will update later
                active_groups[matched_group_id] = result
            else:
                # Create new group
                new_group_id = str(uuid.uuid4())
                result['error_group_id'] = new_group_id
                result['is_continuous_start'] = True
                result['is_continuous_end'] = False
                active_groups[new_group_id] = result
            
            grouped_results.append(result)
        
        # Mark end of continuous errors
        cls._mark_continuous_ends(grouped_results)
        
        return grouped_results
    
    @classmethod
    def _errors_match(cls, result1: Dict[str, Any], result2: Dict[str, Any],
                     use_spatial: bool) -> bool:
        """Check if two errors match for grouping."""
        # Always check description
        if result1.get('description') != result2.get('description'):
            return False
            
        if not use_spatial:
            return True
            
        # Check spatial similarity
        boxes1 = result1.get('bounding_boxes', [])
        boxes2 = result2.get('bounding_boxes', [])
        
        if not boxes1 or not boxes2:
            # No spatial data, match by description only
            return True
            
        # Check if any boxes match
        for box1 in boxes1:
            for box2 in boxes2:
                # Check IoU
                if cls.calculate_iou(box1, box2) >= cls.IOU_THRESHOLD:
                    return True
                    
                # Check position distance
                if cls.calculate_position_distance(box1, box2) <= cls.POSITION_THRESHOLD:
                    return True
                    
        return False
    
    @classmethod
    def _mark_continuous_ends(cls, grouped_results: List[Dict[str, Any]]):
        """Mark the end of each continuous error group."""
        if not grouped_results:
            return
            
        # Track last occurrence of each group
        last_in_group = {}
        
        for result in grouped_results:
            group_id = result.get('error_group_id')
            if group_id:
                last_in_group[group_id] = result
        
        # Mark ends
        for result in last_in_group.values():
            result['is_continuous_end'] = True
    
    @classmethod
    def get_continuous_error_summary(cls, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Get summary of continuous errors from grouped results.
        
        Returns:
            List of continuous error summaries with:
            - error_group_id
            - detector_name
            - description
            - first_frame_id
            - last_frame_id
            - frame_count
            - instances (list of individual results)
            - average_confidence
        """
        if not results:
            return []
            
        # Group by error_group_id
        groups = {}
        
        for result in results:
            group_id = result.get('error_group_id')
            if not group_id:
                # Ungrouped result, create single-instance group
                group_id = str(uuid.uuid4())
                result['error_group_id'] = group_id
                result['is_continuous_start'] = True
                result['is_continuous_end'] = True
                
            if group_id not in groups:
                groups[group_id] = {
                    'error_group_id': group_id,
                    'detector_name': result['detector_name'],
                    'description': result.get('description', ''),
                    'first_frame_id': result['frame_id'],
                    'last_frame_id': result['frame_id'],
                    'instances': [],
                    'confidence_sum': 0,
                    'is_false_positive': result.get('is_false_positive', False)
                }
                
            group = groups[group_id]
            group['instances'].append(result)
            group['first_frame_id'] = min(group['first_frame_id'], result['frame_id'])
            group['last_frame_id'] = max(group['last_frame_id'], result['frame_id'])
            group['confidence_sum'] += result.get('confidence', 0)
            # Update false positive status - if any instance is not false positive, the group isn't
            if not result.get('is_false_positive', False):
                group['is_false_positive'] = False
        
        # Convert to list and calculate averages
        summaries = []
        for group in groups.values():
            instance_count = len(group['instances'])
            group['frame_count'] = instance_count
            group['average_confidence'] = group['confidence_sum'] / instance_count if instance_count > 0 else 0
            del group['confidence_sum']  # Remove temporary field
            
            # Check if all instances are false positives
            all_false_positive = all(inst.get('is_false_positive', False) for inst in group['instances'])
            group['is_false_positive'] = all_false_positive
            
            # Add frame range string
            if group['first_frame_id'] == group['last_frame_id']:
                group['frame_range'] = str(group['first_frame_id'])
            else:
                group['frame_range'] = f"{group['first_frame_id']}-{group['last_frame_id']}"
                
            summaries.append(group)
        
        # Sort by first frame
        return sorted(summaries, key=lambda x: x['first_frame_id'])
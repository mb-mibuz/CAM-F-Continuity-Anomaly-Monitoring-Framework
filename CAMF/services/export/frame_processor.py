# CAMF/services/export/frame_processor.py
"""
Frame processor for adding bounding boxes and annotations to frames.
"""

import cv2
import numpy as np
from typing import List, Dict, Any, Tuple
import colorsys

from CAMF.common.models import DetectorResult


class FrameProcessor:
    """Processes frames for export - adds bounding boxes and annotations."""
    
    def __init__(self):
        # Predefined colors for different detectors/errors
        self.color_palette = self._generate_color_palette(20)
        self.detector_colors = {}
        self.next_color_index = 0
    
    def draw_bounding_boxes(self, frame: np.ndarray, errors: List[DetectorResult]) -> np.ndarray:
        """Draw bounding boxes on frame for all errors."""
        # Make a copy to avoid modifying original
        if frame is None:
            return None
            
        annotated_frame = frame.copy()
        
        # Group errors by detector to assign consistent colors
        for error in errors:
            color = self._get_color_for_detector(error.detector_name)
            
            # Draw each bounding box for this error
            for box in error.bounding_boxes:
                self._draw_single_box(annotated_frame, box, color, error.description)
        
        return annotated_frame
    
    def _draw_single_box(self, frame: np.ndarray, box: Dict[str, Any], 
                        color: Tuple[int, int, int], label: str):
        """Draw a single bounding box with label."""
        x = box.get('x', 0)
        y = box.get('y', 0)
        width = box.get('width', 0)
        height = box.get('height', 0)
        
        # Draw rectangle
        cv2.rectangle(frame, (x, y), (x + width, y + height), color, 2)
        
        # Add label background
        label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        label_y = y - 10 if y - 10 > 10 else y + height + 20
        
        cv2.rectangle(frame, 
                     (x, label_y - label_size[1] - 4),
                     (x + label_size[0] + 4, label_y + 4),
                     color, -1)
        
        # Add label text
        cv2.putText(frame, label, (x + 2, label_y), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    
    def _get_color_for_detector(self, detector_name: str) -> Tuple[int, int, int]:
        """Get consistent color for a detector."""
        if detector_name not in self.detector_colors:
            self.detector_colors[detector_name] = self.color_palette[self.next_color_index]
            self.next_color_index = (self.next_color_index + 1) % len(self.color_palette)
        
        return self.detector_colors[detector_name]
    
    def _generate_color_palette(self, n_colors: int) -> List[Tuple[int, int, int]]:
        """Generate visually distinct colors."""
        colors = []
        for i in range(n_colors):
            hue = i / n_colors
            # Use high saturation and value for vibrant colors
            rgb = colorsys.hsv_to_rgb(hue, 0.8, 0.9)
            # Convert to BGR for OpenCV and scale to 0-255
            bgr = (int(rgb[2] * 255), int(rgb[1] * 255), int(rgb[0] * 255))
            colors.append(bgr)
        
        return colors
    
    def get_error_color_map(self, errors: List[DetectorResult]) -> Dict[str, Tuple[int, int, int]]:
        """Get color mapping for all errors (for text coloring in PDF)."""
        color_map = {}
        for error in errors:
            if error.detector_name not in color_map:
                color_map[error.detector_name] = self._get_color_for_detector(error.detector_name)
        return color_map
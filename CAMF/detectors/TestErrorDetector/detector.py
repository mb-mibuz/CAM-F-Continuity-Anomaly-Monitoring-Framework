"""
Test Error Detector - Generates errors for testing deduplication and processing progress
"""
import os
import sys
import time
import json
import random
from pathlib import Path
from typing import Dict, Any, List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from CAMF.common.models import BaseDetector, DetectorResult, DetectorInfo, DetectorConfigurationSchema, ConfigurationField

class TestErrorDetector(BaseDetector):
    """Test detector that generates errors on every frame"""
    
    def __init__(self):
        super().__init__()
        self.frame_count = 0
        self.processing_delay = 0.1  # 100ms delay to simulate processing
        
    def get_info(self) -> DetectorInfo:
        """Return detector information."""
        return DetectorInfo(
            name="TestErrorDetector",
            description="Generates test errors for UI testing and development",
            version="1.0.0",
            author="CAMF Team",
            category="testing",
            requires_reference=False,
            min_frames_required=1
        )
    
    def get_configuration_schema(self) -> DetectorConfigurationSchema:
        """Return configuration schema for UI generation."""
        return DetectorConfigurationSchema(
            fields={
                "processing_delay": ConfigurationField(
                    field_type="number",
                    title="Processing Delay",
                    description="Simulated processing delay in seconds",
                    required=False,
                    default=0.1,
                    minimum=0.0,
                    maximum=5.0
                ),
                "error_frequency": ConfigurationField(
                    field_type="number",
                    title="Error Frequency",
                    description="How often to generate errors (1=every frame, 2=every other frame, etc)",
                    required=False,
                    default=1,
                    minimum=1,
                    maximum=10
                )
            }
        )
    
    def initialize(self, config: Dict[str, Any], frame_provider) -> bool:
        """Initialize detector with configuration and frame provider."""
        self.config = config
        self.frame_provider = frame_provider
        self.processing_delay = config.get("processing_delay", 0.1)
        self.is_initialized = True
        return True
    
    def process_frame(self, frame_id: int, take_id: int) -> List[DetectorResult]:
        """Process a frame and return detection results (BaseDetector interface)."""
        # This is the method signature required by BaseDetector
        # For testing, we'll just create a dummy frame path
        frame_path = f"frame_{frame_id}.jpg"
        results = self.process_single_frame(frame_path, frame_id)
        return results if results else []
        
    def process_single_frame(self, frame_path: str, frame_index: int) -> List[DetectorResult]:
        """Process a single frame and generate test errors for grouping testing"""
        self.frame_count += 1
        
        # Simulate processing time
        time.sleep(self.processing_delay)
        
        # We'll generate multiple types of errors to test grouping:
        # 1. Continuous errors that should be grouped (same description, similar location)
        # 2. Unique errors that should NOT be grouped
        # 3. Errors that appear, disappear, then reappear (to test group boundaries)
        
        results = []
        
        # Type 1: Continuous error that persists across frames (should be grouped)
        # This appears on frames 0-10, 15-25, 30-40, etc.
        if (frame_index % 50 < 10) or (15 <= frame_index % 50 < 25) or (30 <= frame_index % 50 < 40):
            results.append(DetectorResult(
                confidence=0.92,
                description="Red prop missing from table",  # Same description = should group
                frame_id=frame_index,
                bounding_boxes=[{
                    "x": 200,
                    "y": 150,
                    "width": 100,
                    "height": 80,
                    "label": "Missing: Red Prop",
                    "confidence": 0.92
                }],
                detector_name="TestErrorDetector",
                metadata={
                    "error_type": "object_missing",
                    "severity": "high",
                    "frame_index": frame_index
                },
                error_type="object_missing"
            ))
        
        # Type 2: Another continuous error with slightly different position
        # This tests spatial grouping - appears frames 5-15, 20-30, etc.
        if (5 <= frame_index % 40 < 15) or (20 <= frame_index % 40 < 30):
            # Slightly varying position to test spatial proximity grouping
            x_offset = (frame_index % 3) * 5  # Small variation
            results.append(DetectorResult(
                confidence=0.88,
                description="Actor's watch position changed",  # Same description = should group
                frame_id=frame_index,
                bounding_boxes=[{
                    "x": 400 + x_offset,
                    "y": 250,
                    "width": 50,
                    "height": 50,
                    "label": "Watch Position Error",
                    "confidence": 0.88
                }],
                detector_name="TestErrorDetector",
                metadata={
                    "error_type": "continuity_error",
                    "severity": "medium",
                    "frame_index": frame_index
                },
                error_type="continuity_error"
            ))
        
        # Type 3: Unique errors that should NOT be grouped (different descriptions)
        # These appear sporadically
        if frame_index % 7 == 0:
            unique_id = frame_index // 7
            results.append(DetectorResult(
                confidence=0.75,
                description=f"Lighting inconsistency #{unique_id} detected",  # Unique description
                frame_id=frame_index,
                bounding_boxes=[{
                    "x": 100 + (unique_id * 20) % 300,
                    "y": 300,
                    "width": 80,
                    "height": 60,
                    "label": f"Light Issue #{unique_id}",
                    "confidence": 0.75
                }],
                detector_name="TestErrorDetector",
                metadata={
                    "error_type": "lighting_change",
                    "severity": "low",
                    "frame_index": frame_index
                },
                error_type="lighting_change"
            ))
        
        # Type 4: Moving error (same description but different locations - should NOT group)
        if frame_index % 4 == 0:
            x_pos = 50 + (frame_index * 50) % 500  # Significantly different positions
            results.append(DetectorResult(
                confidence=0.85,
                description="Coffee cup position error",  # Same description
                frame_id=frame_index,
                bounding_boxes=[{
                    "x": x_pos,
                    "y": 100,
                    "width": 40,
                    "height": 60,
                    "label": "Coffee Cup",
                    "confidence": 0.85
                }],
                detector_name="TestErrorDetector",
                metadata={
                    "error_type": "object_position",
                    "severity": "medium",
                    "frame_index": frame_index
                },
                error_type="object_position"
            ))
        
        # Type 5: Intermittent error that appears/disappears rapidly (tests temporal grouping)
        # Appears on frames: 0,1,2, then 8,9,10, then 16,17,18, etc.
        if (frame_index % 8) < 3:
            results.append(DetectorResult(
                confidence=0.94,
                description="Shirt color inconsistency",  # Same description
                frame_id=frame_index,
                bounding_boxes=[{
                    "x": 350,
                    "y": 200,
                    "width": 120,
                    "height": 150,
                    "label": "Color Mismatch",
                    "confidence": 0.94
                }],
                detector_name="TestErrorDetector",
                metadata={
                    "error_type": "color_mismatch",
                    "severity": "high",
                    "frame_index": frame_index
                },
                error_type="color_mismatch"
            ))
        
        # If no errors were generated, return empty list
        if not results:
            # Optionally return a "no errors" result
            results.append(DetectorResult(
                confidence=0.0,
                description="No errors detected",
                frame_id=frame_index,
                bounding_boxes=[],
                detector_name="TestErrorDetector",
                metadata={
                    "processing_time_ms": self.processing_delay * 1000,
                    "frame_count": self.frame_count,
                    "test_mode": True
                },
                error_type=None
            ))
        
        return results
    
    def process_frame_pair(self, current_frame_path: str, reference_frame_path: str, 
                          current_frame_index: int, reference_frame_index: int) -> List[DetectorResult]:
        """Process frame pair for comparison"""
        # For testing, we'll process the current frame and add comparison info
        results = self.process_single_frame(current_frame_path, current_frame_index)
        
        # Add comparison-specific errors
        if current_frame_index != reference_frame_index:
            results.append(DetectorResult(
                confidence=0.65,
                description=f"Frame comparison mismatch: current={current_frame_index}, reference={reference_frame_index}",
                frame_id=current_frame_index,
                bounding_boxes=[],
                detector_name="TestErrorDetector",
                metadata={
                    "error_type": "frame_mismatch",
                    "severity": "low",
                    "frame_index": current_frame_index,
                    "reference_frame": reference_frame_index,
                    "difference_score": random.random()
                },
                error_type="frame_mismatch"
            ))
        
        return results
    
    def get_capabilities(self) -> dict:
        """Return detector capabilities"""
        return {
            "name": "Test Error Detector",
            "version": "1.0.0",
            "description": "Generates test errors for UI testing",
            "supports_frame_pairs": True,
            "supports_batch": False,
            "error_types": [
                "continuity_error",
                "object_missing", 
                "scene_change",
                "frame_mismatch"
            ],
            "processing_time_estimate_ms": 500
        }

def main():
    """Main entry point for detector"""
    # When run directly, just create the detector instance
    # The detector framework will handle the actual execution
    detector = TestErrorDetector()
    print(f"TestErrorDetector initialized: {detector.get_info().name} v{detector.get_info().version}")

if __name__ == "__main__":
    main()
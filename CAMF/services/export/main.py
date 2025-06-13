# CAMF/services/export/main.py
"""
Export Service - Handles PDF report generation for takes, scenes, and projects.
"""

from typing import List, Dict, Any, Optional

from CAMF.services.storage import get_storage_service
from CAMF.services.detector_framework import get_detector_framework_service
from CAMF.common.models import Take

from .pdf_generator import PDFReportGenerator
from .frame_processor import FrameProcessor
from .note_parser import NoteParser


class ExportService:
    """Main service for exporting reports."""
    
    def __init__(self):
        self.storage = get_storage_service()
        self.detector_framework = get_detector_framework_service()
        self.pdf_generator = PDFReportGenerator()
        self.frame_processor = FrameProcessor()
        self.note_parser = NoteParser()
        
        # Connect frame processor to PDF generator for color consistency
        self.pdf_generator.frame_processor = self.frame_processor
        
    def export_take_report(self, take_id: int, output_path: str) -> Optional[str]:
        """Export a single take report as PDF."""
        try:
            # Validate inputs
            if not take_id or take_id < 0:
                print(f"Invalid take_id: {take_id}")
                return None
            
            if not output_path:
                print("Output path is required")
                return None
            
            # Get take data
            take = self.storage.get_take(take_id)
            if not take:
                print(f"Take with id {take_id} not found")
                return None
                
            # Get angle, scene, and project for context
            angle = self.storage.get_angle(take.angle_id)
            if not angle:
                print(f"Angle with id {take.angle_id} not found")
                return None
                
            scene = self.storage.get_scene(angle.scene_id)
            if not scene:
                print(f"Scene with id {angle.scene_id} not found")
                return None
                
            project = self.storage.get_project(scene.project_id)
            if not project:
                print(f"Project with id {scene.project_id} not found")
                return None
            
            # Get frame rate for timecode calculation
            fps = scene.frame_rate
            
            # Prepare report data
            report_data = {
                'type': 'take',
                'project_name': project.name,
                'scene_name': scene.name,
                'angle_name': angle.name,
                'take_name': take.name,
                'is_reference': take.is_reference,
                'fps': fps
            }
            
            # Process notes section
            print(f"Processing notes section...")
            notes_section = self._process_take_notes(take, fps)
            print(f"Notes section processed: {len(notes_section.get('segments', []))} segments")
            
            # Get all error frames
            print(f"Getting error frames...")
            error_frames = self._get_error_frames_for_take(take_id, fps)
            print(f"Found {len(error_frames)} error frames")
            
            # Generate PDF
            print(f"Generating PDF...")
            self.pdf_generator.generate_take_report(
                report_data,
                notes_section,
                error_frames,
                output_path
            )
            print(f"PDF generated successfully at: {output_path}")
            
            return output_path
            
        except Exception as e:
            print(f"Failed to export take report: {e}")
            import traceback
            traceback.print_exc()  # This will show us the exact line causing the error
            return None
    
    def export_scene_report(self, scene_id: int, output_path: str) -> Optional[str]:
        """Export a complete scene report (all takes) as PDF."""
        try:
            # Validate inputs
            if not scene_id or scene_id < 0:
                print(f"Invalid scene_id: {scene_id}")
                return None
            
            if not output_path:
                print("Output path is required")
                return None
            
            scene = self.storage.get_scene(scene_id)
            if not scene:
                print(f"Scene with id {scene_id} not found")
                return None
                
            project = self.storage.get_project(scene.project_id)
            
            # Get all angles and takes
            angles = self.storage.get_angles_for_scene(scene_id)
            
            report_data = {
                'type': 'scene',
                'project_name': project.name,
                'scene_name': scene.name,
                'fps': scene.frame_rate
            }
            
            # Collect all takes organized by angle
            takes_by_angle = []
            for angle in angles:
                takes = self.storage.get_takes_for_angle(angle.id)
                if takes:
                    angle_data = {
                        'angle_name': angle.name,
                        'takes': []
                    }
                    
                    for take in takes:
                        take_data = {
                            'take_name': take.name,
                            'is_reference': take.is_reference,
                            'notes_section': self._process_take_notes(take, scene.frame_rate),
                            'error_frames': self._get_error_frames_for_take(take.id, scene.frame_rate)
                        }
                        angle_data['takes'].append(take_data)
                    
                    takes_by_angle.append(angle_data)
            
            # Generate comprehensive scene PDF
            self.pdf_generator.generate_scene_report(
                report_data,
                takes_by_angle,
                output_path
            )
            
            return output_path
            
        except Exception as e:
            print(f"Failed to export scene report: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def export_project_report(self, project_id: int, output_path: str) -> Optional[str]:
        """Export complete project report (all scenes) as PDF."""
        try:
            # Validate inputs
            if not project_id or project_id < 0:
                print(f"Invalid project_id: {project_id}")
                return None
            
            if not output_path:
                print("Output path is required")
                return None
            
            project = self.storage.get_project(project_id)
            if not project:
                print(f"Project with id {project_id} not found")
                return None
            
            report_data = {
                'type': 'project',
                'project_name': project.name
            }
            
            # Collect all scenes
            scenes = self.storage.get_scenes_for_project(project_id)
            scenes_data = []
            
            for scene in scenes:
                scene_data = {
                    'scene_name': scene.name,
                    'fps': scene.frame_rate,
                    'angles': []
                }
                
                # Get all angles and takes for this scene
                angles = self.storage.get_angles_for_scene(scene.id)
                
                for angle in angles:
                    takes = self.storage.get_takes_for_angle(angle.id)
                    if takes:
                        angle_data = {
                            'angle_name': angle.name,
                            'takes': []
                        }
                        
                        for take in takes:
                            take_data = {
                                'take_name': take.name,
                                'is_reference': take.is_reference,
                                'notes_section': self._process_take_notes(take, scene.frame_rate),
                                'error_frames': self._get_error_frames_for_take(take.id, scene.frame_rate)
                            }
                            angle_data['takes'].append(take_data)
                        
                        scene_data['angles'].append(angle_data)
                
                scenes_data.append(scene_data)
            
            # Generate comprehensive project PDF
            self.pdf_generator.generate_project_report(
                report_data,
                scenes_data,
                output_path
            )
            
            return output_path
            
        except Exception as e:
            print(f"Failed to export project report: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _process_take_notes(self, take: Take, fps: float) -> Dict[str, Any]:
        """Process take notes and parse frame references."""
        try:
            print(f"Processing notes for take {take.id}, notes content: {take.notes}")
            
            # Use the storage service's note parser
            parsed_note = self.storage.parse_take_notes(take.id)
            
            print(f"Parsed note result: {parsed_note}")
            
            if not parsed_note:
                # Return empty parsed note if take not found
                print("Parsed note is None, returning default")
                return {
                    'segments': [{'type': 'text', 'content': take.notes or ''}],
                    'original_notes': take.notes
                }
        except Exception as e:
            print(f"Error parsing notes for take {take.id}: {e}")
            import traceback
            traceback.print_exc()
            # Return empty parsed note on error
            return {
                'segments': [{'type': 'text', 'content': take.notes or ''}],
                'original_notes': take.notes
            }
        
        # Process each segment
        processed_segments = []
        print(f"ParsedNote type: {type(parsed_note)}")
        print(f"ParsedNote segments: {getattr(parsed_note, 'segments', 'NO SEGMENTS ATTR')}")
        
        for i, segment in enumerate(parsed_note.segments):
            print(f"Processing segment {i}: type={segment['type']}")
            if segment['type'] == 'text':
                processed_segments.append(segment)
            else:  # frame reference
                frame_id = segment['frame_id']
                print(f"Loading frame {frame_id} for notes...")
                
                # Get frame and check for errors
                frame_data = self._get_frame_with_errors(take.id, frame_id, fps)
                if frame_data:
                    segment['frame_data'] = frame_data
                    processed_segments.append(segment)
                    print(f"Frame {frame_id} loaded successfully")
                else:
                    print(f"Failed to load frame {frame_id}")
        
        return {
            'segments': processed_segments,
            'original_notes': take.notes
        }
    
    def _get_frame_with_errors(self, take_id: int, frame_id: int, fps: float) -> Optional[Dict[str, Any]]:
        """Get frame data with error information if present."""
        try:
            # Get frame as numpy array
            frame = self.storage.get_frame_array(take_id, frame_id)
            if frame is None:  # Changed from 'if not frame:' to handle numpy arrays
                print(f"Frame not found: take_id={take_id}, frame_id={frame_id}")
                return None
            
            # Get frame metadata
            frame_metadata = self.storage.get_frame_metadata(take_id, frame_id)
            if not frame_metadata:
                print(f"Frame metadata not found: take_id={take_id}, frame_id={frame_id}")
                return None
        except Exception as e:
            print(f"Error getting frame {frame_id} for take {take_id}: {e}")
            return None
        
        # Calculate timecode
        timecode = self._calculate_timecode(frame_id, fps)
        
        # Get detector results for this frame
        detector_results = self.storage.get_detector_results(take_id, frame_id)
        
        # Filter for actual errors
        # Filter for actual errors (confidence > 0.5 means likely or confirmed error)
        errors = [r for r in detector_results if (isinstance(r.confidence, (int, float)) and r.confidence > 0.5) or (hasattr(r.confidence, 'value') and r.confidence.value in [1, 2])]
        
        # Process frame with bounding boxes if errors exist
        try:
            if errors:
                processed_frame = self.frame_processor.draw_bounding_boxes(frame, errors)
            else:
                processed_frame = frame
        except Exception as e:
            print(f"Error processing frame with bounding boxes: {e}")
            processed_frame = frame
        
        return {
            'frame': processed_frame,
            'frame_id': frame_id,
            'timecode': timecode,
            'errors': errors,
            'has_errors': len(errors) > 0
        }
    
    def _get_error_frames_for_take(self, take_id: int, fps: float) -> List[Dict[str, Any]]:
        """Get all frames with errors for a take, filtering to only show first instance of grouped errors."""
        error_frames = []
        
        try:
            # Get all detector results for the take
            all_results = self.storage.get_detector_results(take_id)
            
            # First, build a map of error groups to count occurrences
            error_group_counts = {}
            error_group_frames = {}
            
            for result in all_results:
                # Check for errors (confidence > 0.5 means likely or confirmed error)
                is_error = (isinstance(result.confidence, (int, float)) and result.confidence > 0.5) or \
                          (hasattr(result.confidence, 'value') and result.confidence.value in [1, 2])
                
                if is_error and hasattr(result, 'error_group_id') and result.error_group_id:
                    group_id = result.error_group_id
                    if group_id not in error_group_counts:
                        error_group_counts[group_id] = 0
                        error_group_frames[group_id] = []
                    error_group_counts[group_id] += 1
                    error_group_frames[group_id].append(result.frame_id)
            
            # Now filter to only include first instance of each error group
            frames_with_errors = {}
            error_metadata = {}  # Store group counts separately
            
            for result in all_results:
                # Check for errors
                is_error = (isinstance(result.confidence, (int, float)) and result.confidence > 0.5) or \
                          (hasattr(result.confidence, 'value') and result.confidence.value in [1, 2])
                
                if not is_error:
                    continue
                    
                # For grouped errors, only include if it's the start of the group
                if hasattr(result, 'error_group_id') and result.error_group_id:
                    if not (hasattr(result, 'is_continuous_start') and result.is_continuous_start):
                        continue  # Skip non-start instances of grouped errors
                
                if result.frame_id not in frames_with_errors:
                    frames_with_errors[result.frame_id] = []
                    error_metadata[result.frame_id] = []
                
                frames_with_errors[result.frame_id].append(result)
                
                # Store metadata about this error
                metadata = {
                    'group_count': error_group_counts.get(result.error_group_id, 1) if hasattr(result, 'error_group_id') and result.error_group_id else 1,
                    'group_frame_range': error_group_frames.get(result.error_group_id, [result.frame_id]) if hasattr(result, 'error_group_id') and result.error_group_id else [result.frame_id]
                }
                error_metadata[result.frame_id].append(metadata)
            
            print(f"Found {len(frames_with_errors)} unique error frames from {len(all_results)} total results")
            
            # Process each error frame
            for frame_id in sorted(frames_with_errors.keys()):
                frame_data = self._get_frame_with_errors(take_id, frame_id, fps)
                if frame_data:
                    # Add group count metadata to frame data
                    frame_data['error_metadata'] = error_metadata.get(frame_id, [])
                    error_frames.append(frame_data)
        except Exception as e:
            print(f"Error getting error frames for take {take_id}: {e}")
            import traceback
            traceback.print_exc()
        
        return error_frames
    
    def _calculate_timecode(self, frame_id: int, fps: float) -> str:
        """Calculate timecode from frame ID and FPS."""
        if fps <= 0:
            fps = 30.0  # Default to 30 fps if invalid
        
        total_seconds = frame_id / fps
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        frames = int((total_seconds % 1) * fps)
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"
    
    def cleanup(self):
        """Cleanup method for service shutdown."""
        # No specific cleanup needed for export service
        # PDF generator doesn't maintain persistent connections


# Singleton instance
_export_service = None

def get_export_service() -> ExportService:
    """Get the export service singleton."""
    global _export_service
    if _export_service is None:
        _export_service = ExportService()
    return _export_service
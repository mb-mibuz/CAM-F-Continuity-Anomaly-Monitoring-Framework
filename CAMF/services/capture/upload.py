# CAMF/services/capture/upload.py
"""
Video upload and processing for pre-recorded footage.
"""

import cv2
from typing import Optional, Callable, Dict, Any
import threading
import time
import numpy as np

class VideoUploadProcessor:
    """Processes uploaded video files frame by frame."""
    
    def __init__(self):
        self.current_video_path: Optional[str] = None
        self.video_capture: Optional[cv2.VideoCapture] = None
        self.total_frames: int = 0
        self.current_frame_index: int = 0
        self.fps: float = 24.0
        self.is_processing: bool = False
        self._processing_thread: Optional[threading.Thread] = None
        self._stop_processing = threading.Event()
        self._frame_callbacks = []
        
    def load_video(self, video_path: str) -> Dict[str, Any]:
        """Load a video file and get its metadata."""
        try:
            # Clean up any existing video
            self.cleanup()
            
            # Open video file
            self.video_capture = cv2.VideoCapture(video_path)
            if not self.video_capture.isOpened():
                return {
                    'success': False,
                    'error': 'Failed to open video file'
                }
            
            # Get video properties
            self.total_frames = int(self.video_capture.get(cv2.CAP_PROP_FRAME_COUNT))
            self.fps = self.video_capture.get(cv2.CAP_PROP_FPS)
            width = int(self.video_capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(self.video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            self.current_video_path = video_path
            self.current_frame_index = 0
            
            return {
                'success': True,
                'metadata': {
                    'total_frames': self.total_frames,
                    'fps': self.fps,
                    'duration': self.total_frames / self.fps if self.fps > 0 else 0,
                    'resolution': {'width': width, 'height': height}
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def start_processing(self, target_fps: Optional[float] = None) -> bool:
        """Start processing the video at the specified frame rate."""
        if not self.video_capture or self.is_processing:
            return False
        
        self.is_processing = True
        self._stop_processing.clear()
        
        # Use target FPS or video's original FPS
        processing_fps = target_fps or self.fps
        
        self._processing_thread = threading.Thread(
            target=self._process_frames,
            args=(processing_fps,)
        )
        self._processing_thread.daemon = True
        self._processing_thread.start()
        
        return True
    
    def stop_processing(self):
        """Stop processing the video."""
        self._stop_processing.set()
        self.is_processing = False
        
        if self._processing_thread:
            self._processing_thread.join(timeout=5.0)
    
    def seek_to_frame(self, frame_index: int) -> bool:
        """Seek to a specific frame in the video."""
        if not self.video_capture:
            return False
        
        frame_index = max(0, min(frame_index, self.total_frames - 1))
        self.video_capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        self.current_frame_index = frame_index
        
        return True
    
    def get_current_frame(self) -> Optional[np.ndarray]:
        """Get the current frame without advancing."""
        if not self.video_capture:
            return None
        
        # Save current position
        current_pos = self.video_capture.get(cv2.CAP_PROP_POS_FRAMES)
        
        # Read frame
        ret, frame = self.video_capture.read()
        
        # Restore position
        self.video_capture.set(cv2.CAP_PROP_POS_FRAMES, current_pos)
        
        return frame if ret else None
    
    def add_frame_callback(self, callback: Callable[[np.ndarray, float], None]):
        """Add a callback for processed frames."""
        self._frame_callbacks.append(callback)
    
    def _process_frames(self, target_fps: float):
        """Process frames at the target frame rate."""
        frame_interval = 1.0 / target_fps if target_fps > 0 else 0.0
        time.time()
        
        while not self._stop_processing.is_set() and self.current_frame_index < self.total_frames:
            frame_start_time = time.time()
            
            # Read next frame
            ret, frame = self.video_capture.read()
            if not ret:
                break
            
            # Calculate relative timestamp
            relative_time = self.current_frame_index / self.fps if self.fps > 0 else 0
            
            # Call callbacks
            for callback in self._frame_callbacks:
                try:
                    callback(frame.copy(), relative_time)
                except Exception as e:
                    print(f"Error in frame callback: {e}")
            
            self.current_frame_index += 1
            
            # Control frame rate
            processing_time = time.time() - frame_start_time
            if processing_time < frame_interval:
                time.sleep(frame_interval - processing_time)
        
        self.is_processing = False
    
    def cleanup(self):
        """Clean up resources."""
        self.stop_processing()
        
        if self.video_capture:
            self.video_capture.release()
            self.video_capture = None
        
        self.current_video_path = None
        self.current_frame_index = 0
        self.total_frames = 0
    
    def get_progress(self) -> Dict[str, Any]:
        """Get current processing progress."""
        return {
            'current_frame': self.current_frame_index,
            'total_frames': self.total_frames,
            'progress_percentage': (self.current_frame_index / self.total_frames * 100) if self.total_frames > 0 else 0,
            'is_processing': self.is_processing
        }
    
    def process_upload(self, take_id: int, video_path: str, storage) -> int:
        """Process an uploaded video file and save frames to storage.
        
        Args:
            take_id: ID of the take to save frames to
            video_path: Path to the uploaded video file
            storage: Storage service instance
            
        Returns:
            Number of frames extracted
        """
        try:
            # Load the video
            result = self.load_video(video_path)
            if not result['success']:
                raise Exception(result.get('error', 'Failed to load video'))
            
            # Get scene settings for frame rate
            take = storage.get_take(take_id)
            if not take:
                raise Exception("Take not found")
                
            angle = storage.get_angle(take.angle_id) if take else None
            scene = storage.get_scene(angle.scene_id) if angle else None
            
            # Determine target frame rate from scene or use 1 fps as default for reference captures
            target_fps = 1.0  # Default to 1 fps for reference captures
            if scene and hasattr(scene, 'frame_rate') and scene.frame_rate:
                target_fps = float(scene.frame_rate)
            
            print(f"Processing video with target FPS: {target_fps}, video FPS: {self.fps}, total frames: {self.total_frames}")
            
            # Calculate frame sampling interval
            # If video is 30fps and we want 1fps, we take every 30th frame
            frame_interval = int(self.fps / target_fps) if self.fps > target_fps else 1
            print(f"Frame interval: {frame_interval} (will extract every {frame_interval}th frame)")
            
            # Process frames at the target frame rate
            frame_count = 0
            video_frame_index = 0
            output_frame_number = 0
            
            while video_frame_index < self.total_frames:
                # Seek to the frame we want
                self.video_capture.set(cv2.CAP_PROP_POS_FRAMES, video_frame_index)
                ret, frame = self.video_capture.read()
                
                if not ret:
                    break
                
                # Save frame to storage with sequential frame numbers
                print(f"[VideoUploadProcessor] Saving frame {output_frame_number} from video frame {video_frame_index}")
                frame_metadata = storage.save_frame(take_id, frame, frame_number=output_frame_number)
                if frame_metadata:
                    frame_count += 1
                    print(f"[VideoUploadProcessor] Frame {output_frame_number} saved successfully, total count: {frame_count}")
                    
                    # Send frame captured event via SSE for real-time updates
                    try:
                        from CAMF.services.api_gateway.sse_handler import send_to_take
                        send_to_take(
                            take_id,
                            {
                                "take_id": take_id,
                                "frame_index": output_frame_number,
                                "frame_count": output_frame_number + 1,  # Total frames so far
                                "timestamp": time.time()
                            },
                            event_type="frame_captured"
                        )
                    except Exception as e:
                        print(f"Error sending frame captured event: {e}")
                else:
                    print(f"[VideoUploadProcessor] Failed to save frame {output_frame_number}")
                    
                # Always increment output frame number to ensure sequential numbering
                output_frame_number += 1
                
                # Move to next frame based on interval
                video_frame_index += frame_interval
                
                # Send progress updates periodically
                progress_percentage = (video_frame_index / self.total_frames) * 100
                if frame_count % 5 == 0 or video_frame_index >= self.total_frames:
                    print(f"Video processing progress: {progress_percentage:.1f}% ({frame_count} frames extracted)")
            
            print(f"[VideoUploadProcessor] Returning frame_count: {frame_count}, output_frame_number: {output_frame_number}")
            return output_frame_number  # Return the actual number of frames saved
            
        except Exception as e:
            print(f"Error processing video upload: {e}")
            raise
        finally:
            self.cleanup()
    
    def get_upload_status(self, take_id: int) -> Optional[Dict[str, Any]]:
        """Get the status of a video upload for a specific take.
        
        This is a placeholder for tracking upload status.
        In a real implementation, this would track active uploads.
        """
        # For now, return None indicating no active upload
        return None
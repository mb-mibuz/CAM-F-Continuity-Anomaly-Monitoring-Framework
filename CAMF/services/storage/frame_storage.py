"""
Direct frame storage system for CAMF.
Stores frames as lossless PNG files within the hierarchical project/scene/angle/take structure.
"""

import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import numpy as np
import cv2
from pathlib import Path
import logging
import threading

logger = logging.getLogger(__name__)


@dataclass
class FrameInfo:
    """Information about a stored frame."""
    frame_id: int
    take_id: int
    filepath: str
    timestamp: float
    metadata: Dict[str, Any]
    created_at: str
    file_size: int = 0


class FrameStorage:
    """Direct frame storage system with hierarchical structure."""
    
    def __init__(self, base_path: str):
        self.base_path = base_path
        # Remove the separate frames directory - we'll use the hierarchical structure
        
        # Frame tracking
        self.frame_info: Dict[int, Dict[int, FrameInfo]] = {}  # take_id -> frame_id -> FrameInfo
        self.write_lock = threading.Lock()
        
        # Storage service reference will be set by storage main
        self._storage_service = None
        
        # Initialize from existing data
        self._load_existing_frames()
        
    def set_storage_service(self, storage_service):
        """Set reference to storage service for accessing hierarchical paths."""
        self._storage_service = storage_service
    
    def _load_existing_frames(self):
        """Load information about existing frames from hierarchical structure."""
        # Skip loading if storage service not set yet
        if not self._storage_service:
            return
            
        # Frames are now loaded on-demand from the hierarchical structure
        # No need to scan at startup
    
    def get_take_directory(self, take_id: int) -> Optional[Path]:
        """Get the directory for a take's frames using hierarchical structure."""
        if not self._storage_service:
            logger.error("Storage service not set - cannot determine take directory")
            return None
            
        # Get take information from storage service
        from . import filesystem_names
        
        take = self._storage_service.get_take(take_id)
        if not take:
            logger.error(f"Take {take_id} not found")
            return None
            
        angle = self._storage_service.get_angle(take.angle_id)
        if not angle:
            logger.error(f"Angle {take.angle_id} not found")
            return None
            
        scene = self._storage_service.get_scene(angle.scene_id)
        if not scene:
            logger.error(f"Scene {angle.scene_id} not found")
            return None
            
        project = self._storage_service.get_project(scene.project_id)
        if not project:
            logger.error(f"Project {scene.project_id} not found")
            return None
            
        # Find the take folder in the hierarchical structure
        project_path = filesystem_names.find_project_folder(project.id)
        if not project_path:
            return None
            
        scene_path = filesystem_names.find_scene_folder(project_path, scene.id)
        if not scene_path:
            return None
            
        angle_path = filesystem_names.find_angle_folder(scene_path, angle.id)
        if not angle_path:
            return None
            
        take_path = filesystem_names.find_take_folder(angle_path, take.id)
        if not take_path:
            return None
            
        # Create frames subdirectory within the take folder
        frames_dir = take_path / "frames"
        return frames_dir
    
    def store_frame(self, take_id: int, frame_id: int, frame: np.ndarray, 
                   timestamp: float, metadata: Dict[str, Any] = None) -> bool:
        """Store a frame with lossless compression."""
        try:
            # Get take directory in hierarchical structure
            take_dir = self.get_take_directory(take_id)
            if not take_dir:
                logger.error(f"Could not determine directory for take {take_id}")
                return False
                
            # Create frames directory if needed
            take_dir.mkdir(parents=True, exist_ok=True)
            
            # Save frame as PNG (lossless)
            frame_filename = f'frame_{frame_id:06d}.png'
            frame_path = take_dir / frame_filename
            
            # Write frame with PNG compression (lossless)
            with self.write_lock:
                # PNG compression level 1 = fast, 9 = best compression
                # Using level 3 for good balance of speed and size
                success = cv2.imwrite(
                    str(frame_path), 
                    frame,
                    [cv2.IMWRITE_PNG_COMPRESSION, 3]
                )
                
                if not success:
                    logger.error(f"Failed to write frame {frame_id}")
                    return False
                
                # Get file size
                file_size = frame_path.stat().st_size
                
                # Create frame info
                frame_info = FrameInfo(
                    frame_id=frame_id,
                    take_id=take_id,
                    filepath=str(frame_path),
                    timestamp=timestamp,
                    metadata=metadata or {},
                    created_at=datetime.now().isoformat(),
                    file_size=file_size
                )
                
                # Update tracking
                if take_id not in self.frame_info:
                    self.frame_info[take_id] = {}
                self.frame_info[take_id][frame_id] = frame_info
                
                # Save frame metadata
                meta_path = frame_path.with_suffix('.json')
                with open(meta_path, 'w') as f:
                    json.dump(asdict(frame_info), f, indent=2)
                
                # Update index periodically
                if frame_id % 10 == 0:
                    self._update_frame_index(take_id)
                
                logger.debug(f"Stored frame {frame_id} for take {take_id} ({file_size / 1024:.1f} KB)")
                return True
                
        except Exception as e:
            logger.error(f"Error storing frame {frame_id} for take {take_id}: {e}")
            return False
    
    def get_frame(self, take_id: int, frame_id: int) -> Optional[np.ndarray]:
        """Retrieve a frame."""
        # Get take directory
        take_dir = self.get_take_directory(take_id)
        if not take_dir:
            logger.error(f"Could not determine directory for take {take_id}")
            return None
            
        # Check if frame exists
        frame_path = take_dir / f'frame_{frame_id:06d}.png'
        if not frame_path.exists():
            logger.error(f"Frame {frame_id} not found for take {take_id} at {frame_path}")
            return None
        
        try:
            # Read frame
            frame = cv2.imread(str(frame_path), cv2.IMREAD_UNCHANGED)
            if frame is None:
                logger.error(f"Failed to read frame from {frame_path}")
                return None
                
            # Ensure BGR format (PNG might have alpha channel)
            if frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                
            return frame
            
        except Exception as e:
            logger.error(f"Error reading frame {frame_id} for take {take_id}: {e}")
            return None
    
    def get_frame_info(self, take_id: int, frame_id: int) -> Optional[FrameInfo]:
        """Get frame information without loading the image."""
        if take_id in self.frame_info and frame_id in self.frame_info[take_id]:
            return self.frame_info[take_id][frame_id]
            
        # Get take directory
        take_dir = self.get_take_directory(take_id)
        if not take_dir:
            return None
            
        # Try to load from metadata file
        meta_path = take_dir / f'frame_{frame_id:06d}.json'
        if meta_path.exists():
            try:
                with open(meta_path, 'r') as f:
                    data = json.load(f)
                    return FrameInfo(**data)
            except Exception as e:
                logger.error(f"Error loading frame metadata: {e}")
                
        return None
    
    def get_take_frames(self, take_id: int) -> List[int]:
        """Get list of frame IDs for a take."""
        if take_id in self.frame_info:
            return sorted(self.frame_info[take_id].keys())
            
        # Get take directory
        take_dir = self.get_take_directory(take_id)
        if take_dir and take_dir.exists():
            frames = []
            for f in take_dir.glob('frame_*.png'):
                try:
                    frame_id = int(f.stem.split('_')[1])
                    frames.append(frame_id)
                except (ValueError, IndexError):
                    continue
            return sorted(frames)
            
        return []
    
    def get_frame_count(self, take_id: int) -> int:
        """Get the number of frames in a take."""
        return len(self.get_take_frames(take_id))
    
    def get_frame_path(self, take_id: int, frame_id: int) -> Optional[str]:
        """Get the path to a frame file."""
        take_dir = self.get_take_directory(take_id)
        if not take_dir:
            return None
        
        frame_file = take_dir / f'frame_{frame_id:06d}.png'
        if frame_file.exists():
            return str(frame_file)
        
        return None
    
    def _update_frame_index(self, take_id: int):
        """Update the frame index file for a take."""
        if take_id not in self.frame_info:
            return
            
        take_dir = self.get_take_directory(take_id)
        index_file = take_dir / 'frame_index.json'
        
        frames_data = [asdict(info) for info in self.frame_info[take_id].values()]
        
        data = {
            'take_id': take_id,
            'frame_count': len(frames_data),
            'updated_at': datetime.now().isoformat(),
            'frames': frames_data
        }
        
        try:
            with open(index_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error updating frame index: {e}")
    
    def finalize_take(self, take_id: int):
        """Finalize a take (update index and cleanup)."""
        if take_id in self.frame_info:
            self._update_frame_index(take_id)
            logger.info(f"Finalized take {take_id} with {len(self.frame_info[take_id])} frames")
    
    def get_storage_stats(self, take_id: int) -> Dict[str, Any]:
        """Get storage statistics for a take."""
        frames = self.frame_info.get(take_id, {})
        
        if not frames:
            return {
                'take_id': take_id,
                'frame_count': 0,
                'total_size_mb': 0,
                'avg_frame_size_kb': 0
            }
        
        total_size = sum(f.file_size for f in frames.values())
        avg_size = total_size / len(frames) if frames else 0
        
        return {
            'take_id': take_id,
            'frame_count': len(frames),
            'total_size_mb': total_size / (1024 * 1024),
            'avg_frame_size_kb': avg_size / 1024,
            'compression_type': 'PNG (lossless)'
        }
    
    def delete_take(self, take_id: int):
        """Delete all frames for a take."""
        take_dir = self.get_take_directory(take_id)
        
        if take_dir and take_dir.exists():
            import shutil
            shutil.rmtree(take_dir)
            logger.info(f"Deleted frame directory for take {take_id}: {take_dir}")
            
        if take_id in self.frame_info:
            del self.frame_info[take_id]
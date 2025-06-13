# CAMF/services/detector_framework/batch_progress.py
"""
Progress tracking system for batch processing with real-time updates.
"""

import time
import threading
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class SegmentProgress:
    """Progress information for a single segment."""
    segment_id: int
    start_frame: int
    end_frame: int
    total_frames: int
    processed_frames: int
    status: str  # pending, processing, completed, failed
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    error: Optional[str] = None
    fps: float = 0.0
    eta_seconds: float = 0.0
    
    @property
    def progress_percent(self) -> float:
        """Get progress as percentage."""
        if self.total_frames == 0:
            return 100.0 if self.status == "completed" else 0.0
        return min(100.0, (self.processed_frames / self.total_frames) * 100)
    
    @property
    def elapsed_seconds(self) -> float:
        """Get elapsed time in seconds."""
        if self.start_time:
            end = self.end_time or time.time()
            return end - self.start_time
        return 0.0
    
    def update_fps(self):
        """Update frames per second calculation."""
        if self.elapsed_seconds > 0 and self.processed_frames > 0:
            self.fps = self.processed_frames / self.elapsed_seconds
            
            # Calculate ETA
            if self.fps > 0:
                remaining_frames = self.total_frames - self.processed_frames
                self.eta_seconds = remaining_frames / self.fps
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'segment_id': self.segment_id,
            'start_frame': self.start_frame,
            'end_frame': self.end_frame,
            'total_frames': self.total_frames,
            'processed_frames': self.processed_frames,
            'progress_percent': round(self.progress_percent, 2),
            'status': self.status,
            'elapsed_seconds': round(self.elapsed_seconds, 2),
            'fps': round(self.fps, 2),
            'eta_seconds': round(self.eta_seconds, 2),
            'error': self.error
        }


@dataclass
class BatchProgress:
    """Overall batch processing progress."""
    batch_id: str
    video_path: str
    total_segments: int
    completed_segments: int
    failed_segments: int
    total_frames: int
    processed_frames: int
    start_time: float
    end_time: Optional[float] = None
    status: str = "processing"  # processing, completed, failed
    
    @property
    def active_segments(self) -> int:
        """Get number of currently active segments."""
        return self.total_segments - self.completed_segments - self.failed_segments
    
    @property
    def progress_percent(self) -> float:
        """Get overall progress as percentage."""
        if self.total_frames == 0:
            return 100.0 if self.status == "completed" else 0.0
        return min(100.0, (self.processed_frames / self.total_frames) * 100)
    
    @property
    def elapsed_seconds(self) -> float:
        """Get elapsed time in seconds."""
        end = self.end_time or time.time()
        return end - self.start_time
    
    @property
    def average_fps(self) -> float:
        """Get average processing speed in FPS."""
        if self.elapsed_seconds > 0 and self.processed_frames > 0:
            return self.processed_frames / self.elapsed_seconds
        return 0.0
    
    @property
    def eta_seconds(self) -> float:
        """Get estimated time to completion in seconds."""
        if self.average_fps > 0:
            remaining_frames = self.total_frames - self.processed_frames
            return remaining_frames / self.average_fps
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'batch_id': self.batch_id,
            'video_path': self.video_path,
            'total_segments': self.total_segments,
            'active_segments': self.active_segments,
            'completed_segments': self.completed_segments,
            'failed_segments': self.failed_segments,
            'total_frames': self.total_frames,
            'processed_frames': self.processed_frames,
            'progress_percent': round(self.progress_percent, 2),
            'elapsed_seconds': round(self.elapsed_seconds, 2),
            'average_fps': round(self.average_fps, 2),
            'eta_seconds': round(self.eta_seconds, 2),
            'status': self.status,
            'start_time': datetime.fromtimestamp(self.start_time).isoformat(),
            'end_time': datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None
        }


class ProgressTracker:
    """Tracks and reports batch processing progress."""
    
    def __init__(self, batch_id: str, video_path: str, total_segments: int, total_frames: int):
        self.batch_progress = BatchProgress(
            batch_id=batch_id,
            video_path=video_path,
            total_segments=total_segments,
            completed_segments=0,
            failed_segments=0,
            total_frames=total_frames,
            processed_frames=0,
            start_time=time.time()
        )
        
        self.segments: Dict[int, SegmentProgress] = {}
        self.callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self.update_lock = threading.Lock()
        self.update_thread = None
        self.running = True
        
        # Start update thread for periodic updates
        self._start_update_thread()
    
    def add_segment(self, segment_id: int, start_frame: int, end_frame: int, total_frames: int):
        """Add a segment to track."""
        with self.update_lock:
            self.segments[segment_id] = SegmentProgress(
                segment_id=segment_id,
                start_frame=start_frame,
                end_frame=end_frame,
                total_frames=total_frames,
                processed_frames=0,
                status="pending"
            )
        self._notify_update()
    
    def update_segment_progress(self, segment_id: int, processed_frames: int):
        """Update progress for a specific segment."""
        with self.update_lock:
            if segment_id in self.segments:
                segment = self.segments[segment_id]
                segment.processed_frames = processed_frames
                segment.update_fps()
                
                # Update overall progress
                self._recalculate_overall_progress()
        
        self._notify_update()
    
    def start_segment(self, segment_id: int):
        """Mark segment as started."""
        with self.update_lock:
            if segment_id in self.segments:
                segment = self.segments[segment_id]
                segment.status = "processing"
                segment.start_time = time.time()
        self._notify_update()
    
    def complete_segment(self, segment_id: int):
        """Mark segment as completed."""
        with self.update_lock:
            if segment_id in self.segments:
                segment = self.segments[segment_id]
                segment.status = "completed"
                segment.end_time = time.time()
                segment.processed_frames = segment.total_frames
                
                self.batch_progress.completed_segments += 1
                self._recalculate_overall_progress()
        
        self._notify_update()
    
    def fail_segment(self, segment_id: int, error: str):
        """Mark segment as failed."""
        with self.update_lock:
            if segment_id in self.segments:
                segment = self.segments[segment_id]
                segment.status = "failed"
                segment.end_time = time.time()
                segment.error = error
                
                self.batch_progress.failed_segments += 1
                self._recalculate_overall_progress()
        
        self._notify_update()
    
    def complete_batch(self):
        """Mark entire batch as completed."""
        with self.update_lock:
            self.batch_progress.status = "completed"
            self.batch_progress.end_time = time.time()
            self.running = False
        self._notify_update()
    
    def fail_batch(self, error: str):
        """Mark entire batch as failed."""
        with self.update_lock:
            self.batch_progress.status = "failed"
            self.batch_progress.end_time = time.time()
            self.running = False
        self._notify_update()
    
    def _recalculate_overall_progress(self):
        """Recalculate overall batch progress from segments."""
        total_processed = sum(seg.processed_frames for seg in self.segments.values())
        self.batch_progress.processed_frames = total_processed
    
    def _start_update_thread(self):
        """Start thread for periodic progress updates."""
        def update_loop():
            while self.running:
                time.sleep(1)  # Update every second
                with self.update_lock:
                    # Update FPS for active segments
                    for segment in self.segments.values():
                        if segment.status == "processing":
                            segment.update_fps()
                
                self._notify_update()
        
        self.update_thread = threading.Thread(target=update_loop, daemon=True)
        self.update_thread.start()
    
    def _notify_update(self):
        """Notify all callbacks of progress update."""
        progress_data = self.get_progress()
        
        for callback in self.callbacks:
            try:
                callback(progress_data)
            except Exception as e:
                logger.error(f"Progress callback error: {e}")
    
    def add_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Add a progress update callback."""
        self.callbacks.append(callback)
    
    def get_progress(self) -> Dict[str, Any]:
        """Get current progress state."""
        with self.update_lock:
            return {
                'batch': self.batch_progress.to_dict(),
                'segments': {
                    seg_id: seg.to_dict() 
                    for seg_id, seg in self.segments.items()
                },
                'summary': {
                    'active_segments': [
                        seg_id for seg_id, seg in self.segments.items() 
                        if seg.status == "processing"
                    ],
                    'pending_segments': [
                        seg_id for seg_id, seg in self.segments.items() 
                        if seg.status == "pending"
                    ],
                    'completed_segments': [
                        seg_id for seg_id, seg in self.segments.items() 
                        if seg.status == "completed"
                    ],
                    'failed_segments': [
                        seg_id for seg_id, seg in self.segments.items() 
                        if seg.status == "failed"
                    ]
                }
            }
    
    def get_segment_progress(self, segment_id: int) -> Optional[Dict[str, Any]]:
        """Get progress for specific segment."""
        with self.update_lock:
            if segment_id in self.segments:
                return self.segments[segment_id].to_dict()
        return None
    
    def stop(self):
        """Stop progress tracking."""
        self.running = False
        if self.update_thread:
            self.update_thread.join(timeout=2)


class ProgressAggregator:
    """Aggregates progress from multiple batch processors."""
    
    def __init__(self):
        self.trackers: Dict[str, ProgressTracker] = {}
        self.lock = threading.Lock()
        self.global_callbacks: List[Callable[[Dict[str, Any]], None]] = []
    
    def create_tracker(self, batch_id: str, video_path: str, 
                      total_segments: int, total_frames: int) -> ProgressTracker:
        """Create a new progress tracker."""
        tracker = ProgressTracker(batch_id, video_path, total_segments, total_frames)
        
        # Add callback to propagate updates
        tracker.add_callback(lambda progress: self._on_tracker_update(batch_id, progress))
        
        with self.lock:
            self.trackers[batch_id] = tracker
        
        return tracker
    
    def remove_tracker(self, batch_id: str):
        """Remove a tracker."""
        with self.lock:
            if batch_id in self.trackers:
                self.trackers[batch_id].stop()
                del self.trackers[batch_id]
    
    def _on_tracker_update(self, batch_id: str, progress: Dict[str, Any]):
        """Handle update from individual tracker."""
        # Notify global callbacks with aggregated data
        all_progress = self.get_all_progress()
        for callback in self.global_callbacks:
            try:
                callback(all_progress)
            except Exception as e:
                logger.error(f"Global progress callback error: {e}")
    
    def add_global_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Add a global progress callback."""
        self.global_callbacks.append(callback)
    
    def get_all_progress(self) -> Dict[str, Any]:
        """Get progress for all active batches."""
        with self.lock:
            return {
                'batches': {
                    batch_id: tracker.get_progress()
                    for batch_id, tracker in self.trackers.items()
                },
                'summary': {
                    'active_batches': len(self.trackers),
                    'total_frames': sum(
                        t.batch_progress.total_frames 
                        for t in self.trackers.values()
                    ),
                    'processed_frames': sum(
                        t.batch_progress.processed_frames 
                        for t in self.trackers.values()
                    ),
                    'average_fps': sum(
                        t.batch_progress.average_fps 
                        for t in self.trackers.values()
                    ) / len(self.trackers) if self.trackers else 0
                }
            }
    
    def cleanup_completed(self, max_age_seconds: int = 3600):
        """Remove completed trackers older than max age."""
        current_time = time.time()
        to_remove = []
        
        with self.lock:
            for batch_id, tracker in self.trackers.items():
                if tracker.batch_progress.status in ["completed", "failed"]:
                    if tracker.batch_progress.end_time:
                        age = current_time - tracker.batch_progress.end_time
                        if age > max_age_seconds:
                            to_remove.append(batch_id)
        
        for batch_id in to_remove:
            self.remove_tracker(batch_id)


# Global progress aggregator instance
_progress_aggregator = None


def get_progress_aggregator() -> ProgressAggregator:
    """Get global progress aggregator instance."""
    global _progress_aggregator
    if _progress_aggregator is None:
        _progress_aggregator = ProgressAggregator()
    return _progress_aggregator
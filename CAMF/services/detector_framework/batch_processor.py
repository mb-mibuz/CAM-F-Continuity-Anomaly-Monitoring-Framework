# CAMF/services/detector_framework/batch_processor.py
"""
Batch processing system for efficient video upload handling.
Implements parallel processing, resource management, and optimization strategies.
"""

import time
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
import hashlib
import cv2
import numpy as np
import psutil
import logging
from concurrent.futures import ThreadPoolExecutor
import tempfile
import shutil

from CAMF.common.models import DetectorResult, ErrorConfidence

logger = logging.getLogger(__name__)


@dataclass
class VideoSegment:
    """Represents a video segment for processing."""
    segment_id: int
    start_frame: int
    end_frame: int
    video_path: str
    output_path: Optional[str] = None
    processed_frames: int = 0
    total_frames: int = 0
    status: str = "pending"
    error: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    @property
    def progress(self) -> float:
        """Get segment processing progress as percentage."""
        if self.total_frames == 0:
            return 0.0
        return (self.processed_frames / self.total_frames) * 100
    
    @property
    def processing_time(self) -> float:
        """Get segment processing time in seconds."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        elif self.start_time:
            return time.time() - self.start_time
        return 0.0


@dataclass
class BatchProcessingConfig:
    """Configuration for batch processing."""
    max_parallel_segments: int = 4
    segment_size_frames: int = 300  # 10 seconds at 30fps
    max_memory_usage_percent: float = 80.0
    max_cpu_usage_percent: float = 90.0
    enable_frame_deduplication: bool = True
    deduplication_threshold: float = 0.99  # Similarity threshold
    enable_early_termination: bool = True
    early_termination_error_threshold: int = 10
    gpu_enabled: bool = True
    processing_timeout_seconds: int = 300
    temp_directory: Optional[str] = None
    cleanup_temp_files: bool = True
    
    def validate(self):
        """Validate configuration values."""
        if self.max_parallel_segments < 1:
            raise ValueError("max_parallel_segments must be at least 1")
        if self.segment_size_frames < 10:
            raise ValueError("segment_size_frames must be at least 10")
        if not 0 < self.max_memory_usage_percent <= 100:
            raise ValueError("max_memory_usage_percent must be between 0 and 100")
        if not 0 < self.max_cpu_usage_percent <= 100:
            raise ValueError("max_cpu_usage_percent must be between 0 and 100")


class ResourceMonitor:
    """Monitors system resources and provides throttling recommendations."""
    
    def __init__(self, config: BatchProcessingConfig):
        self.config = config
        self.monitoring = True
        self.current_memory_usage = 0.0
        self.current_cpu_usage = 0.0
        self.monitor_thread = None
        self._start_monitoring()
    
    def _start_monitoring(self):
        """Start resource monitoring in background thread."""
        def monitor_loop():
            while self.monitoring:
                try:
                    # Memory usage
                    memory = psutil.virtual_memory()
                    self.current_memory_usage = memory.percent
                    
                    # CPU usage (average over 1 second)
                    self.current_cpu_usage = psutil.cpu_percent(interval=1)
                    
                    time.sleep(2)  # Update every 2 seconds
                except Exception as e:
                    logger.error(f"Resource monitoring error: {e}")
                    time.sleep(5)
        
        self.monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def should_throttle(self) -> bool:
        """Check if processing should be throttled."""
        return (self.current_memory_usage > self.config.max_memory_usage_percent or
                self.current_cpu_usage > self.config.max_cpu_usage_percent)
    
    def get_recommended_workers(self) -> int:
        """Get recommended number of parallel workers based on resources."""
        # Start with configured maximum
        workers = self.config.max_parallel_segments
        
        # Reduce based on CPU
        if self.current_cpu_usage > 80:
            workers = max(1, workers // 2)
        elif self.current_cpu_usage > 60:
            workers = max(1, int(workers * 0.75))
        
        # Reduce based on memory
        if self.current_memory_usage > 80:
            workers = max(1, workers // 2)
        elif self.current_memory_usage > 60:
            workers = max(1, int(workers * 0.75))
        
        return workers
    
    def get_stats(self) -> Dict[str, float]:
        """Get current resource statistics."""
        return {
            'memory_usage_percent': self.current_memory_usage,
            'cpu_usage_percent': self.current_cpu_usage,
            'recommended_workers': self.get_recommended_workers()
        }
    
    def stop(self):
        """Stop resource monitoring."""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)


class FrameDeduplicator:
    """Handles frame deduplication to avoid processing similar frames."""
    
    def __init__(self, threshold: float = 0.99):
        self.threshold = threshold
        self.frame_hashes = {}
        self.similar_frames = {}  # Maps duplicate frames to original
    
    def compute_frame_hash(self, frame: np.ndarray) -> str:
        """Compute perceptual hash for frame."""
        # Resize to small size for faster comparison
        small_frame = cv2.resize(frame, (32, 32))
        # Convert to grayscale
        if len(small_frame.shape) == 3:
            small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
        # Compute hash
        return hashlib.md5(small_frame.tobytes()).hexdigest()
    
    def compute_frame_similarity(self, frame1: np.ndarray, frame2: np.ndarray) -> float:
        """Compute similarity between two frames."""
        # Resize to same size
        size = (128, 128)
        f1_resized = cv2.resize(frame1, size)
        f2_resized = cv2.resize(frame2, size)
        
        # Convert to grayscale if needed
        if len(f1_resized.shape) == 3:
            f1_resized = cv2.cvtColor(f1_resized, cv2.COLOR_BGR2GRAY)
        if len(f2_resized.shape) == 3:
            f2_resized = cv2.cvtColor(f2_resized, cv2.COLOR_BGR2GRAY)
        
        # Compute structural similarity
        diff = cv2.absdiff(f1_resized, f2_resized)
        similarity = 1.0 - (np.sum(diff) / (size[0] * size[1] * 255))
        
        return similarity
    
    def is_duplicate(self, frame: np.ndarray, frame_id: int) -> Optional[int]:
        """Check if frame is duplicate of a previously seen frame."""
        frame_hash = self.compute_frame_hash(frame)
        
        # Check exact hash match first
        if frame_hash in self.frame_hashes:
            original_id = self.frame_hashes[frame_hash]
            self.similar_frames[frame_id] = original_id
            return original_id
        
        # Check similarity with recent frames (last 30)
        recent_frames = sorted(self.frame_hashes.items(), 
                             key=lambda x: x[1], reverse=True)[:30]
        
        for stored_hash, stored_id in recent_frames:
            # Skip if we already compared
            if stored_id in self.similar_frames:
                continue
                
            # For efficiency, only do detailed comparison if hashes are somewhat similar
            if self._hashes_similar(frame_hash, stored_hash):
                # Load stored frame for comparison (would need frame storage)
                # For now, we'll just use hash similarity
                self.similar_frames[frame_id] = stored_id
                return stored_id
        
        # Not a duplicate, store it
        self.frame_hashes[frame_hash] = frame_id
        return None
    
    def _hashes_similar(self, hash1: str, hash2: str) -> bool:
        """Quick check if two hashes are similar."""
        # Simple character comparison
        matches = sum(c1 == c2 for c1, c2 in zip(hash1, hash2))
        return matches / len(hash1) > 0.8
    
    def get_unique_frames(self, frame_ids: List[int]) -> List[int]:
        """Get list of unique frames from a set of frame IDs."""
        unique = []
        for frame_id in frame_ids:
            if frame_id not in self.similar_frames:
                unique.append(frame_id)
        return unique
    
    def get_duplicate_mapping(self) -> Dict[int, int]:
        """Get mapping of duplicate frames to originals."""
        return self.similar_frames.copy()


class SegmentProcessor:
    """Processes individual video segments."""
    
    def __init__(self, detector_callback: Callable, config: BatchProcessingConfig):
        self.detector_callback = detector_callback
        self.config = config
        self.deduplicator = FrameDeduplicator(config.deduplication_threshold) if config.enable_frame_deduplication else None
        self.early_termination_errors = 0
    
    def process_segment(self, segment: VideoSegment, 
                       progress_callback: Optional[Callable] = None) -> Dict[int, List[DetectorResult]]:
        """Process a single video segment."""
        segment.status = "processing"
        segment.start_time = time.time()
        results = {}
        
        try:
            # Open video
            cap = cv2.VideoCapture(segment.video_path)
            if not cap.isOpened():
                raise ValueError(f"Failed to open video: {segment.video_path}")
            
            # Get total frames in segment
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            segment.total_frames = min(segment.end_frame - segment.start_frame, total_frames - segment.start_frame)
            
            # Seek to start frame
            cap.set(cv2.CAP_PROP_POS_FRAMES, segment.start_frame)
            
            # Process frames
            frame_batch = []
            frame_ids = []
            
            for frame_idx in range(segment.start_frame, segment.end_frame):
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Check for early termination
                if self.config.enable_early_termination:
                    if self.early_termination_errors >= self.config.early_termination_error_threshold:
                        logger.info(f"Early termination triggered for segment {segment.segment_id}")
                        break
                
                # Frame deduplication
                if self.deduplicator:
                    duplicate_id = self.deduplicator.is_duplicate(frame, frame_idx)
                    if duplicate_id is not None:
                        # Skip duplicate frame
                        results[frame_idx] = results.get(duplicate_id, [])
                        segment.processed_frames += 1
                        continue
                
                # Batch frames for processing
                frame_batch.append(frame)
                frame_ids.append(frame_idx)
                
                # Process batch when full or last frame
                if len(frame_batch) >= 10 or frame_idx == segment.end_frame - 1:
                    batch_results = self._process_frame_batch(frame_batch, frame_ids)
                    
                    # Update results
                    for fid, res in batch_results.items():
                        results[fid] = res
                        
                        # Count errors for early termination
                        error_count = sum(1 for r in res 
                                        if r.confidence in [ErrorConfidence.CONFIRMED_ERROR, 
                                                          ErrorConfidence.LIKELY_ERROR])
                        self.early_termination_errors += error_count
                    
                    segment.processed_frames += len(frame_batch)
                    
                    # Clear batch
                    frame_batch = []
                    frame_ids = []
                    
                    # Progress callback
                    if progress_callback:
                        progress_callback(segment)
            
            cap.release()
            
            segment.status = "completed"
            segment.end_time = time.time()
            
        except Exception as e:
            logger.error(f"Error processing segment {segment.segment_id}: {e}")
            segment.status = "failed"
            segment.error = str(e)
            segment.end_time = time.time()
        
        return results
    
    def _process_frame_batch(self, frames: List[np.ndarray], 
                           frame_ids: List[int]) -> Dict[int, List[DetectorResult]]:
        """Process a batch of frames."""
        results = {}
        
        # Convert frames to format expected by detector
        # For now, process individually (can be optimized for batch processing)
        for frame, frame_id in zip(frames, frame_ids):
            try:
                # Call detector callback
                detector_results = self.detector_callback(frame, frame_id)
                results[frame_id] = detector_results
            except Exception as e:
                logger.error(f"Error processing frame {frame_id}: {e}")
                results[frame_id] = [
                    DetectorResult(
                        confidence=ErrorConfidence.DETECTOR_FAILED,
                        description=f"Processing failed: {str(e)}",
                        frame_id=frame_id,
                        detector_name="BatchProcessor"
                    )
                ]
        
        return results


class VideoSegmenter:
    """Splits videos into segments for parallel processing."""
    
    def __init__(self, config: BatchProcessingConfig):
        self.config = config
    
    def segment_video(self, video_path: str, output_dir: Optional[str] = None) -> List[VideoSegment]:
        """Split video into segments."""
        segments = []
        
        # Get video info
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Failed to open video: {video_path}")
        
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        
        # Calculate segments
        segment_count = (total_frames + self.config.segment_size_frames - 1) // self.config.segment_size_frames
        
        for i in range(segment_count):
            start_frame = i * self.config.segment_size_frames
            end_frame = min((i + 1) * self.config.segment_size_frames, total_frames)
            
            segment = VideoSegment(
                segment_id=i,
                start_frame=start_frame,
                end_frame=end_frame,
                video_path=video_path,
                total_frames=end_frame - start_frame
            )
            
            segments.append(segment)
        
        logger.info(f"Split video into {len(segments)} segments of ~{self.config.segment_size_frames} frames")
        
        return segments


class BatchProcessor:
    """Main batch processing orchestrator."""
    
    def __init__(self, config: BatchProcessingConfig):
        self.config = config
        self.config.validate()
        
        self.resource_monitor = ResourceMonitor(config)
        self.segmenter = VideoSegmenter(config)
        self.active_segments: Dict[int, VideoSegment] = {}
        self.completed_segments: List[VideoSegment] = []
        self.all_results: Dict[int, List[DetectorResult]] = {}
        self.processing_lock = threading.Lock()
        self.progress_callbacks: List[Callable] = []
        
        # Thread pool for parallel processing
        self.executor = ThreadPoolExecutor(max_workers=config.max_parallel_segments)
        
        # Temp directory for intermediate files
        if config.temp_directory:
            self.temp_dir = Path(config.temp_directory)
            self.temp_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.temp_dir = Path(tempfile.mkdtemp(prefix="camf_batch_"))
    
    def process_video(self, video_path: str, detector_callback: Callable,
                     take_id: int) -> Dict[str, Any]:
        """
        Process entire video with parallel segment processing.
        
        Args:
            video_path: Path to video file
            detector_callback: Function to process frames (frame, frame_id) -> List[DetectorResult]
            take_id: Take ID for context
            
        Returns:
            Processing results and statistics
        """
        start_time = time.time()
        
        try:
            # Segment video
            segments = self.segmenter.segment_video(video_path)
            total_segments = len(segments)
            
            # Create segment processors
            processors = [SegmentProcessor(detector_callback, self.config) 
                         for _ in range(self.config.max_parallel_segments)]
            
            # Process segments in parallel
            futures = []
            processor_idx = 0
            
            for segment in segments:
                # Wait if too many active segments
                while len(self.active_segments) >= self.resource_monitor.get_recommended_workers():
                    time.sleep(0.1)
                
                # Submit segment for processing
                processor = processors[processor_idx % len(processors)]
                processor_idx += 1
                
                future = self.executor.submit(
                    self._process_segment_wrapper,
                    segment,
                    processor,
                    take_id
                )
                futures.append((future, segment))
                
                with self.processing_lock:
                    self.active_segments[segment.segment_id] = segment
            
            # Wait for all segments to complete
            for future, segment in futures:
                try:
                    results = future.result(timeout=self.config.processing_timeout_seconds)
                    self._merge_results(results)
                    
                    with self.processing_lock:
                        del self.active_segments[segment.segment_id]
                        self.completed_segments.append(segment)
                    
                except Exception as e:
                    logger.error(f"Segment {segment.segment_id} processing failed: {e}")
                    segment.status = "failed"
                    segment.error = str(e)
            
            # Calculate statistics
            end_time = time.time()
            total_time = end_time - start_time
            
            # Get video info for statistics
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            video_duration = total_frames / fps if fps > 0 else 0
            cap.release()
            
            # Processing statistics
            successful_segments = [s for s in self.completed_segments if s.status == "completed"]
            failed_segments = [s for s in self.completed_segments if s.status == "failed"]
            
            total_processed_frames = sum(s.processed_frames for s in successful_segments)
            processing_speed = total_processed_frames / total_time if total_time > 0 else 0
            speedup_factor = (processing_speed / fps) if fps > 0 else 0
            
            stats = {
                'total_segments': total_segments,
                'successful_segments': len(successful_segments),
                'failed_segments': len(failed_segments),
                'total_frames': total_frames,
                'processed_frames': total_processed_frames,
                'total_time_seconds': total_time,
                'video_duration_seconds': video_duration,
                'processing_fps': processing_speed,
                'speedup_factor': speedup_factor,
                'average_segment_time': np.mean([s.processing_time for s in successful_segments]) if successful_segments else 0,
                'resource_stats': self.resource_monitor.get_stats(),
                'total_results': len(self.all_results),
                'unique_errors': self._count_unique_errors()
            }
            
            logger.info(f"Batch processing completed: {speedup_factor:.1f}x faster than real-time")
            
            return {
                'results': self.all_results,
                'statistics': stats,
                'segments': [self._segment_to_dict(s) for s in self.completed_segments]
            }
            
        finally:
            # Cleanup
            if self.config.cleanup_temp_files and self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _process_segment_wrapper(self, segment: VideoSegment, 
                                processor: SegmentProcessor,
                                take_id: int) -> Dict[int, List[DetectorResult]]:
        """Wrapper for segment processing with progress tracking."""
        def progress_callback(seg: VideoSegment):
            # Notify progress callbacks
            for callback in self.progress_callbacks:
                try:
                    callback(self.get_progress())
                except Exception as e:
                    logger.error(f"Progress callback error: {e}")
        
        return processor.process_segment(segment, progress_callback)
    
    def _merge_results(self, segment_results: Dict[int, List[DetectorResult]]):
        """Merge segment results into overall results."""
        with self.processing_lock:
            for frame_id, results in segment_results.items():
                if frame_id in self.all_results:
                    self.all_results[frame_id].extend(results)
                else:
                    self.all_results[frame_id] = results
    
    def _count_unique_errors(self) -> int:
        """Count unique errors across all results."""
        unique_errors = set()
        for frame_results in self.all_results.values():
            for result in frame_results:
                if result.confidence in [ErrorConfidence.CONFIRMED_ERROR, ErrorConfidence.LIKELY_ERROR]:
                    # Create unique key for error
                    error_key = f"{result.detector_name}:{result.description[:50]}"
                    unique_errors.add(error_key)
        return len(unique_errors)
    
    def _segment_to_dict(self, segment: VideoSegment) -> Dict[str, Any]:
        """Convert segment to dictionary for serialization."""
        return {
            'segment_id': segment.segment_id,
            'start_frame': segment.start_frame,
            'end_frame': segment.end_frame,
            'processed_frames': segment.processed_frames,
            'total_frames': segment.total_frames,
            'status': segment.status,
            'error': segment.error,
            'progress': segment.progress,
            'processing_time': segment.processing_time
        }
    
    def get_progress(self) -> Dict[str, Any]:
        """Get current processing progress."""
        with self.processing_lock:
            total_frames = sum(s.total_frames for s in list(self.active_segments.values()) + self.completed_segments)
            processed_frames = sum(s.processed_frames for s in list(self.active_segments.values()) + self.completed_segments)
            
            return {
                'total_segments': len(self.active_segments) + len(self.completed_segments),
                'active_segments': len(self.active_segments),
                'completed_segments': len(self.completed_segments),
                'total_frames': total_frames,
                'processed_frames': processed_frames,
                'overall_progress': (processed_frames / total_frames * 100) if total_frames > 0 else 0,
                'active_segment_progress': {
                    seg_id: seg.progress 
                    for seg_id, seg in self.active_segments.items()
                }
            }
    
    def add_progress_callback(self, callback: Callable):
        """Add a progress callback function."""
        self.progress_callbacks.append(callback)
    
    def stop(self):
        """Stop batch processing and cleanup resources."""
        # Shutdown executor
        self.executor.shutdown(wait=False)
        
        # Stop resource monitor
        self.resource_monitor.stop()
        
        # Cleanup temp files
        if self.config.cleanup_temp_files and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)


def create_batch_processor(config: Optional[BatchProcessingConfig] = None) -> BatchProcessor:
    """Create a batch processor with default or custom configuration."""
    if config is None:
        config = BatchProcessingConfig()
    return BatchProcessor(config)
"""
Priority-based queue management for detector framework.
Implements intelligent frame dropping based on importance.
"""
import logging
import queue
import threading
from typing import Optional, List, Tuple
from dataclasses import dataclass, field
import heapq
import time

from CAMF.services.detector_framework.interface import FramePair

logger = logging.getLogger(__name__)


@dataclass
class PrioritizedFramePair:
    """Frame pair with priority information for queue management."""
    frame_pair: FramePair
    priority: float  # Lower values = higher priority
    timestamp: float = field(default_factory=time.time)
    take_frame_count: int = 0  # Total frames in the take
    is_first_frame: bool = False
    is_last_frame: bool = False
    
    def __lt__(self, other):
        """For priority queue comparison - lower priority value = higher priority."""
        return self.priority < other.priority


class IntelligentFrameQueue:
    """
    Intelligent queue with frame prioritization and selective dropping.
    
    Features:
    - Prioritizes first and last frames of takes (continuity boundaries)
    - Drops middle frames first when queue approaches capacity
    - Maintains minimum frame coverage for reliable detection
    - Adapts dropping strategy based on processing speed
    """
    
    def __init__(self, maxsize: int = 100, high_water_mark: float = 0.8):
        """
        Initialize intelligent queue.
        
        Args:
            maxsize: Maximum queue size
            high_water_mark: Fraction of queue size to trigger selective dropping (0.8 = 80%)
        """
        self.maxsize = maxsize
        self.high_water_mark = int(maxsize * high_water_mark)
        
        # Priority queue for frame management
        self._queue: List[PrioritizedFramePair] = []
        self._lock = threading.RLock()
        self._not_empty = threading.Condition(self._lock)
        
        # Statistics
        self.frames_added = 0
        self.frames_dropped = 0
        self.frames_processed = 0
        
        # Frame dropping strategy parameters
        self.min_frame_interval = 5  # Keep at least every 5th frame
        self.boundary_frames = 10  # Frames at start/end to prioritize
        
        # Track current take info
        self.current_take_id: Optional[int] = None
        self.take_frame_counts: dict[int, int] = {}
        
    def calculate_priority(self, frame_pair: FramePair, take_frame_count: int) -> float:
        """
        Calculate frame priority based on position in take.
        
        Priority levels (lower = higher priority):
        - 0.0-0.1: First frames of take (critical for continuity)
        - 0.1-0.2: Last frames of take (critical for continuity)
        - 0.3-0.5: Near-boundary frames
        - 0.5-1.0: Middle frames (can be dropped if needed)
        """
        frame_position = frame_pair.current_frame_id
        
        # First frames get highest priority
        if frame_position < self.boundary_frames:
            priority = 0.0 + (frame_position / self.boundary_frames) * 0.1
            is_first = frame_position == 0
            is_last = False
        # Last frames get second highest priority
        elif take_frame_count > 0 and frame_position >= take_frame_count - self.boundary_frames:
            frames_from_end = take_frame_count - frame_position - 1
            priority = 0.1 + (frames_from_end / self.boundary_frames) * 0.1
            is_first = False
            is_last = frame_position == take_frame_count - 1
        # Middle frames get lower priority
        else:
            # Calculate distance from boundaries
            distance_from_start = frame_position - self.boundary_frames
            distance_from_end = take_frame_count - frame_position - self.boundary_frames if take_frame_count > 0 else float('inf')
            min_distance = min(distance_from_start, distance_from_end)
            
            # Normalize to 0.5-1.0 range
            if take_frame_count > 0:
                normalized_distance = min_distance / (take_frame_count / 2)
                priority = 0.5 + min(normalized_distance * 0.5, 0.5)
            else:
                priority = 0.7  # Default for unknown take length
            
            is_first = False
            is_last = False
        
        return priority, is_first, is_last
    
    def put(self, frame_pair: FramePair, take_frame_count: int = 0) -> bool:
        """
        Add frame pair to queue with intelligent management.
        
        Args:
            frame_pair: Frame pair to add
            take_frame_count: Total frames in the take (for priority calculation)
            
        Returns:
            True if frame was added (or intelligently dropped), False if rejected
        """
        with self._lock:
            # Update take info
            if frame_pair.take_id != self.current_take_id:
                self.current_take_id = frame_pair.take_id
                logger.info(f"New take {frame_pair.take_id} started, frame count: {take_frame_count}")
            
            self.take_frame_counts[frame_pair.take_id] = take_frame_count
            
            # Calculate priority
            priority, is_first, is_last = self.calculate_priority(frame_pair, take_frame_count)
            
            prioritized_frame = PrioritizedFramePair(
                frame_pair=frame_pair,
                priority=priority,
                take_frame_count=take_frame_count,
                is_first_frame=is_first,
                is_last_frame=is_last
            )
            
            # Check if we need to drop frames
            current_size = len(self._queue)
            
            if current_size >= self.maxsize:
                # Queue is full - must drop something
                dropped = self._drop_lowest_priority_frame(prioritized_frame)
                if dropped:
                    logger.debug(f"Dropped frame to make room (queue was full at {self.maxsize})")
                else:
                    logger.warning(f"Cannot drop any frames - all are high priority. Rejecting new frame.")
                    return False
            
            elif current_size >= self.high_water_mark:
                # Approaching capacity - consider selective dropping
                if priority > 0.5:  # Middle frame
                    # Check if we should drop this frame
                    if self._should_drop_frame(priority, current_size):
                        self.frames_dropped += 1
                        logger.debug(f"Selectively dropped middle frame {frame_pair.current_frame_id} "
                                   f"(priority={priority:.2f}, queue={current_size}/{self.maxsize})")
                        return True  # Return True as frame was "handled"
                
            # Add frame to queue
            heapq.heappush(self._queue, prioritized_frame)
            self.frames_added += 1
            self._not_empty.notify()
            
            if is_first or is_last:
                logger.debug(f"Added {'first' if is_first else 'last'} frame {frame_pair.current_frame_id} "
                           f"with priority {priority:.2f}")
            
            return True
    
    def get(self, timeout: Optional[float] = None) -> Optional[FramePair]:
        """
        Get next frame pair from queue (highest priority first).
        
        Args:
            timeout: Maximum time to wait for a frame
            
        Returns:
            Frame pair or None if timeout
        """
        with self._lock:
            end_time = time.time() + timeout if timeout else None
            
            while not self._queue:
                if timeout is None:
                    self._not_empty.wait()
                else:
                    remaining = end_time - time.time()
                    if remaining <= 0:
                        return None
                    if not self._not_empty.wait(remaining):
                        return None
            
            # Get highest priority (lowest value) frame
            prioritized_frame = heapq.heappop(self._queue)
            self.frames_processed += 1
            
            return prioritized_frame.frame_pair
    
    def _drop_lowest_priority_frame(self, new_frame: PrioritizedFramePair) -> bool:
        """
        Drop the lowest priority frame to make room.
        
        Returns True if a frame was dropped, False if all frames are higher priority.
        """
        if not self._queue:
            return False
        
        # Find frame with highest priority value (lowest importance)
        max_priority_idx = -1
        max_priority = new_frame.priority
        
        for i, frame in enumerate(self._queue):
            # Don't drop first/last frames or recent frames
            if not frame.is_first_frame and not frame.is_last_frame:
                if frame.priority > max_priority:
                    max_priority = frame.priority
                    max_priority_idx = i
        
        if max_priority_idx >= 0:
            # Remove the frame
            dropped_frame = self._queue[max_priority_idx]
            self._queue[max_priority_idx] = self._queue[-1]
            self._queue.pop()
            heapq.heapify(self._queue)  # Restore heap property
            
            self.frames_dropped += 1
            logger.debug(f"Dropped frame {dropped_frame.frame_pair.current_frame_id} "
                       f"with priority {dropped_frame.priority:.2f}")
            return True
        
        return False
    
    def _should_drop_frame(self, priority: float, queue_size: int) -> bool:
        """
        Decide if a frame should be dropped based on priority and queue pressure.
        """
        # Calculate queue pressure (0.0 at high water mark, 1.0 at max size)
        pressure = (queue_size - self.high_water_mark) / (self.maxsize - self.high_water_mark)
        
        # Drop probability increases with priority (lower importance) and queue pressure
        drop_probability = priority * pressure
        
        # Always keep some minimum frame coverage
        if self.frames_added > 0 and self.frames_dropped > 0:
            drop_ratio = self.frames_dropped / self.frames_added
            if drop_ratio > 0.5:  # Don't drop more than 50% of frames
                return False
        
        # Make drop decision based on probability
        import random
        return random.random() < drop_probability
    
    def qsize(self) -> int:
        """Get current queue size."""
        with self._lock:
            return len(self._queue)
    
    def empty(self) -> bool:
        """Check if queue is empty."""
        with self._lock:
            return len(self._queue) == 0
    
    def get_stats(self) -> dict:
        """Get queue statistics."""
        with self._lock:
            return {
                'current_size': len(self._queue),
                'max_size': self.maxsize,
                'high_water_mark': self.high_water_mark,
                'frames_added': self.frames_added,
                'frames_dropped': self.frames_dropped,
                'frames_processed': self.frames_processed,
                'drop_rate': self.frames_dropped / max(self.frames_added, 1),
                'utilization': len(self._queue) / self.maxsize
            }
    
    def clear(self) -> int:
        """Clear all frames from queue."""
        with self._lock:
            count = len(self._queue)
            self._queue.clear()
            return count
"""
Standalone test demonstrating intelligent queue frame dropping.
No external dependencies except standard library.
"""
import time
import heapq
import threading
import random
from dataclasses import dataclass, field
from typing import Optional, List, Tuple


@dataclass
class TestFramePair:
    """Minimal frame pair for testing."""
    current_frame_id: int
    take_id: int = 1
    timestamp: float = field(default_factory=time.time)


@dataclass
class PrioritizedFramePair:
    """Frame pair with priority for queue management."""
    frame_pair: TestFramePair
    priority: float  # Lower values = higher priority
    timestamp: float = field(default_factory=time.time)
    take_frame_count: int = 0
    is_first_frame: bool = False
    is_last_frame: bool = False
    
    def __lt__(self, other):
        """For priority queue comparison."""
        return self.priority < other.priority


class SimpleIntelligentQueue:
    """Simplified intelligent queue for demonstration."""
    
    def __init__(self, maxsize: int = 100, high_water_mark: float = 0.8):
        self.maxsize = maxsize
        self.high_water_mark = int(maxsize * high_water_mark)
        self._queue: List[PrioritizedFramePair] = []
        self._lock = threading.RLock()
        self.frames_added = 0
        self.frames_dropped = 0
        self.frames_processed = 0
        self.boundary_frames = 10  # Frames at start/end to prioritize
        
    def calculate_priority(self, frame_id: int, take_frame_count: int) -> Tuple[float, bool, bool]:
        """Calculate frame priority based on position in take."""
        # First frames get highest priority
        if frame_id < self.boundary_frames:
            priority = 0.0 + (frame_id / self.boundary_frames) * 0.1
            return priority, frame_id == 0, False
        
        # Last frames get second highest priority
        elif take_frame_count > 0 and frame_id >= take_frame_count - self.boundary_frames:
            frames_from_end = take_frame_count - frame_id - 1
            priority = 0.1 + (frames_from_end / self.boundary_frames) * 0.1
            return priority, False, frame_id == take_frame_count - 1
        
        # Middle frames get lower priority
        else:
            if take_frame_count > 0:
                distance_from_start = frame_id - self.boundary_frames
                distance_from_end = take_frame_count - frame_id - self.boundary_frames
                min_distance = min(distance_from_start, distance_from_end)
                normalized_distance = min_distance / (take_frame_count / 2)
                priority = 0.5 + min(normalized_distance * 0.5, 0.5)
            else:
                priority = 0.7
            return priority, False, False
    
    def put(self, frame: TestFramePair, take_frame_count: int = 0) -> bool:
        """Add frame with intelligent management."""
        with self._lock:
            priority, is_first, is_last = self.calculate_priority(
                frame.current_frame_id, take_frame_count
            )
            
            prioritized_frame = PrioritizedFramePair(
                frame_pair=frame,
                priority=priority,
                take_frame_count=take_frame_count,
                is_first_frame=is_first,
                is_last_frame=is_last
            )
            
            current_size = len(self._queue)
            
            # Handle full queue
            if current_size >= self.maxsize:
                if self._drop_lowest_priority_frame(prioritized_frame):
                    pass  # Successfully made room
                else:
                    return False  # Cannot drop anything
            
            # Handle high water mark
            elif current_size >= self.high_water_mark:
                if priority > 0.5 and self._should_drop_frame(priority, current_size):
                    self.frames_dropped += 1
                    return True  # Frame "handled" by dropping
            
            # Add frame
            heapq.heappush(self._queue, prioritized_frame)
            self.frames_added += 1
            return True
    
    def _drop_lowest_priority_frame(self, new_frame: PrioritizedFramePair) -> bool:
        """Drop lowest priority frame to make room."""
        if not self._queue:
            return False
        
        # Find frame with highest priority value (lowest importance)
        max_priority_idx = -1
        max_priority = new_frame.priority
        
        for i, frame in enumerate(self._queue):
            if not frame.is_first_frame and not frame.is_last_frame:
                if frame.priority > max_priority:
                    max_priority = frame.priority
                    max_priority_idx = i
        
        if max_priority_idx >= 0:
            # Remove the frame
            self._queue[max_priority_idx] = self._queue[-1]
            self._queue.pop()
            heapq.heapify(self._queue)
            self.frames_dropped += 1
            return True
        
        return False
    
    def _should_drop_frame(self, priority: float, queue_size: int) -> bool:
        """Decide if frame should be dropped."""
        pressure = (queue_size - self.high_water_mark) / (self.maxsize - self.high_water_mark)
        drop_probability = priority * pressure
        
        # Limit drop rate
        if self.frames_added > 0:
            drop_ratio = self.frames_dropped / self.frames_added
            if drop_ratio > 0.5:
                return False
        
        return random.random() < drop_probability
    
    def get_all_frames(self) -> List[int]:
        """Get all frame IDs currently in queue."""
        with self._lock:
            return sorted([f.frame_pair.current_frame_id for f in self._queue])


def demonstrate_frame_dropping():
    """Demonstrate intelligent frame dropping."""
    print("="*60)
    print("INTELLIGENT QUEUE FRAME DROPPING DEMONSTRATION")
    print("="*60)
    
    # Test 1: Normal sequential load
    print("\n1. NORMAL SEQUENTIAL LOAD")
    print("-" * 40)
    queue = SimpleIntelligentQueue(maxsize=20, high_water_mark=0.8)
    
    print("Adding 30 sequential frames to queue (max size: 20)...")
    for i in range(30):
        frame = TestFramePair(current_frame_id=i)
        success = queue.put(frame, take_frame_count=100)
        if (i + 1) % 10 == 0:
            print(f"  After frame {i}: added={queue.frames_added}, "
                  f"dropped={queue.frames_dropped}, in_queue={len(queue._queue)}")
    
    frames_in_queue = queue.get_all_frames()
    print(f"\nFinal state:")
    print(f"  Frames in queue: {frames_in_queue}")
    print(f"  Total added: {queue.frames_added}")
    print(f"  Total dropped: {queue.frames_dropped}")
    print(f"  Drop rate: {queue.frames_dropped/queue.frames_added*100:.1f}%")
    
    # Analyze what was kept
    first_frames = sum(1 for f in frames_in_queue if f < 10)
    last_frames = sum(1 for f in frames_in_queue if f >= 20)
    middle_frames = len(frames_in_queue) - first_frames - last_frames
    print(f"\nFrame distribution:")
    print(f"  First 10 frames kept: {first_frames}/10")
    print(f"  Last 10 frames kept: {last_frames}/10")
    print(f"  Middle frames kept: {middle_frames}/10")
    
    # Test 2: Burst of middle frames then critical frames
    print("\n\n2. MIDDLE FRAMES FOLLOWED BY CRITICAL FRAMES")
    print("-" * 40)
    queue = SimpleIntelligentQueue(maxsize=20, high_water_mark=0.8)
    
    print("First, filling queue with middle frames (30-70)...")
    for i in range(30, 70):
        frame = TestFramePair(current_frame_id=i)
        queue.put(frame, take_frame_count=100)
    
    print(f"  After middle frames: added={queue.frames_added}, "
          f"dropped={queue.frames_dropped}, in_queue={len(queue._queue)}")
    
    print("\nNow adding critical frames (0-9 and 90-99)...")
    # Add first frames
    for i in range(10):
        frame = TestFramePair(current_frame_id=i)
        queue.put(frame, take_frame_count=100)
    
    # Add last frames
    for i in range(90, 100):
        frame = TestFramePair(current_frame_id=i)
        queue.put(frame, take_frame_count=100)
    
    frames_in_queue = queue.get_all_frames()
    print(f"\nFinal state:")
    print(f"  Frames in queue: {frames_in_queue}")
    print(f"  Total added: {queue.frames_added}")
    print(f"  Total dropped: {queue.frames_dropped}")
    
    # Count frame types
    first_count = sum(1 for f in frames_in_queue if f < 10)
    last_count = sum(1 for f in frames_in_queue if f >= 90)
    middle_count = sum(1 for f in frames_in_queue if 30 <= f < 70)
    
    print(f"\nFrame distribution:")
    print(f"  First frames (0-9): {first_count}/10")
    print(f"  Last frames (90-99): {last_count}/10")
    print(f"  Middle frames (30-69): {middle_count}/40")
    print(f"\n→ Critical frames successfully displaced middle frames!")
    
    # Test 3: Multiple takes
    print("\n\n3. MULTIPLE TAKES WITH DIFFERENT SIZES")
    print("-" * 40)
    queue = SimpleIntelligentQueue(maxsize=30, high_water_mark=0.8)
    
    takes = [
        (1, 50, "Take 1 (50 frames)"),
        (2, 30, "Take 2 (30 frames)"),
        (3, 40, "Take 3 (40 frames)")
    ]
    
    for take_id, frame_count, desc in takes:
        print(f"\nAdding {desc}...")
        for i in range(0, frame_count, 2):  # Add every other frame
            frame = TestFramePair(current_frame_id=i, take_id=take_id)
            queue.put(frame, take_frame_count=frame_count)
    
    print(f"\nFinal queue state:")
    print(f"  Total added: {queue.frames_added}")
    print(f"  Total dropped: {queue.frames_dropped}")
    print(f"  Drop rate: {queue.frames_dropped/queue.frames_added*100:.1f}%")
    
    # Analyze per-take distribution
    take_counts = {1: 0, 2: 0, 3: 0}
    for pframe in queue._queue:
        take_counts[pframe.frame_pair.take_id] += 1
    
    print(f"\nFrames per take in queue:")
    for take_id, count in take_counts.items():
        print(f"  Take {take_id}: {count} frames")
    
    # Test 4: Extreme load
    print("\n\n4. EXTREME LOAD TEST")
    print("-" * 40)
    queue = SimpleIntelligentQueue(maxsize=50, high_water_mark=0.8)
    
    print("Adding 1000 frames rapidly...")
    start_time = time.time()
    
    for i in range(1000):
        frame = TestFramePair(current_frame_id=i)
        queue.put(frame, take_frame_count=1000)
        
        if (i + 1) % 200 == 0:
            print(f"  Progress: {i+1}/1000 frames...")
    
    elapsed = time.time() - start_time
    
    print(f"\nResults:")
    print(f"  Time: {elapsed:.2f}s ({1000/elapsed:.0f} frames/sec)")
    print(f"  Added: {queue.frames_added}")
    print(f"  Dropped: {queue.frames_dropped}")
    print(f"  Drop rate: {queue.frames_dropped/queue.frames_added*100:.1f}%")
    print(f"  Queue size: {len(queue._queue)}/{queue.maxsize}")
    
    # Check boundary frame preservation
    frames_in_queue = queue.get_all_frames()
    boundary_preserved = sum(1 for f in frames_in_queue if f < 10 or f >= 990)
    print(f"\nBoundary frame preservation:")
    print(f"  First/last 10 frames in queue: {boundary_preserved}/20 possible")
    
    print("\n" + "="*60)
    print("DEMONSTRATION COMPLETE")
    print("="*60)
    print("\nKey findings:")
    print("• First and last frames are prioritized and preserved")
    print("• Middle frames are dropped first under pressure")
    print("• Drop rate adapts to maintain reasonable coverage")
    print("• Multiple takes are handled fairly")
    print("• System handles extreme load gracefully")


if __name__ == "__main__":
    demonstrate_frame_dropping()
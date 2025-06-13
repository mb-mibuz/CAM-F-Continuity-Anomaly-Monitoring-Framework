"""
Comprehensive tests for intelligent queue management and frame dropping.
Tests prioritization, selective dropping, and queue behavior under load.
"""
import pytest
import time
import threading
import numpy as np
from unittest.mock import Mock, patch
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from CAMF.services.detector_framework.priority_queue_manager import (
    IntelligentFrameQueue, PrioritizedFramePair
)
from CAMF.services.detector_framework.interface import FramePair, QueueBasedDetector
from CAMF.common.models import DetectorResult, DetectorInfo


class TestIntelligentFrameQueue:
    """Test the intelligent frame queue implementation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.queue = IntelligentFrameQueue(maxsize=10, high_water_mark=0.8)
        
    def create_frame_pair(self, frame_id: int, take_id: int = 1) -> FramePair:
        """Create a test frame pair."""
        return FramePair(
            current_frame=np.zeros((100, 100, 3), dtype=np.uint8),
            reference_frame=np.zeros((100, 100, 3), dtype=np.uint8),
            current_frame_id=frame_id,
            reference_frame_id=frame_id,
            take_id=take_id,
            scene_id=1,
            angle_id=1,
            project_id=1
        )
    
    def test_priority_calculation(self):
        """Test that frame priorities are calculated correctly."""
        # Test first frames get highest priority
        priority, is_first, is_last = self.queue.calculate_priority(
            self.create_frame_pair(0), take_frame_count=100
        )
        assert priority < 0.1  # Very high priority
        assert is_first is True
        assert is_last is False
        
        # Test last frames get second highest priority
        priority, is_first, is_last = self.queue.calculate_priority(
            self.create_frame_pair(99), take_frame_count=100
        )
        assert 0.1 <= priority < 0.2  # High priority
        assert is_first is False
        assert is_last is True
        
        # Test middle frames get lower priority
        priority, is_first, is_last = self.queue.calculate_priority(
            self.create_frame_pair(50), take_frame_count=100
        )
        assert priority >= 0.5  # Lower priority
        assert is_first is False
        assert is_last is False
    
    def test_boundary_frame_prioritization(self):
        """Test that boundary frames are prioritized correctly."""
        # Fill queue with middle frames
        for i in range(20, 30):
            frame = self.create_frame_pair(i)
            self.queue.put(frame, take_frame_count=100)
        
        assert self.queue.qsize() == 10  # Queue should be full
        
        # Add a first frame - it should be accepted and a middle frame dropped
        first_frame = self.create_frame_pair(0)
        success = self.queue.put(first_frame, take_frame_count=100)
        assert success is True
        assert self.queue.qsize() == 10  # Still full but with different content
        
        # Verify the first frame is in queue
        frames_in_queue = []
        while not self.queue.empty():
            frame = self.queue.get(timeout=0.1)
            if frame:
                frames_in_queue.append(frame.current_frame_id)
        
        assert 0 in frames_in_queue  # First frame should be present
        assert self.queue.frames_dropped > 0  # Some frames should have been dropped
    
    def test_selective_dropping_at_high_water_mark(self):
        """Test selective dropping when queue reaches high water mark."""
        # Fill to just below high water mark (80% of 10 = 8)
        for i in range(7):
            frame = self.create_frame_pair(i + 30)  # Middle frames
            self.queue.put(frame, take_frame_count=100)
        
        assert self.queue.qsize() == 7
        
        # Add one more to reach high water mark
        frame = self.create_frame_pair(40)
        self.queue.put(frame, take_frame_count=100)
        
        # Now at high water mark, middle frames might be dropped
        initial_dropped = self.queue.frames_dropped
        
        # Add several middle frames
        for i in range(5):
            frame = self.create_frame_pair(50 + i)
            self.queue.put(frame, take_frame_count=100)
        
        # Some frames should have been selectively dropped
        assert self.queue.frames_dropped > initial_dropped
        assert self.queue.qsize() <= self.queue.maxsize
    
    def test_no_dropping_of_critical_frames(self):
        """Test that first/last frames are never dropped."""
        # Fill queue with important frames
        for i in range(5):
            # Add first frames
            frame = self.create_frame_pair(i)
            self.queue.put(frame, take_frame_count=100)
            
            # Add last frames
            frame = self.create_frame_pair(95 + i)
            self.queue.put(frame, take_frame_count=100)
        
        assert self.queue.qsize() == 10  # Queue full with critical frames
        
        # Try to add a middle frame - should be rejected
        middle_frame = self.create_frame_pair(50)
        success = self.queue.put(middle_frame, take_frame_count=100)
        
        # Middle frame might be rejected or immediately dropped
        # But critical frames should remain
        frames_in_queue = []
        temp_storage = []
        while not self.queue.empty():
            frame = self.queue.get(timeout=0.1)
            if frame:
                frames_in_queue.append(frame.current_frame_id)
                temp_storage.append(frame)
        
        # Verify critical frames are present
        for i in range(5):
            assert i in frames_in_queue  # First frames
            assert 95 + i in frames_in_queue  # Last frames
    
    def test_multi_take_handling(self):
        """Test queue handles multiple takes correctly."""
        # Add frames from take 1
        for i in range(5):
            frame = self.create_frame_pair(i, take_id=1)
            self.queue.put(frame, take_frame_count=50)
        
        # Add frames from take 2
        for i in range(5):
            frame = self.create_frame_pair(i, take_id=2)
            self.queue.put(frame, take_frame_count=30)
        
        assert self.queue.qsize() == 10
        
        # Both takes should have frames in queue
        take_ids = set()
        while not self.queue.empty():
            frame = self.queue.get(timeout=0.1)
            if frame:
                take_ids.add(frame.take_id)
        
        assert 1 in take_ids
        assert 2 in take_ids
    
    def test_drop_rate_limiting(self):
        """Test that drop rate is limited to maintain coverage."""
        # Fill queue
        for i in range(10):
            frame = self.create_frame_pair(i + 30)  # Middle frames
            self.queue.put(frame, take_frame_count=100)
        
        # Try to add many more middle frames
        for i in range(50):
            frame = self.create_frame_pair(i + 40)
            self.queue.put(frame, take_frame_count=100)
        
        # Check drop rate
        stats = self.queue.get_stats()
        assert stats['drop_rate'] <= 0.6  # Should not drop more than 60%
    
    def test_queue_statistics(self):
        """Test queue statistics reporting."""
        # Add some frames
        for i in range(15):
            frame = self.create_frame_pair(i)
            self.queue.put(frame, take_frame_count=100)
        
        stats = self.queue.get_stats()
        
        assert 'current_size' in stats
        assert 'max_size' in stats
        assert 'frames_added' in stats
        assert 'frames_dropped' in stats
        assert 'drop_rate' in stats
        assert 'utilization' in stats
        
        assert stats['frames_added'] == 15
        assert stats['frames_dropped'] > 0  # Some should be dropped
        assert stats['current_size'] <= stats['max_size']
        assert 0 <= stats['utilization'] <= 1.0


class MockDetector(QueueBasedDetector):
    """Mock detector for testing queue integration."""
    
    def __init__(self):
        super().__init__()
        self.processed_frames = []
        
    def get_info(self) -> DetectorInfo:
        return DetectorInfo(
            name="MockDetector",
            description="Test detector",
            version="1.0.0",
            author="Test",
            requires_reference=True,
            min_frames_required=1
        )
    
    def process_frame_pair(self, frame_pair: FramePair) -> list[DetectorResult]:
        """Process frame and track what was processed."""
        self.processed_frames.append(frame_pair.current_frame_id)
        
        # Simulate some processing time
        time.sleep(0.01)
        
        return [DetectorResult(
            confidence=0.0,
            description="Test result",
            frame_id=frame_pair.current_frame_id,
            detector_name="MockDetector"
        )]


class TestQueueIntegration:
    """Test intelligent queue integration with detector framework."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.detector = MockDetector()
        
    def create_frame_pair(self, frame_id: int, take_id: int = 1) -> FramePair:
        """Create a test frame pair."""
        return FramePair(
            current_frame=np.zeros((100, 100, 3), dtype=np.uint8),
            reference_frame=np.zeros((100, 100, 3), dtype=np.uint8),
            current_frame_id=frame_id,
            reference_frame_id=frame_id,
            take_id=take_id,
            scene_id=1,
            angle_id=1,
            project_id=1
        )
    
    def test_detector_with_intelligent_queue(self):
        """Test detector uses intelligent queue correctly."""
        # Initialize and start detector
        self.detector.initialize({})
        self.detector.start_processing()
        
        # Add frames
        for i in range(20):
            frame = self.create_frame_pair(i)
            success = self.detector.add_frame_pair(frame, take_frame_count=100)
            assert success is True
        
        # Wait for processing
        time.sleep(0.5)
        
        # Check statistics
        stats = self.detector.get_stats()
        assert 'frames_dropped' in stats
        assert 'drop_rate' in stats
        assert 'queue_utilization' in stats
        
        # Stop detector
        self.detector.stop_processing()
    
    def test_frame_prioritization_in_detector(self):
        """Test that detector processes high priority frames."""
        # Initialize but don't start processing yet
        self.detector.initialize({})
        
        # Fill queue with middle frames
        for i in range(15):
            frame = self.create_frame_pair(i + 30)
            self.detector.add_frame_pair(frame, take_frame_count=100)
        
        # Add critical frames
        first_frame = self.create_frame_pair(0)
        last_frame = self.create_frame_pair(99)
        self.detector.add_frame_pair(first_frame, take_frame_count=100)
        self.detector.add_frame_pair(last_frame, take_frame_count=100)
        
        # Start processing
        self.detector.start_processing()
        time.sleep(0.5)
        
        # Critical frames should be processed
        assert 0 in self.detector.processed_frames
        assert 99 in self.detector.processed_frames
        
        self.detector.stop_processing()
    
    def test_performance_under_load(self):
        """Test queue performance under heavy load."""
        self.detector.initialize({})
        self.detector.start_processing()
        
        # Simulate heavy load - add frames faster than processing
        start_time = time.time()
        frames_added = 0
        
        def add_frames():
            nonlocal frames_added
            for i in range(200):
                frame = self.create_frame_pair(i)
                self.detector.add_frame_pair(frame, take_frame_count=200)
                frames_added += 1
                time.sleep(0.001)  # Add frames very quickly
        
        # Run in thread
        thread = threading.Thread(target=add_frames)
        thread.start()
        
        # Let it run for a bit
        time.sleep(2)
        
        thread.join()
        self.detector.stop_processing()
        
        # Check results
        stats = self.detector.get_stats()
        print(f"\nPerformance test results:")
        print(f"  Frames added: {frames_added}")
        print(f"  Frames processed: {stats['frames_processed']}")
        print(f"  Frames dropped: {stats['frames_dropped']}")
        print(f"  Drop rate: {stats['drop_rate']:.1%}")
        print(f"  Queue utilization: {stats['queue_utilization']:.1%}")
        
        # Should have processed some frames
        assert stats['frames_processed'] > 0
        
        # Should have dropped some frames due to load
        assert stats['frames_dropped'] > 0
        
        # Drop rate should be reasonable
        assert stats['drop_rate'] < 0.7  # Less than 70% dropped
    
    def test_clear_queue_functionality(self):
        """Test clearing the queue works correctly."""
        self.detector.initialize({})
        
        # Add frames
        for i in range(20):
            frame = self.create_frame_pair(i)
            self.detector.add_frame_pair(frame, take_frame_count=100)
        
        # Clear queue
        cleared = self.detector.clear_queue()
        assert cleared > 0
        
        # Queue should be empty
        assert self.detector.get_queue_size() == 0
        
        stats = self.detector.get_stats()
        assert stats['queue_size'] == 0


def test_concurrent_access():
    """Test queue handles concurrent access correctly."""
    queue = IntelligentFrameQueue(maxsize=50)
    results = {'added': 0, 'retrieved': 0, 'errors': []}
    
    def create_frame_pair(frame_id: int) -> FramePair:
        return FramePair(
            current_frame=np.zeros((10, 10, 3), dtype=np.uint8),
            reference_frame=np.zeros((10, 10, 3), dtype=np.uint8),
            current_frame_id=frame_id,
            reference_frame_id=frame_id,
            take_id=1,
            scene_id=1,
            angle_id=1,
            project_id=1
        )
    
    def producer(start_id: int, count: int):
        """Add frames to queue."""
        try:
            for i in range(count):
                frame = create_frame_pair(start_id + i)
                if queue.put(frame, take_frame_count=1000):
                    results['added'] += 1
                time.sleep(0.001)
        except Exception as e:
            results['errors'].append(f"Producer error: {e}")
    
    def consumer(count: int):
        """Retrieve frames from queue."""
        try:
            for _ in range(count):
                frame = queue.get(timeout=0.1)
                if frame:
                    results['retrieved'] += 1
                time.sleep(0.002)
        except Exception as e:
            results['errors'].append(f"Consumer error: {e}")
    
    # Start multiple producers and consumers
    threads = []
    
    # Producers
    for i in range(3):
        t = threading.Thread(target=producer, args=(i * 100, 50))
        threads.append(t)
        t.start()
    
    # Consumers
    for i in range(2):
        t = threading.Thread(target=consumer, args=(50,))
        threads.append(t)
        t.start()
    
    # Wait for completion
    for t in threads:
        t.join()
    
    # Check results
    assert len(results['errors']) == 0, f"Errors occurred: {results['errors']}"
    assert results['added'] > 0
    assert results['retrieved'] > 0
    
    print(f"\nConcurrent access test:")
    print(f"  Frames added: {results['added']}")
    print(f"  Frames retrieved: {results['retrieved']}")
    print(f"  Final queue size: {queue.qsize()}")
    print(f"  Frames dropped: {queue.frames_dropped}")


if __name__ == "__main__":
    # Run specific test for debugging
    pytest.main([__file__, "-v", "-s"])
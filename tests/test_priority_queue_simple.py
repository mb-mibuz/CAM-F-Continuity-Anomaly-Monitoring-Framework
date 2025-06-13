"""
Simple test for priority queue without complex dependencies.
Can be run directly with: python test_priority_queue_simple.py
"""
import sys
import os
import time
import numpy as np

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the module directly to avoid __init__.py dependencies
import importlib.util
spec = importlib.util.spec_from_file_location(
    "priority_queue_manager",
    os.path.join(os.path.dirname(__file__), '..', 'CAMF', 'services', 'detector_framework', 'priority_queue_manager.py')
)
priority_queue_manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(priority_queue_manager)
IntelligentFrameQueue = priority_queue_manager.IntelligentFrameQueue

# Create a minimal FramePair for testing
class SimpleFramePair:
    def __init__(self, frame_id, take_id=1):
        self.current_frame = np.zeros((10, 10, 3), dtype=np.uint8)
        self.reference_frame = np.zeros((10, 10, 3), dtype=np.uint8)
        self.current_frame_id = frame_id
        self.reference_frame_id = frame_id
        self.take_id = take_id
        self.scene_id = 1
        self.angle_id = 1
        self.project_id = 1
        self.timestamp = time.time()
        self.metadata = {}


def test_priority_calculation():
    """Test frame priority calculation."""
    print("\n=== Testing Priority Calculation ===")
    
    queue = IntelligentFrameQueue(maxsize=20, high_water_mark=0.8)
    
    # Test first frames (should get highest priority)
    for i in range(5):
        frame = SimpleFramePair(i)
        priority, is_first, is_last = queue.calculate_priority(frame, take_frame_count=100)
        print(f"Frame {i}: priority={priority:.3f}, is_first={is_first}, is_last={is_last}")
        assert priority < 0.1, f"First frame {i} should have very high priority"
        assert is_first == (i == 0), f"Only frame 0 should be marked as first"
    
    # Test last frames (should get second highest priority)
    for i in range(95, 100):
        frame = SimpleFramePair(i)
        priority, is_first, is_last = queue.calculate_priority(frame, take_frame_count=100)
        print(f"Frame {i}: priority={priority:.3f}, is_first={is_first}, is_last={is_last}")
        assert 0.1 <= priority < 0.2, f"Last frame {i} should have high priority"
        assert is_last == (i == 99), f"Only frame 99 should be marked as last"
    
    # Test middle frames (should get lower priority)
    for i in [40, 50, 60]:
        frame = SimpleFramePair(i)
        priority, is_first, is_last = queue.calculate_priority(frame, take_frame_count=100)
        print(f"Frame {i}: priority={priority:.3f}, is_first={is_first}, is_last={is_last}")
        assert priority >= 0.5, f"Middle frame {i} should have lower priority"
        assert not is_first and not is_last
    
    print("✓ Priority calculation test passed!")


def test_frame_dropping():
    """Test intelligent frame dropping behavior."""
    print("\n=== Testing Frame Dropping ===")
    
    queue = IntelligentFrameQueue(maxsize=10, high_water_mark=0.8)
    
    # Fill queue with middle frames
    print("\nFilling queue with middle frames...")
    for i in range(30, 45):
        frame = SimpleFramePair(i)
        success = queue.put(frame, take_frame_count=100)
        print(f"  Added frame {i}: success={success}, queue_size={queue.qsize()}")
    
    print(f"\nQueue stats after filling: {queue.get_stats()}")
    
    # Now add a first frame - it should be accepted and a middle frame dropped
    print("\nAdding first frame (high priority)...")
    first_frame = SimpleFramePair(0)
    success = queue.put(first_frame, take_frame_count=100)
    print(f"  Added frame 0: success={success}")
    print(f"  Frames dropped so far: {queue.frames_dropped}")
    
    # Verify first frame is in queue
    frames_found = []
    temp_storage = []
    while not queue.empty():
        frame = queue.get(timeout=0.1)
        if frame:
            frames_found.append(frame.current_frame_id)
            temp_storage.append(frame)
    
    print(f"\nFrames in queue: {sorted(frames_found)}")
    assert 0 in frames_found, "First frame should be in queue"
    assert queue.frames_dropped > 0, "Some frames should have been dropped"
    
    print("✓ Frame dropping test passed!")


def test_queue_under_load():
    """Test queue behavior under heavy load."""
    print("\n=== Testing Queue Under Load ===")
    
    queue = IntelligentFrameQueue(maxsize=50, high_water_mark=0.8)
    
    # Simulate rapid frame addition
    print("\nAdding 200 frames rapidly...")
    start_time = time.time()
    
    for i in range(200):
        frame = SimpleFramePair(i)
        queue.put(frame, take_frame_count=200)
        
        # Print progress every 50 frames
        if (i + 1) % 50 == 0:
            stats = queue.get_stats()
            print(f"  After {i+1} frames: queue_size={stats['current_size']}, "
                  f"dropped={stats['frames_dropped']}, drop_rate={stats['drop_rate']:.1%}")
    
    elapsed = time.time() - start_time
    final_stats = queue.get_stats()
    
    print(f"\nFinal statistics:")
    print(f"  Time elapsed: {elapsed:.2f}s")
    print(f"  Frames/second: {200/elapsed:.0f}")
    print(f"  Total dropped: {final_stats['frames_dropped']}")
    print(f"  Drop rate: {final_stats['drop_rate']:.1%}")
    print(f"  Queue utilization: {final_stats['utilization']:.1%}")
    
    # Check which frames made it through
    boundary_frames = 0
    middle_frames = 0
    
    while not queue.empty():
        frame = queue.get(timeout=0.1)
        if frame:
            if frame.current_frame_id < 10 or frame.current_frame_id >= 190:
                boundary_frames += 1
            else:
                middle_frames += 1
    
    print(f"\nFrame distribution in final queue:")
    print(f"  Boundary frames (first/last): {boundary_frames}")
    print(f"  Middle frames: {middle_frames}")
    
    # Boundary frames should be prioritized
    if boundary_frames + middle_frames > 0:
        boundary_ratio = boundary_frames / (boundary_frames + middle_frames)
        print(f"  Boundary frame ratio: {boundary_ratio:.1%}")
        assert boundary_ratio > 0.3, "Boundary frames should be well represented"
    
    print("✓ Load test passed!")


def test_multi_take_handling():
    """Test handling of multiple takes."""
    print("\n=== Testing Multi-Take Handling ===")
    
    queue = IntelligentFrameQueue(maxsize=20, high_water_mark=0.8)
    
    # Add frames from multiple takes
    print("\nAdding frames from 3 different takes...")
    
    for take_id in [1, 2, 3]:
        print(f"\nTake {take_id}:")
        for i in range(0, 30, 5):
            frame = SimpleFramePair(i, take_id=take_id)
            success = queue.put(frame, take_frame_count=50)
            print(f"  Frame {i}: success={success}")
    
    # Check distribution
    take_counts = {1: 0, 2: 0, 3: 0}
    frame_ids = {1: [], 2: [], 3: []}
    
    while not queue.empty():
        frame = queue.get(timeout=0.1)
        if frame:
            take_counts[frame.take_id] += 1
            frame_ids[frame.take_id].append(frame.current_frame_id)
    
    print(f"\nFrames per take in final queue:")
    for take_id in [1, 2, 3]:
        print(f"  Take {take_id}: {take_counts[take_id]} frames - {sorted(frame_ids[take_id])}")
    
    # All takes should have some representation
    for take_id in [1, 2, 3]:
        assert take_counts[take_id] > 0, f"Take {take_id} should have frames in queue"
    
    print("✓ Multi-take test passed!")


def run_all_tests():
    """Run all tests."""
    print("="*60)
    print("INTELLIGENT QUEUE TESTS")
    print("="*60)
    
    try:
        test_priority_calculation()
        test_frame_dropping()
        test_queue_under_load()
        test_multi_take_handling()
        
        print("\n" + "="*60)
        print("ALL TESTS PASSED! ✓")
        print("="*60)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
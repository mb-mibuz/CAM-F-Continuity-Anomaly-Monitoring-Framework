"""
Visual demonstration of intelligent queue frame dropping behavior.
Shows which frames are kept and which are dropped under various load scenarios.
"""
import sys
import os
import time
import numpy as np
from typing import List, Tuple
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from CAMF.services.detector_framework.priority_queue_manager import IntelligentFrameQueue
from CAMF.services.detector_framework.interface import FramePair


class QueueVisualizer:
    """Visualize queue behavior and frame dropping patterns."""
    
    def __init__(self, queue_size: int = 20, high_water_mark: float = 0.8):
        self.queue = IntelligentFrameQueue(maxsize=queue_size, high_water_mark=high_water_mark)
        self.frame_history = []  # Track all frames added
        self.processed_frames = []  # Track frames that made it through
        self.dropped_frames = []  # Track explicitly dropped frames
        
    def create_frame_pair(self, frame_id: int, take_id: int = 1) -> FramePair:
        """Create a test frame pair."""
        return FramePair(
            current_frame=np.zeros((10, 10, 3), dtype=np.uint8),
            reference_frame=np.zeros((10, 10, 3), dtype=np.uint8),
            current_frame_id=frame_id,
            reference_frame_id=frame_id,
            take_id=take_id,
            scene_id=1,
            angle_id=1,
            project_id=1
        )
    
    def simulate_scenario(self, scenario_name: str, frame_pattern: List[Tuple[int, int]]):
        """
        Simulate a frame addition scenario.
        
        Args:
            scenario_name: Name of the scenario
            frame_pattern: List of (frame_id, take_frame_count) tuples
        """
        print(f"\n=== Simulating: {scenario_name} ===")
        
        # Reset state
        self.queue = IntelligentFrameQueue(
            maxsize=self.queue.maxsize, 
            high_water_mark=self.queue.high_water_mark
        )
        self.frame_history = []
        self.processed_frames = []
        self.dropped_frames = []
        
        # Track initial stats
        initial_dropped = 0
        
        # Add frames according to pattern
        for frame_id, take_frame_count in frame_pattern:
            frame = self.create_frame_pair(frame_id)
            
            # Track frame
            self.frame_history.append({
                'frame_id': frame_id,
                'take_frame_count': take_frame_count,
                'queue_size_before': self.queue.qsize(),
                'dropped_before': self.queue.frames_dropped
            })
            
            # Add to queue
            success = self.queue.put(frame, take_frame_count)
            
            # Check if frame was dropped
            new_dropped = self.queue.frames_dropped - initial_dropped
            if new_dropped > len(self.dropped_frames):
                self.dropped_frames.append(frame_id)
            
            initial_dropped = self.queue.frames_dropped
        
        # Process all frames from queue
        while not self.queue.empty():
            frame = self.queue.get(timeout=0.1)
            if frame:
                self.processed_frames.append(frame.current_frame_id)
        
        # Print summary
        print(f"Total frames added: {len(self.frame_history)}")
        print(f"Frames processed: {len(self.processed_frames)}")
        print(f"Frames dropped: {self.queue.frames_dropped}")
        print(f"Drop rate: {self.queue.frames_dropped / len(self.frame_history) * 100:.1f}%")
        
        return {
            'name': scenario_name,
            'history': self.frame_history,
            'processed': self.processed_frames,
            'dropped': self.dropped_frames,
            'stats': self.queue.get_stats()
        }
    
    def visualize_results(self, results: List[dict]):
        """Create visualization of frame dropping patterns."""
        fig, axes = plt.subplots(len(results), 1, figsize=(14, 4 * len(results)))
        if len(results) == 1:
            axes = [axes]
        
        for idx, result in enumerate(results):
            ax = axes[idx]
            ax.set_title(f"{result['name']} - Drop Rate: {result['stats']['drop_rate']:.1%}")
            
            # Create timeline visualization
            all_frames = [h['frame_id'] for h in result['history']]
            max_frame = max(all_frames) if all_frames else 100
            
            # Plot each frame as a bar
            for frame_info in result['history']:
                frame_id = frame_info['frame_id']
                x = frame_id
                
                # Determine color based on frame position
                if frame_id < 10:  # First frames
                    color = 'green'
                    label = 'First frames (high priority)'
                elif frame_id >= max_frame - 10:  # Last frames
                    color = 'orange'
                    label = 'Last frames (high priority)'
                else:  # Middle frames
                    color = 'blue'
                    label = 'Middle frames (low priority)'
                
                # Check if frame was processed or dropped
                if frame_id in result['processed']:
                    alpha = 1.0
                    edgecolor = 'black'
                    linewidth = 1
                else:
                    alpha = 0.3
                    edgecolor = 'red'
                    linewidth = 2
                
                rect = Rectangle((x - 0.4, 0), 0.8, 1, 
                               facecolor=color, alpha=alpha,
                               edgecolor=edgecolor, linewidth=linewidth)
                ax.add_patch(rect)
            
            # Set axis properties
            ax.set_xlim(-1, max_frame + 1)
            ax.set_ylim(0, 1.5)
            ax.set_xlabel('Frame ID')
            ax.set_yticks([])
            
            # Add legend
            from matplotlib.patches import Patch
            legend_elements = [
                Patch(facecolor='green', label='First frames (high priority)'),
                Patch(facecolor='orange', label='Last frames (high priority)'),
                Patch(facecolor='blue', label='Middle frames (low priority)'),
                Patch(facecolor='gray', alpha=0.3, edgecolor='red', 
                      linewidth=2, label='Dropped frames')
            ]
            ax.legend(handles=legend_elements, loc='upper right')
            
            # Add queue stats
            stats_text = f"Queue: {result['stats']['current_size']}/{result['stats']['max_size']}"
            ax.text(0.02, 0.95, stats_text, transform=ax.transAxes, 
                   verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat'))
        
        plt.tight_layout()
        return fig


def run_demonstrations():
    """Run various demonstration scenarios."""
    visualizer = QueueVisualizer(queue_size=20, high_water_mark=0.8)
    results = []
    
    # Scenario 1: Normal load - sequential frames
    print("\n" + "="*60)
    print("SCENARIO 1: Normal Sequential Load")
    print("="*60)
    pattern = [(i, 100) for i in range(30)]
    results.append(visualizer.simulate_scenario("Normal Sequential Load", pattern))
    
    # Scenario 2: Burst at beginning
    print("\n" + "="*60)
    print("SCENARIO 2: Burst at Beginning")
    print("="*60)
    pattern = [(i, 100) for i in range(50)]  # Many frames quickly
    results.append(visualizer.simulate_scenario("Burst at Beginning", pattern))
    
    # Scenario 3: Mixed priority frames
    print("\n" + "="*60)
    print("SCENARIO 3: Mixed Priority Frames")
    print("="*60)
    pattern = []
    # Add middle frames first
    for i in range(30, 70):
        pattern.append((i, 100))
    # Then add critical frames
    for i in range(5):
        pattern.append((i, 100))  # First frames
        pattern.append((95 + i, 100))  # Last frames
    results.append(visualizer.simulate_scenario("Mixed Priority Frames", pattern))
    
    # Scenario 4: Multiple takes
    print("\n" + "="*60)
    print("SCENARIO 4: Multiple Takes")
    print("="*60)
    pattern = []
    # Take 1 (50 frames)
    for i in range(0, 50, 2):
        pattern.append((i, 50))
    # Take 2 (30 frames) 
    for i in range(0, 30, 2):
        pattern.append((i, 30))
    results.append(visualizer.simulate_scenario("Multiple Takes", pattern))
    
    # Create visualization
    fig = visualizer.visualize_results(results)
    
    # Save or show
    output_path = "intelligent_queue_demonstration.png"
    fig.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\nVisualization saved to: {output_path}")
    
    # Also create a detailed report
    create_detailed_report(results)


def create_detailed_report(results: List[dict]):
    """Create a detailed text report of the results."""
    report_path = "intelligent_queue_report.txt"
    
    with open(report_path, 'w') as f:
        f.write("INTELLIGENT QUEUE FRAME DROPPING ANALYSIS\n")
        f.write("=" * 60 + "\n\n")
        
        for result in results:
            f.write(f"Scenario: {result['name']}\n")
            f.write("-" * 40 + "\n")
            
            # Statistics
            stats = result['stats']
            f.write(f"Queue Configuration:\n")
            f.write(f"  Max Size: {stats['max_size']}\n")
            f.write(f"  High Water Mark: {stats['high_water_mark']}\n")
            f.write(f"\nResults:\n")
            f.write(f"  Total Frames Added: {stats['frames_added']}\n")
            f.write(f"  Frames Processed: {stats['frames_processed']}\n")
            f.write(f"  Frames Dropped: {stats['frames_dropped']}\n")
            f.write(f"  Drop Rate: {stats['drop_rate']:.1%}\n")
            f.write(f"  Final Queue Utilization: {stats['utilization']:.1%}\n")
            
            # Analyze which frames were kept/dropped
            processed = set(result['processed'])
            all_frames = [h['frame_id'] for h in result['history']]
            
            first_frames_kept = sum(1 for f in processed if f < 10)
            last_frames_kept = sum(1 for f in processed if f >= 90)
            middle_frames_kept = len(processed) - first_frames_kept - last_frames_kept
            
            f.write(f"\nFrame Priority Analysis:\n")
            f.write(f"  First frames (0-9) kept: {first_frames_kept}\n")
            f.write(f"  Last frames (90-99) kept: {last_frames_kept}\n")
            f.write(f"  Middle frames kept: {middle_frames_kept}\n")
            
            f.write("\n" + "=" * 60 + "\n\n")
    
    print(f"\nDetailed report saved to: {report_path}")


def test_extreme_scenarios():
    """Test extreme scenarios to verify robustness."""
    print("\n" + "="*60)
    print("EXTREME SCENARIO TESTS")
    print("="*60)
    
    # Test 1: All critical frames
    print("\nTest 1: Queue full of critical frames")
    queue = IntelligentFrameQueue(maxsize=10)
    
    # Fill with first/last frames only
    for i in range(10):
        if i < 5:
            frame = FramePair(
                current_frame=np.zeros((10, 10, 3)),
                reference_frame=np.zeros((10, 10, 3)),
                current_frame_id=i,
                reference_frame_id=i,
                take_id=1,
                scene_id=1,
                angle_id=1,
                project_id=1
            )
        else:
            frame = FramePair(
                current_frame=np.zeros((10, 10, 3)),
                reference_frame=np.zeros((10, 10, 3)),
                current_frame_id=95 + (i - 5),
                reference_frame_id=95 + (i - 5),
                take_id=1,
                scene_id=1,
                angle_id=1,
                project_id=1
            )
        queue.put(frame, 100)
    
    # Try to add middle frame - should fail
    middle_frame = FramePair(
        current_frame=np.zeros((10, 10, 3)),
        reference_frame=np.zeros((10, 10, 3)),
        current_frame_id=50,
        reference_frame_id=50,
        take_id=1,
        scene_id=1,
        angle_id=1,
        project_id=1
    )
    success = queue.put(middle_frame, 100)
    
    print(f"  Queue size: {queue.qsize()}")
    print(f"  Middle frame accepted: {success}")
    print(f"  Frames dropped: {queue.frames_dropped}")
    
    # Test 2: Rapid fire frames
    print("\nTest 2: Rapid fire frame addition")
    queue = IntelligentFrameQueue(maxsize=50)
    
    start_time = time.time()
    frames_added = 0
    
    for i in range(1000):
        frame = FramePair(
            current_frame=np.zeros((10, 10, 3)),
            reference_frame=np.zeros((10, 10, 3)),
            current_frame_id=i,
            reference_frame_id=i,
            take_id=1,
            scene_id=1,
            angle_id=1,
            project_id=1
        )
        if queue.put(frame, 1000):
            frames_added += 1
    
    elapsed = time.time() - start_time
    
    print(f"  Time elapsed: {elapsed:.2f}s")
    print(f"  Frames added: {frames_added}")
    print(f"  Frames/second: {frames_added/elapsed:.0f}")
    print(f"  Drop rate: {queue.frames_dropped/1000*100:.1f}%")


if __name__ == "__main__":
    # Run demonstrations
    run_demonstrations()
    
    # Run extreme tests
    test_extreme_scenarios()
    
    print("\nAll tests completed!")
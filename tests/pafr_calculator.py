#!/usr/bin/env python3
"""
Production-Aligned Frame Rate (PAFR) Calculator

This tool calculates the maximum sustainable capture frame rate for continuity
detection systems during film production, accounting for processing backlogs
during takes and recovery during reset windows.

The PAFR metric ensures that all frame processing completes before the next
take begins, preventing production delays.
"""

import argparse
import sys
from typing import Tuple

def calculate_pafr(time_to_detect: float, take_duration: float = 45.0, 
                   reset_window: float = 300.0) -> Tuple[float, float, float]:
    """
    Calculate Production-Aligned Frame Rate (PAFR) metrics.
    
    Args:
        time_to_detect: Time to process one frame pair (seconds)
        take_duration: Typical take duration (seconds), default 45s
        reset_window: Reset time between takes (seconds), default 300s (5 min)
    
    Returns:
        Tuple of (strict_realtime_fps, production_realtime_fps, frames_sampled_ratio)
    """
    # Strict real-time: processing keeps pace with capture
    strict_realtime_fps = 1.0 / time_to_detect
    
    # Production real-time: frames queue during filming but clear during reset
    # Maximum sustainable frame rate: y_max = (R/S + 1) / x
    production_realtime_fps = ((reset_window / take_duration) + 1) / time_to_detect
    
    # Calculate how many frames get sampled from a 24fps stream
    standard_fps = 24.0
    frames_sampled_ratio = standard_fps / production_realtime_fps if production_realtime_fps > 0 else float('inf')
    
    return strict_realtime_fps, production_realtime_fps, frames_sampled_ratio

def calculate_backlog_time(fps: float, time_to_detect: float, take_duration: float) -> float:
    """
    Calculate time needed to clear processing backlog after a take.
    
    Args:
        fps: Capture frame rate
        time_to_detect: Time to process one frame pair (seconds)
        take_duration: Take duration (seconds)
    
    Returns:
        Time needed to clear backlog (seconds)
    """
    if fps <= 1.0 / time_to_detect:
        return 0  # No backlog if processing keeps up
    
    # Backlog clearing time: T_clear = S * (y * x - 1)
    return take_duration * (fps * time_to_detect - 1)

def print_analysis(detector_name: str, time_to_detect: float, 
                   take_duration: float, reset_window: float):
    """Print detailed PAFR analysis for a detector."""
    
    strict_fps, pafr, sample_ratio = calculate_pafr(time_to_detect, take_duration, reset_window)
    
    print(f"\n{'='*60}")
    print(f"PAFR Analysis for: {detector_name}")
    print(f"{'='*60}")
    print(f"Time to detect per frame pair: {time_to_detect:.2f} seconds")
    print(f"Take duration: {take_duration:.0f} seconds")
    print(f"Reset window: {reset_window:.0f} seconds")
    print(f"\nResults:")
    print(f"  Strict real-time capability: {strict_fps:.2f} fps")
    print(f"  Production-aligned frame rate (PAFR): {pafr:.2f} fps")
    print(f"  Sampling ratio: 1 in every {sample_ratio:.0f} frames from 24fps")
    
    # Check various capture rates
    print(f"\nBacklog clearing times for different capture rates:")
    for test_fps in [0.5, 1.0, 2.0, 4.0, 6.0, 8.0, 12.0, 24.0]:
        backlog_time = calculate_backlog_time(test_fps, time_to_detect, take_duration)
        if backlog_time <= reset_window:
            status = "✓ Sustainable" if test_fps <= pafr else "⚠ Marginal"
        else:
            status = "✗ Unsustainable"
        print(f"  {test_fps:4.1f} fps: {backlog_time:6.1f}s to clear backlog - {status}")
    
    # Production viability assessment
    print(f"\nProduction Viability:")
    if pafr >= 1.0:
        print(f"  ✓ System can process at {pafr:.1f} fps during production")
        print(f"  ✓ All frames processed before next take begins")
    else:
        print(f"  ⚠ System limited to {pafr:.2f} fps")
        print(f"  ⚠ May miss some continuity errors between sampled frames")

def main():
    parser = argparse.ArgumentParser(
        description="Calculate Production-Aligned Frame Rate (PAFR) for continuity detectors",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Calculate PAFR for ClockDetector (1.92s detection time)
  python pafr_calculator.py 1.92 --name ClockDetector
  
  # Calculate for custom production timing (30s takes, 2min resets)
  python pafr_calculator.py 6.37 --take 30 --reset 120 --name DifferenceDetector
  
  # Compare multiple detectors
  python pafr_calculator.py 1.92 6.37 0.5 --name Clock Difference FastDetector
        """
    )
    
    parser.add_argument('detection_times', type=float, nargs='+',
                        help='Time to detect per frame pair in seconds')
    parser.add_argument('--take', '-t', type=float, default=45.0,
                        help='Take duration in seconds (default: 45)')
    parser.add_argument('--reset', '-r', type=float, default=300.0,
                        help='Reset window between takes in seconds (default: 300)')
    parser.add_argument('--name', '-n', type=str, nargs='*',
                        help='Names for the detectors (optional)')
    
    args = parser.parse_args()
    
    # Validate inputs
    if any(t <= 0 for t in args.detection_times):
        print("Error: Detection times must be positive", file=sys.stderr)
        sys.exit(1)
    
    if args.take <= 0 or args.reset <= 0:
        print("Error: Take duration and reset window must be positive", file=sys.stderr)
        sys.exit(1)
    
    # Prepare detector names
    if args.name:
        names = args.name[:len(args.detection_times)]
        names.extend([f"Detector {i+1}" for i in range(len(names), len(args.detection_times))])
    else:
        names = [f"Detector {i+1}" for i in range(len(args.detection_times))]
    
    # Analyze each detector
    for name, ttd in zip(names, args.detection_times):
        print_analysis(name, ttd, args.take, args.reset)
    
    # If multiple detectors, show system-wide constraint
    if len(args.detection_times) > 1:
        print(f"\n{'='*60}")
        print("System-Wide Analysis")
        print(f"{'='*60}")
        
        # Find slowest detector
        slowest_idx = args.detection_times.index(max(args.detection_times))
        slowest_name = names[slowest_idx]
        slowest_ttd = args.detection_times[slowest_idx]
        _, slowest_pafr, _ = calculate_pafr(slowest_ttd, args.take, args.reset)
        
        print(f"Bottleneck: {slowest_name} ({slowest_ttd:.2f}s per frame)")
        print(f"System constrained to: {slowest_pafr:.2f} fps")
        print("\nRecommendation: Run detectors selectively based on production needs")

if __name__ == "__main__":
    main()
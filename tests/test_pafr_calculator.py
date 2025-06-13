#!/usr/bin/env python3
"""
Test script for PAFR calculator - demonstrates usage with CAM-F detectors
"""

import subprocess
import sys

def run_pafr_analysis():
    """Run PAFR analysis for CAM-F detectors."""
    
    print("CAM-F Production-Aligned Frame Rate (PAFR) Analysis")
    print("=" * 70)
    
    # Test with default production timing (45s takes, 300s resets)
    print("\n1. Testing with standard production timing (45s takes, 5min resets):")
    subprocess.run([
        sys.executable, "pafr_calculator.py", 
        "1.92", "6.37",  # ClockDetector and DifferenceDetector times
        "--name", "ClockDetector", "DifferenceDetector"
    ])
    
    # Test with shorter production timing
    print("\n\n2. Testing with rapid production timing (30s takes, 2min resets):")
    subprocess.run([
        sys.executable, "pafr_calculator.py", 
        "1.92", "6.37",
        "--take", "30", "--reset", "120",
        "--name", "ClockDetector", "DifferenceDetector"
    ])
    
    # Test with a hypothetical fast detector
    print("\n\n3. Testing with hypothetical improved detector (0.5s detection):")
    subprocess.run([
        sys.executable, "pafr_calculator.py", 
        "0.5",
        "--name", "ImprovedDetector"
    ])

if __name__ == "__main__":
    run_pafr_analysis()
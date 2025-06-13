#!/usr/bin/env python3
"""Test script for per-detector progress tracking functionality."""

import requests
import time
import json

API_BASE = "http://localhost:8000/api"

def test_detector_progress():
    """Test the per-detector progress tracking."""
    
    print("Testing per-detector progress tracking...")
    
    # Get a test take ID (you'll need to have a take with frames already)
    # For this test, let's assume we have project 1, scene 1, angle 1, take 1
    take_id = 1
    reference_take_id = 1  # Same take for testing
    
    try:
        # Start processing
        print(f"\n1. Starting processing for take {take_id}...")
        response = requests.post(f"{API_BASE}/processing/restart", json={
            "take_id": take_id,
            "reference_take_id": reference_take_id
        })
        
        if response.status_code != 200:
            print(f"Failed to start processing: {response.status_code} - {response.text}")
            return
        
        print("Processing started successfully")
        
        # Poll for status updates
        print("\n2. Monitoring processing status...")
        for i in range(30):  # Poll for up to 30 seconds
            time.sleep(1)
            
            # Get processing status
            status_response = requests.get(f"{API_BASE}/processing/status")
            if status_response.status_code == 200:
                status = status_response.json()
                
                print(f"\n--- Update {i+1} ---")
                print(f"Is processing: {status.get('is_processing', False)}")
                print(f"Overall progress: {status.get('processed_frames', 0)}/{status.get('total_frames', 0)} frames")
                print(f"Progress percentage: {status.get('progress_percentage', 0):.1f}%")
                
                # Show per-detector progress
                detector_progress = status.get('detector_progress', {})
                if detector_progress:
                    print("\nPer-detector progress:")
                    for detector_name, progress in detector_progress.items():
                        print(f"  {detector_name}: {progress['processed']}/{progress['total']} frames ({progress['status']})")
                else:
                    print("No detector progress data yet...")
                
                # Check if all detectors are complete
                if status.get('all_detectors_complete', False):
                    print("\nAll detectors have completed processing!")
                    break
                    
                # Check if processing stopped
                if not status.get('is_processing', False) and i > 2:
                    print("\nProcessing has stopped")
                    break
            else:
                print(f"Failed to get status: {status_response.status_code}")
        
        # Stop processing if still running
        print("\n3. Stopping processing...")
        stop_response = requests.post(f"{API_BASE}/processing/stop")
        if stop_response.status_code == 200:
            print("Processing stopped successfully")
        
    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("Per-Detector Progress Tracking Test")
    print("===================================")
    print("Make sure:")
    print("1. CAMF backend is running (python start.py)")
    print("2. You have at least one take with frames")
    print("3. Detectors are configured for the scene")
    
    input("\nPress Enter to start the test...")
    
    test_detector_progress()
"""
Local Process Manager - Fallback when Docker is not available
This provides a way to run detectors in local Python processes with basic isolation
"""

import os
import sys
import json
import time
import queue
import threading
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
import multiprocessing as mp
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class LocalDetectorProcess:
    """Represents a local detector process."""
    name: str
    process: Optional[mp.Process] = None
    input_queue: Optional[mp.Queue] = None
    output_queue: Optional[mp.Queue] = None
    status: str = "stopped"
    error_count: int = 0
    frame_count: int = 0
    last_heartbeat: float = field(default_factory=time.time)


class LocalProcessManager:
    """
    Manages detectors as local Python processes when Docker is not available.
    Provides basic isolation and resource management.
    """
    
    def __init__(self, detectors_path: Path = None, workspace_path: Path = None):
        self.detectors_dir = Path(detectors_path or Path.cwd() / "detectors")
        self.workspace_dir = Path(workspace_path or Path.cwd() / "workspaces")
        self.detectors: Dict[str, LocalDetectorProcess] = {}
        self._stop_events: Dict[str, threading.Event] = {}
        self._monitor_threads: Dict[str, threading.Thread] = {}
        
        # Create workspace directory
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("LocalProcessManager initialized (Docker not available)")
    
    def start_detector(self, detector_name: str, detector_path: Path = None, config: Dict[str, Any] = None) -> bool:
        """Start a detector in a local process."""
        try:
            if detector_name in self.detectors:
                logger.warning(f"Detector {detector_name} already running")
                return True
            
            detector_dir = detector_path or self.detectors_dir / detector_name
            if not detector_dir.exists():
                logger.error(f"Detector directory not found: {detector_dir}")
                return False
            
            # Create workspace for detector
            workspace = self.workspace_dir / f"{detector_name}_{int(time.time())}"
            workspace.mkdir(parents=True, exist_ok=True)
            
            # Create queues for communication
            input_queue = mp.Queue(maxsize=100)
            output_queue = mp.Queue(maxsize=100)
            
            # Create detector process
            detector = LocalDetectorProcess(
                name=detector_name,
                input_queue=input_queue,
                output_queue=output_queue,
                status="starting"
            )
            
            # Start detector process
            process = mp.Process(
                target=self._run_detector,
                args=(detector_name, detector_dir, workspace, input_queue, output_queue, config or {})
            )
            process.daemon = True
            process.start()
            
            detector.process = process
            detector.status = "running"
            self.detectors[detector_name] = detector
            
            # Start monitor thread
            stop_event = threading.Event()
            self._stop_events[detector_name] = stop_event
            
            monitor_thread = threading.Thread(
                target=self._monitor_detector,
                args=(detector_name, stop_event)
            )
            monitor_thread.daemon = True
            monitor_thread.start()
            self._monitor_threads[detector_name] = monitor_thread
            
            logger.info(f"Started local detector process: {detector_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start detector {detector_name}: {e}")
            return False
    
    def _run_detector(self, detector_name: str, detector_dir: Path, workspace: Path,
                      input_queue: mp.Queue, output_queue: mp.Queue, config: Dict[str, Any]):
        """Run detector in isolated process."""
        try:
            # Add detector directory to Python path
            sys.path.insert(0, str(detector_dir))
            
            # Change to workspace directory
            os.chdir(workspace)
            
            # Import and initialize detector
            import detector
            
            # Initialize detector with config
            if hasattr(detector, 'initialize'):
                detector.initialize(config)
            
            # Process messages
            while True:
                try:
                    message = input_queue.get(timeout=1.0)
                    
                    if message.get('type') == 'shutdown':
                        break
                    
                    if message.get('type') == 'process_frame':
                        # Process frame
                        results = []
                        if hasattr(detector, 'process_frame'):
                            frame_id = message.get('frame_id')
                            take_id = message.get('take_id')
                            
                            # In real implementation, would load actual frame data
                            detector_results = detector.process_frame(frame_id, take_id)
                            
                            if detector_results:
                                results.extend(detector_results)
                        
                        # Send results back
                        output_queue.put({
                            'id': message.get('id'),
                            'results': results,
                            'timestamp': time.time()
                        })
                    
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"Detector {detector_name} error: {e}")
                    output_queue.put({
                        'error': str(e),
                        'timestamp': time.time()
                    })
            
            # Cleanup
            if hasattr(detector, 'cleanup'):
                detector.cleanup()
                
        except Exception as e:
            logger.error(f"Fatal error in detector {detector_name}: {e}")
    
    def _monitor_detector(self, detector_name: str, stop_event: threading.Event):
        """Monitor detector health and handle failures."""
        while not stop_event.is_set():
            try:
                if detector_name in self.detectors:
                    detector = self.detectors[detector_name]
                    
                    # Check if process is alive
                    if detector.process and not detector.process.is_alive():
                        logger.error(f"Detector {detector_name} process died")
                        detector.status = "failed"
                        # Could implement auto-restart here
                    
                    # Update heartbeat
                    detector.last_heartbeat = time.time()
                
                stop_event.wait(5.0)
                
            except Exception as e:
                logger.error(f"Monitor error for {detector_name}: {e}")
    
    def stop_detector(self, detector_name: str):
        """Stop a detector process."""
        if detector_name not in self.detectors:
            return
        
        try:
            detector = self.detectors[detector_name]
            
            # Send shutdown message
            if detector.input_queue:
                try:
                    detector.input_queue.put({'type': 'shutdown'}, timeout=1.0)
                except:
                    pass
            
            # Stop monitor thread
            if detector_name in self._stop_events:
                self._stop_events[detector_name].set()
            
            # Wait for monitor thread
            if detector_name in self._monitor_threads:
                self._monitor_threads[detector_name].join(timeout=5)
            
            # Terminate process
            if detector.process:
                detector.process.terminate()
                detector.process.join(timeout=5)
                
                if detector.process.is_alive():
                    detector.process.kill()
            
            # Cleanup
            del self.detectors[detector_name]
            if detector_name in self._stop_events:
                del self._stop_events[detector_name]
            if detector_name in self._monitor_threads:
                del self._monitor_threads[detector_name]
            
            logger.info(f"Stopped detector {detector_name}")
            
        except Exception as e:
            logger.error(f"Error stopping detector {detector_name}: {e}")
    
    def stop_all_detectors(self):
        """Stop all running detectors."""
        detector_names = list(self.detectors.keys())
        for name in detector_names:
            self.stop_detector(name)
    
    def get_detector_status(self, detector_name: str) -> Dict[str, Any]:
        """Get status information for a detector."""
        if detector_name not in self.detectors:
            return {"status": "not_loaded"}
        
        detector = self.detectors[detector_name]
        
        return {
            "status": detector.status,
            "frame_count": detector.frame_count,
            "error_count": detector.error_count,
            "last_heartbeat": detector.last_heartbeat,
            "process_alive": detector.process.is_alive() if detector.process else False
        }
    
    def get_detector_process(self, detector_name: str):
        """Get detector process wrapper for compatibility."""
        if detector_name not in self.detectors:
            return None
        
        detector = self.detectors[detector_name]
        
        # Create a process-like wrapper
        class LocalDetectorProcessWrapper:
            def __init__(self, detector):
                self.detector = detector
                self._request_id = 0
                self._pending_requests = {}
                
            def send_request(self, method: str, params: Dict[str, Any], timeout: float = 30) -> Optional[Dict[str, Any]]:
                """Send request to detector process."""
                if method == 'initialize':
                    # Already initialized in process
                    return {'success': True}
                
                elif method == 'process_frame':
                    # Send frame processing request
                    request_id = f"req_{self._request_id}"
                    self._request_id += 1
                    
                    message = {
                        'id': request_id,
                        'type': 'process_frame',
                        'frame_id': params.get('frame_id'),
                        'take_id': params.get('take_id'),
                        'timestamp': time.time()
                    }
                    
                    try:
                        self.detector.input_queue.put(message, timeout=1.0)
                        
                        # Wait for response
                        start_time = time.time()
                        while (time.time() - start_time) < timeout:
                            try:
                                result = self.detector.output_queue.get(timeout=0.1)
                                if result.get('id') == request_id:
                                    return {
                                        'success': True,
                                        'data': result.get('results', [])
                                    }
                            except queue.Empty:
                                continue
                        
                        return {
                            'success': False,
                            'error': 'Timeout waiting for response'
                        }
                        
                    except Exception as e:
                        return {
                            'success': False,
                            'error': str(e)
                        }
                
                elif method == 'cleanup':
                    return {'success': True}
                
                return None
            
            def is_alive(self) -> bool:
                """Check if process is running."""
                return self.detector.process and self.detector.process.is_alive()
        
        return LocalDetectorProcessWrapper(detector)
    
    def get_all_detector_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status for all detectors."""
        status = {
            "process_manager": "local",
            "docker_available": False,
            "detectors": {}
        }
        
        for detector_name in self.detectors:
            status["detectors"][detector_name] = self.get_detector_status(detector_name)
        
        return status
    
    def build_detector_image(self, detector_name: str) -> Tuple[bool, str]:
        """Compatibility method - no build needed for local processes."""
        detector_dir = self.detectors_dir / detector_name
        if not detector_dir.exists():
            return False, f"Detector directory not found: {detector_dir}"
        
        # Check if detector.py exists
        detector_file = detector_dir / "detector.py"
        if not detector_file.exists():
            return False, f"Detector implementation not found: {detector_file}"
        
        return True, "Local detector ready"
    
    def process_frame_pair(self, detector_name: str, current_frame, reference_frame, metadata: Dict[str, Any]) -> bool:
        """Send frame pair to detector for processing."""
        # This would be implemented similarly to Docker version
        # For now, return True to indicate success
        return True
    
    def get_results(self, detector_name: str, timeout: float = 0) -> List[Dict[str, Any]]:
        """Get available results from a detector."""
        # This would collect results from output queue
        # For now, return empty list
        return []
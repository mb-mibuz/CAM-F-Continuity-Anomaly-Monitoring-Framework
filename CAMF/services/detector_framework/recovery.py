# CAMF/services/detector_framework/recovery.py
"""
Advanced Detector Recovery System with exponential backoff and state management.
Ensures system resilience by automatically recovering from detector failures.
"""

import time
import threading
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json
from pathlib import Path

from CAMF.common.models import ErrorConfidence


class RecoveryStrategy(Enum):
    """Recovery strategies for failed detectors."""
    RESTART_IMMEDIATE = "restart_immediate"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    SKIP_FRAMES = "skip_frames"
    FALLBACK_MODE = "fallback_mode"
    DISABLE = "disable"


@dataclass
class FailureRecord:
    """Record of a detector failure."""
    timestamp: datetime
    frame_id: int
    error_message: str
    stack_trace: Optional[str] = None
    recovery_attempted: bool = False
    recovery_successful: bool = False


@dataclass
class DetectorHealthRecord:
    """Health record for a detector."""
    detector_name: str
    total_failures: int = 0
    consecutive_failures: int = 0
    last_failure: Optional[datetime] = None
    last_successful_frame: Optional[int] = None
    recovery_attempts: int = 0
    current_backoff_seconds: float = 1.0
    is_healthy: bool = True
    failure_history: List[FailureRecord] = field(default_factory=list)
    performance_degraded: bool = False
    average_processing_time_ms: float = 0.0
    processing_time_samples: List[float] = field(default_factory=list)


class DetectorRecoveryManager:
    """
    Manages detector recovery with sophisticated strategies.
    Implements exponential backoff, state persistence, and automatic healing.
    """
    
    def __init__(self, detector_framework_service, 
                 max_consecutive_failures: int = 3,
                 initial_backoff_seconds: float = 1.0,
                 max_backoff_seconds: float = 60.0,
                 backoff_multiplier: float = 2.0):
        """
        Initialize recovery manager.
        
        Args:
            detector_framework_service: Reference to detector framework
            max_consecutive_failures: Failures before changing strategy
            initial_backoff_seconds: Initial backoff time
            max_backoff_seconds: Maximum backoff time
            backoff_multiplier: Backoff time multiplier
        """
        self.detector_service = detector_framework_service
        self.max_consecutive_failures = max_consecutive_failures
        self.initial_backoff = initial_backoff_seconds
        self.max_backoff = max_backoff_seconds
        self.backoff_multiplier = backoff_multiplier
        
        # Health records
        self.health_records: Dict[str, DetectorHealthRecord] = {}
        self.recovery_queue: List[Tuple[str, datetime]] = []
        
        # Recovery strategies per detector
        self.recovery_strategies: Dict[str, RecoveryStrategy] = {}
        self.default_strategy = RecoveryStrategy.EXPONENTIAL_BACKOFF
        
        # State persistence
        # Use absolute path in data directory
        from pathlib import Path
        import os
        
        # Get data directory from environment or use default
        data_dir = os.environ.get('STORAGE_DIR', './data')
        state_dir = Path(data_dir).resolve()
        state_dir.mkdir(parents=True, exist_ok=True)
        
        self.state_file = state_dir / "detector_recovery_state.json"
        self._load_state()
        
        # Recovery worker
        self.recovery_thread = None
        self.stop_recovery = threading.Event()
        self.recovery_lock = threading.RLock()
        
        # Monitoring
        self.recovery_callbacks = []
        
    def start(self):
        """Start recovery manager."""
        self.stop_recovery.clear()
        self.recovery_thread = threading.Thread(target=self._recovery_worker)
        self.recovery_thread.daemon = True
        self.recovery_thread.start()
        print("Detector recovery manager started")
    
    def stop(self):
        """Stop recovery manager."""
        self.stop_recovery.set()
        if self.recovery_thread:
            self.recovery_thread.join(timeout=5.0)
        self._save_state()
        print("Detector recovery manager stopped")
    
    def report_failure(self, detector_name: str, frame_id: int, 
                      error_message: str, stack_trace: Optional[str] = None):
        """
        Report a detector failure.
        
        Args:
            detector_name: Name of failed detector
            frame_id: Frame where failure occurred
            error_message: Error message
            stack_trace: Optional stack trace
        """
        with self.recovery_lock:
            # Get or create health record
            if detector_name not in self.health_records:
                self.health_records[detector_name] = DetectorHealthRecord(
                    detector_name=detector_name
                )
            
            record = self.health_records[detector_name]
            
            # Create failure record
            failure = FailureRecord(
                timestamp=datetime.now(),
                frame_id=frame_id,
                error_message=error_message,
                stack_trace=stack_trace
            )
            
            # Update health record
            record.total_failures += 1
            record.consecutive_failures += 1
            record.last_failure = failure.timestamp
            record.is_healthy = False
            record.failure_history.append(failure)
            
            # Keep only recent failure history
            if len(record.failure_history) > 100:
                record.failure_history = record.failure_history[-100:]
            
            # Determine recovery strategy
            strategy = self._determine_recovery_strategy(record)
            self.recovery_strategies[detector_name] = strategy
            
            # Schedule recovery
            if strategy != RecoveryStrategy.DISABLE:
                recovery_time = datetime.now() + timedelta(
                    seconds=record.current_backoff_seconds
                )
                self.recovery_queue.append((detector_name, recovery_time))
                
                # Update backoff
                record.current_backoff_seconds = min(
                    record.current_backoff_seconds * self.backoff_multiplier,
                    self.max_backoff
                )
            
            # Notify callbacks
            self._notify_failure(detector_name, failure, strategy)
            
            # Log failure
            print(f"Detector {detector_name} failed on frame {frame_id}: {error_message}")
            print(f"Recovery strategy: {strategy.value}")
    
    def report_success(self, detector_name: str, frame_id: int, 
                      processing_time_ms: float):
        """
        Report successful detector processing.
        
        Args:
            detector_name: Name of detector
            frame_id: Successfully processed frame
            processing_time_ms: Processing time in milliseconds
        """
        with self.recovery_lock:
            if detector_name not in self.health_records:
                self.health_records[detector_name] = DetectorHealthRecord(
                    detector_name=detector_name
                )
            
            record = self.health_records[detector_name]
            
            # Reset consecutive failures on success
            if record.consecutive_failures > 0:
                print(f"Detector {detector_name} recovered after "
                      f"{record.consecutive_failures} failures")
                record.consecutive_failures = 0
                record.current_backoff_seconds = self.initial_backoff
                
                # Mark last failure as recovered
                if record.failure_history:
                    record.failure_history[-1].recovery_successful = True
            
            # Update health status
            record.is_healthy = True
            record.last_successful_frame = frame_id
            
            # Track performance
            record.processing_time_samples.append(processing_time_ms)
            if len(record.processing_time_samples) > 100:
                record.processing_time_samples.pop(0)
            
            # Calculate average
            if record.processing_time_samples:
                record.average_processing_time_ms = sum(record.processing_time_samples) / len(record.processing_time_samples)
            
            # Check for performance degradation
            if record.average_processing_time_ms > 100:  # Threshold
                record.performance_degraded = True
            else:
                record.performance_degraded = False
    
    def _determine_recovery_strategy(self, record: DetectorHealthRecord) -> RecoveryStrategy:
        """
        Determine recovery strategy based on failure patterns.
        
        Args:
            record: Detector health record
            
        Returns:
            Appropriate recovery strategy
        """
        # Check consecutive failures
        if record.consecutive_failures >= self.max_consecutive_failures * 2:
            # Too many failures, disable detector
            return RecoveryStrategy.DISABLE
        
        # Check failure rate over time
        recent_failures = [
            f for f in record.failure_history
            if (datetime.now() - f.timestamp).total_seconds() < 300  # Last 5 minutes
        ]
        
        if len(recent_failures) > 10:
            # High failure rate, use skip frames strategy
            return RecoveryStrategy.SKIP_FRAMES
        
        # Check if failures happen on specific frames
        if len(record.failure_history) >= 3:
            recent_frame_ids = [f.frame_id for f in record.failure_history[-3:]]
            if len(set(recent_frame_ids)) == 1:
                # Same frame causing issues, skip it
                return RecoveryStrategy.SKIP_FRAMES
        
        # Default to exponential backoff
        return RecoveryStrategy.EXPONENTIAL_BACKOFF
    
    def _recovery_worker(self):
        """Worker thread for processing recovery queue."""
        while not self.stop_recovery.is_set():
            try:
                current_time = datetime.now()
                
                with self.recovery_lock:
                    # Process recovery queue
                    ready_for_recovery = []
                    remaining = []
                    
                    for detector_name, recovery_time in self.recovery_queue:
                        if current_time >= recovery_time:
                            ready_for_recovery.append(detector_name)
                        else:
                            remaining.append((detector_name, recovery_time))
                    
                    self.recovery_queue = remaining
                
                # Attempt recovery for ready detectors
                for detector_name in ready_for_recovery:
                    self._attempt_recovery(detector_name)
                
                # Check detector health periodically
                self._check_detector_health()
                
                # Save state periodically
                if int(time.time()) % 60 == 0:  # Every minute
                    self._save_state()
                
                self.stop_recovery.wait(1.0)
                
            except Exception as e:
                print(f"Recovery worker error: {e}")
                self.stop_recovery.wait(5.0)
    
    def _attempt_recovery(self, detector_name: str):
        """
        Attempt to recover a failed detector.
        
        Args:
            detector_name: Name of detector to recover
        """
        with self.recovery_lock:
            if detector_name not in self.health_records:
                return
            
            record = self.health_records[detector_name]
            strategy = self.recovery_strategies.get(
                detector_name, 
                self.default_strategy
            )
            
            print(f"Attempting recovery for {detector_name} using {strategy.value}")
            record.recovery_attempts += 1
            
            if record.failure_history:
                record.failure_history[-1].recovery_attempted = True
        
        try:
            if strategy == RecoveryStrategy.RESTART_IMMEDIATE:
                success = self._restart_detector(detector_name)
                
            elif strategy == RecoveryStrategy.EXPONENTIAL_BACKOFF:
                success = self._restart_detector(detector_name)
                
            elif strategy == RecoveryStrategy.SKIP_FRAMES:
                success = self._restart_detector_skip_frames(detector_name)
                
            elif strategy == RecoveryStrategy.FALLBACK_MODE:
                success = self._enable_fallback_mode(detector_name)
                
            else:  # DISABLE
                self._disable_detector(detector_name)
                success = False
            
            if success:
                print(f"Successfully recovered {detector_name}")
                self._notify_recovery(detector_name, strategy)
            else:
                print(f"Failed to recover {detector_name}")
                
        except Exception as e:
            print(f"Recovery attempt failed for {detector_name}: {e}")
    
    def _restart_detector(self, detector_name: str) -> bool:
        """
        Restart a detector with same configuration.
        
        Args:
            detector_name: Detector to restart
            
        Returns:
            True if successful
        """
        try:
            # Get current configuration
            if not self.detector_service.current_scene_id:
                return False
            
            config = self.detector_service.config_manager.load_detector_config(
                self.detector_service.current_scene_id,
                detector_name
            )
            
            # Disable detector
            self.detector_service.disable_detector(detector_name)
            
            # Wait briefly
            time.sleep(0.5)
            
            # Re-enable detector
            return self.detector_service.enable_detector(detector_name, config)
            
        except Exception as e:
            print(f"Failed to restart detector {detector_name}: {e}")
            return False
    
    def _restart_detector_skip_frames(self, detector_name: str) -> bool:
        """
        Restart detector and skip to current frame.
        
        Args:
            detector_name: Detector to restart
            
        Returns:
            True if successful
        """
        success = self._restart_detector(detector_name)
        
        if success:
            # Get current frame ID from the detector service
            current_frame_id = None
            if self.detector_service.current_take_id:
                current_frame_id = self.detector_service.frame_provider.get_latest_frame_id(
                    self.detector_service.current_take_id
                )
            
            if current_frame_id:
                # Add skip frame marker to the detector's health record
                with self.recovery_lock:
                    if detector_name in self.health_records:
                        record = self.health_records[detector_name]
                        # Store the frame to skip to
                        record.skip_to_frame = current_frame_id
                        
                        # Also store in detector manager for processing
                        if detector_name in self.detector_service.active_detectors:
                            manager = self.detector_service.active_detectors[detector_name]
                            # Add a flag to skip frames up to current
                            manager.skip_frames_until = current_frame_id
                
                print(f"Detector {detector_name} restarted, will skip to frame {current_frame_id}")
            else:
                print(f"Detector {detector_name} restarted, no frames to skip")
        
        return success
    
    def _enable_fallback_mode(self, detector_name: str) -> bool:
        """
        Enable detector in fallback/degraded mode.
        
        Args:
            detector_name: Detector name
            
        Returns:
            True if successful
        """
        try:
            # Get current configuration
            if not self.detector_service.current_scene_id:
                return False
            
            config = self.detector_service.config_manager.load_detector_config(
                self.detector_service.current_scene_id,
                detector_name
            )
            
            # Modify configuration for fallback mode
            config["fallback_mode"] = True
            config["processing_quality"] = "low"
            config["skip_complex_analysis"] = True
            
            # Restart with fallback config
            self.detector_service.disable_detector(detector_name)
            time.sleep(0.5)
            
            return self.detector_service.enable_detector(detector_name, config)
            
        except Exception as e:
            print(f"Failed to enable fallback mode for {detector_name}: {e}")
            return False
    
    def _disable_detector(self, detector_name: str):
        """
        Permanently disable a detector.
        
        Args:
            detector_name: Detector to disable
        """
        try:
            self.detector_service.disable_detector(detector_name)
            print(f"Detector {detector_name} has been disabled due to repeated failures")
            
            # Notify UI/user
            self._notify_disabled(detector_name)
            
        except Exception as e:
            print(f"Failed to disable detector {detector_name}: {e}")
    
    def _check_detector_health(self):
        """Periodic health check of all detectors."""
        current_time = datetime.now()
        
        with self.recovery_lock:
            for detector_name, record in self.health_records.items():
                # Check for stale detectors (no activity in 5 minutes)
                if record.last_successful_frame is not None:
                    time_since_success = (current_time - record.last_failure).total_seconds() if record.last_failure else float('inf')
                    
                    if time_since_success > 300 and record.is_healthy:
                        print(f"Detector {detector_name} appears stale, marking unhealthy")
                        record.is_healthy = False
                
                # Check performance degradation
                if record.performance_degraded and record.is_healthy:
                    print(f"Detector {detector_name} showing performance degradation")
                    # Could trigger optimization or alert
    
    def get_health_report(self) -> Dict[str, Any]:
        """
        Get comprehensive health report for all detectors.
        
        Returns:
            Health report dictionary
        """
        with self.recovery_lock:
            report = {
                "timestamp": datetime.now().isoformat(),
                "detectors": {}
            }
            
            for detector_name, record in self.health_records.items():
                detector_report = {
                    "is_healthy": record.is_healthy,
                    "total_failures": record.total_failures,
                    "consecutive_failures": record.consecutive_failures,
                    "recovery_attempts": record.recovery_attempts,
                    "average_processing_ms": record.average_processing_time_ms,
                    "performance_degraded": record.performance_degraded,
                    "current_strategy": self.recovery_strategies.get(
                        detector_name, 
                        self.default_strategy
                    ).value
                }
                
                if record.last_failure:
                    detector_report["last_failure"] = record.last_failure.isoformat()
                    detector_report["time_since_failure"] = (
                        datetime.now() - record.last_failure
                    ).total_seconds()
                
                # Recent failures
                recent_failures = [
                    {
                        "timestamp": f.timestamp.isoformat(),
                        "frame_id": f.frame_id,
                        "error": f.error_message,
                        "recovered": f.recovery_successful
                    }
                    for f in record.failure_history[-5:]  # Last 5 failures
                ]
                detector_report["recent_failures"] = recent_failures
                
                report["detectors"][detector_name] = detector_report
            
            # Overall health
            healthy_count = sum(
                1 for r in self.health_records.values() if r.is_healthy
            )
            total_count = len(self.health_records)
            
            report["overall_health"] = {
                "healthy_detectors": healthy_count,
                "total_detectors": total_count,
                "health_percentage": (healthy_count / total_count * 100) if total_count > 0 else 100
            }
            
            return report
    
    def reset_detector_health(self, detector_name: str):
        """
        Reset health record for a detector.
        
        Args:
            detector_name: Detector to reset
        """
        with self.recovery_lock:
            if detector_name in self.health_records:
                self.health_records[detector_name] = DetectorHealthRecord(
                    detector_name=detector_name
                )
                print(f"Reset health record for {detector_name}")
    
    def add_recovery_callback(self, callback):
        """
        Add callback for recovery events.
        
        Args:
            callback: Function to call on recovery events
        """
        self.recovery_callbacks.append(callback)
    
    def _notify_failure(self, detector_name: str, failure: FailureRecord, 
                       strategy: RecoveryStrategy):
        """Notify callbacks of detector failure."""
        event = {
            "type": "failure",
            "detector_name": detector_name,
            "frame_id": failure.frame_id,
            "error": failure.error_message,
            "strategy": strategy.value,
            "timestamp": failure.timestamp.isoformat()
        }
        
        for callback in self.recovery_callbacks:
            try:
                callback(event)
            except Exception as e:
                print(f"Recovery callback error: {e}")
    
    def _notify_recovery(self, detector_name: str, strategy: RecoveryStrategy):
        """Notify callbacks of successful recovery."""
        event = {
            "type": "recovery",
            "detector_name": detector_name,
            "strategy": strategy.value,
            "timestamp": datetime.now().isoformat()
        }
        
        for callback in self.recovery_callbacks:
            try:
                callback(event)
            except Exception as e:
                print(f"Recovery callback error: {e}")
    
    def _notify_disabled(self, detector_name: str):
        """Notify callbacks of detector being disabled."""
        event = {
            "type": "disabled",
            "detector_name": detector_name,
            "reason": "repeated_failures",
            "timestamp": datetime.now().isoformat()
        }
        
        for callback in self.recovery_callbacks:
            try:
                callback(event)
            except Exception as e:
                print(f"Recovery callback error: {e}")
    
    def _save_state(self):
        """Save recovery state to disk."""
        try:
            # Ensure directory exists
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            
            state = {
                "timestamp": datetime.now().isoformat(),
                "health_records": {},
                "recovery_strategies": {}
            }
            
            # Serialize health records
            for detector_name, record in self.health_records.items():
                state["health_records"][detector_name] = {
                    "total_failures": record.total_failures,
                    "consecutive_failures": record.consecutive_failures,
                    "recovery_attempts": record.recovery_attempts,
                    "is_healthy": record.is_healthy,
                    "average_processing_ms": record.average_processing_time_ms,
                    "performance_degraded": record.performance_degraded
                }
            
            # Serialize strategies
            for detector_name, strategy in self.recovery_strategies.items():
                state["recovery_strategies"][detector_name] = strategy.value
            
            # Write to temporary file first, then rename (atomic operation)
            temp_file = self.state_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(state, f, indent=2)
            
            # Atomic rename
            temp_file.replace(self.state_file)
                
        except Exception as e:
            print(f"Failed to save recovery state to {self.state_file}: {e}")
            import traceback
            traceback.print_exc()
    
    def _load_state(self):
        """Load recovery state from disk."""
        try:
            if not self.state_file.exists():
                return
            
            with open(self.state_file, 'r') as f:
                state = json.load(f)
            
            # Restore health records
            for detector_name, record_data in state.get("health_records", {}).items():
                record = DetectorHealthRecord(detector_name=detector_name)
                record.total_failures = record_data.get("total_failures", 0)
                record.consecutive_failures = record_data.get("consecutive_failures", 0)
                record.recovery_attempts = record_data.get("recovery_attempts", 0)
                record.is_healthy = record_data.get("is_healthy", True)
                record.average_processing_time_ms = record_data.get("average_processing_ms", 0)
                record.performance_degraded = record_data.get("performance_degraded", False)
                
                self.health_records[detector_name] = record
            
            # Restore strategies
            for detector_name, strategy_value in state.get("recovery_strategies", {}).items():
                try:
                    self.recovery_strategies[detector_name] = RecoveryStrategy(strategy_value)
                except ValueError:
                    pass
            
            print(f"Loaded recovery state for {len(self.health_records)} detectors")
            
        except json.JSONDecodeError as e:
            print(f"Failed to parse recovery state file {self.state_file}: {e}")
            # Backup corrupted file
            if self.state_file.exists():
                backup_file = self.state_file.with_suffix('.corrupted')
                self.state_file.rename(backup_file)
                print(f"Backed up corrupted state file to {backup_file}")
        except Exception as e:
            print(f"Failed to load recovery state from {self.state_file}: {e}")
            import traceback
            traceback.print_exc()


# Integration with detector framework
def integrate_recovery_manager(detector_framework_service):
    """
    Integrate recovery manager with detector framework.
    
    Args:
        detector_framework_service: Detector framework instance
    """
    # Create recovery manager
    recovery_manager = DetectorRecoveryManager(detector_framework_service)
    
    # Start recovery manager
    recovery_manager.start()
    
    # Hook into detector processing
    detector_framework_service.process_frame
    
    def process_frame_with_recovery(frame_id: int, take_id: int) -> List[Any]:
        """Enhanced process_frame with recovery tracking."""
        results = []
        
        for detector_name, manager in detector_framework_service.active_detectors.items():
            try:
                start_time = time.time()
                detector_results = manager.process_frame(frame_id, take_id)
                processing_time = (time.time() - start_time) * 1000
                
                # Report success
                recovery_manager.report_success(
                    detector_name, 
                    frame_id, 
                    processing_time
                )
                
                # Check for detector-reported failures
                for result in detector_results:
                    if result.confidence == -1.0:  # Special value for detector failures
                        recovery_manager.report_failure(
                            detector_name,
                            frame_id,
                            result.description
                        )
                
                results.extend(detector_results)
                
            except Exception as e:
                # Report failure
                import traceback
                recovery_manager.report_failure(
                    detector_name,
                    frame_id,
                    str(e),
                    traceback.format_exc()
                )
                
                # Create failure result
                from CAMF.common.models import DetectorResult
                failure_result = DetectorResult(
                    confidence=-1.0,  # Special value for detector failures
                    description=f"Detector crashed: {str(e)}",
                    frame_id=frame_id,
                    detector_name=detector_name
                )
                results.append(failure_result)
        
        return results
    
    # Replace process_frame method
    detector_framework_service.process_frame = process_frame_with_recovery
    
    # Add recovery manager to service
    detector_framework_service.recovery_manager = recovery_manager
    
    # Add cleanup
    original_cleanup = detector_framework_service.cleanup
    
    def cleanup_with_recovery():
        """Enhanced cleanup with recovery manager."""
        recovery_manager.stop()
        original_cleanup()
    
    detector_framework_service.cleanup = cleanup_with_recovery
    
    return recovery_manager
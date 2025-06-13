"""
Comprehensive tests for detector framework recovery and resilience.
Tests error recovery, automatic restart, state persistence, and failover.
"""

import pytest
import asyncio
import time
import json
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from datetime import datetime, timedelta
import threading

from CAMF.services.detector_framework.recovery import (
    RecoveryManager, RecoveryPolicy, FailureDetector,
    StateManager, HealthMonitor
)
from CAMF.services.detector_framework.detector_wrapper import DetectorWrapper


class TestRecoveryManager:
    """Test recovery manager functionality."""
    
    @pytest.fixture
    def recovery_policy(self):
        """Create recovery policy."""
        return RecoveryPolicy(
            max_retries=3,
            retry_delay=1.0,
            backoff_factor=2.0,
            max_backoff=30.0,
            restart_on_failure=True,
            preserve_state=True
        )
    
    @pytest.fixture
    def recovery_manager(self, recovery_policy):
        """Create recovery manager."""
        return RecoveryManager(policy=recovery_policy)
    
    @pytest.fixture
    def mock_detector(self):
        """Create mock detector."""
        detector = MagicMock()
        detector.name = "TestDetector"
        detector.initialize = AsyncMock(return_value=True)
        detector.process_frame = AsyncMock()
        detector.cleanup = AsyncMock()
        return detector
    
    @pytest.mark.asyncio
    async def test_detector_restart(self, recovery_manager, mock_detector):
        """Test automatic detector restart on failure."""
        # Register detector
        recovery_manager.register_detector("test_id", mock_detector)
        
        # Simulate failure
        mock_detector.process_frame.side_effect = Exception("Detector crashed")
        
        # Attempt recovery
        recovered = await recovery_manager.recover_detector("test_id")
        
        assert recovered is True
        assert mock_detector.cleanup.called
        assert mock_detector.initialize.call_count == 2  # Initial + restart
    
    @pytest.mark.asyncio
    async def test_exponential_backoff(self, recovery_manager, mock_detector):
        """Test exponential backoff retry strategy."""
        recovery_manager.register_detector("test_id", mock_detector)
        
        # Make initialization fail repeatedly
        mock_detector.initialize.side_effect = Exception("Init failed")
        
        start_time = time.time()
        recovered = await recovery_manager.recover_detector("test_id")
        duration = time.time() - start_time
        
        assert recovered is False
        assert mock_detector.initialize.call_count == 4  # Initial + 3 retries
        # Should have delays: 1s, 2s, 4s = 7s total (approximately)
        assert duration >= 6.0
    
    @pytest.mark.asyncio
    async def test_recovery_with_state_preservation(self, recovery_manager, mock_detector):
        """Test preserving detector state during recovery."""
        recovery_manager.register_detector("test_id", mock_detector)
        
        # Set some state
        state_data = {
            "processed_frames": 100,
            "last_detection": {"frame_id": 99, "detected": True},
            "calibration": {"threshold": 0.8}
        }
        recovery_manager.save_detector_state("test_id", state_data)
        
        # Simulate failure and recovery
        mock_detector.process_frame.side_effect = Exception("Crashed")
        recovered = await recovery_manager.recover_detector("test_id")
        
        # State should be restored
        restored_state = recovery_manager.get_detector_state("test_id")
        assert restored_state == state_data
    
    @pytest.mark.asyncio
    async def test_circuit_breaker(self, recovery_manager, mock_detector):
        """Test circuit breaker pattern for failing detectors."""
        recovery_manager.register_detector("test_id", mock_detector)
        recovery_manager.enable_circuit_breaker(
            failure_threshold=5,
            reset_timeout=60
        )
        
        # Simulate repeated failures
        mock_detector.process_frame.side_effect = Exception("Consistent failure")
        
        for i in range(10):
            try:
                await mock_detector.process_frame({})
            except:
                recovery_manager.record_failure("test_id")
        
        # Circuit should be open
        assert recovery_manager.is_circuit_open("test_id") is True
        
        # Should not attempt recovery while circuit is open
        recovered = await recovery_manager.recover_detector("test_id")
        assert recovered is False
        assert mock_detector.initialize.call_count == 1  # No additional attempts
    
    @pytest.mark.asyncio
    async def test_cascading_failure_prevention(self, recovery_manager):
        """Test prevention of cascading failures."""
        # Register multiple detectors
        detectors = []
        for i in range(5):
            detector = MagicMock()
            detector.name = f"Detector{i}"
            detector.initialize = AsyncMock(return_value=True)
            detector.process_frame = AsyncMock()
            detectors.append(detector)
            recovery_manager.register_detector(f"detector_{i}", detector)
        
        # Simulate failures in multiple detectors
        for i in range(3):
            detectors[i].process_frame.side_effect = Exception("Failed")
            recovery_manager.record_failure(f"detector_{i}")
        
        # Check system health
        health = recovery_manager.get_system_health()
        assert health["total_detectors"] == 5
        assert health["failed_detectors"] == 3
        assert health["health_percentage"] == 40.0
        
        # Should trigger system protection if too many failures
        assert recovery_manager.should_enable_degraded_mode() is True


class TestFailureDetector:
    """Test failure detection mechanisms."""
    
    @pytest.fixture
    def failure_detector(self):
        """Create failure detector."""
        return FailureDetector(
            heartbeat_interval=1.0,
            timeout_threshold=3.0,
            failure_threshold=3
        )
    
    def test_heartbeat_monitoring(self, failure_detector):
        """Test heartbeat-based failure detection."""
        detector_id = "test_detector"
        
        # Start monitoring
        failure_detector.start_monitoring(detector_id)
        
        # Send heartbeats
        for _ in range(5):
            failure_detector.record_heartbeat(detector_id)
            time.sleep(0.5)
        
        # Should be healthy
        assert failure_detector.is_healthy(detector_id) is True
        
        # Stop heartbeats
        time.sleep(4)
        
        # Should be detected as failed
        assert failure_detector.is_healthy(detector_id) is False
    
    def test_performance_degradation_detection(self, failure_detector):
        """Test detecting performance degradation."""
        detector_id = "test_detector"
        failure_detector.start_monitoring(detector_id)
        
        # Record normal processing times
        for _ in range(10):
            failure_detector.record_processing_time(detector_id, 0.1)
        
        # Record degraded performance
        for _ in range(5):
            failure_detector.record_processing_time(detector_id, 1.0)
        
        # Should detect degradation
        degradation = failure_detector.get_performance_degradation(detector_id)
        assert degradation > 5.0  # 10x slower
        assert failure_detector.is_degraded(detector_id) is True
    
    def test_error_rate_monitoring(self, failure_detector):
        """Test monitoring detector error rates."""
        detector_id = "test_detector"
        failure_detector.start_monitoring(detector_id)
        
        # Record mix of successes and failures
        for i in range(100):
            if i % 4 == 0:  # 25% error rate
                failure_detector.record_error(detector_id)
            else:
                failure_detector.record_success(detector_id)
        
        # Check error rate
        error_rate = failure_detector.get_error_rate(detector_id)
        assert error_rate == pytest.approx(0.25, rel=0.01)
        
        # Should trigger alert for high error rate
        assert failure_detector.should_alert(detector_id) is True
    
    def test_memory_leak_detection(self, failure_detector):
        """Test detecting memory leaks in detectors."""
        detector_id = "test_detector"
        failure_detector.start_monitoring(detector_id)
        
        # Simulate increasing memory usage
        base_memory = 100 * 1024 * 1024  # 100MB
        for i in range(20):
            memory = base_memory + (i * 10 * 1024 * 1024)  # +10MB each time
            failure_detector.record_memory_usage(detector_id, memory)
            time.sleep(0.1)
        
        # Should detect memory leak
        assert failure_detector.has_memory_leak(detector_id) is True
        leak_rate = failure_detector.get_memory_leak_rate(detector_id)
        assert leak_rate > 0  # MB per second


class TestStateManager:
    """Test detector state management."""
    
    @pytest.fixture
    def state_manager(self):
        """Create state manager."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = StateManager(state_dir=temp_dir)
            yield manager
    
    def test_save_load_detector_state(self, state_manager):
        """Test saving and loading detector state."""
        detector_id = "test_detector"
        state = {
            "version": "1.0.0",
            "processed_count": 1000,
            "last_frame_id": 999,
            "calibration": {
                "threshold": 0.85,
                "sensitivity": "high"
            },
            "statistics": {
                "total_detections": 150,
                "false_positives": 5
            }
        }
        
        # Save state
        state_manager.save_state(detector_id, state)
        
        # Load state
        loaded_state = state_manager.load_state(detector_id)
        assert loaded_state == state
    
    def test_state_versioning(self, state_manager):
        """Test state versioning for compatibility."""
        detector_id = "test_detector"
        
        # Save multiple versions
        for version in range(1, 4):
            state = {
                "version": f"1.0.{version}",
                "data": f"version_{version}"
            }
            state_manager.save_state(detector_id, state, version=version)
        
        # Load specific version
        state_v2 = state_manager.load_state(detector_id, version=2)
        assert state_v2["version"] == "1.0.2"
        
        # Load latest version
        latest_state = state_manager.load_state(detector_id)
        assert latest_state["version"] == "1.0.3"
    
    def test_state_migration(self, state_manager):
        """Test migrating state between detector versions."""
        detector_id = "test_detector"
        
        # Old state format
        old_state = {
            "version": "1.0.0",
            "threshold": 0.8,  # Old flat structure
            "detections": 100
        }
        
        # Define migration
        def migrate_v1_to_v2(state):
            return {
                "version": "2.0.0",
                "config": {
                    "threshold": state["threshold"]
                },
                "stats": {
                    "detections": state["detections"]
                }
            }
        
        state_manager.register_migration("1.0.0", "2.0.0", migrate_v1_to_v2)
        
        # Save old state
        state_manager.save_state(detector_id, old_state)
        
        # Load with migration
        migrated_state = state_manager.load_state(
            detector_id,
            target_version="2.0.0"
        )
        
        assert migrated_state["version"] == "2.0.0"
        assert migrated_state["config"]["threshold"] == 0.8
        assert migrated_state["stats"]["detections"] == 100
    
    def test_state_compression(self, state_manager):
        """Test state compression for large states."""
        detector_id = "test_detector"
        
        # Create large state
        large_state = {
            "version": "1.0.0",
            "large_data": [{"id": i, "data": "x" * 1000} for i in range(1000)]
        }
        
        # Save with compression
        state_manager.save_state(
            detector_id,
            large_state,
            compress=True
        )
        
        # Load compressed state
        loaded_state = state_manager.load_state(detector_id)
        assert loaded_state["version"] == "1.0.0"
        assert len(loaded_state["large_data"]) == 1000
    
    def test_state_backup_rotation(self, state_manager):
        """Test automatic state backup rotation."""
        detector_id = "test_detector"
        state_manager.set_backup_policy(max_backups=3)
        
        # Save multiple states
        for i in range(5):
            state = {"version": "1.0.0", "iteration": i}
            state_manager.save_state(detector_id, state)
            time.sleep(0.1)
        
        # Should only keep last 3 backups
        backups = state_manager.list_backups(detector_id)
        assert len(backups) == 3
        
        # Newest backup should have iteration=4
        latest_backup = state_manager.load_backup(detector_id, backups[0])
        assert latest_backup["iteration"] == 4


class TestHealthMonitor:
    """Test health monitoring functionality."""
    
    @pytest.fixture
    def health_monitor(self):
        """Create health monitor."""
        return HealthMonitor(check_interval=1.0)
    
    def test_comprehensive_health_check(self, health_monitor):
        """Test comprehensive health checking."""
        detector_id = "test_detector"
        
        # Define health checks
        checks = {
            "memory": lambda: {"status": "ok", "usage_mb": 150},
            "processing": lambda: {"status": "ok", "avg_time_ms": 50},
            "error_rate": lambda: {"status": "warning", "rate": 0.05},
            "queue": lambda: {"status": "ok", "size": 10}
        }
        
        health_monitor.register_checks(detector_id, checks)
        
        # Run health check
        health_report = health_monitor.check_health(detector_id)
        
        assert health_report["overall_status"] == "warning"  # Due to error_rate
        assert health_report["checks"]["memory"]["status"] == "ok"
        assert health_report["checks"]["error_rate"]["status"] == "warning"
    
    def test_health_history_tracking(self, health_monitor):
        """Test tracking health history."""
        detector_id = "test_detector"
        
        # Record health over time
        for i in range(10):
            health_data = {
                "timestamp": time.time(),
                "status": "ok" if i < 7 else "error",
                "metrics": {"cpu": 20 + i * 5}
            }
            health_monitor.record_health(detector_id, health_data)
            time.sleep(0.1)
        
        # Get health history
        history = health_monitor.get_health_history(
            detector_id,
            duration_seconds=2.0
        )
        
        assert len(history) == 10
        assert history[-1]["status"] == "error"
        
        # Calculate uptime
        uptime = health_monitor.calculate_uptime(detector_id)
        assert uptime < 1.0  # Less than 100% due to errors
    
    def test_health_alerts(self, health_monitor):
        """Test health-based alerting."""
        alerts = []
        
        def alert_handler(alert):
            alerts.append(alert)
        
        health_monitor.set_alert_handler(alert_handler)
        
        # Configure alert rules
        health_monitor.add_alert_rule(
            name="high_memory",
            condition=lambda health: health.get("memory_mb", 0) > 500,
            severity="warning"
        )
        
        health_monitor.add_alert_rule(
            name="detector_down",
            condition=lambda health: health.get("status") == "error",
            severity="critical"
        )
        
        # Trigger alerts
        health_monitor.check_and_alert("detector1", {"memory_mb": 600, "status": "ok"})
        health_monitor.check_and_alert("detector2", {"memory_mb": 200, "status": "error"})
        
        assert len(alerts) == 2
        assert any(a["rule"] == "high_memory" for a in alerts)
        assert any(a["severity"] == "critical" for a in alerts)


class TestRecoveryIntegration:
    """Test integrated recovery scenarios."""
    
    @pytest.mark.asyncio
    async def test_full_recovery_workflow(self):
        """Test complete recovery workflow."""
        # Create components
        recovery_policy = RecoveryPolicy(max_retries=2, retry_delay=0.1)
        recovery_manager = RecoveryManager(policy=recovery_policy)
        failure_detector = FailureDetector()
        state_manager = StateManager()
        
        # Create mock detector
        detector = MagicMock()
        detector.name = "TestDetector"
        detector.initialize = AsyncMock()
        detector.process_frame = AsyncMock()
        
        # Register detector
        recovery_manager.register_detector("test", detector)
        failure_detector.start_monitoring("test")
        
        # Simulate normal operation
        for i in range(5):
            await detector.process_frame({"frame_id": i})
            failure_detector.record_success("test")
            state_manager.save_state("test", {"last_frame": i})
        
        # Simulate failure
        detector.process_frame.side_effect = Exception("Detector failed")
        
        # Detect and recover
        for i in range(5, 8):
            try:
                await detector.process_frame({"frame_id": i})
            except:
                failure_detector.record_error("test")
                
                if failure_detector.should_recover("test"):
                    # Attempt recovery
                    state = state_manager.load_state("test")
                    recovered = await recovery_manager.recover_detector("test")
                    
                    if recovered:
                        # Restore state and continue
                        detector.process_frame.side_effect = None
                        last_frame = state.get("last_frame", 0)
                        # Continue from last successful frame
        
        # Verify recovery
        assert detector.initialize.call_count > 1  # Was reinitialized
        assert failure_detector.is_healthy("test") is True
"""
Comprehensive tests for common modules.
Tests models, utilities, configuration, and protocol definitions.
"""

import pytest
from datetime import datetime, timedelta
import json
import os
import tempfile
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import yaml

from CAMF.common.models import (
    Project, Scene, Angle, Take, Frame,
    ProjectCreate, SceneCreate, AngleCreate, TakeCreate, FrameCreate,
    DetectorResult, CaptureStatus, ProcessingStatus,
    ValidationError, ModelBase
)
from CAMF.common.config import (
    Config, ConfigLoader, ConfigValidator,
    EnvironmentConfig, get_config, update_config
)
from CAMF.common.utils import (
    Timer, retry, RateLimiter, Cache,
    generate_id, format_timestamp, parse_duration,
    ensure_directory, safe_json_loads, merge_dicts
)
from CAMF.common.protocol import (
    Protocol, MessageType, Message,
    RequestMessage, ResponseMessage, ErrorMessage,
    encode_message, decode_message
)
from CAMF.common.service_discovery import (
    ServiceInfo, ServiceRegistry, ServiceDiscovery,
    HeartbeatMonitor
)


class TestModels:
    """Test data models and validation."""
    
    def test_project_model(self):
        """Test Project model creation and validation."""
        # Valid project
        project = Project(
            id=1,
            name="Test Production",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        assert project.id == 1
        assert project.name == "Test Production"
        assert isinstance(project.created_at, datetime)
        
        # Project creation model
        project_create = ProjectCreate(name="New Project")
        assert project_create.name == "New Project"
        
        # Validation
        with pytest.raises(ValidationError):
            ProjectCreate(name="")  # Empty name
        
        with pytest.raises(ValidationError):
            ProjectCreate(name="x" * 256)  # Too long
    
    def test_scene_model(self):
        """Test Scene model with detector configs."""
        detector_configs = {
            "ClockDetector": {
                "enabled": True,
                "threshold": 0.8,
                "parameters": {"mode": "digital"}
            },
            "ContinuityDetector": {
                "enabled": False
            }
        }
        
        scene = Scene(
            id=1,
            project_id=1,
            name="Opening Scene",
            detector_configs=detector_configs,
            created_at=datetime.now()
        )
        
        assert scene.detector_configs["ClockDetector"]["enabled"] is True
        assert scene.detector_configs["ClockDetector"]["threshold"] == 0.8
        
        # Scene creation with validation
        scene_create = SceneCreate(
            project_id=1,
            name="Scene 2",
            detector_configs=detector_configs
        )
        assert scene_create.project_id == 1
    
    def test_frame_model(self):
        """Test Frame model with detector results."""
        detector_results = {
            "ClockDetector": DetectorResult(
                detected=True,
                confidence=0.95,
                details={"time": "14:30", "type": "digital"}
            ),
            "ContinuityDetector": DetectorResult(
                detected=False,
                confidence=0.0
            )
        }
        
        frame = Frame(
            id=1,
            take_id=1,
            frame_number=100,
            timestamp=3.33,
            file_path="/frames/frame_100.jpg",
            detector_results=detector_results,
            created_at=datetime.now()
        )
        
        assert frame.frame_number == 100
        assert frame.timestamp == 3.33
        assert frame.detector_results["ClockDetector"].detected is True
        assert frame.detector_results["ClockDetector"].confidence == 0.95
    
    def test_capture_status_enum(self):
        """Test CaptureStatus enumeration."""
        assert CaptureStatus.IDLE.value == "idle"
        assert CaptureStatus.RECORDING.value == "recording"
        assert CaptureStatus.PROCESSING.value == "processing"
        assert CaptureStatus.COMPLETED.value == "completed"
        assert CaptureStatus.ERROR.value == "error"
        
        # Status transitions
        valid_transitions = {
            CaptureStatus.IDLE: [CaptureStatus.RECORDING],
            CaptureStatus.RECORDING: [CaptureStatus.PROCESSING, CaptureStatus.STOPPED],
            CaptureStatus.PROCESSING: [CaptureStatus.COMPLETED, CaptureStatus.ERROR]
        }
        
        assert CaptureStatus.RECORDING in valid_transitions[CaptureStatus.IDLE]
    
    def test_model_serialization(self):
        """Test model serialization to/from JSON."""
        take = Take(
            id=1,
            angle_id=1,
            name="Take 1",
            take_number=1,
            is_reference=True,
            status=CaptureStatus.COMPLETED,
            created_at=datetime.now()
        )
        
        # Serialize to dict
        take_dict = take.dict()
        assert take_dict["name"] == "Take 1"
        assert take_dict["status"] == "completed"
        
        # Serialize to JSON
        take_json = take.json()
        assert isinstance(take_json, str)
        
        # Deserialize
        parsed = json.loads(take_json)
        assert parsed["take_number"] == 1
        assert parsed["is_reference"] is True
    
    def test_model_validation_errors(self):
        """Test model validation error handling."""
        # Invalid frame number
        with pytest.raises(ValidationError) as exc_info:
            FrameCreate(
                take_id=1,
                frame_number=-1,  # Negative frame number
                timestamp=0.0,
                file_path="/test.jpg"
            )
        assert "frame_number" in str(exc_info.value)
        
        # Invalid timestamp
        with pytest.raises(ValidationError) as exc_info:
            FrameCreate(
                take_id=1,
                frame_number=1,
                timestamp=-5.0,  # Negative timestamp
                file_path="/test.jpg"
            )
        assert "timestamp" in str(exc_info.value)
    
    def test_model_inheritance(self):
        """Test model inheritance and shared fields."""
        # All models should inherit from ModelBase
        assert issubclass(Project, ModelBase)
        assert issubclass(Scene, ModelBase)
        
        # Check common fields
        project = Project(id=1, name="Test")
        assert hasattr(project, "dict")
        assert hasattr(project, "json")
        assert hasattr(project, "copy")


class TestConfiguration:
    """Test configuration management."""
    
    @pytest.fixture
    def config_file(self):
        """Create temporary config file."""
        config_data = {
            "app": {
                "name": "CAMF",
                "version": "1.0.0",
                "debug": False
            },
            "api": {
                "host": "localhost",
                "port": 8000,
                "workers": 4
            },
            "storage": {
                "database_url": "sqlite:///test.db",
                "frame_storage_path": "/tmp/frames"
            },
            "detectors": {
                "max_concurrent": 5,
                "timeout": 30
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name
        
        yield temp_path
        os.unlink(temp_path)
    
    def test_config_loading(self, config_file):
        """Test loading configuration from file."""
        config = ConfigLoader.load_file(config_file)
        
        assert config["app"]["name"] == "CAMF"
        assert config["api"]["port"] == 8000
        assert config["storage"]["database_url"] == "sqlite:///test.db"
    
    def test_environment_override(self, config_file):
        """Test environment variable override."""
        # Set environment variables
        os.environ["CAMF_API_PORT"] = "9000"
        os.environ["CAMF_APP_DEBUG"] = "true"
        
        try:
            config = ConfigLoader.load_with_env(config_file, prefix="CAMF")
            
            assert config["api"]["port"] == 9000  # Overridden
            assert config["app"]["debug"] is True  # Overridden
            assert config["api"]["host"] == "localhost"  # Not overridden
        finally:
            # Cleanup
            del os.environ["CAMF_API_PORT"]
            del os.environ["CAMF_APP_DEBUG"]
    
    def test_config_validation(self):
        """Test configuration validation."""
        validator = ConfigValidator()
        
        # Define schema
        schema = {
            "api": {
                "port": {"type": "int", "min": 1, "max": 65535},
                "host": {"type": "str", "pattern": r"^[\w\.-]+$"},
                "workers": {"type": "int", "min": 1}
            },
            "storage": {
                "database_url": {"type": "str", "required": True}
            }
        }
        
        # Valid config
        valid_config = {
            "api": {"port": 8000, "host": "localhost", "workers": 4},
            "storage": {"database_url": "sqlite:///db.sqlite"}
        }
        
        errors = validator.validate(valid_config, schema)
        assert len(errors) == 0
        
        # Invalid config
        invalid_config = {
            "api": {"port": 70000, "host": "invalid host!", "workers": 0},
            "storage": {}  # Missing required field
        }
        
        errors = validator.validate(invalid_config, schema)
        assert len(errors) > 0
        assert any("port" in str(e) for e in errors)
        assert any("database_url" in str(e) for e in errors)
    
    def test_config_singleton(self):
        """Test configuration singleton pattern."""
        # First access creates instance
        config1 = get_config()
        config1.set("test_key", "test_value")
        
        # Second access returns same instance
        config2 = get_config()
        assert config2.get("test_key") == "test_value"
        assert config1 is config2
    
    def test_config_hot_reload(self, config_file):
        """Test configuration hot reload."""
        config = Config()
        config.load_file(config_file)
        
        original_port = config.get("api.port")
        
        # Modify file
        with open(config_file, 'r') as f:
            data = yaml.safe_load(f)
        data["api"]["port"] = 9999
        with open(config_file, 'w') as f:
            yaml.dump(data, f)
        
        # Reload
        config.reload()
        assert config.get("api.port") == 9999
        assert config.get("api.port") != original_port
    
    def test_config_defaults(self):
        """Test configuration defaults."""
        config = Config()
        
        # Set defaults
        defaults = {
            "api": {"timeout": 30, "retry_count": 3},
            "cache": {"ttl": 300, "max_size": 1000}
        }
        config.set_defaults(defaults)
        
        # Get with defaults
        assert config.get("api.timeout", default=60) == 30  # Uses set default
        assert config.get("api.unknown", default=10) == 10  # Uses provided default
        assert config.get("cache.ttl") == 300


class TestUtilities:
    """Test utility functions and classes."""
    
    def test_timer_utility(self):
        """Test Timer utility."""
        import time
        
        # Context manager usage
        with Timer() as timer:
            time.sleep(0.1)
        
        assert 0.09 < timer.elapsed < 0.12
        
        # Manual usage
        timer = Timer()
        timer.start()
        time.sleep(0.05)
        elapsed = timer.stop()
        assert 0.04 < elapsed < 0.06
    
    def test_retry_decorator(self):
        """Test retry decorator."""
        call_count = 0
        
        @retry(max_attempts=3, delay=0.1, exceptions=(ValueError,))
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary failure")
            return "success"
        
        result = flaky_function()
        assert result == "success"
        assert call_count == 3
        
        # Test permanent failure
        @retry(max_attempts=2, delay=0.1)
        def always_fails():
            raise RuntimeError("Permanent failure")
        
        with pytest.raises(RuntimeError):
            always_fails()
    
    def test_rate_limiter(self):
        """Test rate limiting utility."""
        # 5 requests per second
        limiter = RateLimiter(rate=5, period=1.0)
        
        # Should allow first 5 immediately
        for _ in range(5):
            assert limiter.acquire() is True
        
        # 6th should be rate limited
        start = time.time()
        result = limiter.acquire()  # Will wait
        elapsed = time.time() - start
        
        assert result is True
        assert elapsed > 0.1  # Had to wait
    
    def test_cache_utility(self):
        """Test caching utility."""
        cache = Cache(max_size=3, ttl=1.0)
        
        # Add items
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        
        # Get items
        assert cache.get("key1") == "value1"
        assert cache.get("key2") == "value2"
        
        # LRU eviction
        cache.set("key4", "value4")  # Should evict key3
        assert cache.get("key3") is None
        assert cache.get("key4") == "value4"
        
        # TTL expiration
        time.sleep(1.1)
        assert cache.get("key1") is None  # Expired
    
    def test_id_generation(self):
        """Test ID generation utilities."""
        # UUID generation
        id1 = generate_id()
        id2 = generate_id()
        assert id1 != id2
        assert len(id1) == 36  # Standard UUID length
        
        # With prefix
        prefixed_id = generate_id(prefix="frame")
        assert prefixed_id.startswith("frame_")
        
        # Short ID
        short_id = generate_id(length=8)
        assert len(short_id) == 8
    
    def test_timestamp_formatting(self):
        """Test timestamp formatting utilities."""
        # Format timestamp
        formatted = format_timestamp(90.5, format="hh:mm:ss")
        assert formatted == "00:01:30"
        
        formatted = format_timestamp(3661.2, format="hh:mm:ss.f")
        assert formatted == "01:01:01.2"
        
        # Parse duration
        assert parse_duration("01:30") == 90
        assert parse_duration("1h30m") == 5400
        assert parse_duration("90s") == 90
        assert parse_duration("1:30:45") == 5445
    
    def test_path_utilities(self):
        """Test path-related utilities."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Ensure directory
            new_dir = os.path.join(temp_dir, "a", "b", "c")
            ensure_directory(new_dir)
            assert os.path.exists(new_dir)
            
            # Safe JSON load
            json_data = '{"key": "value", "number": 123}'
            result = safe_json_loads(json_data)
            assert result["key"] == "value"
            
            # Invalid JSON
            invalid_json = '{"key": "value"'
            result = safe_json_loads(invalid_json, default={})
            assert result == {}
    
    def test_dict_utilities(self):
        """Test dictionary manipulation utilities."""
        # Merge dicts
        dict1 = {"a": 1, "b": {"c": 2}}
        dict2 = {"b": {"d": 3}, "e": 4}
        
        merged = merge_dicts(dict1, dict2)
        assert merged["a"] == 1
        assert merged["b"]["c"] == 2
        assert merged["b"]["d"] == 3
        assert merged["e"] == 4
        
        # Deep merge
        dict3 = {"b": {"c": 5}}  # Override nested value
        merged2 = merge_dicts(merged, dict3)
        assert merged2["b"]["c"] == 5
        assert merged2["b"]["d"] == 3  # Preserved


class TestProtocol:
    """Test protocol definitions and message handling."""
    
    def test_message_types(self):
        """Test message type definitions."""
        assert MessageType.REQUEST.value == "request"
        assert MessageType.RESPONSE.value == "response"
        assert MessageType.ERROR.value == "error"
        assert MessageType.EVENT.value == "event"
        assert MessageType.HEARTBEAT.value == "heartbeat"
    
    def test_request_message(self):
        """Test request message creation."""
        request = RequestMessage(
            id="req_123",
            method="get_frame",
            params={"frame_id": 100, "include_metadata": True}
        )
        
        assert request.id == "req_123"
        assert request.type == MessageType.REQUEST
        assert request.method == "get_frame"
        assert request.params["frame_id"] == 100
    
    def test_response_message(self):
        """Test response message creation."""
        response = ResponseMessage(
            id="resp_123",
            request_id="req_123",
            result={"frame_data": "base64_encoded_data", "timestamp": 3.33}
        )
        
        assert response.id == "resp_123"
        assert response.type == MessageType.RESPONSE
        assert response.request_id == "req_123"
        assert response.result["timestamp"] == 3.33
    
    def test_error_message(self):
        """Test error message creation."""
        error = ErrorMessage(
            id="err_123",
            request_id="req_123",
            code=404,
            message="Frame not found",
            data={"frame_id": 100}
        )
        
        assert error.type == MessageType.ERROR
        assert error.code == 404
        assert error.message == "Frame not found"
        assert error.data["frame_id"] == 100
    
    def test_message_encoding_decoding(self):
        """Test message encoding and decoding."""
        # Create message
        original = RequestMessage(
            id="test_123",
            method="process_frame",
            params={"frame_path": "/frames/001.jpg", "detectors": ["clock", "continuity"]}
        )
        
        # Encode
        encoded = encode_message(original)
        assert isinstance(encoded, bytes)
        
        # Decode
        decoded = decode_message(encoded)
        assert decoded.id == original.id
        assert decoded.method == original.method
        assert decoded.params == original.params
    
    def test_protocol_version_negotiation(self):
        """Test protocol version negotiation."""
        protocol = Protocol(version="2.0")
        
        # Check compatibility
        assert protocol.is_compatible("2.0") is True
        assert protocol.is_compatible("2.1") is True  # Minor version compatible
        assert protocol.is_compatible("1.0") is False  # Major version incompatible
        
        # Negotiate version
        client_versions = ["1.0", "2.0", "2.1"]
        negotiated = protocol.negotiate_version(client_versions)
        assert negotiated == "2.0"


class TestServiceDiscovery:
    """Test service discovery functionality."""
    
    def test_service_info(self):
        """Test service information model."""
        service = ServiceInfo(
            name="StorageService",
            id="storage_001",
            host="localhost",
            port=8001,
            protocol="http",
            version="1.0.0",
            metadata={
                "capacity": "1TB",
                "region": "us-west"
            }
        )
        
        assert service.name == "StorageService"
        assert service.endpoint == "http://localhost:8001"
        assert service.metadata["capacity"] == "1TB"
    
    def test_service_registry(self):
        """Test service registry operations."""
        registry = ServiceRegistry()
        
        # Register service
        service = ServiceInfo(
            name="APIGateway",
            id="api_001",
            host="localhost",
            port=8000
        )
        
        registry.register(service)
        
        # Lookup by name
        found = registry.lookup_by_name("APIGateway")
        assert len(found) == 1
        assert found[0].id == "api_001"
        
        # Lookup by ID
        found = registry.lookup_by_id("api_001")
        assert found is not None
        assert found.port == 8000
        
        # Deregister
        registry.deregister("api_001")
        assert registry.lookup_by_id("api_001") is None
    
    def test_heartbeat_monitoring(self):
        """Test service heartbeat monitoring."""
        monitor = HeartbeatMonitor(interval=0.1, timeout=0.3)
        
        service_id = "test_service"
        
        # Start monitoring
        monitor.start_monitoring(service_id)
        
        # Send heartbeats
        for _ in range(3):
            monitor.heartbeat(service_id)
            time.sleep(0.08)
        
        assert monitor.is_healthy(service_id) is True
        
        # Stop heartbeats
        time.sleep(0.4)
        
        assert monitor.is_healthy(service_id) is False
        
        # Get last heartbeat
        last_heartbeat = monitor.get_last_heartbeat(service_id)
        assert time.time() - last_heartbeat > 0.3
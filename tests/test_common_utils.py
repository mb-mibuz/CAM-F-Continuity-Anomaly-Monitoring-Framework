"""
Tests for CAMF common utilities and helper functions.
"""

import pytest
import json
import os
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from CAMF.common.utils import (
    get_timestamp,
    ensure_directory,
    safe_json_dump,
    safe_json_load,
    format_file_size,
    sanitize_filename,
    get_file_hash
)
from CAMF.common.config import Config
from CAMF.common.resolution_utils import (
    parse_resolution,
    get_resolution_string,
    calculate_aspect_ratio,
    is_valid_resolution
)


class TestCommonUtils:
    """Test common utility functions."""
    
    def test_get_timestamp(self):
        """Test timestamp generation."""
        # Test basic timestamp
        ts1 = get_timestamp()
        assert isinstance(ts1, str)
        assert len(ts1) == 19  # YYYY-MM-DD_HH-MM-SS
        
        # Test timestamps are unique
        import time
        time.sleep(1)
        ts2 = get_timestamp()
        assert ts1 != ts2
        
        # Test format
        datetime.strptime(ts1, "%Y-%m-%d_%H-%M-%S")
    
    def test_ensure_directory(self, tmp_path):
        """Test directory creation."""
        # Test creating new directory
        new_dir = tmp_path / "test_dir"
        result = ensure_directory(str(new_dir))
        assert result == str(new_dir)
        assert new_dir.exists()
        assert new_dir.is_dir()
        
        # Test with existing directory
        result2 = ensure_directory(str(new_dir))
        assert result2 == str(new_dir)
        
        # Test nested directories
        nested = tmp_path / "a" / "b" / "c"
        result3 = ensure_directory(str(nested))
        assert nested.exists()
    
    def test_safe_json_dump(self, tmp_path):
        """Test safe JSON dumping."""
        data = {
            "name": "test",
            "value": 123,
            "nested": {"key": "value"},
            "list": [1, 2, 3]
        }
        
        # Test successful dump
        json_file = tmp_path / "test.json"
        result = safe_json_dump(data, str(json_file))
        assert result is True
        assert json_file.exists()
        
        # Verify content
        with open(json_file) as f:
            loaded = json.load(f)
        assert loaded == data
        
        # Test with invalid data
        invalid_data = {"func": lambda x: x}  # Functions can't be serialized
        result2 = safe_json_dump(invalid_data, str(tmp_path / "invalid.json"))
        assert result2 is False
    
    def test_safe_json_load(self, tmp_path):
        """Test safe JSON loading."""
        # Create test file
        data = {"test": "data", "num": 42}
        json_file = tmp_path / "test.json"
        with open(json_file, 'w') as f:
            json.dump(data, f)
        
        # Test successful load
        loaded = safe_json_load(str(json_file))
        assert loaded == data
        
        # Test non-existent file
        result = safe_json_load(str(tmp_path / "missing.json"))
        assert result is None
        
        # Test invalid JSON
        invalid_file = tmp_path / "invalid.json"
        with open(invalid_file, 'w') as f:
            f.write("not json")
        result2 = safe_json_load(str(invalid_file))
        assert result2 is None
    
    def test_format_file_size(self):
        """Test file size formatting."""
        # Test bytes
        assert format_file_size(500) == "500.0 B"
        
        # Test KB
        assert format_file_size(1500) == "1.5 KB"
        assert format_file_size(1024) == "1.0 KB"
        
        # Test MB
        assert format_file_size(1024 * 1024) == "1.0 MB"
        assert format_file_size(1024 * 1024 * 2.5) == "2.5 MB"
        
        # Test GB
        assert format_file_size(1024 * 1024 * 1024) == "1.0 GB"
        
        # Test TB
        assert format_file_size(1024 * 1024 * 1024 * 1024) == "1.0 TB"
        
        # Test zero
        assert format_file_size(0) == "0.0 B"
    
    def test_sanitize_filename(self):
        """Test filename sanitization."""
        # Test normal filename
        assert sanitize_filename("test.txt") == "test.txt"
        
        # Test with spaces
        assert sanitize_filename("my file.txt") == "my_file.txt"
        
        # Test with special characters
        assert sanitize_filename("file/with\\slashes.txt") == "file_with_slashes.txt"
        assert sanitize_filename("file:with*chars?.txt") == "file_with_chars_.txt"
        
        # Test with multiple dots
        assert sanitize_filename("file.name.with.dots.txt") == "file.name.with.dots.txt"
        
        # Test empty string
        assert sanitize_filename("") == "unnamed"
        
        # Test very long filename
        long_name = "a" * 300 + ".txt"
        sanitized = sanitize_filename(long_name)
        assert len(sanitized) <= 255
        assert sanitized.endswith(".txt")
    
    def test_get_file_hash(self, tmp_path):
        """Test file hash calculation."""
        # Create test file
        test_file = tmp_path / "test.txt"
        content = b"Hello, World!"
        with open(test_file, 'wb') as f:
            f.write(content)
        
        # Test MD5 hash
        md5_hash = get_file_hash(str(test_file), algorithm='md5')
        assert isinstance(md5_hash, str)
        assert len(md5_hash) == 32  # MD5 produces 32 hex chars
        
        # Test SHA256 hash
        sha256_hash = get_file_hash(str(test_file), algorithm='sha256')
        assert isinstance(sha256_hash, str)
        assert len(sha256_hash) == 64  # SHA256 produces 64 hex chars
        
        # Test consistency
        hash2 = get_file_hash(str(test_file), algorithm='md5')
        assert hash2 == md5_hash
        
        # Test non-existent file
        result = get_file_hash(str(tmp_path / "missing.txt"))
        assert result is None


class TestConfig:
    """Test configuration management."""
    
    def test_config_singleton(self):
        """Test Config is a singleton."""
        config1 = Config()
        config2 = Config()
        assert config1 is config2
    
    def test_config_get_set(self):
        """Test getting and setting config values."""
        config = Config()
        
        # Test setting and getting
        config.set("test_key", "test_value")
        assert config.get("test_key") == "test_value"
        
        # Test default value
        assert config.get("missing_key", "default") == "default"
        
        # Test nested keys
        config.set("nested.key", "nested_value")
        assert config.get("nested.key") == "nested_value"
    
    def test_config_get_all(self):
        """Test getting all config values."""
        config = Config()
        config.set("key1", "value1")
        config.set("key2", "value2")
        
        all_config = config.get_all()
        assert isinstance(all_config, dict)
        assert "key1" in all_config
        assert "key2" in all_config
    
    @patch.dict(os.environ, {"CAMF_TEST_VAR": "env_value"})
    def test_config_from_env(self):
        """Test loading config from environment."""
        config = Config()
        
        # Test environment variable override
        value = config.get("TEST_VAR", env_prefix="CAMF_")
        assert value == "env_value"
    
    def test_config_load_save(self, tmp_path):
        """Test loading and saving config files."""
        config_file = tmp_path / "config.json"
        
        config = Config()
        config.set("save_test", "save_value")
        
        # Test save
        config.save(str(config_file))
        assert config_file.exists()
        
        # Test load
        config2 = Config()
        config2.load(str(config_file))
        assert config2.get("save_test") == "save_value"


class TestResolutionUtils:
    """Test resolution utility functions."""
    
    def test_parse_resolution(self):
        """Test resolution parsing."""
        # Test standard formats
        assert parse_resolution("1920x1080") == (1920, 1080)
        assert parse_resolution("1280x720") == (1280, 720)
        assert parse_resolution("3840x2160") == (3840, 2160)
        
        # Test with different separators
        assert parse_resolution("1920X1080") == (1920, 1080)
        assert parse_resolution("1920*1080") == (1920, 1080)
        
        # Test invalid formats
        assert parse_resolution("invalid") == (0, 0)
        assert parse_resolution("1920") == (0, 0)
        assert parse_resolution("") == (0, 0)
    
    def test_get_resolution_string(self):
        """Test resolution string formatting."""
        assert get_resolution_string(1920, 1080) == "1920x1080"
        assert get_resolution_string(1280, 720) == "1280x720"
        assert get_resolution_string(0, 0) == "0x0"
    
    def test_calculate_aspect_ratio(self):
        """Test aspect ratio calculation."""
        # Test common ratios
        assert calculate_aspect_ratio(1920, 1080) == pytest.approx(16/9, rel=0.01)
        assert calculate_aspect_ratio(1280, 720) == pytest.approx(16/9, rel=0.01)
        assert calculate_aspect_ratio(2560, 1440) == pytest.approx(16/9, rel=0.01)
        
        # Test 4:3 ratio
        assert calculate_aspect_ratio(1024, 768) == pytest.approx(4/3, rel=0.01)
        
        # Test edge cases
        assert calculate_aspect_ratio(1920, 0) == 0
        assert calculate_aspect_ratio(0, 1080) == 0
    
    def test_is_valid_resolution(self):
        """Test resolution validation."""
        # Test valid resolutions
        assert is_valid_resolution(1920, 1080) is True
        assert is_valid_resolution(1280, 720) is True
        assert is_valid_resolution(640, 480) is True
        
        # Test invalid resolutions
        assert is_valid_resolution(0, 1080) is False
        assert is_valid_resolution(1920, 0) is False
        assert is_valid_resolution(-1920, 1080) is False
        assert is_valid_resolution(1920, -1080) is False
        assert is_valid_resolution(100000, 100000) is False  # Too large


class TestServiceDiscovery:
    """Test service discovery functionality."""
    
    @patch('CAMF.common.service_discovery.requests.get')
    def test_discover_service(self, mock_get):
        """Test service discovery."""
        from CAMF.common.service_discovery import discover_service
        
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "healthy"}
        mock_get.return_value = mock_response
        
        # Test discovery
        result = discover_service("test_service", port=8000)
        assert result == "http://localhost:8000"
        
        # Test with custom host
        result2 = discover_service("test_service", host="192.168.1.1", port=9000)
        assert result2 == "http://192.168.1.1:9000"
    
    @patch('CAMF.common.service_discovery.requests.get')
    def test_check_service_health(self, mock_get):
        """Test service health check."""
        from CAMF.common.service_discovery import check_service_health
        
        # Mock healthy response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "healthy"}
        mock_get.return_value = mock_response
        
        # Test health check
        is_healthy = check_service_health("http://localhost:8000")
        assert is_healthy is True
        
        # Mock unhealthy response
        mock_get.side_effect = Exception("Connection error")
        is_healthy2 = check_service_health("http://localhost:8000")
        assert is_healthy2 is False


class TestProtocol:
    """Test protocol utilities."""
    
    def test_message_packing(self):
        """Test message packing and unpacking."""
        from CAMF.common.protocol import pack_message, unpack_message
        
        # Test simple message
        data = {"type": "test", "value": 42}
        packed = pack_message(data)
        assert isinstance(packed, bytes)
        
        unpacked = unpack_message(packed)
        assert unpacked == data
        
        # Test complex message
        complex_data = {
            "type": "complex",
            "nested": {"key": "value"},
            "list": [1, 2, 3],
            "timestamp": 1234567890.123
        }
        packed2 = pack_message(complex_data)
        unpacked2 = unpack_message(packed2)
        assert unpacked2 == complex_data
    
    def test_protocol_version(self):
        """Test protocol version handling."""
        from CAMF.common.protocol import get_protocol_version, is_compatible_version
        
        version = get_protocol_version()
        assert isinstance(version, str)
        assert "." in version  # Should be like "1.0"
        
        # Test compatibility
        assert is_compatible_version(version) is True
        assert is_compatible_version("0.1") is False  # Old version
        assert is_compatible_version("99.0") is False  # Future version


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
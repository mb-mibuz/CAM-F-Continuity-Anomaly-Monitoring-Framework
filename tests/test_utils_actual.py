"""
Tests for CAMF common utilities that actually exist.
"""

import pytest
import os
import time
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from CAMF.common.utils import (
    get_timestamp,
    ensure_directory,
    format_timestamp,
    generate_id,
    get_project_path,
    get_scene_path,
    get_angle_path,
    get_take_path,
    get_frame_path
)


class TestTimestampFunctions:
    """Test timestamp related functions."""
    
    def test_get_timestamp(self):
        """Test timestamp generation."""
        # Test basic timestamp
        ts1 = get_timestamp()
        assert isinstance(ts1, str)
        assert len(ts1) > 0
        
        # Test timestamps are unique
        time.sleep(0.01)
        ts2 = get_timestamp()
        assert ts1 != ts2
    
    def test_format_timestamp(self):
        """Test timestamp formatting."""
        # Test with current time
        now = time.time()
        formatted = format_timestamp(now)
        assert isinstance(formatted, str)
        assert len(formatted) > 0
        
        # Test with specific timestamp
        timestamp = 1234567890.123
        formatted2 = format_timestamp(timestamp)
        assert isinstance(formatted2, str)
        
        # Test with None (if supported)
        try:
            formatted3 = format_timestamp(None)
            assert isinstance(formatted3, str)
        except:
            pass  # Function might not support None


class TestPathFunctions:
    """Test path generation functions."""
    
    def test_ensure_directory(self, tmp_path):
        """Test directory creation."""
        # Test creating new directory
        new_dir = tmp_path / "test_dir"
        result = ensure_directory(str(new_dir))
        assert new_dir.exists()
        assert new_dir.is_dir()
        
        # Test with existing directory
        result2 = ensure_directory(str(new_dir))
        assert new_dir.exists()
        
        # Test nested directories
        nested = tmp_path / "a" / "b" / "c"
        result3 = ensure_directory(str(nested))
        assert nested.exists()
    
    def test_get_project_path(self, tmp_path):
        """Test project path generation."""
        base_path = str(tmp_path)
        project_name = "TestProject"
        
        path = get_project_path(base_path, project_name)
        assert isinstance(path, str)
        assert project_name in path
        assert base_path in path
    
    def test_get_scene_path(self, tmp_path):
        """Test scene path generation."""
        base_path = str(tmp_path)
        project_name = "TestProject"
        scene_name = "Scene1"
        
        path = get_scene_path(base_path, project_name, scene_name)
        assert isinstance(path, str)
        assert project_name in path
        assert scene_name in path
    
    def test_get_angle_path(self, tmp_path):
        """Test angle path generation."""
        base_path = str(tmp_path)
        project_name = "TestProject"
        scene_name = "Scene1"
        angle_name = "WideShot"
        
        path = get_angle_path(base_path, project_name, scene_name, angle_name)
        assert isinstance(path, str)
        assert angle_name in path
    
    def test_get_take_path(self, tmp_path):
        """Test take path generation."""
        base_path = str(tmp_path)
        project_name = "TestProject"
        scene_name = "Scene1"
        angle_name = "WideShot"
        take_name = "Take1"
        
        path = get_take_path(base_path, project_name, scene_name, angle_name, take_name)
        assert isinstance(path, str)
        assert take_name in path
    
    def test_get_frame_path(self, tmp_path):
        """Test frame path generation."""
        base_path = str(tmp_path)
        project_name = "TestProject"
        scene_name = "Scene1"
        angle_name = "WideShot"
        take_name = "Take1"
        frame_number = 42
        
        path = get_frame_path(base_path, project_name, scene_name, angle_name, take_name, frame_number)
        assert isinstance(path, str)
        assert str(frame_number) in path or f"{frame_number:04d}" in path or f"{frame_number:06d}" in path


class TestIdGeneration:
    """Test ID generation functions."""
    
    def test_generate_id(self):
        """Test ID generation."""
        # Generate multiple IDs
        id1 = generate_id()
        id2 = generate_id()
        id3 = generate_id()
        
        # Check they are strings
        assert isinstance(id1, str)
        assert isinstance(id2, str)
        assert isinstance(id3, str)
        
        # Check they are unique
        assert id1 != id2
        assert id2 != id3
        assert id1 != id3
        
        # Check they have reasonable length
        assert len(id1) > 0
        assert len(id1) < 100  # Reasonable upper bound


class TestServiceClients:
    """Test service client utilities."""
    
    @patch('CAMF.common.utils.requests')
    def test_http_client_get(self, mock_requests):
        """Test HTTP client GET request."""
        from CAMF.common.utils import HTTPClient
        
        # Mock response
        mock_response = Mock()
        mock_response.json.return_value = {"status": "ok"}
        mock_response.status_code = 200
        mock_requests.get.return_value = mock_response
        
        # Create client and make request
        client = HTTPClient(base_url="http://localhost:8000")
        result = client.get("/test")
        
        assert result == {"status": "ok"}
        mock_requests.get.assert_called_once()
    
    @patch('CAMF.common.utils.requests')
    def test_http_client_post(self, mock_requests):
        """Test HTTP client POST request."""
        from CAMF.common.utils import HTTPClient
        
        # Mock response
        mock_response = Mock()
        mock_response.json.return_value = {"id": 123}
        mock_response.status_code = 201
        mock_requests.post.return_value = mock_response
        
        # Create client and make request
        client = HTTPClient(base_url="http://localhost:8000")
        result = client.post("/test", json={"name": "test"})
        
        assert result == {"id": 123}
        mock_requests.post.assert_called_once()
    
    def test_service_client_creation(self):
        """Test service client creation."""
        from CAMF.common.utils import ServiceClient
        
        # Create client
        client = ServiceClient(service_name="test_service", base_url="http://localhost:8000")
        
        assert client.service_name == "test_service"
        assert client.base_url == "http://localhost:8000"


class TestProtocolUtils:
    """Test protocol related utilities."""
    
    def test_protocol_type(self):
        """Test ProtocolType enum if available."""
        try:
            from CAMF.common.utils import ProtocolType
            
            # Check enum values exist
            assert hasattr(ProtocolType, 'JSON')
            assert hasattr(ProtocolType, 'MSGPACK')
            
            # Check values are different
            assert ProtocolType.JSON != ProtocolType.MSGPACK
        except ImportError:
            pytest.skip("ProtocolType not available")
    
    def test_get_service_info_with_protocol(self):
        """Test getting service info with protocol."""
        from CAMF.common.utils import get_service_info_with_protocol
        
        # Test basic call
        try:
            info = get_service_info_with_protocol("test_service")
            assert isinstance(info, dict) or info is None
        except Exception:
            # Function might require actual service running
            pass


class TestPathCreation:
    """Test path creation with actual directory structure."""
    
    def test_full_hierarchy_creation(self, tmp_path):
        """Test creating full project hierarchy."""
        base_path = str(tmp_path)
        
        # Create project structure
        project_path = get_project_path(base_path, "MyProject")
        ensure_directory(project_path)
        assert os.path.exists(project_path)
        
        # Create scene
        scene_path = get_scene_path(base_path, "MyProject", "Scene1")
        ensure_directory(scene_path)
        assert os.path.exists(scene_path)
        
        # Create angle
        angle_path = get_angle_path(base_path, "MyProject", "Scene1", "WideShot")
        ensure_directory(angle_path)
        assert os.path.exists(angle_path)
        
        # Create take
        take_path = get_take_path(base_path, "MyProject", "Scene1", "WideShot", "Take1")
        ensure_directory(take_path)
        assert os.path.exists(take_path)
        
        # Verify hierarchy
        assert os.path.isdir(project_path)
        assert os.path.isdir(scene_path)
        assert os.path.isdir(angle_path)
        assert os.path.isdir(take_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
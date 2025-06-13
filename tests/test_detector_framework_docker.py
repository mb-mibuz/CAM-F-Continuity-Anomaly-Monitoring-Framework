"""
Comprehensive tests for detector framework Docker management.
Tests Docker container lifecycle, resource limits, and security isolation.
"""

import pytest
import docker
from unittest.mock import Mock, patch, MagicMock, call
import tempfile
import os
import json
import time
import threading
from datetime import datetime
import shutil

from CAMF.services.detector_framework.docker_manager import (
    DockerDetectorManager, DockerContainer, ContainerStatus,
    ResourceLimits, SecurityProfile
)
from CAMF.services.detector_framework.docker_detector_base import DockerDetectorBase
from CAMF.services.detector_framework.docker_installer import DockerInstaller


class TestDockerDetectorManager:
    """Test Docker detector management functionality."""
    
    @pytest.fixture
    def mock_docker_client(self):
        """Create mock Docker client."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.version.return_value = {"Version": "20.10.0"}
        
        # Mock container
        mock_container = MagicMock()
        mock_container.id = "test_container_123"
        mock_container.status = "running"
        mock_container.attrs = {
            "State": {"Status": "running", "Running": True},
            "Config": {"Image": "detector:latest"}
        }
        mock_container.logs.return_value = b"Container logs"
        
        mock_client.containers.create.return_value = mock_container
        mock_client.containers.get.return_value = mock_container
        mock_client.containers.list.return_value = [mock_container]
        
        return mock_client
    
    @pytest.fixture
    def docker_manager(self, mock_docker_client):
        """Create Docker manager with mocked client."""
        with patch('docker.from_env', return_value=mock_docker_client):
            manager = DockerDetectorManager()
            manager.client = mock_docker_client
            return manager
    
    def test_docker_availability_check(self, docker_manager):
        """Test checking Docker availability."""
        # Docker available
        is_available = docker_manager.check_docker_availability()
        assert is_available is True
        
        # Docker not available
        docker_manager.client.ping.side_effect = Exception("Docker not running")
        is_available = docker_manager.check_docker_availability()
        assert is_available is False
    
    def test_create_detector_container(self, docker_manager, mock_docker_client):
        """Test creating detector container."""
        detector_config = {
            "name": "ClockDetector",
            "image": "camf/clock-detector:latest",
            "environment": {"DETECTOR_MODE": "production"}
        }
        
        # Create container
        container = docker_manager.create_detector_container(
            detector_name="ClockDetector",
            config=detector_config
        )
        
        assert container is not None
        assert container.id == "test_container_123"
        
        # Verify container creation parameters
        mock_docker_client.containers.create.assert_called_once()
        call_args = mock_docker_client.containers.create.call_args
        
        assert call_args[1]["name"] == "camf_detector_ClockDetector"
        assert call_args[1]["environment"]["DETECTOR_MODE"] == "production"
    
    def test_container_resource_limits(self, docker_manager, mock_docker_client):
        """Test setting container resource limits."""
        limits = ResourceLimits(
            cpu_shares=512,      # 0.5 CPU
            memory_limit="512m",
            memory_swap="1g",
            pids_limit=100,
            cpu_period=100000,
            cpu_quota=50000      # 50% CPU
        )
        
        # Create container with limits
        container = docker_manager.create_detector_container(
            detector_name="TestDetector",
            config={"image": "test:latest"},
            resource_limits=limits
        )
        
        # Verify resource limits
        call_args = mock_docker_client.containers.create.call_args[1]
        assert call_args["cpu_shares"] == 512
        assert call_args["mem_limit"] == "512m"
        assert call_args["memswap_limit"] == "1g"
        assert call_args["pids_limit"] == 100
    
    def test_container_security_profile(self, docker_manager, mock_docker_client):
        """Test applying security profile to container."""
        security = SecurityProfile(
            read_only_root=True,
            no_new_privileges=True,
            drop_capabilities=["ALL"],
            add_capabilities=["SYS_PTRACE"],
            seccomp_profile="default",
            user="1000:1000"
        )
        
        # Create container with security profile
        container = docker_manager.create_detector_container(
            detector_name="SecureDetector",
            config={"image": "secure:latest"},
            security_profile=security
        )
        
        # Verify security settings
        call_args = mock_docker_client.containers.create.call_args[1]
        assert call_args["read_only"] is True
        assert call_args["security_opt"] == ["no-new-privileges"]
        assert call_args["cap_drop"] == ["ALL"]
        assert call_args["cap_add"] == ["SYS_PTRACE"]
        assert call_args["user"] == "1000:1000"
    
    def test_container_volume_mounting(self, docker_manager, mock_docker_client):
        """Test volume mounting for detector workspace."""
        workspace_dir = "/tmp/detector_workspace"
        
        # Create container with volume
        container = docker_manager.create_detector_container(
            detector_name="VolumeDetector",
            config={"image": "volume:latest"},
            workspace_dir=workspace_dir
        )
        
        # Verify volume mounting
        call_args = mock_docker_client.containers.create.call_args[1]
        assert "volumes" in call_args
        assert workspace_dir in str(call_args["volumes"])
    
    def test_container_lifecycle_management(self, docker_manager, mock_docker_client):
        """Test container lifecycle operations."""
        container = docker_manager.create_detector_container(
            detector_name="LifecycleDetector",
            config={"image": "lifecycle:latest"}
        )
        
        # Start container
        success = docker_manager.start_container(container.id)
        assert success is True
        container.start.assert_called_once()
        
        # Stop container
        success = docker_manager.stop_container(container.id, timeout=10)
        assert success is True
        container.stop.assert_called_with(timeout=10)
        
        # Remove container
        success = docker_manager.remove_container(container.id, force=True)
        assert success is True
        container.remove.assert_called_with(force=True)
    
    def test_container_health_monitoring(self, docker_manager, mock_docker_client):
        """Test container health monitoring."""
        container = docker_manager.create_detector_container(
            detector_name="HealthDetector",
            config={"image": "health:latest"}
        )
        
        # Check healthy container
        health = docker_manager.get_container_health(container.id)
        assert health["status"] == ContainerStatus.RUNNING
        assert health["cpu_usage"] >= 0
        assert health["memory_usage"] >= 0
        
        # Simulate unhealthy container
        container.attrs["State"]["Status"] = "exited"
        container.attrs["State"]["Running"] = False
        container.attrs["State"]["ExitCode"] = 1
        
        health = docker_manager.get_container_health(container.id)
        assert health["status"] == ContainerStatus.EXITED
        assert health["exit_code"] == 1
    
    def test_container_logs_retrieval(self, docker_manager, mock_docker_client):
        """Test retrieving container logs."""
        container = docker_manager.create_detector_container(
            detector_name="LogDetector",
            config={"image": "log:latest"}
        )
        
        # Get logs
        logs = docker_manager.get_container_logs(
            container.id,
            tail=100,
            since=datetime.now()
        )
        
        assert logs is not None
        container.logs.assert_called_once()
    
    def test_multiple_container_management(self, docker_manager, mock_docker_client):
        """Test managing multiple detector containers."""
        # Create multiple containers
        containers = []
        for i in range(3):
            container = docker_manager.create_detector_container(
                detector_name=f"Detector{i}",
                config={"image": f"detector{i}:latest"}
            )
            containers.append(container)
        
        # List all detector containers
        all_containers = docker_manager.list_detector_containers()
        assert len(all_containers) >= 3
        
        # Stop all containers
        docker_manager.stop_all_containers()
        for container in containers:
            container.stop.assert_called()


class TestDockerDetectorBase:
    """Test Docker detector base functionality."""
    
    @pytest.fixture
    def detector_config(self):
        """Create detector configuration."""
        return {
            "name": "TestDetector",
            "version": "1.0.0",
            "image": "test-detector:latest",
            "command": ["python", "detector.py"],
            "working_dir": "/app",
            "environment": {
                "PYTHONUNBUFFERED": "1",
                "DETECTOR_MODE": "production"
            }
        }
    
    @pytest.fixture
    def docker_detector(self, detector_config):
        """Create Docker detector instance."""
        return DockerDetectorBase(config=detector_config)
    
    def test_detector_initialization(self, docker_detector, detector_config):
        """Test Docker detector initialization."""
        assert docker_detector.name == "TestDetector"
        assert docker_detector.version == "1.0.0"
        assert docker_detector.image == "test-detector:latest"
        assert docker_detector.status == ContainerStatus.CREATED
    
    def test_build_container_config(self, docker_detector):
        """Test building container configuration."""
        container_config = docker_detector.build_container_config()
        
        assert container_config["image"] == "test-detector:latest"
        assert container_config["command"] == ["python", "detector.py"]
        assert container_config["working_dir"] == "/app"
        assert container_config["environment"]["DETECTOR_MODE"] == "production"
        
        # Security defaults
        assert container_config["network_mode"] == "none"  # Network isolation
        assert container_config["read_only"] is True
        assert container_config["security_opt"] == ["no-new-privileges"]
    
    def test_detector_workspace_setup(self, docker_detector):
        """Test detector workspace setup."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = docker_detector.setup_workspace(base_dir=temp_dir)
            
            assert os.path.exists(workspace)
            assert os.path.exists(os.path.join(workspace, "input"))
            assert os.path.exists(os.path.join(workspace, "output"))
            assert os.path.exists(os.path.join(workspace, "temp"))
            
            # Check permissions
            stat_info = os.stat(workspace)
            assert stat_info.st_mode & 0o777 == 0o755
    
    def test_detector_input_preparation(self, docker_detector):
        """Test preparing input for detector."""
        with tempfile.TemporaryDirectory() as workspace:
            input_data = {
                "frame_path": "/frames/frame_001.jpg",
                "metadata": {"timestamp": 1234567890}
            }
            
            # Prepare input
            input_file = docker_detector.prepare_input(
                workspace=workspace,
                data=input_data
            )
            
            assert os.path.exists(input_file)
            
            # Verify input content
            with open(input_file, 'r') as f:
                loaded_data = json.load(f)
            assert loaded_data["frame_path"] == input_data["frame_path"]
            assert loaded_data["metadata"]["timestamp"] == 1234567890
    
    def test_detector_output_parsing(self, docker_detector):
        """Test parsing detector output."""
        with tempfile.TemporaryDirectory() as workspace:
            output_data = {
                "detected": True,
                "confidence": 0.95,
                "objects": [
                    {"type": "clock", "bbox": [100, 100, 200, 150]}
                ]
            }
            
            # Write output file
            output_file = os.path.join(workspace, "output", "result.json")
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            with open(output_file, 'w') as f:
                json.dump(output_data, f)
            
            # Parse output
            result = docker_detector.parse_output(workspace=workspace)
            
            assert result["detected"] is True
            assert result["confidence"] == 0.95
            assert len(result["objects"]) == 1
            assert result["objects"][0]["type"] == "clock"


class TestDockerInstaller:
    """Test Docker image installation and management."""
    
    @pytest.fixture
    def mock_docker_client(self):
        """Create mock Docker client for installer."""
        mock_client = MagicMock()
        
        # Mock image operations
        mock_image = MagicMock()
        mock_image.tags = ["test-detector:latest"]
        mock_image.id = "sha256:abcdef123456"
        mock_image.attrs = {
            "Size": 500 * 1024 * 1024,  # 500MB
            "Created": "2024-01-01T00:00:00Z"
        }
        
        mock_client.images.pull.return_value = mock_image
        mock_client.images.get.return_value = mock_image
        mock_client.images.list.return_value = [mock_image]
        mock_client.images.build.return_value = (mock_image, [])
        
        return mock_client
    
    @pytest.fixture
    def docker_installer(self, mock_docker_client):
        """Create Docker installer with mocked client."""
        with patch('docker.from_env', return_value=mock_docker_client):
            installer = DockerInstaller()
            installer.client = mock_docker_client
            return installer
    
    def test_pull_detector_image(self, docker_installer, mock_docker_client):
        """Test pulling detector image from registry."""
        # Pull image
        success = docker_installer.pull_image(
            image_name="camf/clock-detector",
            tag="latest"
        )
        
        assert success is True
        mock_docker_client.images.pull.assert_called_with(
            "camf/clock-detector",
            tag="latest"
        )
    
    def test_build_detector_image(self, docker_installer, mock_docker_client):
        """Test building detector image from Dockerfile."""
        with tempfile.TemporaryDirectory() as build_dir:
            # Create Dockerfile
            dockerfile_content = """
            FROM python:3.9-slim
            WORKDIR /app
            COPY . .
            RUN pip install -r requirements.txt
            CMD ["python", "detector.py"]
            """
            
            dockerfile_path = os.path.join(build_dir, "Dockerfile")
            with open(dockerfile_path, 'w') as f:
                f.write(dockerfile_content)
            
            # Build image
            success, image_id = docker_installer.build_image(
                build_context=build_dir,
                tag="custom-detector:latest"
            )
            
            assert success is True
            assert image_id == "sha256:abcdef123456"
            
            mock_docker_client.images.build.assert_called_once()
            call_args = mock_docker_client.images.build.call_args
            assert call_args[1]["path"] == build_dir
            assert call_args[1]["tag"] == "custom-detector:latest"
    
    def test_image_cache_management(self, docker_installer):
        """Test Docker image cache management."""
        # Get cached images
        cached_images = docker_installer.get_cached_images(prefix="camf/")
        assert len(cached_images) > 0
        
        # Check cache size
        cache_size = docker_installer.get_cache_size()
        assert cache_size > 0
        
        # Clean old images
        removed = docker_installer.clean_old_images(days_old=30)
        assert isinstance(removed, list)
    
    def test_image_verification(self, docker_installer, mock_docker_client):
        """Test verifying detector image integrity."""
        # Verify image exists
        exists = docker_installer.image_exists("test-detector:latest")
        assert exists is True
        
        # Verify image signature (if supported)
        is_verified = docker_installer.verify_image_signature(
            image="test-detector:latest",
            expected_digest="sha256:abcdef123456"
        )
        assert is_verified is True
    
    def test_multi_platform_support(self, docker_installer):
        """Test multi-platform image support."""
        platforms = docker_installer.get_supported_platforms()
        
        # Should support common platforms
        assert "linux/amd64" in platforms
        assert "linux/arm64" in platforms
        
        # Check current platform
        current_platform = docker_installer.get_current_platform()
        assert current_platform in platforms


class TestDockerResourceMonitoring:
    """Test Docker resource monitoring and limits."""
    
    @pytest.fixture
    def resource_monitor(self, mock_docker_client):
        """Create resource monitor."""
        from CAMF.services.detector_framework.docker_manager import DockerResourceMonitor
        monitor = DockerResourceMonitor(client=mock_docker_client)
        return monitor
    
    def test_container_resource_usage(self, resource_monitor, mock_docker_client):
        """Test monitoring container resource usage."""
        container_id = "test_container_123"
        
        # Mock stats
        mock_stats = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 1000000000},
                "system_cpu_usage": 2000000000
            },
            "memory_stats": {
                "usage": 100 * 1024 * 1024,  # 100MB
                "limit": 512 * 1024 * 1024   # 512MB
            }
        }
        
        mock_container = MagicMock()
        mock_container.stats.return_value = iter([mock_stats])
        mock_docker_client.containers.get.return_value = mock_container
        
        # Get resource usage
        usage = resource_monitor.get_container_usage(container_id)
        
        assert usage["cpu_percent"] > 0
        assert usage["memory_mb"] == 100
        assert usage["memory_percent"] == pytest.approx(19.5, rel=0.1)
    
    def test_resource_limit_enforcement(self, resource_monitor):
        """Test enforcing resource limits."""
        limits = {
            "cpu_percent": 50,
            "memory_mb": 512,
            "disk_mb": 1024
        }
        
        # Check if usage exceeds limits
        usage = {
            "cpu_percent": 75,
            "memory_mb": 300,
            "disk_mb": 2000
        }
        
        violations = resource_monitor.check_limit_violations(usage, limits)
        
        assert len(violations) == 2
        assert "cpu_percent" in violations
        assert "disk_mb" in violations
        assert "memory_mb" not in violations
    
    def test_resource_alerts(self, resource_monitor):
        """Test resource usage alerts."""
        alert_callbacks = []
        
        def alert_handler(alert):
            alert_callbacks.append(alert)
        
        # Set alert thresholds
        resource_monitor.set_alert_handler(alert_handler)
        resource_monitor.set_alert_thresholds({
            "cpu_percent": 80,
            "memory_percent": 90
        })
        
        # Simulate high usage
        high_usage = {
            "container_id": "test_123",
            "cpu_percent": 85,
            "memory_percent": 95
        }
        
        resource_monitor.check_alerts(high_usage)
        
        assert len(alert_callbacks) == 2
        assert any(a["metric"] == "cpu_percent" for a in alert_callbacks)
        assert any(a["metric"] == "memory_percent" for a in alert_callbacks)


class TestDockerNetworkIsolation:
    """Test Docker network isolation for detectors."""
    
    @pytest.fixture
    def network_manager(self, mock_docker_client):
        """Create network manager."""
        from CAMF.services.detector_framework.docker_manager import DockerNetworkManager
        return DockerNetworkManager(client=mock_docker_client)
    
    def test_create_isolated_network(self, network_manager, mock_docker_client):
        """Test creating isolated network for detectors."""
        # Create network
        network = network_manager.create_detector_network(
            name="detector_isolated",
            internal=True,  # No external access
            enable_ipv6=False
        )
        
        mock_docker_client.networks.create.assert_called_with(
            name="detector_isolated",
            internal=True,
            enable_ipv6=False,
            driver="bridge"
        )
    
    def test_network_policies(self, network_manager):
        """Test applying network policies."""
        policies = {
            "allow_internet": False,
            "allow_local_network": False,
            "allow_inter_container": True,
            "allowed_ports": [8080]
        }
        
        # Apply policies
        iptables_rules = network_manager.generate_network_policies(
            container_id="test_123",
            policies=policies
        )
        
        assert len(iptables_rules) > 0
        assert any("DROP" in rule for rule in iptables_rules)
        assert any("8080" in rule for rule in iptables_rules)
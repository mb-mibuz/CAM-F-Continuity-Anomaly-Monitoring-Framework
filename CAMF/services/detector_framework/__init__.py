# CAMF/services/detector_framework/__init__.py
"""
Detector Framework Service

Provides a plugin-based system for continuity error detection with Docker isolation.
Supports automatic detector discovery, configuration management,
parallel processing with timeout handling, and secure container-based execution.
"""

from .main import get_detector_framework_service, DetectorFrameworkService
from .interface import QueueBasedDetector, FramePair, FalsePositiveManager
from .docker_manager import SecureDockerManager
from .docker_installer import DockerDetectorInstaller
from .docker_detector_base import DockerDetector, ContinuityError
from .validation import ConfigurationValidator

# Export main service getter
__all__ = [
    'get_detector_framework_service',
    'DetectorFrameworkService',
    'QueueBasedDetector',
    'FramePair',
    'FalsePositiveManager',
    'SecureDockerManager',
    'DockerDetectorInstaller',
    'DockerDetector',
    'ContinuityError',
    'ConfigurationValidator'
]
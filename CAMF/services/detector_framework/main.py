# CAMF/services/detector_framework/main.py - Docker-based Detector Framework
"""
Docker-based Detector Framework Service
Orchestrates detector system with Docker container isolation and security.
"""

import json
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Tuple
from datetime import datetime
import logging
import numpy as np

from .validation import ConfigurationValidator
from .deduplication import ErrorDeduplicationService

from .benchmarking import PerformanceBenchmark
from .validation import DetectorValidator
from .documentation import DocumentationGenerator
from .recovery import DetectorRecoveryManager
from .version_control import DetectorVersionControl, VersionedDetectorLoader, VersionChange

from CAMF.common.models import (
    DetectorConfigurationSchema, DetectorResult, DetectorStatus, ErrorConfidence, DetectorInfo
)
from CAMF.services.storage import get_storage_service
from .interface import (
    FramePair
)

# Compatibility classes for detector management
class AdaptiveTimeout:
    """Simple adaptive timeout for detector operations"""
    def __init__(self, initial_timeout=None):
        from CAMF.common.config import get_config
        config = get_config()
        self.timeout = initial_timeout or config.detector.adaptive_timeout_initial
        self.min_timeout = 5.0
        self.max_timeout = 300.0
    
    def get_timeout(self):
        return self.timeout
    
    def update(self, actual_time):
        # Simple exponential moving average
        self.timeout = 0.9 * self.timeout + 0.1 * (actual_time * 2)
        self.timeout = max(self.min_timeout, min(self.timeout, self.max_timeout))

class DetectorLoader:
    """Minimal detector loader for Docker-based system"""
    def __init__(self, detectors_path: str):
        self.detectors_path = Path(detectors_path)
        self.registry = DetectorRegistry()
    
    def discover_detectors(self) -> List[str]:
        """Discover available detectors"""
        detectors = []
        if self.detectors_path.exists():
            for detector_dir in self.detectors_path.iterdir():
                # Skip template directories and hidden directories
                if detector_dir.name.startswith('.') or detector_dir.name == 'detector_template':
                    continue
                if detector_dir.is_dir() and (detector_dir / "detector.json").exists():
                    # Validate that the detector has required files
                    if self._validate_detector_files(detector_dir):
                        detectors.append(detector_dir.name)
                    else:
                        logger.warning(f"Detector {detector_dir.name} is missing required files, skipping")
        return detectors
    
    def _validate_detector_files(self, detector_dir: Path) -> bool:
        """Validate that a detector directory has all required files"""
        required_files = ["detector.json", "detector.py"]
        for req_file in required_files:
            if not (detector_dir / req_file).exists():
                return False
        
        # Also check if detector.json is valid
        try:
            with open(detector_dir / "detector.json", 'r') as f:
                config = json.load(f)
                # Basic validation - must have name and version
                if not config.get('name') or not config.get('version'):
                    return False
        except Exception:
            return False
        
        return True
    
    def find_detector_by_name(self, name: str) -> Optional[str]:
        """Find detector directory by name"""
        for detector_dir in self.detectors_path.iterdir():
            if detector_dir.is_dir() and detector_dir.name.lower() == name.lower():
                return detector_dir.name
        return None
    
    def get_detector_directory(self, name: str) -> Optional[str]:
        """Get detector directory name"""
        return self.find_detector_by_name(name)

class DetectorRegistry:
    """Minimal detector registry"""
    def __init__(self):
        self._info_cache = {}
    
    def get_detector_info(self, name: str) -> Optional[DetectorInfo]:
        """Get detector information"""
        if name in self._info_cache:
            return self._info_cache[name]
        
        # Try to load from detector.json
        detector_path = Path(__file__).parent.parent.parent / "detectors" / name / "detector.json"
        if detector_path.exists():
            with open(detector_path) as f:
                data = json.load(f)
            info = DetectorInfo(
                name=data.get("name", name),
                version=data.get("version", "1.0.0"),
                description=data.get("description", ""),
                author=data.get("author", "Unknown"),
                category=data.get("category", "general")
            )
            self._info_cache[name] = info
            return info
        return None
    
    def get_detector_metadata(self, name: str) -> Optional[Dict]:
        """Get detector metadata including schema"""
        detector_path = Path(__file__).parent.parent.parent / "detectors" / name / "detector.json"
        if detector_path.exists():
            with open(detector_path) as f:
                return json.load(f)
        return None

class ConfigurationManager:
    """Minimal configuration manager for Docker-based system"""
    def __init__(self, storage):
        self.storage = storage
    
    def get_enabled_detectors(self, scene_id: int) -> List[str]:
        """Get list of enabled detectors for a scene"""
        scene = self.storage.get_scene(scene_id)
        if scene and hasattr(scene, 'detector_settings'):
            return [name for name, config in scene.detector_settings.items() 
                   if config.get('enabled', False)]
        return []
    
    def set_enabled_detectors(self, scene_id: int, detectors: List[str]):
        """Set enabled detectors for a scene"""
        scene = self.storage.get_scene(scene_id)
        if scene:
            if not hasattr(scene, 'detector_settings'):
                scene.detector_settings = {}
            # Update enabled status for each detector
            for detector_name in detectors:
                if detector_name not in scene.detector_settings:
                    scene.detector_settings[detector_name] = {}
                scene.detector_settings[detector_name]['enabled'] = True
            # Disable others
            for name in list(scene.detector_settings.keys()):
                if name not in detectors:
                    scene.detector_settings[name]['enabled'] = False
            # Save scene
            self.storage.update_scene(scene.id, detector_settings=scene.detector_settings)
    
    def load_detector_config(self, scene_id: int, detector_name: str) -> Dict[str, Any]:
        """Load detector configuration"""
        scene = self.storage.get_scene(scene_id)
        if scene and hasattr(scene, 'detector_settings'):
            return scene.detector_settings.get(detector_name, {})
        return {}
    
    def save_detector_config(self, scene_id: int, detector_name: str, config: Dict[str, Any]):
        """Save detector configuration"""
        scene = self.storage.get_scene(scene_id)
        if scene:
            if not hasattr(scene, 'detector_settings'):
                scene.detector_settings = {}
            scene.detector_settings[detector_name] = config
            # Save scene
            self.storage.update_scene(scene.id, detector_settings=scene.detector_settings)

class DetectorTemplate:
    """Minimal detector template generator"""
    @staticmethod
    def generate_template(detector_name: str, output_path: str) -> bool:
        """Generate a detector template"""
        # For Docker-based system, copy the template directory
        template_path = Path(__file__).parent.parent.parent / "detectors" / "detector_template"
        if template_path.exists():
            import shutil
            dest_path = Path(output_path)
            shutil.copytree(template_path, dest_path)
            
            # Update detector.json with the new name
            detector_json = dest_path / "detector.json"
            if detector_json.exists():
                with open(detector_json) as f:
                    config = json.load(f)
                config["name"] = detector_name
                with open(detector_json, 'w') as f:
                    json.dump(config, f, indent=2)
            
            return True
        return False


# Performance monitoring is handled by a separate service
PERFORMANCE_AVAILABLE = False

# Direct file access is used for frame data
PREDICTIVE_CACHE_AVAILABLE = False

from .docker_installer import DockerDetectorInstaller
from .result_cache import get_result_cache, CacheKey
from .batch_processor import BatchProcessingConfig, create_batch_processor
from .batch_progress import get_progress_aggregator
from PIL import Image

logger = logging.getLogger(__name__)

class DetectorManager:
    """Manager for Docker-based detectors."""
    
    def __init__(self, detector_info: DetectorInfo, detector_process):
        self.info = detector_info
        self.process = detector_process  # This will be a DockerDetectorProcess from docker_manager
        self.status = DetectorStatus(
            name=detector_info.name,
            enabled=False,
            running=False
        )
        self.skip_frames_until = None
        self.processing_times = []
        self.lock = threading.RLock()
        self.is_initialized = False
        self.adaptive_timeout = AdaptiveTimeout()
        self.config = {}  # Store config for caching
        self.version = "1.0.0"  # Default version
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize the detector process."""
        with self.lock:
            try:
                self.config = config  # Store config for caching
                from CAMF.common.config import get_config
                app_config = get_config()
                response = self.process.send_request('initialize', {'config': config}, timeout=app_config.detector.communication_timeout)
                
                if response and response.get('success'):
                    self.status.enabled = True
                    self.status.last_error = None
                    self.status.last_error_time = None
                    self.is_initialized = True
                    return True
                else:
                    error_msg = response.get('error', 'Unknown initialization error') if response else 'No response'
                    self.status.last_error = error_msg
                    self.status.last_error_time = datetime.now()
                    return False
                    
            except Exception as e:
                self.status.last_error = str(e)
                self.status.last_error_time = datetime.now()
                return False
    
    def process_frame(self, frame_id: int, take_id: int, frame_hash: Optional[str] = None, 
                      cache: Optional['ResultCache'] = None, scene_context: Optional[str] = None,
                      timeout: Optional[float] = None) -> List[DetectorResult]:
        """Process a frame with the detector, using cache if available."""

        frame_start_time = time.time()
        
        # Try cache first if available
        if cache and frame_hash:
            cached_results = cache.get(
                frame_hash, self.info.name, self.version, 
                self.config, scene_context
            )
            if cached_results is not None:
                # Update status for cached result
                with self.lock:
                    self.status.total_processed += 1
                return cached_results
        
        # Track frame timestamp for FPS calculation
        if not hasattr(self, '_frame_timestamps'):
            self._frame_timestamps = []
        self._frame_timestamps.append(frame_start_time)
        
        # Keep only recent timestamps (last 5 seconds)
        cutoff_time = frame_start_time - 5.0
        self._frame_timestamps = [t for t in self._frame_timestamps if t > cutoff_time]

        if self.skip_frames_until is not None and frame_id < self.skip_frames_until:
            with self.lock:
                # Clear skip flag if we've reached the target frame
                if frame_id >= self.skip_frames_until - 1:
                    self.skip_frames_until = None
            return []

        with self.lock:
            if not self.status.enabled or self.status.running or not self.is_initialized:
                return []
            
            self.status.running = True
        
        # Use adaptive timeout if no specific timeout provided
        if timeout is None:
            timeout = self.adaptive_timeout.get_timeout()
        
        try:
            start_time = time.time()
            
            response = self.process.send_request(
                'process_frame', 
                {'frame_id': frame_id, 'take_id': take_id}, 
                timeout=timeout
            )
            
            processing_time = time.time() - start_time
            
            # Update adaptive timeout with this processing time
            self.adaptive_timeout.update(processing_time)
            
            with self.lock:
                self.status.running = False
                self.status.total_processed += 1
                
                # Update current timeout in status
                self.status.current_timeout = self.adaptive_timeout.get_timeout()
                
                # Update processing time statistics
                self.processing_times.append(processing_time)
                if len(self.processing_times) > 100:
                    self.processing_times.pop(0)
                
                self.status.average_processing_time = sum(self.processing_times) / len(self.processing_times)
            
            if not response:
                error_result = DetectorResult(
                    confidence=-1.0,  # Special value for detector failures
                    description="No response from detector process",
                    frame_id=frame_id,
                    detector_name=self.info.name
                )
                return [error_result]
            
            if not response.get('success'):
                error_msg = response.get('error', 'Unknown processing error')
                with self.lock:
                    self.status.last_error = error_msg
                    self.status.last_error_time = datetime.now()
                
                error_result = DetectorResult(
                    confidence=-1.0,  # Special value for detector failures
                    description=f"Processing failed: {error_msg}",
                    frame_id=frame_id,
                    detector_name=self.info.name
                )
                return [error_result]
            
            # Convert response data back to DetectorResult objects
            results = []
            for result_data in response.get('data', []):
                # Handle both float confidence and legacy ErrorConfidence enum
                confidence_value = result_data['confidence']
                if isinstance(confidence_value, (int, float)):
                    # If it's already a number, use it directly
                    confidence = float(confidence_value)
                    # Map legacy enum values to float equivalents
                    if confidence == 0:  # NO_ERROR
                        confidence = 0.0
                    elif confidence == 1:  # CONFIRMED_ERROR (legacy)
                        confidence = 0.9
                    elif confidence == 2:  # LIKELY_ERROR (legacy)
                        confidence = 0.6
                    elif confidence == 3:  # DETECTOR_FAILED
                        confidence = -1.0  # Special value for failures
                else:
                    confidence = float(confidence_value)
                
                result = DetectorResult(
                    confidence=confidence,
                    description=result_data['description'],
                    frame_id=result_data['frame_id'],
                    detector_name=result_data['detector_name'],
                    bounding_boxes=result_data.get('bounding_boxes', []),
                    metadata=result_data.get('metadata', {}),
                    timestamp=result_data.get('timestamp', time.time()),
                    error_type=result_data.get('error_type'),
                    location=result_data.get('location')
                )
                results.append(result)
            
            # Update error count - consider anything above 0.5 confidence as an error
            error_results = [r for r in results if r.confidence > 0.5]
            with self.lock:
                self.status.total_errors_found += len(error_results)
            
            # Cache results if successful
            if cache and frame_hash and results:
                cache.put(
                    frame_hash, self.info.name, self.version,
                    self.config, results, scene_context
                )
            
            return results
            
        except Exception as e:
            with self.lock:
                self.status.running = False
                self.status.last_error = str(e)
                self.status.last_error_time = datetime.now()
            
            error_result = DetectorResult(
                confidence=-1.0,  # Special value for detector failures
                description=f"Unexpected error: {str(e)}",
                frame_id=frame_id,
                detector_name=self.info.name
            )
            return [error_result]
    
    def cleanup(self):
        """Clean up detector resources."""
        with self.lock:
            try:
                if self.is_initialized:
                    from CAMF.common.config import get_config
                    config = get_config()
                    self.process.send_request('cleanup', {}, timeout=config.detector.cleanup_timeout)
                self.status.enabled = False
                self.status.running = False
                self.is_initialized = False
            except Exception as e:
                self.status.last_error = f"Cleanup failed: {str(e)}"
                self.status.last_error_time = datetime.now()

class DetectorFrameworkService:
    """Docker-based detector framework service with container management."""
    
    def __init__(self):
        """Initialize the Docker-based detector framework service."""
        self.storage = get_storage_service()
        
        # Get paths
        base_path = Path(__file__).parent.parent.parent
        self.detectors_path = base_path / "detectors"

        self.config_validator = ConfigurationValidator()
        self.deduplication_service = ErrorDeduplicationService(self.storage)
        
        # Create environments directory in project root
        # Go up one more level to get out of CAMF folder
        project_root = base_path.parent
        project_root / "detector_environments"
        workspace_path = project_root / "detector_workspaces"
        
        # Initialize Docker manager for secure container-based execution
        from .docker_manager import SecureDockerManager
        
        # Create the Docker manager
        self.docker_manager = SecureDockerManager(
            detectors_path=self.detectors_path,
            workspace_path=workspace_path
        )
        
        # Check if Docker is available, fallback to simple runner if not
        if not self.docker_manager.docker_available:
            logger.warning("Docker not available, using simple detector runner")
            # We'll use simple runners on demand instead of a process manager
            self.process_manager = None
            self.simple_runners = {}  # Will store SimpleDetectorRunner instances
        else:
            # Process manager reference for API compatibility
            self.process_manager = self.docker_manager
            self.simple_runners = None
        
        # Use Docker installer instead of regular installer
        self.installer = DockerDetectorInstaller(
            self.detectors_path, 
            registry_file=project_root / "detector_registry.json"
        )

        # Initialize version control
        self.version_control = DetectorVersionControl(str(self.detectors_path))
        self.versioned_loader = VersionedDetectorLoader(self.version_control)
        
        # Initialize result cache
        cache_dir = project_root / "detector_cache"
        self.result_cache = get_result_cache(str(cache_dir))
        
        # Initialize batch processor
        self.batch_config = BatchProcessingConfig(
            max_parallel_segments=4,
            segment_size_frames=300,
            enable_frame_deduplication=True,
            enable_early_termination=True
        )
        self.batch_processor = None  # Created per batch
        self.progress_aggregator = get_progress_aggregator()
        
        # Configuration and loader components
        self.loader = DetectorLoader(str(self.detectors_path))
        self.config_manager = ConfigurationManager(self.storage)
        
        # Detector management
        self.detector_managers: Dict[str, DetectorManager] = {}
        self.active_detectors: Dict[str, DetectorManager] = {}
        
        # Processing context
        self.current_scene_id: Optional[int] = None
        self.current_angle_id: Optional[int] = None
        self.current_take_id: Optional[int] = None
        
        # Callbacks
        self.result_callbacks: List[Callable[[List[DetectorResult]], None]] = []
        self.status_callbacks: List[Callable[[Dict[str, DetectorStatus]], None]] = []
        self.processing_callbacks = {
            'processing_started': None,
            'processing_complete': None
        }
        
        # Load available detectors
        self.refresh_detectors()

        # Performance monitoring services (optional)
        self.performance_service = None
        self.gpu_manager = None
        self.resource_optimizer = None
        
        # Performance metrics collection
        self.frame_processing_times = {}
        self.detector_recovery_attempts = {}

        # Initialize recovery manager
        self.recovery_manager = DetectorRecoveryManager(self)
        self.recovery_manager.start()
        
        # Processing service integration
        self.is_processing = False
        self.current_processing_take_id: Optional[int] = None
        self.reference_take_id: Optional[int] = None
        self.current_frame_index = 0
        self.processing_thread: Optional[threading.Thread] = None
        self._stop_requested = False
        
        # Processing progress tracking
        self.total_frames = 0
        self.processed_frames = 0
        self.failed_frames = 0
        
        # Per-detector progress tracking
        self.detector_progress = {}  # detector_name -> {processed: int, total: int, status: str}
        self._detector_completion_status = {}  # detector_name -> bool
        
        # Processing performance tracking
        self.processing_start_time: Optional[float] = None
        self.processing_end_time: Optional[float] = None
        
        # Frame cache for processing efficiency
        self._frame_cache: Dict[int, np.ndarray] = {}
        self._cache_size = 100  # Keep last 100 frames in memory
        
        # Processing thread lock
        self._processing_lock = threading.RLock()

    def start_benchmark_session(self, frame_count: int, frame_rate: float, 
                          image_quality: int) -> str:
        """Start a performance benchmark session."""
        if not hasattr(self, 'benchmark'):
            self.benchmark = PerformanceBenchmark()
        
        detector_count = len(self.active_detectors)
        return self.benchmark.start_session(
            frame_count, frame_rate, image_quality, detector_count
        )

    def benchmark_process_frame(self, frame_id: int, take_id: int) -> List[DetectorResult]:
        """Process frame with benchmarking enabled."""
        if hasattr(self, 'benchmark') and self.benchmark.is_running:
            # Record frame start
            frame_start = self.benchmark.record_frame_start(frame_id)
            
            # Process normally
            results = self.process_frame(frame_id, take_id)
            
            # Group results by detector
            detector_results = {}
            for result in results:
                if result.detector_name not in detector_results:
                    detector_results[result.detector_name] = []
                detector_results[result.detector_name].append(result)
            
            # Record frame end
            self.benchmark.record_frame_end(frame_start, detector_results)
            
            return results
        else:
            return self.process_frame(frame_id, take_id)

    def end_benchmark_session(self) -> Dict[str, Any]:
        """End benchmark session and get results."""
        if hasattr(self, 'benchmark') and self.benchmark.is_running:
            return self.benchmark.end_session()
        return {}

    def validate_detector_package(self, package_path: str) -> Tuple[bool, Dict[str, Any]]:
        """Validate a detector package before installation."""
        validator = DetectorValidator()
        return validator.validate_detector_package(package_path)

    def generate_documentation(self, output_dir: str = "docs"):
        """Generate documentation for all detectors."""
        doc_generator = DocumentationGenerator(str(self.detectors_path))
        doc_generator.generate_all_documentation(output_dir)

    def get_detector_versions(self, detector_name: str) -> List[Dict[str, Any]]:
        """Get all versions of a detector."""
        versions = self.version_control.list_versions(detector_name)
        return [v.to_dict() for v in versions]

    def install_detector_version(self, detector_name: str, version: Optional[str] = None) -> Tuple[bool, str]:
        """Install a specific version of a detector."""
        try:
            # Get current version if detector is already installed
            current_version = None
            detector_dir = self.detectors_path / detector_name
            version_file = detector_dir / ".version"
            
            if version_file.exists():
                with open(version_file, 'r') as f:
                    version_data = json.load(f)
                    current_version = version_data.get('version')
            
            # If upgrading, migrate all scene configurations
            if current_version and version and current_version != version:
                self._migrate_scene_configurations(detector_name, current_version, version)
            
            success = self.versioned_loader.load_detector(detector_name, version)
            if success:
                # Invalidate cache for updated detector
                self.invalidate_detector_cache(detector_name)
                
                # Refresh detectors to pick up the new version
                self.refresh_detectors()
                return True, f"Successfully installed {detector_name} version {version or 'latest'}"
            else:
                return False, "Failed to install detector version"
        except Exception as e:
            return False, f"Installation error: {str(e)}"
    
    def _migrate_scene_configurations(self, detector_name: str, from_version: str, to_version: str):
        """Migrate detector configurations in all scenes when detector is upgraded."""
        try:
            # Get all projects and iterate through their scenes
            projects = self.storage.list_projects()
            
            for project in projects:
                scenes = self.storage.list_scenes(project.id)
                
                for scene in scenes:
                    # Check if scene has detector settings (some storage implementations use different names)
                    detector_configs = None
                    if hasattr(scene, 'detector_settings'):
                        detector_configs = scene.detector_settings
                    elif hasattr(scene, 'detector_settings'):
                        detector_configs = scene.detector_settings
                    
                    if detector_configs and detector_name in detector_configs:
                        # Get current configuration
                        current_config = detector_configs[detector_name]
                        
                        # Run migration
                        success, migrated_config, _, error = self.version_control.run_migration(
                            detector_name, from_version, to_version, current_config
                        )
                        
                        if success:
                            # Update scene with migrated configuration
                            detector_configs[detector_name] = migrated_config
                            if hasattr(scene, 'detector_settings'):
                                self.storage.update_scene(scene.id, detector_settings=detector_configs)
                            else:
                                self.storage.update_scene(scene.id, detector_settings=detector_configs)
                            logger.info(f"Migrated {detector_name} config for scene {scene.id} in project {project.id}")
                        else:
                            logger.error(f"Failed to migrate {detector_name} config for scene {scene.id}: {error}")
                            
        except Exception as e:
            logger.error(f"Error migrating scene configurations: {e}")

    def create_detector_version(self, detector_name: str, change_type: str, 
                            changelog: str, breaking_changes: List[str] = None) -> Tuple[bool, str]:
        """Create a new version of a detector."""
        try:
            # Get detector directory
            detector_dir = self.detectors_path / detector_name
            if not detector_dir.exists():
                return False, f"Detector {detector_name} not found"
            
            # Map string to enum
            change_type_enum = VersionChange[change_type.upper()]
            
            # Create version
            new_version = self.version_control.create_version(
                detector_name,
                detector_dir,
                change_type_enum,
                changelog,
                breaking_changes
            )
            
            return True, f"Created version {new_version}"
        except Exception as e:
            return False, f"Version creation error: {str(e)}"

    def check_detector_updates(self, detector_name: str) -> Dict[str, Any]:
        """Check if detector has available updates."""
        try:
            # Get current version
            detector_dir = self.detectors_path / detector_name
            version_file = detector_dir / ".version"
            
            current_version = "1.0.0"  # Default
            if version_file.exists():
                with open(version_file, 'r') as f:
                    version_data = json.load(f)
                    current_version = version_data.get('version', '1.0.0')
            
            # Get latest version
            latest = self.version_control.get_latest_version(detector_name)
            
            return {
                'current_version': current_version,
                'latest_version': latest.version if latest else current_version,
                'update_available': latest and latest.version != current_version,
                'changelog': latest.changelog if latest else ""
            }
        except Exception as e:
            return {
                'error': str(e),
                'update_available': False
            }

    def get_detector_configuration_schema(self, detector_name: str) -> Optional[DetectorConfigurationSchema]:
        """Get configuration schema for a detector."""
        # Check if detector is in the discovered list (filters out templates)
        discovered = self.loader.discover_detectors()
        
        # Find actual detector directory name
        dir_name = self.loader.find_detector_by_name(detector_name)
        if not dir_name or dir_name not in discovered:
            return None
            
        detector_info = self.loader.registry.get_detector_info(dir_name)
        if not detector_info:
            return None
        
        # Get schema from detector metadata
        metadata = self.loader.registry.get_detector_metadata(dir_name)
        if metadata and 'schema' in metadata:
            return metadata['schema']
        
        return None
    
    def get_detector_schema(self, detector_name: str) -> Optional[Dict]:
        """Alias for get_detector_configuration_schema for API compatibility."""
        return self.get_detector_configuration_schema(detector_name)

    def validate_and_migrate_configs(self, scene_id: int):
        """Validate and migrate configurations for all detectors in a scene."""
        enabled_detectors = self.config_manager.get_enabled_detectors(scene_id)
        migration_report = {}
        
        for detector_name in enabled_detectors:
            # Get current schema from metadata
            metadata = self.loader.registry.get_detector_metadata(detector_name)
            if not metadata or 'schema' not in metadata:
                migration_report[detector_name] = {
                    "status": "failed",
                    "message": "No schema found in metadata"
                }
                continue
            
            # Convert metadata schema to ConfigurationSchema
            # This is a simplified version - in production you'd have proper conversion
            metadata['schema']
            
            # Load existing config
            self.config_manager.load_detector_config(scene_id, detector_name)
            
            # For now, just mark as valid
            migration_report[detector_name] = {
                "status": "valid"
            }
        
        return migration_report
    
    def refresh_detectors(self) -> List[str]:
        """Discover and load all available detectors."""
        try:
            # First, discover detectors using the legacy loader for info
            discovered = self.loader.discover_detectors()
            
            # Clear detector_managers and rebuild from scratch
            # Keep track of active detectors to avoid disrupting them
            active_names = set(self.active_detectors.keys())
            
            # Create new detector_managers dict with only discovered detectors
            new_managers = {}
            for detector_name in discovered:
                detector_info = self.loader.registry.get_detector_info(detector_name)
                if detector_info:
                    # Preserve active detector managers
                    if detector_name in active_names and detector_name in self.detector_managers:
                        new_managers[detector_name] = self.detector_managers[detector_name]
                    else:
                        # We'll create the process when the detector is enabled
                        new_managers[detector_name] = None
            
            # Replace the old managers with the new ones
            self.detector_managers = new_managers
            
            logger.info(f"Discovered {len(discovered)} detectors: {discovered}")
            return discovered
            
        except Exception as e:
            logger.error(f"Failed to refresh detectors: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def get_available_detectors(self) -> List[DetectorInfo]:
        """Get information about all available detectors."""
        detectors = []
        
        # Use the loader to discover all detectors, not just those in detector_managers
        discovered = self.loader.discover_detectors()
        
        for detector_name in discovered:
            info = self.loader.registry.get_detector_info(detector_name)
            if info:
                # Convert dict to DetectorInfo if needed
                if isinstance(info, dict):
                    detector_info = DetectorInfo(
                        name=info.get('name', detector_name),
                        version=info.get('version', '1.0.0'),
                        description=info.get('description', ''),
                        author=info.get('author', 'Unknown'),
                        category=info.get('category', 'general')
                    )
                    detectors.append(detector_info)
                else:
                    detectors.append(info)
        return detectors
    
    def get_detector_info(self, detector_name: str) -> Optional[DetectorInfo]:
        """Get information about a specific detector."""
        # Check if detector is in the discovered list (filters out templates)
        discovered = self.loader.discover_detectors()
        
        # Find actual detector directory name
        dir_name = self.loader.find_detector_by_name(detector_name)
        if dir_name and dir_name in discovered:
            return self.loader.registry.get_detector_info(dir_name)
        return None
    
    def get_detector_status(self, detector_name: str) -> Optional[DetectorStatus]:
        """Get status of a specific detector."""
        manager = self.active_detectors.get(detector_name)
        return manager.status if manager else None
    
    def get_all_detector_statuses(self) -> Dict[str, DetectorStatus]:
        """Get status of all active detectors."""
        return {name: manager.status for name, manager in self.active_detectors.items()}
    
    def get_active_detectors(self) -> Dict[str, 'DetectorManager']:
        """Get all active detector managers for push-based processing."""
        return self.active_detectors
    
    def get_detector_gpu_status(self, detector_name: str) -> Optional[Dict[str, Any]]:
        """Get GPU status for a specific detector."""
        # Docker containers handle GPU allocation internally
        return self.docker_manager.get_detector_status(detector_name)
    
    def set_context(self, scene_id: int, angle_id: int, take_id: int):
        """Set current processing context."""
        self.current_scene_id = scene_id
        self.current_angle_id = angle_id
        self.current_take_id = take_id
        
        # Update frame provider context
        project = None
        if scene_id:
            scene = self.storage.get_scene(scene_id)
            if scene:
                project = self.storage.get_project(scene.project_id)
        
        self.storage.set_frame_context(
            project_id=project.id if project else None,
            scene_id=scene_id,
            angle_id=angle_id,
            take_id=take_id
        )
    
    def enable_detector(self, detector_name: str, config: Dict[str, Any] = None) -> bool:
        """Enable detector with resource optimization."""
        try:
            # Find actual detector directory name
            dir_name = self.loader.find_detector_by_name(detector_name)
            if not dir_name:
                logger.error(f"Detector not found: {detector_name}")
                return False
                
            # Use directory name for internal operations
            if dir_name not in self.detector_managers:
                logger.error(f"Detector not found in managers: {dir_name}")
                return False
            
            if self.current_scene_id is None:
                logger.error("No scene context set")
                return False
            
            # Get detector info
            detector_info = self.loader.registry.get_detector_info(dir_name)
            if not detector_info:
                logger.error(f"Could not get detector info: {dir_name}")
                return False
            
            # Use provided config or load from storage
            if config is None:
                config = self.config_manager.load_detector_config(self.current_scene_id, detector_name)
            
            # Use the directory name we already found
            detector_dir = self.detectors_path / dir_name
            if not detector_dir.exists():
                logger.error(f"Detector directory not found: {detector_dir}")
                return False
            
            # Use Docker manager or simple runner
            if self.docker_manager.docker_available:
                success = self.docker_manager.start_detector(
                    detector_name=dir_name,
                    detector_path=detector_dir,
                    config=config
                )
                
                if not success:
                    logger.error(f"Failed to start detector container: {detector_name}")
                    return False
                
                # Get the Docker process wrapper
                detector_process = self.docker_manager.get_detector_process(dir_name)
            
                if not detector_process:
                    logger.error(f"Could not get detector process: {detector_name}")
                    return False
            else:
                # Use simple runner for non-Docker environment
                from .simple_detector_runner import SimpleDetectorRunner
                runner = SimpleDetectorRunner(dir_name, detector_dir)
                
                if not runner.initialize(config):
                    logger.error(f"Failed to initialize detector: {detector_name}")
                    return False
                
                # Store the runner
                self.simple_runners[dir_name] = runner
                
                # Create a process wrapper for compatibility
                class SimpleProcessWrapper:
                    def __init__(self, runner):
                        self.runner = runner
                    
                    def send_request(self, method: str, params: Dict[str, Any], timeout: float = 30):
                        if method == 'initialize':
                            return {'success': True}  # Already initialized
                        elif method == 'process_frame':
                            results = self.runner.process_frame(
                                params.get('frame_id'),
                                params.get('take_id')
                            )
                            return {
                                'success': True,
                                'data': [r.dict() for r in results]
                            }
                        elif method == 'cleanup':
                            self.runner.cleanup()
                            return {'success': True}
                        return {'success': False, 'error': f'Unknown method: {method}'}
                
                detector_process = SimpleProcessWrapper(runner)
            
            # Create enhanced manager
            manager = DetectorManager(detector_info, detector_process)
            
            # Initialize detector
            if manager.initialize(config):
                self.active_detectors[detector_name] = manager
                
                # Update enabled detectors in scene
                enabled_detectors = self.config_manager.get_enabled_detectors(self.current_scene_id)
                if detector_name not in enabled_detectors:
                    enabled_detectors.append(detector_name)
                    self.config_manager.set_enabled_detectors(self.current_scene_id, enabled_detectors)
                
                # Save configuration
                if config:
                    # Check if config changed
                    old_config = self.config_manager.load_detector_config(self.current_scene_id, detector_name)
                    if old_config != config:
                        # Invalidate cache for changed config
                        self.invalidate_config_cache(detector_name, old_config)
                    
                    self.config_manager.save_detector_config(self.current_scene_id, detector_name, config)
                
                logger.info(f"Enabled detector: {detector_name}")
                self._notify_status_callbacks()
                return True
            else:
                # Cleanup failed process
                self.process_manager.stop_detector(dir_name)
                logger.error(f"Failed to initialize detector: {detector_name}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to enable detector {detector_name}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def disable_detector(self, detector_name: str) -> bool:
        """Disable a detector and stop its process."""
        try:
            if detector_name in self.active_detectors:
                manager = self.active_detectors[detector_name]
                manager.cleanup()
                del self.active_detectors[detector_name]
                
                # Get detector directory name
                detector_dir_name = self.loader.get_detector_directory(detector_name)
                if detector_dir_name:
                    if self.docker_manager.docker_available:
                        # Stop the Docker container
                        self.docker_manager.stop_detector(detector_dir_name)
                    else:
                        # Clean up simple runner
                        if detector_dir_name in self.simple_runners:
                            self.simple_runners[detector_dir_name].cleanup()
                            del self.simple_runners[detector_dir_name]
                
                # Update enabled detectors in scene
                if self.current_scene_id:
                    enabled_detectors = self.config_manager.get_enabled_detectors(self.current_scene_id)
                    if detector_name in enabled_detectors:
                        enabled_detectors.remove(detector_name)
                        self.config_manager.set_enabled_detectors(self.current_scene_id, enabled_detectors)
                
                logger.info(f"Disabled detector: {detector_name}")
                self._notify_status_callbacks()
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to disable detector {detector_name}: {e}")
            return False
    
    def process_frame(self, frame_id: int, take_id: int) -> List[DetectorResult]:
        """Process a frame with all active detectors."""
        all_results = []
        time.time()
        
        if not self.active_detectors:
            return all_results
        
        
        # Calculate timestamp relative to take start
        take = self.storage.get_take(take_id)
        if not take:
            return all_results
        
        # Get FPS from scene settings
        angle = self.storage.get_angle(take.angle_id)
        if not angle:
            return all_results
            
        scene = self.storage.get_scene(angle.scene_id)
        fps = scene.frame_rate if scene else 1
        timestamp = frame_id / fps
        
        # Get frame hash for caching
        frame_hash = None
        scene_context = None
        try:
            # Get frame metadata to find path
            frame_meta = self.storage.get_frame_metadata(take_id, frame_id)
            if frame_meta:
                # Try to get the frame path directly from frame storage
                frame_path_str = self.storage.frame_storage.get_frame_path(take_id, frame_id)
                if frame_path_str:
                    frame_path = Path(frame_path_str)
                    if frame_path.exists():
                        with open(frame_path, 'rb') as f:
                            frame_data = f.read()
                        frame_hash = CacheKey.generate_frame_hash(frame_data)
            
            # Generate scene context for cache key
            if scene:
                scene_context = f"scene_{scene.id}_angle_{angle.id}"
        except Exception as e:
            logger.warning(f"Failed to calculate frame hash: {e}")

        # Collect detector processing times
        detector_times = {}
        detector_results = {}
        
        # Process with each active detector
        for detector_name, manager in self.active_detectors.items():
            try:
                detector_start = time.time()
                results = manager.process_frame(
                    frame_id, take_id, 
                    frame_hash=frame_hash,
                    cache=self.result_cache,
                    scene_context=scene_context
                )
                detector_time = (time.time() - detector_start) * 1000  # ms

                # Report success to recovery manager
                self.recovery_manager.report_success(
                    detector_name,
                    frame_id,
                    detector_time
                )
                
                detector_times[detector_name] = detector_time
                detector_results[detector_name] = results

                
                # Handle detector failures
                if any(r.confidence == -1.0 for r in results):  # Special value for detector failures
                    self._handle_detector_failure(detector_name, frame_id)
                
                if results:
                    for result in results:
                        # Process through deduplication
                        continuous_error_id = self.deduplication_service.process_detector_result(
                            result, take_id, timestamp
                        )
                        
                        # Add continuous_error_id to result for UI
                        result.metadata = result.metadata or {}
                        result.metadata['continuous_error_id'] = continuous_error_id
                        
                    all_results.extend(results)
                
            except Exception as e:
                # Report failure to recovery manager
                import traceback
                self.recovery_manager.report_failure(
                    detector_name,
                    frame_id,
                    str(e),
                    traceback.format_exc()
                )
                
                # Create error result
                error_result = DetectorResult(
                    confidence=-1.0,  # Special value for detector failures
                    description=f"Detector processing failed: {str(e)}",
                    frame_id=frame_id,
                    detector_name=detector_name
                )
                all_results.append(error_result)
        
        
        return all_results
    
    def _handle_detector_failure(self, detector_name: str, frame_id: int):
        """Handle detector failure with automatic recovery."""
        if detector_name not in self.detector_recovery_attempts:
            self.detector_recovery_attempts[detector_name] = []
        
        self.detector_recovery_attempts[detector_name].append(time.time())
        
        # Clean old attempts
        current_time = time.time()
        self.detector_recovery_attempts[detector_name] = [
            t for t in self.detector_recovery_attempts[detector_name] 
            if current_time - t < 300  # 5 minutes
        ]
        
        # Check if too many failures
        if len(self.detector_recovery_attempts[detector_name]) >= 3:
            logger.warning(f"Detector {detector_name} has failed too many times, disabling")
            self.disable_detector(detector_name)
            return
        
        # Attempt recovery
        logger.info(f"Attempting to recover detector {detector_name}")
        config = self.config_manager.load_detector_config(self.current_scene_id, detector_name)
        
        # Disable and re-enable
        self.disable_detector(detector_name)
        time.sleep(1)  # Brief pause
        self.enable_detector(detector_name, config)

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics for UI display."""
        metrics = {}
        
        if self.performance_service:
            try:
                # Get real-time metrics
                metrics = self.performance_service.get_realtime_metrics()
            except Exception as e:
                logger.warning(f"Failed to get performance metrics: {e}")
                # Continue with empty metrics
        
        # Add GPU status if available
        if self.gpu_manager:
            try:
                metrics['gpu'] = self.gpu_manager.get_status()
            except Exception as e:
                logger.warning(f"Failed to get GPU status: {e}")
                metrics['gpu'] = {'available': False, 'error': str(e)}
        
        # Add resource optimization status if available
        if self.resource_optimizer:
            try:
                metrics['resources'] = self.resource_optimizer.get_optimization_status()
            except Exception as e:
                logger.warning(f"Failed to get resource optimization status: {e}")
                metrics['resources'] = {'available': False, 'error': str(e)}
        
        # Add detector-specific metrics
        metrics['detector_health'] = self.get_detector_health()
        
        return metrics

    def export_performance_report(self, duration_hours: float = 1.0, output_dir: str = "reports") -> Dict[str, str]:
        """Export comprehensive performance report."""
        if self.performance_service:
            try:
                from CAMF.services.performance.exporters import MetricsExporter
                return MetricsExporter.export_summary_report(
                    self.performance_service,
                    duration_hours,
                    output_dir
                )
            except Exception as e:
                logger.warning(f"Failed to export performance report: {e}")
                return {"error": f"Failed to export: {str(e)}"}
        return {"error": "Performance service not available"}
    
    def _get_detector_memory_usage(self, detector_name: str) -> float:
        """Get memory usage for a detector process."""
        try:
            if self.resource_optimizer and detector_name in self.resource_optimizer.detector_processes:
                process = self.resource_optimizer.detector_processes[detector_name]
                return process.memory_info().rss / (1024 * 1024)  # MB
        except Exception as e:
            logger.debug(f"Failed to get memory usage for detector {detector_name}: {e}")
        return 0.0
    
    def _calculate_current_fps(self) -> float:
        """Calculate current frame processing rate."""
        # Track frame processing times
        if not hasattr(self, '_frame_timestamps'):
            self._frame_timestamps = []
        
        # Add current timestamp
        current_time = time.time()
        self._frame_timestamps.append(current_time)
        
        # Keep only recent timestamps (last 5 seconds)
        cutoff_time = current_time - 5.0
        self._frame_timestamps = [t for t in self._frame_timestamps if t > cutoff_time]
        
        # Calculate FPS from recent frames
        if len(self._frame_timestamps) >= 2:
            time_span = self._frame_timestamps[-1] - self._frame_timestamps[0]
            if time_span > 0:
                # Number of frames processed in the time span
                frame_count = len(self._frame_timestamps) - 1
                return frame_count / time_span
        
        # Fallback to target FPS if not enough data
        return self._get_target_fps()

    def _get_target_fps(self) -> float:
        """Get target FPS from current scene."""
        if self.current_scene_id:
            scene = self.storage.get_scene(self.current_scene_id)
            if scene:
                return float(scene.frame_rate)
        return 24.0
    
    def install_detector_from_zip(self, zip_path: str, force_reinstall: bool = False) -> Tuple[bool, str]:
        """Install detector from ZIP file."""
        return self.installer.install_from_zip(zip_path, force_reinstall)
    
    def uninstall_detector(self, detector_name: str) -> Tuple[bool, str]:
        """Uninstall a detector."""
        # First disable if active
        if detector_name in self.active_detectors:
            self.disable_detector(detector_name)
        
        # Remove from managers
        if detector_name in self.detector_managers:
            del self.detector_managers[detector_name]
        
        # Uninstall
        return self.installer.uninstall_detector(detector_name)
    
    def list_installed_detectors(self) -> List[Dict[str, Any]]:
        """List all installed detectors."""
        return self.installer.list_installed_detectors()
    
    def get_detector_health(self) -> Dict[str, Dict[str, Any]]:
        """Get health status of all detector containers."""
        return self.docker_manager.get_all_detector_status()
    
    def repair_detector(self, detector_name: str) -> Tuple[bool, str]:
        """Repair a corrupted detector by rebuilding its Docker image."""
        detector_dir_name = self.loader.get_detector_directory(detector_name)
        if not detector_dir_name:
            return False, "Detector not found"
        
        detector_dir = self.detectors_path / detector_dir_name
        
        try:
            # Stop the detector if running
            if detector_name in self.active_detectors:
                self.disable_detector(detector_name)
            
            # Rebuild the Docker image
            success, message = self.installer._build_detector_image(
                detector_dir_name, detector_dir
            )
            
            if success:
                return True, "Detector Docker image rebuilt successfully"
            else:
                return False, f"Failed to rebuild Docker image: {message}"
                
        except Exception as e:
            return False, f"Repair failed: {str(e)}"
    
    def _save_detector_result(self, result: DetectorResult, take_id: int):
        """Save detector result to storage."""
        try:
            self.storage.add_detector_result(
                take_id=take_id,
                frame_id=result.frame_id,
                detector_name=result.detector_name,
                confidence=result.confidence,
                description=result.description,
                bounding_boxes=result.bounding_boxes,
                metadata=result.metadata
            )
        except Exception as e:
            logger.error(f"Failed to save detector result: {e}")
    
    def add_result_callback(self, callback: Callable[[List[DetectorResult]], None]):
        """Add callback for detector results."""
        self.result_callbacks.append(callback)
    
    def add_status_callback(self, callback: Callable[[Dict[str, DetectorStatus]], None]):
        """Add callback for detector status updates."""
        self.status_callbacks.append(callback)
    
    def set_processing_callbacks(self, processing_started=None, processing_complete=None):
        """Set callbacks for processing lifecycle events."""
        if processing_started:
            self.processing_callbacks['processing_started'] = processing_started
            logger.info("Registered processing_started callback")
        if processing_complete:
            self.processing_callbacks['processing_complete'] = processing_complete
            logger.info("Registered processing_complete callback")
    
    def _notify_result_callbacks(self, results: List[DetectorResult]):
        """Notify all result callbacks."""
        for callback in self.result_callbacks:
            try:
                callback(results)
            except Exception as e:
                logger.error(f"Error in result callback: {e}")
    
    def _notify_status_callbacks(self):
        """Notify all status callbacks."""
        statuses = self.get_all_detector_statuses()
        for callback in self.status_callbacks:
            try:
                callback(statuses)
            except Exception as e:
                print(f"Error in status callback: {e}")
    
    def create_detector_template(self, detector_name: str, output_path: str = None) -> bool:
        """Create a new detector template."""
        if output_path is None:
            output_path = str(self.detectors_path / detector_name.replace(" ", "_").lower())
        
        return DetectorTemplate.generate_template(detector_name, output_path)
    
    # Cache management methods
    def invalidate_detector_cache(self, detector_name: str):
        """Invalidate all cache entries for a detector."""
        self.result_cache.invalidate_detector(detector_name)
    
    def invalidate_config_cache(self, detector_name: str, config: Dict[str, Any]):
        """Invalidate cache entries for specific detector configuration."""
        self.result_cache.invalidate_config(detector_name, config)
    
    def invalidate_scene_cache(self, scene_id: int):
        """Invalidate all cache entries for a scene."""
        scene_context = f"scene_{scene_id}"
        self.result_cache.invalidate_scene(scene_context)
    
    def clear_all_cache(self):
        """Clear entire result cache."""
        self.result_cache.clear()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        return self.result_cache.get_stats()
    
    def warm_detector_cache(self, detector_name: str, frame_ids: List[int], take_id: int):
        """Pre-warm cache for a detector with specific frames."""
        if detector_name not in self.active_detectors:
            return 0
        
        manager = self.active_detectors[detector_name]
        warmed = 0
        
        for frame_id in frame_ids:
            try:
                # Get frame path
                frame_path_str = self.storage.frame_storage.get_frame_path(take_id, frame_id)
                if frame_path_str:
                    frame_path = Path(frame_path_str)
                    if frame_path.exists():
                        with open(frame_path, 'rb') as f:
                            frame_data = f.read()
                        frame_hash = CacheKey.generate_frame_hash(frame_data)
                        
                        # Check if already cached
                        cached = self.result_cache.get(
                            frame_hash, manager.info.name, manager.version,
                            manager.config
                        )
                        
                        if cached is None:
                            # Process frame to populate cache
                            manager.process_frame(
                                frame_id, take_id,
                                frame_hash=frame_hash,
                                cache=self.result_cache
                            )
                            warmed += 1
            except Exception as e:
                logger.warning(f"Failed to warm cache for frame {frame_id}: {e}")
        
        return warmed
    
    def process_video_batch(self, video_path: str, take_id: int, 
                           detector_names: Optional[List[str]] = None,
                           progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """
        Process video using batch processing for high performance.
        
        Args:
            video_path: Path to video file
            take_id: Take ID for storing results
            detector_names: List of detector names to use (None = all active)
            progress_callback: Optional callback for progress updates
            
        Returns:
            Dictionary with results and processing statistics
        """
        import uuid
        batch_id = str(uuid.uuid4())
        
        # Use specified detectors or all active ones
        if detector_names is None:
            detector_names = list(self.active_detectors.keys())
        
        if not detector_names:
            return {
                'error': 'No active detectors',
                'results': {},
                'statistics': {}
            }
        
        # Get video info for progress tracking
        import cv2
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        
        # Create batch processor
        self.batch_processor = create_batch_processor(self.batch_config)
        
        # Create progress tracker
        segments = self.batch_processor.segmenter.segment_video(video_path)
        tracker = self.progress_aggregator.create_tracker(
            batch_id, video_path, len(segments), total_frames
        )
        
        # Add progress callback
        if progress_callback:
            tracker.add_callback(progress_callback)
        
        # SSE progress updates
        def sse_progress_update(progress):
            # Send progress through SSE if available
            if hasattr(self, 'sse_callback'):
                self.sse_callback({
                    'type': 'batch_progress',
                    'batch_id': batch_id,
                    'progress': progress
                })
        
        tracker.add_callback(sse_progress_update)
        
        try:
            # Create detector callback that processes all detectors
            def process_frame_batch(frame_data: np.ndarray, frame_id: int) -> List[DetectorResult]:
                all_results = []
                
                # Calculate frame hash once
                frame_bytes = cv2.imencode('.jpg', frame_data)[1].tobytes()
                frame_hash = CacheKey.generate_frame_hash(frame_bytes)
                
                # Get scene context
                take = self.storage.get_take(take_id)
                angle = self.storage.get_angle(take.angle_id) if take else None
                scene = self.storage.get_scene(angle.scene_id) if angle else None
                scene_context = f"scene_{scene.id}_angle_{angle.id}" if scene and angle else None
                
                # Process with each detector
                for detector_name in detector_names:
                    if detector_name not in self.active_detectors:
                        continue
                    
                    manager = self.active_detectors[detector_name]
                    
                    # Try cache first
                    cached_results = self.result_cache.get(
                        frame_hash, manager.info.name, manager.version,
                        manager.config, scene_context
                    )
                    
                    if cached_results is not None:
                        all_results.extend(cached_results)
                    else:
                        # Process frame
                        try:
                            # Create a mock frame object for the detector
                            # Note: This is simplified - in production you'd save the frame
                            # and pass the proper frame_id from storage
                            results = manager.process_frame(
                                frame_id, take_id,
                                frame_hash=frame_hash,
                                cache=self.result_cache,
                                scene_context=scene_context
                            )
                            all_results.extend(results)
                        except Exception as e:
                            logger.error(f"Detector {detector_name} failed on frame {frame_id}: {e}")
                            all_results.append(
                                DetectorResult(
                                    confidence=-1.0,  # Special value for detector failures
                                    description=f"Detector failed: {str(e)}",
                                    frame_id=frame_id,
                                    detector_name=detector_name
                                )
                            )
                
                return all_results
            
            # Process video
            batch_results = self.batch_processor.process_video(
                video_path, process_frame_batch, take_id
            )
            
            # Mark batch as completed
            tracker.complete_batch()
            
            # Save results to storage
            results_by_frame = batch_results.get('results', {})
            for frame_id, frame_results in results_by_frame.items():
                for result in frame_results:
                    try:
                        self._save_detector_result(result, take_id)
                    except Exception as e:
                        logger.error(f"Failed to save result: {e}")
            
            # Add cache statistics
            cache_stats = self.get_cache_stats()
            batch_results['statistics']['cache'] = cache_stats
            
            return batch_results
            
        except Exception as e:
            logger.error(f"Batch processing failed: {e}")
            tracker.fail_batch(str(e))
            return {
                'error': str(e),
                'results': {},
                'statistics': {}
            }
        finally:
            # Cleanup
            if self.batch_processor:
                self.batch_processor.stop()
                self.batch_processor = None
            
            # Remove tracker after delay
            def cleanup_tracker():
                time.sleep(60)  # Keep for 1 minute for UI
                self.progress_aggregator.remove_tracker(batch_id)
            
            threading.Thread(target=cleanup_tracker, daemon=True).start()
    
    def get_batch_progress(self, batch_id: Optional[str] = None) -> Dict[str, Any]:
        """Get progress for batch processing."""
        if batch_id:
            tracker = self.progress_aggregator.trackers.get(batch_id)
            if tracker:
                return tracker.get_progress()
            return {'error': 'Batch not found'}
        else:
            return self.progress_aggregator.get_all_progress()
    
    def configure_batch_processing(self, config: Dict[str, Any]):
        """Update batch processing configuration."""
        if 'max_parallel_segments' in config:
            self.batch_config.max_parallel_segments = config['max_parallel_segments']
        if 'segment_size_frames' in config:
            self.batch_config.segment_size_frames = config['segment_size_frames']
        if 'enable_frame_deduplication' in config:
            self.batch_config.enable_frame_deduplication = config['enable_frame_deduplication']
        if 'enable_early_termination' in config:
            self.batch_config.enable_early_termination = config['enable_early_termination']
        if 'max_memory_usage_percent' in config:
            self.batch_config.max_memory_usage_percent = config['max_memory_usage_percent']
        
        self.batch_config.validate()
    
    def start_processing(self, take_id: int, reference_take_id: Optional[int] = None) -> bool:
        """Start processing frames for a take."""
        with self._processing_lock:
            # Stop any existing processing
            if self.is_processing:
                self.stop_processing()
                time.sleep(0.5)  # Wait for thread to stop
                
            # Validate take exists
            take = self.storage.get_take(take_id)
            if not take:
                logger.error(f"Take {take_id} not found")
                return False
                
            # Get reference take ID if not provided
            if reference_take_id is None:
                angle = self.storage.get_angle(take.angle_id)
                if angle and getattr(angle, 'reference_take_id', None):
                    reference_take_id = angle.reference_take_id
                else:
                    logger.warning(f"No reference take found for angle {take.angle_id}")
                    return False
                    
            # Validate reference take exists
            reference_take = self.storage.get_take(reference_take_id)
            if not reference_take:
                logger.error(f"Reference take {reference_take_id} not found")
                return False
                
            # Get frame counts
            frames = self.storage.get_frames_for_take(take_id)
            reference_frames = self.storage.get_frames_for_take(reference_take_id)
            
            if not frames:
                logger.error(f"No frames found for take {take_id}")
                return False
                
            if not reference_frames:
                logger.error(f"No frames found for reference take {reference_take_id}")
                return False
                
            # Set up processing state
            self.current_processing_take_id = take_id
            self.reference_take_id = reference_take_id
            self.current_frame_index = 0
            # Only count frames up to the minimum of both takes for processing
            max_reference_frame_number = max(rf.frame_number for rf in reference_frames) if reference_frames else 0
            max_current_frame_number = max(f.frame_number for f in frames) if frames else 0
            max_frame_to_process = min(max_reference_frame_number, max_current_frame_number)
            frames_to_process = [f for f in frames if f.frame_number <= max_frame_to_process]
            self.total_frames = len(frames_to_process)
            self.processed_frames = 0
            self.failed_frames = 0
            self._stop_requested = False
            self.processing_start_time = time.time()
            self.processing_end_time = None
            
            # Clear frame cache
            self._frame_cache.clear()
            
            # Initialize per-detector progress tracking
            active_detectors = self.get_active_detectors()
            self.detector_progress = {}
            self._detector_completion_status = {}
            for detector_name in active_detectors:
                self.detector_progress[detector_name] = {
                    'processed': 0,
                    'total': self.total_frames,
                    'status': 'starting',
                    'last_frame': 0
                }
                self._detector_completion_status[detector_name] = False
            
            # Get scene info for detector context
            angle = self.storage.get_angle(take.angle_id)
            scene = self.storage.get_scene(angle.scene_id) if angle else None
            project = self.storage.get_project(scene.project_id) if scene else None
            
            # Set detector context
            if scene and angle:
                self.set_context(
                    scene_id=scene.id,
                    angle_id=angle.id,
                    take_id=take_id
                )
            
            # Start processing thread
            self.is_processing = True
            self.processing_thread = threading.Thread(
                target=self._processing_worker,
                args=(frames, reference_frames, take, angle, scene, project)
            )
            self.processing_thread.start()
            
            # Notify processing started callback
            if self.processing_callbacks.get('processing_started'):
                try:
                    detector_names = list(active_detectors.keys())
                    self.processing_callbacks['processing_started'](take_id, detector_names)
                    logger.info(f"Processing started callback triggered for take {take_id}")
                except Exception as e:
                    logger.error(f"Error in processing started callback: {e}")
            
            logger.info(f"Started processing take {take_id} with reference {reference_take_id}")
            return True
            
    def _processing_worker(self, frames: List[Any], reference_frames: List[Any], 
                          take: Any, angle: Any, scene: Any, project: Any):
        """Worker thread for processing frames."""
        try:
            # Create mapping of frame numbers to frame objects
            reference_frame_map = {rf.frame_number: rf for rf in reference_frames}
            
            # Determine the maximum frame number to process based on BOTH takes
            max_reference_frame_number = max(rf.frame_number for rf in reference_frames) if reference_frames else 0
            max_current_frame_number = max(f.frame_number for f in frames) if frames else 0
            max_frame_to_process = min(max_reference_frame_number, max_current_frame_number)
            
            logger.info(f"Processing frames up to frame number {max_frame_to_process} " +
                       f"(current: {max_current_frame_number}, reference: {max_reference_frame_number})")
            
            for frame in frames:
                if self._stop_requested:
                    break
                    
                # Skip frames beyond the minimum of both takes
                if frame.frame_number > max_frame_to_process:
                    logger.info(f"Skipping frame {frame.frame_number} - beyond processing limit ({max_frame_to_process})")
                    continue
                    
                try:
                    # Get corresponding reference frame
                    reference_frame = reference_frame_map.get(frame.frame_number)
                    if not reference_frame:
                        # Use first reference frame as fallback
                        reference_frame = reference_frames[0] if reference_frames else None
                        
                    if not reference_frame:
                        logger.warning(f"No reference frame for frame {frame.frame_number}")
                        self.failed_frames += 1
                        continue
                        
                    # Load frame data
                    current_frame_data = self._load_frame(frame)
                    reference_frame_data = self._load_frame(reference_frame)
                    
                    if current_frame_data is None or reference_frame_data is None:
                        logger.error(f"Failed to load frame data for frame {frame.id}")
                        self.failed_frames += 1
                        continue
                        
                    # Create frame pair
                    frame_pair = FramePair(
                        current_frame=current_frame_data,
                        reference_frame=reference_frame_data,
                        current_frame_id=frame.id,
                        reference_frame_id=reference_frame.id,
                        take_id=take.id,
                        scene_id=scene.id if scene else 0,
                        angle_id=angle.id if angle else 0,
                        project_id=project.id if project else 0,
                        metadata={
                            'frame_number': frame.frame_number,
                            'timestamp': frame.timestamp,
                            'reference_frame_number': reference_frame.frame_number
                        }
                    )
                    
                    # Process frame pair with all active detectors
                    active_detectors = self.get_active_detectors()
                    
                    # Process frame with each detector in parallel using threads
                    detector_threads = []
                    
                    def process_with_detector(detector_name, detector_manager, frame_obj, take_obj, scene_obj, angle_obj):
                        try:
                            # Process frame with detector
                            results = detector_manager.process_frame(
                                frame_obj.id, take_obj.id,
                                frame_hash=None,
                                cache=self.result_cache,
                                scene_context=f"scene_{scene_obj.id}_angle_{angle_obj.id}" if scene_obj and angle_obj else None
                            )
                            
                            # Save results
                            for result in results:
                                self._save_detector_result(result, take_obj.id)
                            
                            # Notify callbacks with take_id added
                            if results:
                                # Add take_id and frame_index to results for SSE
                                for result in results:
                                    result.take_id = take_obj.id
                                    result.frame_index = frame_obj.frame_number
                                self._notify_result_callbacks(results)
                                
                            # Update per-detector progress
                            with self._processing_lock:
                                if detector_name in self.detector_progress:
                                    self.detector_progress[detector_name]['processed'] += 1
                                    self.detector_progress[detector_name]['last_frame'] = frame_obj.frame_number
                                    self.detector_progress[detector_name]['status'] = 'processing'
                                    
                                    # Check if this detector is done
                                    if self.detector_progress[detector_name]['processed'] >= self.detector_progress[detector_name]['total']:
                                        self.detector_progress[detector_name]['status'] = 'completed'
                                        self._detector_completion_status[detector_name] = True
                                
                        except Exception as e:
                            logger.error(f"Error processing frame {frame_obj.id} with detector {detector_name}: {e}")
                            with self._processing_lock:
                                if detector_name in self.detector_progress:
                                    self.detector_progress[detector_name]['status'] = f'error: {str(e)}'
                    
                    # Start threads for each detector
                    for detector_name, detector_manager in active_detectors.items():
                        thread = threading.Thread(
                            target=process_with_detector,
                            args=(detector_name, detector_manager, frame, take, scene, angle)
                        )
                        thread.start()
                        detector_threads.append(thread)
                    
                    # Wait for all detector threads to complete for this frame
                    for thread in detector_threads:
                        thread.join(timeout=30)  # 30 second timeout per detector
                            
                    # Update progress
                    with self._processing_lock:
                        self.processed_frames += 1
                        self.current_frame_index = frame.frame_number
                        
                    # Log progress periodically
                    if self.processed_frames % 10 == 0:
                        progress = (self.processed_frames / self.total_frames) * 100
                        logger.info(f"Processing progress: {progress:.1f}% ({self.processed_frames}/{self.total_frames})")
                        
                    # Small delay to prevent overwhelming detectors
                    time.sleep(0.01)
                    
                except Exception as e:
                    logger.error(f"Error processing frame {frame.id}: {e}")
                    self.failed_frames += 1
                    
            # Wait for all detectors to finish processing
            logger.info("Waiting for all detectors to finish processing...")
            
            # Check for completion with timeout
            completion_timeout = time.time() + 60  # 60 second timeout
            while time.time() < completion_timeout:
                with self._processing_lock:
                    all_complete = all(self._detector_completion_status.get(name, False) 
                                     for name in active_detectors.keys())
                    if all_complete:
                        logger.info("All detectors have completed processing")
                        break
                    
                    # Log detector status
                    for detector_name in active_detectors:
                        if detector_name in self.detector_progress:
                            progress = self.detector_progress[detector_name]
                            logger.debug(f"Detector {detector_name}: {progress['processed']}/{progress['total']} frames, status: {progress['status']}")
                
                time.sleep(0.5)
            
            # Final check and log completion status
            with self._processing_lock:
                for detector_name in active_detectors:
                    if detector_name in self.detector_progress:
                        progress = self.detector_progress[detector_name]
                        logger.info(f"Detector {detector_name} final status: {progress['processed']}/{progress['total']} frames processed")
                        if not self._detector_completion_status.get(detector_name, False):
                            logger.warning(f"Detector {detector_name} did not complete all frames")
                    
        except Exception as e:
            logger.error(f"Processing worker error: {e}", exc_info=True)
        finally:
            with self._processing_lock:
                self.is_processing = False
                self.processing_end_time = time.time()
                
            # Clear frame cache
            self._frame_cache.clear()
            
            # Calculate and log statistics
            duration = 0
            if self.processing_start_time and self.processing_end_time:
                duration = self.processing_end_time - self.processing_start_time
                fps = self.processed_frames / duration if duration > 0 else 0
                logger.info(
                    f"Processing completed: {self.processed_frames} frames in {duration:.2f}s "
                    f"({fps:.2f} fps), {self.failed_frames} failures"
                )
                
            # Notify processing complete callback
            logger.info(f"Checking processing callbacks: {self.processing_callbacks}")
            if self.processing_callbacks.get('processing_complete'):
                try:
                    # Get results summary for the take
                    results_summary = {
                        'total_frames': self.total_frames,
                        'processed_frames': self.processed_frames,
                        'failed_frames': self.failed_frames,
                        'detector_count': len(self._detector_completion_status),
                        'duration': duration
                    }
                    self.processing_callbacks['processing_complete'](
                        self.current_processing_take_id,
                        results_summary
                    )
                    logger.info(f"Processing complete callback triggered for take {self.current_processing_take_id}")
                except Exception as e:
                    logger.error(f"Error in processing complete callback: {e}")
            else:
                logger.warning("No processing_complete callback registered!")
                
    def _load_frame(self, frame) -> Optional[np.ndarray]:
        """Load frame data from storage."""
        # Check cache first
        if frame.id in self._frame_cache:
            return self._frame_cache[frame.id]
            
        try:
            # Load from file
            if hasattr(frame, 'path') and frame.path:
                frame_path = Path(frame.path)
                if frame_path.exists():
                    # Load image and convert to numpy array
                    image = Image.open(frame_path)
                    frame_data = np.array(image)
                    
                    # Update cache
                    self._frame_cache[frame.id] = frame_data
                    
                    # Limit cache size
                    if len(self._frame_cache) > self._cache_size:
                        # Remove oldest entries
                        oldest_keys = list(self._frame_cache.keys())[:10]
                        for key in oldest_keys:
                            del self._frame_cache[key]
                            
                    return frame_data
                    
            logger.error(f"Frame file not found: {frame.path if hasattr(frame, 'path') else 'No path'}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to load frame {frame.id}: {e}")
            return None
            
    def stop_processing(self):
        """Stop processing frames."""
        with self._processing_lock:
            self._stop_requested = True
            
        if self.processing_thread and self.processing_thread.is_alive():
            logger.info("Stopping processing...")
            self.processing_thread.join(timeout=10)
            
            if self.processing_thread.is_alive():
                logger.warning("Processing thread did not stop cleanly")
                
        with self._processing_lock:
            self.is_processing = False
            
    def get_processing_status(self) -> Dict[str, Any]:
        """Get current processing status."""
        with self._processing_lock:
            # Calculate overall progress based on all detectors
            total_detector_progress = 0
            active_detector_count = len(self.detector_progress)
            
            if active_detector_count > 0:
                for detector_info in self.detector_progress.values():
                    if detector_info['total'] > 0:
                        detector_percentage = (detector_info['processed'] / detector_info['total']) * 100
                        total_detector_progress += detector_percentage
                overall_progress = total_detector_progress / active_detector_count
            else:
                overall_progress = (self.processed_frames / self.total_frames * 100) if self.total_frames > 0 else 0
            
            status = {
                'is_processing': self.is_processing,
                'current_take_id': self.current_processing_take_id,
                'reference_take_id': self.reference_take_id,
                'current_frame_index': self.current_frame_index,
                'total_frames': self.total_frames,
                'processed_frames': self.processed_frames,
                'failed_frames': self.failed_frames,
                'progress_percentage': overall_progress,
                'detector_progress': dict(self.detector_progress),  # Include per-detector progress
                'all_detectors_complete': all(self._detector_completion_status.values()) if self._detector_completion_status else False
            }
            
            # Add timing info
            if self.processing_start_time:
                elapsed = (self.processing_end_time or time.time()) - self.processing_start_time
                status['elapsed_time'] = elapsed
                
                if elapsed > 0:
                    status['frames_per_second'] = self.processed_frames / elapsed
                    
                    if self.processed_frames < self.total_frames and self.is_processing:
                        remaining_frames = self.total_frames - self.processed_frames
                        fps = self.processed_frames / elapsed
                        status['estimated_time_remaining'] = remaining_frames / fps if fps > 0 else 0
                        
            return status
    
    def process_frame_pair(self, reference_take_id: int, current_take_id: int, frame_id: int) -> bool:
        """Process a single frame pair immediately (for real-time capture).
        
        Args:
            reference_take_id: ID of the reference take
            current_take_id: ID of the current take being captured
            frame_id: ID of the frame to process
            
        Returns:
            True if processing was successful
        """
        logger.info(f"[DetectorFramework] process_frame_pair called - reference_take_id: {reference_take_id}, current_take_id: {current_take_id}, frame_id: {frame_id}")
        
        try:
            # Get detector configurations for the take's scene
            take = self.storage.get_take(current_take_id)
            if not take:
                logger.error(f"Take {current_take_id} not found")
                return False
                
            angle = self.storage.get_angle(take.angle_id)
            if not angle:
                logger.error(f"Angle {take.angle_id} not found")
                return False
                
            scene = self.storage.get_scene(angle.scene_id)
            if not scene:
                logger.error(f"Scene {angle.scene_id} not found")
                return False
            
            logger.info(f"[DetectorFramework] Found scene {scene.id} for take {current_take_id}")
            
            # Set context if not already set
            if self.current_scene_id != scene.id:
                logger.info(f"[DetectorFramework] Setting context to scene {scene.id}, angle {angle.id}, take {current_take_id}")
                self.set_context(scene.id, angle.id, current_take_id)
            
            # Get enabled detectors for the scene
            detector_configs = scene.detector_settings or {}
            enabled_detectors = [
                name for name, config in detector_configs.items()
                if config.get('enabled', True)  # Default to True if not specified
            ]
            
            logger.info(f"[DetectorFramework] Scene {scene.id} has detector_settings: {list(detector_configs.keys())}")
            logger.info(f"[DetectorFramework] Enabled detectors: {enabled_detectors}")
            
            if not enabled_detectors:
                logger.info(f"No detectors enabled for scene {scene.id}")
                return True
            
            # Load frames
            current_frame = self.storage.get_frame(current_take_id, frame_id)
            reference_frame = self.storage.get_frame(reference_take_id, frame_id)
            
            if current_frame is None or reference_frame is None:
                logger.error(f"Failed to load frames for pair ({reference_take_id}, {current_take_id}, {frame_id})")
                return False
            
            # Create frame pair
            frame_pair = FramePair(
                take_id=current_take_id,
                frame_id=frame_id,
                current_frame=current_frame,
                reference_frame=reference_frame
            )
            
            # Queue to each enabled detector
            logger.info(f"[DetectorFramework] Processing frame {frame_id} with {len(enabled_detectors)} detectors")
            for detector_name in enabled_detectors:
                try:
                    # Enable detector if not already active
                    if detector_name not in self.active_detectors:
                        config = detector_configs.get(detector_name, {})
                        logger.info(f"[DetectorFramework] Enabling detector {detector_name} with config: {config}")
                        success = self.enable_detector(detector_name, config)
                        if success:
                            logger.info(f"[DetectorFramework] Successfully enabled detector {detector_name} for real-time processing")
                        else:
                            logger.error(f"[DetectorFramework] Failed to enable detector {detector_name}")
                            continue
                    
                    # Process the frame with the detector
                    detector_manager = self.active_detectors.get(detector_name)
                    if detector_manager:
                        logger.info(f"[DetectorFramework] Processing frame {frame_id} with detector {detector_name}")
                        
                        # For Docker-based detectors, we process frames directly
                        # Calculate frame hash for caching if available
                        frame_hash = None
                        scene_context = f"scene_{scene.id}_angle_{angle.id}"
                        
                        try:
                            # Process the frame
                            results = detector_manager.process_frame(
                                frame_id, current_take_id,
                                frame_hash=frame_hash,
                                cache=self.result_cache,
                                scene_context=scene_context
                            )
                            
                            # Save results
                            for result in results:
                                self._save_detector_result(result, current_take_id)
                                
                            # Detector processed frame successfully
                            
                            # Notify callbacks with take_id added
                            if results:
                                # Add take_id to results for SSE
                                for result in results:
                                    result.take_id = current_take_id
                                self._notify_result_callbacks(results)
                                
                        except Exception as e:
                            logger.error(f"[DetectorFramework] Error processing frame {frame_id} with detector {detector_name}: {e}", exc_info=True)
                    else:
                        logger.error(f"[DetectorFramework] No active manager found for detector {detector_name}")
                        
                except Exception as e:
                    logger.error(f"[DetectorFramework] Error queuing to detector {detector_name}: {e}", exc_info=True)
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing frame pair: {e}")
            return False

    def cleanup(self):
        """Clean up all active detectors and processes."""
        # Stop any processing first
        self.stop_processing()
        self._frame_cache.clear()
        
        # Stop recovery manager first
        if hasattr(self, 'recovery_manager'):
            self.recovery_manager.stop()
        
        # Disable all active detectors
        for detector_name in list(self.active_detectors.keys()):
            self.disable_detector(detector_name)
        
        # Stop all Docker containers
        self.docker_manager.stop_all_detectors()

        # Stop performance services if available
        if self.performance_service:
            try:
                self.performance_service.stop()
            except Exception as e:
                logger.debug(f"Error stopping performance service: {e}")
                
        if self.gpu_manager:
            try:
                # Release all GPU allocations
                if hasattr(self.gpu_manager, 'allocations'):
                    for detector_name in list(self.gpu_manager.allocations.keys()):
                        self.gpu_manager.release_gpu(detector_name)
                self.gpu_manager.stop()
            except Exception as e:
                logger.debug(f"Error stopping GPU manager: {e}")
                
        if self.resource_optimizer:
            try:
                self.resource_optimizer.stop_monitoring()
            except Exception as e:
                logger.debug(f"Error stopping resource optimizer: {e}")
        
        # Clean up result cache
        if hasattr(self, 'result_cache'):
            try:
                self.result_cache.cleanup()
            except Exception as e:
                logger.debug(f"Error cleaning up result cache: {e}")

# Singleton instance
_detector_framework_service = None

def get_detector_framework_service() -> DetectorFrameworkService:
    """Get the detector framework service singleton."""
    global _detector_framework_service
    if _detector_framework_service is None:
        _detector_framework_service = DetectorFrameworkService()
    return _detector_framework_service
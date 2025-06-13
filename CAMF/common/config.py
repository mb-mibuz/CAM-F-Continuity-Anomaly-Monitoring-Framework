import os
from pathlib import Path
from pydantic import BaseModel, field_validator, Field, ConfigDict
from typing import Dict, Any, Optional
import json
import logging

# Try to load dotenv but don't fail if it's not available
try:
    from dotenv import load_dotenv
    # Load environment variables from .env file
    load_dotenv()
except ImportError:
    # If dotenv is not available, just use system environment variables
    pass

# Add validation for environment variables
class EnvironmentConfig(BaseModel):
    """Validates and provides defaults for environment variables."""
    
    # Database
    database_url: str = Field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL", 
            f"sqlite:///{Path.home() / 'continuity_monitoring' / 'metadata.db'}"
        )
    )
    
    # Storage
    storage_dir: Path = Field(
        default_factory=lambda: Path(
            os.getenv("STORAGE_DIR", str(Path.home() / "continuity_monitoring"))
        )
    )
    temp_dir: Path = Field(
        default_factory=lambda: Path(
            os.getenv("TEMP_DIR", str(Path.home() / "continuity_monitoring" / "temp"))
        )
    )
    
    # API
    api_host: str = Field(default="127.0.0.1")
    api_port: int = Field(default=8000)
    debug: bool = Field(default=False)
    
    # Capture
    default_fps: float = Field(default=24.0, gt=0.0) 
    default_image_quality: int = Field(default=90, ge=10, le=100)
    
    # Performance
    max_cache_size_mb: int = Field(default=1024, ge=100)
    max_detector_processes: int = Field(default=4, ge=1)
    detector_timeout_seconds: float = Field(default=30.0, ge=1.0)
    detector_adaptive_timeout_initial: float = Field(default=30.0, ge=1.0)
    detector_communication_timeout: float = Field(default=30.0, ge=1.0)
    
    # GPU
    enable_gpu: bool = Field(default=True)
    gpu_memory_limit_mb: int = Field(default=2048, ge=512)
    
    # Logging
    log_level: str = Field(default="INFO")
    log_file: Optional[Path] = None
    
    # Service Configuration
    health_check_interval_seconds: float = Field(default=30.0, ge=5.0)
    service_recovery_check_interval: float = Field(default=30.0, ge=5.0)
    ipc_timeout_ms: int = Field(default=100, ge=10)
    ipc_poll_timeout_ms: int = Field(default=100, ge=10)
    thread_join_timeout: float = Field(default=1.0, ge=0.1)
    
    # Frame Processing
    frame_cache_duration_seconds: int = Field(default=30, ge=5)
    frame_processing_timeout: float = Field(default=5.0, ge=1.0)
    
    # Docker Configuration
    docker_healthcheck_interval: str = Field(default="30s")
    docker_healthcheck_timeout: str = Field(default="10s")
    docker_healthcheck_retries: int = Field(default=3, ge=1)
    docker_container_stop_timeout: int = Field(default=10, ge=1)

    # Camera settings
    camera_backend: str = Field(default="AUTO")
    camera_init_delay_ms: int = Field(default=500)
    camera_max_retries: int = Field(default=3)
    camera_preview_fps: float = Field(default=5.0)
    camera_disable_preview_during_capture: bool = Field(default=True)
    
    @field_validator('storage_dir', 'temp_dir', 'log_file', mode='before')
    @classmethod
    def create_directories(cls, v):
        if v and not isinstance(v, Path):
            v = Path(v)
        if v and v.suffix == '':  # It's a directory
            v.mkdir(parents=True, exist_ok=True)
        return v
    
    @field_validator('debug', 'enable_gpu', 'camera_disable_preview_during_capture', mode="before")
    @classmethod
    def parse_bool(cls, v):
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on')
        return v
    
    model_config = ConfigDict(
        env_prefix="",
        case_sensitive=False
    )

# Create validated environment config
env_config = EnvironmentConfig()

# Set up logging based on config
logging.basicConfig(
    level=getattr(logging, env_config.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(env_config.log_file) if env_config.log_file else logging.NullHandler()
    ]
)

class CaptureConfig(BaseModel):
    """Configuration for capture service."""
    default_frame_rate: int = Field(default_factory=lambda: int(env_config.default_fps))
    default_quality: int = Field(default_factory=lambda: env_config.default_image_quality)

class StorageConfig(BaseModel):
    """Storage configuration."""
    base_dir: str = Field(default_factory=lambda: str(env_config.storage_dir))
    database_url: str = Field(default_factory=lambda: env_config.database_url)
    
    @property
    def absolute_base_dir(self) -> Path:
        """Get absolute path for base directory."""
        path = Path(self.base_dir)
        return path.resolve()
    
class DetectorConfig(BaseModel):
    """Configuration for detector framework."""
    detector_dir: str = Field(default="detectors")
    parallel_processing: bool = True
    max_workers: int = Field(default_factory=lambda: env_config.max_detector_processes)
    timeout_seconds: float = Field(default_factory=lambda: env_config.detector_timeout_seconds)
    adaptive_timeout_initial: float = Field(default_factory=lambda: env_config.detector_adaptive_timeout_initial)
    communication_timeout: float = Field(default_factory=lambda: env_config.detector_communication_timeout)
    cleanup_timeout: float = Field(default=10.0)

class ExportConfig(BaseModel):
    """Configuration for export service."""
    report_template_dir: str = "templates"

class CameraConfig(BaseModel):
    """Camera-specific configuration."""
    backend: str = Field(default="AUTO", description="Camera backend to use")
    init_delay_ms: int = Field(default=500, ge=0, le=5000, description="Camera initialization delay")
    max_retries: int = Field(default=3, ge=1, le=10, description="Maximum connection retries")
    preview_fps: float = Field(default=5.0, ge=1.0, le=30.0, description="Preview frame rate")
    disable_preview_during_capture: bool = Field(default=True, description="Disable preview during capture")
    
    @field_validator('backend')
    def validate_backend(cls, v):
        valid_backends = ["AUTO", "MSMF", "DSHOW", "V4L2"]
        if v.upper() not in valid_backends:
            raise ValueError(f"Invalid camera backend. Must be one of: {', '.join(valid_backends)}")
        return v.upper()
    
class ServiceConfig(BaseModel):
    """Service-level configuration."""
    health_check_interval: float = Field(default_factory=lambda: env_config.health_check_interval_seconds)
    recovery_check_interval: float = Field(default_factory=lambda: env_config.service_recovery_check_interval)
    ipc_timeout_ms: int = Field(default_factory=lambda: env_config.ipc_timeout_ms)
    ipc_poll_timeout_ms: int = Field(default_factory=lambda: env_config.ipc_poll_timeout_ms)
    thread_join_timeout: float = Field(default_factory=lambda: env_config.thread_join_timeout)

class FrameConfig(BaseModel):
    """Frame processing configuration."""
    cache_duration_seconds: int = Field(default_factory=lambda: env_config.frame_cache_duration_seconds)
    processing_timeout: float = Field(default_factory=lambda: env_config.frame_processing_timeout)

class DockerConfig(BaseModel):
    """Docker-specific configuration."""
    healthcheck_interval: str = Field(default_factory=lambda: env_config.docker_healthcheck_interval)
    healthcheck_timeout: str = Field(default_factory=lambda: env_config.docker_healthcheck_timeout)
    healthcheck_retries: int = Field(default_factory=lambda: env_config.docker_healthcheck_retries)
    container_stop_timeout: int = Field(default_factory=lambda: env_config.docker_container_stop_timeout)

class AppConfig(BaseModel):
    """Main application configuration."""
    capture: CaptureConfig = Field(default_factory=CaptureConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    detector: DetectorConfig = Field(default_factory=DetectorConfig)
    camera: CameraConfig = Field(default_factory=CameraConfig)
    export: ExportConfig = Field(default_factory=ExportConfig)
    service: ServiceConfig = Field(default_factory=ServiceConfig)
    frame: FrameConfig = Field(default_factory=FrameConfig)
    docker: DockerConfig = Field(default_factory=DockerConfig)
    debug: bool = Field(default_factory=lambda: env_config.debug)

# Singleton instance
_config = None

def get_config() -> AppConfig:
    """Get the application configuration singleton."""
    global _config
    if _config is None:
        # Create camera config from environment
        camera_config = CameraConfig(
            backend=env_config.camera_backend,
            init_delay_ms=env_config.camera_init_delay_ms,
            max_retries=env_config.camera_max_retries,
            preview_fps=env_config.camera_preview_fps,
            disable_preview_during_capture=env_config.camera_disable_preview_during_capture
        )
        
        _config = AppConfig(
            camera=camera_config
        )
        
        # Ensure base directories exist
        os.makedirs(_config.storage.base_dir, exist_ok=True)
        
        # Ensure database directory exists
        if _config.storage.database_url.startswith('sqlite:///'):
            db_path = _config.storage.database_url.replace('sqlite:///', '')
            db_dir = os.path.dirname(db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
    
    return _config

def load_project_config(project_id: int) -> Dict[str, Any]:
    """Load project-specific configuration."""
    config_path = Path(get_config().storage.base_dir) / str(project_id) / "config.json"
    if config_path.exists():
        with open(config_path, "r") as f:
            return json.load(f)
    return {}

def save_project_config(project_id: int, config: Dict[str, Any]):
    """Save project-specific configuration."""
    config_dir = Path(get_config().storage.base_dir) / str(project_id)
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
# CAMF/common/models.py - Enhanced version with detector framework support
from datetime import datetime
from enum import Enum
import time
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from abc import ABC, abstractmethod

from dataclasses import dataclass
from typing import List, Optional

class ErrorConfidence(Enum):
    """DEPRECATED: Use float confidence values instead."""
    NO_ERROR = 0
    CONFIRMED_ERROR = 1
    LIKELY_ERROR = 2
    DETECTOR_FAILED = 3
    PROCESSING_PENDING = 4  # New: Detector needs more frames

class DetectorResult(BaseModel):
    """Result from a detector run on a frame."""
    id: Optional[int] = None  # Database ID
    confidence: float  # Changed from ErrorConfidence to float (0.0-1.0)
    description: str
    frame_id: int
    bounding_boxes: List[Dict[str, Any]] = Field(default_factory=list) 
    detector_name: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    result_image_path: Optional[str] = None  # Path to result image with bounding boxes
    timestamp: float = Field(default_factory=lambda: time.time())  # Add timestamp with default
    error_type: Optional[str] = None  # Add error type from ContinuityError
    location: Optional[Dict[str, Any]] = None  # Add location for consistency
    is_false_positive: bool = False  # Whether this result is marked as false positive
    false_positive_reason: Optional[str] = None  # Reason for false positive marking

class DetectorInfo(BaseModel):
    """Information about a detector."""
    name: str
    description: str
    version: str
    author: str
    category: str = "general"  # Category of detector (e.g., "general", "custom", "ml", "continuity")
    requires_reference: bool = False  # Whether detector needs reference frames
    min_frames_required: int = 1  # Minimum frames needed for processing

class ConfigurationField(BaseModel):
    """Schema for a single configuration field."""
    field_type: str  # "text", "number", "boolean", "file", "file_multiple"
    title: str
    description: str = ""
    required: bool = False
    default: Any = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    options: Optional[List[str]] = None  # For dropdown/select fields
    accept_extensions: Optional[List[str]] = None  # For file fields

class DetectorConfigurationSchema(BaseModel):
    """Complete configuration schema for a detector."""
    fields: Dict[str, ConfigurationField]

class DetectorStatus(BaseModel):
    """Runtime status of a detector."""
    name: str
    enabled: bool
    running: bool
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None
    total_processed: int = 0
    total_errors_found: int = 0
    average_processing_time: float = 0.0
    current_timeout: float = 10.0

# DEPRECATED: Old pull-based detector interface - DO NOT USE
# All new detectors should use QueueBasedDetector from CAMF.services.detector_framework.interface
class BaseDetector(ABC):
    """DEPRECATED: Legacy abstract base class. Use QueueBasedDetector instead.
    
    This class is maintained only for backward compatibility during migration.
    It will be removed in a future version.
    """
    
    def __init__(self):
        import warnings
        warnings.warn(
            "BaseDetector is deprecated. Use QueueBasedDetector from "
            "CAMF.services.detector_framework.interface instead.",
            DeprecationWarning,
            stacklevel=2
        )
        self.frame_provider = None
        self.config = {}
        self.is_initialized = False
    
    @abstractmethod
    def get_info(self) -> 'DetectorInfo':
        """Return detector information."""
    
    @abstractmethod
    def get_configuration_schema(self) -> 'DetectorConfigurationSchema':
        """Return configuration schema for UI generation."""
    
    @abstractmethod
    def initialize(self, config: Dict[str, Any], frame_provider) -> bool:
        """DEPRECATED: Initialize detector with configuration and frame provider."""
    
    @abstractmethod
    def process_frame(self, frame_id: int, take_id: int) -> List['DetectorResult']:
        """DEPRECATED: Process a frame and return detection results."""
    
    def cleanup(self):
        """Optional cleanup when detector is disabled."""
    
    def validate_configuration(self, config: Dict[str, Any]) -> bool:
        """Validate configuration against schema."""
        schema = self.get_configuration_schema()
        for field_name, field_schema in schema.fields.items():
            if field_schema.required and field_name not in config:
                return False
        return True

# Add to existing models...

class Frame(BaseModel):
    """Represents a single captured frame."""
    id: int
    take_id: int
    timestamp: float
    filepath: str
    width: int = 0
    height: int = 0
    file_size: int = 0
    frame_number: Optional[int] = None
    path: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class Take(BaseModel):
    """Represents a single take within an angle."""
    id: int
    angle_id: int
    name: str
    created_at: datetime = Field(default_factory=datetime.now)
    is_reference: bool = False
    notes: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

class Angle(BaseModel):
    """Represents a camera angle within a scene."""
    id: int
    scene_id: int
    name: str
    reference_take_id: Optional[int] = None
    takes: List[Take] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class Scene(BaseModel):
    """Represents a scene within a project."""
    id: int
    project_id: int
    name: str
    frame_rate: float = 1.0  # Default to 1 FPS as requested
    image_quality: int = 90  # JPEG quality (0-100)
    resolution: str = "1080p"  # Default resolution: "4K", "1080p", "720p", "480p", etc.
    angles: List[Angle] = Field(default_factory=list)
    enabled_detectors: List[str] = Field(default_factory=list)
    detector_settings: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class Project(BaseModel):
    """Represents a film production project."""
    id: int
    name: str
    scenes: List[Scene] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    last_modified: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

@dataclass
class ErrorOccurrence:
    """Single occurrence of an error."""
    id: int
    frame_id: int
    confidence: int
    timestamp: float

@dataclass
class ContinuousError:
    """Grouped continuous error for UI display."""
    id: int
    detector_name: str
    description: str
    first_frame: int
    last_frame: int
    frame_range: str
    confidence: int
    is_active: bool
    occurrences: List[ErrorOccurrence]
    
    @property
    def is_single_frame(self) -> bool:
        return self.first_frame == self.last_frame
    
    @property
    def duration(self) -> float:
        """Duration in seconds."""
        if self.occurrences:
            return self.occurrences[-1].timestamp - self.occurrences[0].timestamp
        return 0.0
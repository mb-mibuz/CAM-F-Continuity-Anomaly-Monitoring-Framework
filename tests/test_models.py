"""
Tests for CAMF data models.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from CAMF.common.models import (
    Project, Scene, Angle, Take, Frame,
    DetectorResult, DetectorInfo, ConfigurationField,
    DetectorConfigurationSchema, DetectorStatus,
    ErrorConfidence, ContinuousError, ErrorOccurrence
)


class TestProject:
    """Test Project model."""
    
    def test_project_creation(self):
        """Test creating a project."""
        project = Project(
            id=1,
            name="Test Project"
        )
        
        assert project.id == 1
        assert project.name == "Test Project"
        assert isinstance(project.created_at, datetime)
        assert isinstance(project.last_modified, datetime)
        assert project.scenes == []
        assert project.metadata == {}
    
    def test_project_with_scenes(self):
        """Test project with scenes."""
        scene = Scene(
            id=1,
            project_id=1,
            name="Scene 1",
            scene_number=1
        )
        
        project = Project(
            id=1,
            name="Test Project",
            scenes=[scene]
        )
        
        assert len(project.scenes) == 1
        assert project.scenes[0].name == "Scene 1"
    
    def test_project_validation(self):
        """Test project validation."""
        # Missing required fields
        with pytest.raises(ValidationError):
            Project(name="Test")  # Missing id
        
        with pytest.raises(ValidationError):
            Project(id=1)  # Missing name
    
    def test_project_json_serialization(self):
        """Test JSON serialization."""
        project = Project(
            id=1,
            name="Test Project",
            metadata={"key": "value"}
        )
        
        json_str = project.model_dump_json()
        assert isinstance(json_str, str)
        assert "Test Project" in json_str
        
        # Test round trip
        data = project.model_dump()
        project2 = Project(**data)
        assert project2.id == project.id
        assert project2.name == project.name


class TestScene:
    """Test Scene model."""
    
    def test_scene_creation(self):
        """Test creating a scene."""
        scene = Scene(
            id=1,
            project_id=1,
            name="Scene 1",
            scene_number=1
        )
        
        assert scene.id == 1
        assert scene.project_id == 1
        assert scene.name == "Scene 1"
        assert scene.scene_number == 1
        assert scene.description == ""
        assert scene.location == ""
        assert scene.enabled_detectors == []
        assert scene.detector_settings == {}
    
    def test_scene_with_detectors(self):
        """Test scene with detector configuration."""
        scene = Scene(
            id=1,
            project_id=1,
            name="Scene 1",
            scene_number=1,
            enabled_detectors=["ClockDetector", "DifferenceDetector"],
            detector_settings={
                "ClockDetector": {"threshold": 0.8},
                "DifferenceDetector": {"sensitivity": "high"}
            }
        )
        
        assert len(scene.enabled_detectors) == 2
        assert "ClockDetector" in scene.enabled_detectors
        assert scene.detector_settings["ClockDetector"]["threshold"] == 0.8


class TestAngle:
    """Test Angle model."""
    
    def test_angle_creation(self):
        """Test creating an angle."""
        angle = Angle(
            id=1,
            scene_id=1,
            name="Wide Shot",
            angle_number=1
        )
        
        assert angle.id == 1
        assert angle.scene_id == 1
        assert angle.name == "Wide Shot"
        assert angle.angle_number == 1
        assert angle.description == ""
        assert angle.camera_info == ""
        assert angle.reference_take_id is None
    
    def test_angle_with_reference(self):
        """Test angle with reference take."""
        angle = Angle(
            id=1,
            scene_id=1,
            name="Wide Shot",
            angle_number=1,
            reference_take_id=5,
            camera_info="RED Komodo, 24mm lens"
        )
        
        assert angle.reference_take_id == 5
        assert angle.camera_info == "RED Komodo, 24mm lens"


class TestTake:
    """Test Take model."""
    
    def test_take_creation(self):
        """Test creating a take."""
        take = Take(
            id=1,
            angle_id=1,
            take_number=1,
            name="Take 1"
        )
        
        assert take.id == 1
        assert take.angle_id == 1
        assert take.take_number == 1
        assert take.name == "Take 1"
        assert take.status == "pending"
        assert take.is_reference is False
        assert take.notes == ""
    
    def test_take_as_reference(self):
        """Test take marked as reference."""
        take = Take(
            id=1,
            angle_id=1,
            take_number=1,
            name="Take 1",
            is_reference=True,
            status="completed"
        )
        
        assert take.is_reference is True
        assert take.status == "completed"
    
    def test_take_with_timestamps(self):
        """Test take with timing information."""
        start_time = datetime.now()
        end_time = datetime.now()
        
        take = Take(
            id=1,
            angle_id=1,
            take_number=1,
            name="Take 1",
            start_time=start_time,
            end_time=end_time,
            duration=5.5,
            frame_count=165  # 30fps * 5.5s
        )
        
        assert take.start_time == start_time
        assert take.end_time == end_time
        assert take.duration == 5.5
        assert take.frame_count == 165


class TestFrame:
    """Test Frame model."""
    
    def test_frame_creation(self):
        """Test creating a frame."""
        frame = Frame(
            id=1,
            take_id=1,
            frame_number=1,
            filepath="/path/to/frame.jpg"
        )
        
        assert frame.id == 1
        assert frame.take_id == 1
        assert frame.frame_number == 1
        assert frame.filepath == "/path/to/frame.jpg"
        assert isinstance(frame.timestamp, datetime)
        assert frame.detector_results == []
    
    def test_frame_with_detector_results(self):
        """Test frame with detector results."""
        result = DetectorResult(
            confidence=0.95,
            description="Clock detected",
            frame_id=1,
            detector_name="ClockDetector"
        )
        
        frame = Frame(
            id=1,
            take_id=1,
            frame_number=1,
            filepath="/path/to/frame.jpg",
            detector_results=[result]
        )
        
        assert len(frame.detector_results) == 1
        assert frame.detector_results[0].confidence == 0.95


class TestDetectorResult:
    """Test DetectorResult model."""
    
    def test_detector_result_creation(self):
        """Test creating a detector result."""
        result = DetectorResult(
            confidence=0.85,
            description="Continuity error detected",
            frame_id=1,
            detector_name="ContinuityDetector"
        )
        
        assert result.confidence == 0.85
        assert result.description == "Continuity error detected"
        assert result.frame_id == 1
        assert result.detector_name == "ContinuityDetector"
        assert result.bounding_boxes == []
        assert result.metadata == {}
        assert isinstance(result.timestamp, float)
        assert result.is_false_positive is False
    
    def test_detector_result_with_bounding_boxes(self):
        """Test detector result with bounding boxes."""
        bounding_boxes = [
            {"x": 100, "y": 100, "width": 200, "height": 150, "label": "clock"},
            {"x": 400, "y": 300, "width": 100, "height": 100, "label": "watch"}
        ]
        
        result = DetectorResult(
            confidence=0.95,
            description="Multiple clocks detected",
            frame_id=1,
            detector_name="ClockDetector",
            bounding_boxes=bounding_boxes
        )
        
        assert len(result.bounding_boxes) == 2
        assert result.bounding_boxes[0]["label"] == "clock"
    
    def test_detector_result_false_positive(self):
        """Test marking result as false positive."""
        result = DetectorResult(
            confidence=0.75,
            description="Error detected",
            frame_id=1,
            detector_name="TestDetector",
            is_false_positive=True,
            false_positive_reason="Shadow mistaken for object"
        )
        
        assert result.is_false_positive is True
        assert result.false_positive_reason == "Shadow mistaken for object"


class TestDetectorInfo:
    """Test DetectorInfo model."""
    
    def test_detector_info_creation(self):
        """Test creating detector info."""
        info = DetectorInfo(
            name="ClockDetector",
            description="Detects clocks in frames",
            version="1.0.0",
            author="CAMF Team"
        )
        
        assert info.name == "ClockDetector"
        assert info.description == "Detects clocks in frames"
        assert info.version == "1.0.0"
        assert info.author == "CAMF Team"
        assert info.category == "general"
        assert info.requires_reference is False
        assert info.min_frames_required == 1
    
    def test_detector_info_with_requirements(self):
        """Test detector with special requirements."""
        info = DetectorInfo(
            name="DifferenceDetector",
            description="Detects differences between frames",
            version="2.0.0",
            author="CAMF Team",
            category="continuity",
            requires_reference=True,
            min_frames_required=2
        )
        
        assert info.category == "continuity"
        assert info.requires_reference is True
        assert info.min_frames_required == 2


class TestConfigurationField:
    """Test ConfigurationField model."""
    
    def test_configuration_field_text(self):
        """Test text configuration field."""
        field = ConfigurationField(
            field_type="text",
            title="API Key",
            description="Enter your API key"
        )
        
        assert field.field_type == "text"
        assert field.title == "API Key"
        assert field.description == "Enter your API key"
        assert field.default is None
        assert field.required is True
    
    def test_configuration_field_number(self):
        """Test number configuration field."""
        field = ConfigurationField(
            field_type="number",
            title="Threshold",
            description="Detection threshold (0-1)",
            default=0.8,
            min_value=0.0,
            max_value=1.0,
            step=0.1
        )
        
        assert field.field_type == "number"
        assert field.default == 0.8
        assert field.min_value == 0.0
        assert field.max_value == 1.0
        assert field.step == 0.1
    
    def test_configuration_field_boolean(self):
        """Test boolean configuration field."""
        field = ConfigurationField(
            field_type="boolean",
            title="Enable Debug Mode",
            description="Show debug information",
            default=False
        )
        
        assert field.field_type == "boolean"
        assert field.default is False
    
    def test_configuration_field_select(self):
        """Test select configuration field."""
        field = ConfigurationField(
            field_type="select",
            title="Mode",
            description="Select detection mode",
            default="normal",
            options=["fast", "normal", "accurate"]
        )
        
        assert field.field_type == "select"
        assert field.default == "normal"
        assert len(field.options) == 3
        assert "accurate" in field.options


class TestDetectorConfigurationSchema:
    """Test DetectorConfigurationSchema model."""
    
    def test_configuration_schema(self):
        """Test detector configuration schema."""
        fields = [
            ConfigurationField(
                field_type="number",
                title="Threshold",
                description="Detection threshold"
            ),
            ConfigurationField(
                field_type="boolean",
                title="Debug",
                description="Enable debug mode"
            )
        ]
        
        schema = DetectorConfigurationSchema(
            fields=fields
        )
        
        assert len(schema.fields) == 2
        assert schema.fields[0].title == "Threshold"
        assert schema.fields[1].title == "Debug"


class TestDetectorStatus:
    """Test DetectorStatus enum."""
    
    def test_detector_status_values(self):
        """Test detector status enum values."""
        assert DetectorStatus.IDLE.value == "idle"
        assert DetectorStatus.PROCESSING.value == "processing"
        assert DetectorStatus.ERROR.value == "error"
        assert DetectorStatus.DISABLED.value == "disabled"
    
    def test_detector_status_comparison(self):
        """Test status comparison."""
        status1 = DetectorStatus.IDLE
        status2 = DetectorStatus.IDLE
        status3 = DetectorStatus.PROCESSING
        
        assert status1 == status2
        assert status1 != status3


class TestContinuousError:
    """Test ContinuousError model."""
    
    def test_continuous_error_creation(self):
        """Test creating continuous error."""
        occurrences = [
            ErrorOccurrence(id=1, frame_id=10, confidence=85, timestamp=1234567890.0),
            ErrorOccurrence(id=2, frame_id=11, confidence=90, timestamp=1234567891.0),
            ErrorOccurrence(id=3, frame_id=12, confidence=88, timestamp=1234567892.0)
        ]
        
        error = ContinuousError(
            id=1,
            detector_name="ClockDetector",
            description="Clock position changed",
            first_frame=10,
            last_frame=12,
            frame_range="10-12",
            confidence=88,
            is_active=True,
            occurrences=occurrences
        )
        
        assert error.id == 1
        assert error.detector_name == "ClockDetector"
        assert error.first_frame == 10
        assert error.last_frame == 12
        assert error.frame_range == "10-12"
        assert len(error.occurrences) == 3
        assert not error.is_single_frame
    
    def test_single_frame_error(self):
        """Test single frame error."""
        occurrence = ErrorOccurrence(id=1, frame_id=50, confidence=95, timestamp=1234567890.0)
        
        error = ContinuousError(
            id=1,
            detector_name="TestDetector",
            description="Single frame error",
            first_frame=50,
            last_frame=50,
            frame_range="50",
            confidence=95,
            is_active=False,
            occurrences=[occurrence]
        )
        
        assert error.is_single_frame


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
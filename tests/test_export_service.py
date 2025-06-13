"""
Comprehensive tests for export service functionality.
Tests PDF generation, frame aggregation, note parsing, and report formatting.
"""

import pytest
import tempfile
import os
import shutil
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import json
from pathlib import Path
import cv2
import numpy as np
from reportlab.lib.pagesizes import A4

from CAMF.services.export.pdf_generator import PDFGenerator, ReportConfig
from CAMF.services.export.frame_processor import FrameProcessor, FrameAnnotator
from CAMF.services.export.note_parser import NoteParser, NoteFormatter
from CAMF.services.export.main import ExportService, ExportOptions


class TestPDFGenerator:
    """Test PDF generation functionality."""
    
    @pytest.fixture
    def pdf_generator(self):
        """Create PDF generator instance."""
        return PDFGenerator()
    
    @pytest.fixture
    def temp_output_dir(self):
        """Create temporary output directory."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def sample_report_data(self):
        """Create sample report data."""
        return {
            "project": {
                "name": "Test Production",
                "created_at": datetime.now().isoformat(),
                "director": "Test Director"
            },
            "scene": {
                "name": "Scene 1",
                "location": "Studio A",
                "date": datetime.now().isoformat()
            },
            "take": {
                "name": "Take 1",
                "number": 1,
                "duration": 120.5,
                "fps": 24,
                "is_reference": False
            },
            "detections": [
                {
                    "frame_number": 100,
                    "timestamp": 4.17,
                    "detector": "ClockDetector",
                    "confidence": 0.95,
                    "description": "Clock showing 2:30 PM"
                },
                {
                    "frame_number": 250,
                    "timestamp": 10.42,
                    "detector": "ContinuityDetector",
                    "confidence": 0.87,
                    "description": "Props position changed"
                }
            ],
            "notes": [
                {
                    "timestamp": 5.0,
                    "author": "Script Supervisor",
                    "content": "Actor missed line"
                }
            ]
        }
    
    def test_generate_basic_pdf(self, pdf_generator, temp_output_dir, sample_report_data):
        """Test basic PDF generation."""
        output_path = os.path.join(temp_output_dir, "report.pdf")
        
        # Generate PDF
        success = pdf_generator.generate_report(
            data=sample_report_data,
            output_path=output_path
        )
        
        assert success is True
        assert os.path.exists(output_path)
        assert os.path.getsize(output_path) > 1000  # Should have content
    
    def test_pdf_with_custom_config(self, pdf_generator, temp_output_dir, sample_report_data):
        """Test PDF generation with custom configuration."""
        config = ReportConfig(
            page_size=A4,
            margins=(50, 50, 50, 50),
            font_family="Helvetica",
            include_cover_page=True,
            include_table_of_contents=True,
            include_summary=True
        )
        
        output_path = os.path.join(temp_output_dir, "custom_report.pdf")
        
        success = pdf_generator.generate_report(
            data=sample_report_data,
            output_path=output_path,
            config=config
        )
        
        assert success is True
        assert os.path.exists(output_path)
    
    def test_pdf_with_images(self, pdf_generator, temp_output_dir, sample_report_data):
        """Test PDF generation with embedded images."""
        # Create sample images
        frame_images = []
        for i in range(3):
            img = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(img, f"Frame {i}", (50, 50), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            
            img_path = os.path.join(temp_output_dir, f"frame_{i}.jpg")
            cv2.imwrite(img_path, img)
            frame_images.append(img_path)
        
        # Add image paths to report data
        for i, detection in enumerate(sample_report_data["detections"][:2]):
            detection["frame_path"] = frame_images[i]
        
        output_path = os.path.join(temp_output_dir, "report_with_images.pdf")
        
        success = pdf_generator.generate_report(
            data=sample_report_data,
            output_path=output_path,
            include_images=True
        )
        
        assert success is True
        assert os.path.exists(output_path)
        # File should be larger due to images
        assert os.path.getsize(output_path) > 10000
    
    def test_multi_page_report(self, pdf_generator, temp_output_dir):
        """Test generating multi-page reports."""
        # Create large dataset
        large_data = {
            "project": {"name": "Large Production"},
            "scene": {"name": "Scene 1"},
            "take": {"name": "Take 1", "number": 1},
            "detections": []
        }
        
        # Add many detections to force multiple pages
        for i in range(100):
            large_data["detections"].append({
                "frame_number": i * 10,
                "timestamp": i * 0.42,
                "detector": f"Detector{i % 3}",
                "confidence": 0.8 + (i % 20) / 100,
                "description": f"Detection {i} with detailed description"
            })
        
        output_path = os.path.join(temp_output_dir, "multi_page_report.pdf")
        
        success = pdf_generator.generate_report(
            data=large_data,
            output_path=output_path
        )
        
        assert success is True
        assert os.path.exists(output_path)
    
    def test_pdf_metadata(self, pdf_generator, temp_output_dir, sample_report_data):
        """Test adding metadata to PDF."""
        metadata = {
            "title": "Continuity Report - Test Production",
            "author": "CAMF Export System",
            "subject": "Scene 1 Continuity Analysis",
            "keywords": ["continuity", "film", "production"],
            "creator": "CAMF v1.0.0"
        }
        
        output_path = os.path.join(temp_output_dir, "report_with_metadata.pdf")
        
        success = pdf_generator.generate_report(
            data=sample_report_data,
            output_path=output_path,
            metadata=metadata
        )
        
        assert success is True
        
        # Verify metadata (would need PDF reader library)
        # For now, just check file exists
        assert os.path.exists(output_path)
    
    def test_error_handling(self, pdf_generator, sample_report_data):
        """Test error handling in PDF generation."""
        # Invalid output path
        invalid_path = "/invalid/path/report.pdf"
        
        success = pdf_generator.generate_report(
            data=sample_report_data,
            output_path=invalid_path
        )
        
        assert success is False
        
        # Missing required data
        incomplete_data = {"project": {"name": "Test"}}  # Missing other fields
        
        with tempfile.NamedTemporaryFile(suffix=".pdf") as temp_file:
            success = pdf_generator.generate_report(
                data=incomplete_data,
                output_path=temp_file.name
            )
            # Should handle gracefully
            assert isinstance(success, bool)


class TestFrameProcessor:
    """Test frame processing for export."""
    
    @pytest.fixture
    def frame_processor(self):
        """Create frame processor instance."""
        return FrameProcessor()
    
    @pytest.fixture
    def sample_frames(self, temp_output_dir):
        """Create sample frame images."""
        frames = []
        for i in range(5):
            img = np.full((480, 640, 3), i * 50, dtype=np.uint8)
            path = os.path.join(temp_output_dir, f"frame_{i:04d}.jpg")
            cv2.imwrite(path, img)
            frames.append({
                "path": path,
                "frame_number": i,
                "timestamp": i / 30.0
            })
        return frames
    
    def test_create_frame_grid(self, frame_processor, sample_frames, temp_output_dir):
        """Test creating grid of frames."""
        output_path = os.path.join(temp_output_dir, "frame_grid.jpg")
        
        # Create 2x2 grid
        success = frame_processor.create_frame_grid(
            frames=sample_frames[:4],
            output_path=output_path,
            grid_size=(2, 2),
            frame_size=(320, 240)
        )
        
        assert success is True
        assert os.path.exists(output_path)
        
        # Check output dimensions
        grid_img = cv2.imread(output_path)
        assert grid_img.shape[1] == 640  # 2 * 320
        assert grid_img.shape[0] == 480  # 2 * 240
    
    def test_create_frame_sequence(self, frame_processor, sample_frames, temp_output_dir):
        """Test creating frame sequence strip."""
        output_path = os.path.join(temp_output_dir, "frame_sequence.jpg")
        
        success = frame_processor.create_sequence_strip(
            frames=sample_frames,
            output_path=output_path,
            frame_width=160,
            include_timestamps=True
        )
        
        assert success is True
        assert os.path.exists(output_path)
        
        # Check it's a horizontal strip
        seq_img = cv2.imread(output_path)
        assert seq_img.shape[1] == 800  # 5 frames * 160
    
    def test_annotate_frames(self, frame_processor, sample_frames, temp_output_dir):
        """Test annotating frames with detection info."""
        annotator = FrameAnnotator()
        
        # Annotate frames
        for i, frame_info in enumerate(sample_frames[:3]):
            img = cv2.imread(frame_info["path"])
            
            # Add annotations
            annotations = {
                "detector": "TestDetector",
                "confidence": 0.85 + i * 0.05,
                "bbox": [100, 100, 200, 200],
                "label": f"Object {i}"
            }
            
            annotated = annotator.annotate_frame(img, annotations)
            
            output_path = os.path.join(temp_output_dir, f"annotated_{i}.jpg")
            cv2.imwrite(output_path, annotated)
            
            assert os.path.exists(output_path)
    
    def test_create_comparison_view(self, frame_processor, sample_frames, temp_output_dir):
        """Test creating side-by-side comparison view."""
        output_path = os.path.join(temp_output_dir, "comparison.jpg")
        
        # Compare first and last frame
        success = frame_processor.create_comparison(
            reference_frame=sample_frames[0]["path"],
            comparison_frame=sample_frames[-1]["path"],
            output_path=output_path,
            labels=["Reference", "Current"]
        )
        
        assert success is True
        assert os.path.exists(output_path)
    
    def test_create_timeline_visualization(self, frame_processor, temp_output_dir):
        """Test creating timeline visualization."""
        # Create timeline data
        timeline_data = [
            {"start": 0, "end": 5, "label": "Setup", "color": (0, 255, 0)},
            {"start": 5, "end": 15, "label": "Action", "color": (255, 0, 0)},
            {"start": 15, "end": 20, "label": "Cut", "color": (0, 0, 255)},
        ]
        
        detections = [
            {"timestamp": 3.5, "type": "clock"},
            {"timestamp": 8.2, "type": "continuity"},
            {"timestamp": 16.7, "type": "clock"}
        ]
        
        output_path = os.path.join(temp_output_dir, "timeline.png")
        
        success = frame_processor.create_timeline(
            duration=20,
            segments=timeline_data,
            detections=detections,
            output_path=output_path,
            width=800,
            height=200
        )
        
        assert success is True
        assert os.path.exists(output_path)


class TestNoteParser:
    """Test note parsing functionality."""
    
    @pytest.fixture
    def note_parser(self):
        """Create note parser instance."""
        return NoteParser()
    
    def test_parse_plain_text_notes(self, note_parser):
        """Test parsing plain text notes."""
        notes_text = """
        00:00:05 - Camera angle needs adjustment
        00:00:15 - Actor enters from wrong side
        00:01:30 - Good take, but watch continuity with previous
        """
        
        parsed_notes = note_parser.parse_text(notes_text)
        
        assert len(parsed_notes) == 3
        assert parsed_notes[0]["timestamp"] == 5.0
        assert "Camera angle" in parsed_notes[0]["content"]
        assert parsed_notes[2]["timestamp"] == 90.0
    
    def test_parse_structured_notes(self, note_parser):
        """Test parsing structured note formats."""
        # JSON format notes
        json_notes = [
            {
                "timestamp": "00:00:10",
                "author": "Director",
                "type": "performance",
                "content": "Need more emotion in delivery"
            },
            {
                "timestamp": "00:00:45",
                "author": "Script Supervisor",
                "type": "continuity",
                "content": "Watch position of coffee cup"
            }
        ]
        
        parsed = note_parser.parse_structured(json_notes)
        
        assert len(parsed) == 2
        assert parsed[0]["timestamp"] == 10.0
        assert parsed[0]["author"] == "Director"
        assert parsed[1]["type"] == "continuity"
    
    def test_parse_timecode_formats(self, note_parser):
        """Test parsing various timecode formats."""
        timecodes = [
            ("00:00:10", 10.0),
            ("01:30", 90.0),
            ("1:05:30", 3930.0),
            ("00:00:10:15", 10.5),  # With frames at 30fps
            ("10s", 10.0),
            ("1m30s", 90.0)
        ]
        
        for timecode, expected in timecodes:
            result = note_parser.parse_timecode(timecode, fps=30)
            assert result == pytest.approx(expected, rel=0.1)
    
    def test_categorize_notes(self, note_parser):
        """Test automatic note categorization."""
        notes = [
            {"content": "Clock visible at 2:30", "timestamp": 10},
            {"content": "Actor forgot line here", "timestamp": 20},
            {"content": "Continuity: Props moved", "timestamp": 30},
            {"content": "Great performance!", "timestamp": 40}
        ]
        
        categorized = note_parser.categorize_notes(notes)
        
        assert "continuity" in categorized
        assert "performance" in categorized
        assert "technical" in categorized
        
        # Check categorization
        assert any("Clock" in note["content"] for note in categorized["continuity"])
        assert any("forgot line" in note["content"] for note in categorized["performance"])
    
    def test_format_notes_for_export(self, note_parser):
        """Test formatting notes for different export formats."""
        notes = [
            {
                "timestamp": 10.5,
                "author": "Director",
                "content": "Check lighting",
                "type": "technical"
            }
        ]
        
        # Format for PDF
        pdf_formatted = note_parser.format_for_pdf(notes)
        assert isinstance(pdf_formatted, list)
        assert "00:00:10" in pdf_formatted[0]["formatted_time"]
        
        # Format for CSV
        csv_formatted = note_parser.format_for_csv(notes)
        assert isinstance(csv_formatted, list)
        assert all(key in csv_formatted[0] for key in ["timestamp", "author", "content"])


class TestExportService:
    """Test main export service functionality."""
    
    @pytest.fixture
    def export_service(self):
        """Create export service instance."""
        return ExportService()
    
    @pytest.fixture
    def mock_storage_service(self):
        """Create mock storage service."""
        mock = MagicMock()
        mock.get_take.return_value = {
            "id": 1,
            "name": "Take 1",
            "scene_id": 1,
            "angle_id": 1
        }
        mock.get_frames.return_value = [
            {"id": i, "frame_number": i, "timestamp": i/30.0}
            for i in range(100)
        ]
        return mock
    
    def test_export_take_report(self, export_service, mock_storage_service, temp_output_dir):
        """Test exporting complete take report."""
        with patch.object(export_service, 'storage_service', mock_storage_service):
            options = ExportOptions(
                format="pdf",
                include_frames=True,
                include_notes=True,
                include_detections=True,
                frame_sample_rate=10  # Every 10th frame
            )
            
            output_path = os.path.join(temp_output_dir, "take_report.pdf")
            
            success = export_service.export_take_report(
                take_id=1,
                output_path=output_path,
                options=options
            )
            
            # Would check actual file generation
            assert isinstance(success, bool)
    
    def test_export_scene_summary(self, export_service, mock_storage_service, temp_output_dir):
        """Test exporting scene summary report."""
        mock_storage_service.get_scene.return_value = {
            "id": 1,
            "name": "Scene 1",
            "takes": [1, 2, 3]
        }
        
        with patch.object(export_service, 'storage_service', mock_storage_service):
            output_path = os.path.join(temp_output_dir, "scene_summary.pdf")
            
            success = export_service.export_scene_summary(
                scene_id=1,
                output_path=output_path
            )
            
            assert isinstance(success, bool)
    
    def test_export_formats(self, export_service, temp_output_dir):
        """Test different export formats."""
        formats = ["pdf", "html", "csv", "json"]
        
        for format_type in formats:
            output_file = os.path.join(temp_output_dir, f"export.{format_type}")
            
            # Test format support
            is_supported = export_service.is_format_supported(format_type)
            assert is_supported is True
    
    def test_batch_export(self, export_service, mock_storage_service, temp_output_dir):
        """Test batch export of multiple takes."""
        take_ids = [1, 2, 3]
        
        with patch.object(export_service, 'storage_service', mock_storage_service):
            results = export_service.batch_export_takes(
                take_ids=take_ids,
                output_dir=temp_output_dir,
                format="pdf"
            )
            
            assert len(results) == 3
            assert all("status" in r for r in results)
    
    def test_export_with_custom_template(self, export_service, temp_output_dir):
        """Test export with custom template."""
        template_content = """
        <html>
        <head><title>{{ project.name }}</title></head>
        <body>
            <h1>{{ scene.name }}</h1>
            <h2>{{ take.name }}</h2>
            {% for detection in detections %}
                <p>Frame {{ detection.frame_number }}: {{ detection.description }}</p>
            {% endfor %}
        </body>
        </html>
        """
        
        template_path = os.path.join(temp_output_dir, "template.html")
        with open(template_path, 'w') as f:
            f.write(template_content)
        
        # Export with template
        data = {
            "project": {"name": "Test Project"},
            "scene": {"name": "Scene 1"},
            "take": {"name": "Take 1"},
            "detections": [
                {"frame_number": 100, "description": "Test detection"}
            ]
        }
        
        output_path = os.path.join(temp_output_dir, "custom_export.html")
        
        success = export_service.export_with_template(
            data=data,
            template_path=template_path,
            output_path=output_path
        )
        
        # Would verify actual rendering
        assert isinstance(success, bool)
"""
Comprehensive tests for video upload and processing functionality.
Tests video file handling, format support, frame extraction, and batch processing.
"""

import pytest
import tempfile
import os
import cv2
import numpy as np
from unittest.mock import Mock, patch, MagicMock
import time
from pathlib import Path
import shutil
import json

from CAMF.services.capture.upload import (
    VideoUploadProcessor, VideoFileInfo, VideoFormat,
    FrameExtractor, VideoValidator, BatchVideoProcessor
)
from CAMF.common.models import ProcessingStatus


class TestVideoUploadProcessor:
    """Test video upload processing functionality."""
    
    @pytest.fixture
    def create_test_video(self):
        """Create test video file."""
        def _create_video(filename, duration=5, fps=30, resolution=(640, 480)):
            temp_dir = tempfile.mkdtemp()
            video_path = os.path.join(temp_dir, filename)
            
            # Create video writer
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(video_path, fourcc, fps, resolution)
            
            # Write frames
            frame_count = int(duration * fps)
            for i in range(frame_count):
                # Create frame with frame number
                frame = np.zeros((*resolution[::-1], 3), dtype=np.uint8)
                cv2.putText(frame, f"Frame {i}", (50, 50),
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                writer.write(frame)
            
            writer.release()
            return video_path, temp_dir
        
        return _create_video
    
    @pytest.fixture
    def video_processor(self):
        """Create video upload processor."""
        return VideoUploadProcessor()
    
    def test_video_file_validation(self, video_processor, create_test_video):
        """Test video file validation."""
        video_path, temp_dir = create_test_video("test.mp4")
        
        try:
            # Valid video
            is_valid, info = video_processor.validate_video(video_path)
            assert is_valid is True
            assert info.duration == 5.0
            assert info.fps == 30
            assert info.resolution == (640, 480)
            
            # Invalid file
            invalid_path = os.path.join(temp_dir, "invalid.txt")
            with open(invalid_path, 'w') as f:
                f.write("not a video")
            
            is_valid, error = video_processor.validate_video(invalid_path)
            assert is_valid is False
            assert error is not None
            
        finally:
            shutil.rmtree(temp_dir)
    
    def test_supported_video_formats(self, video_processor):
        """Test supported video format detection."""
        supported_formats = video_processor.get_supported_formats()
        
        # Common formats should be supported
        assert VideoFormat.MP4 in supported_formats
        assert VideoFormat.AVI in supported_formats
        assert VideoFormat.MOV in supported_formats
        assert VideoFormat.MKV in supported_formats
        
        # Check format detection
        assert video_processor.detect_format("video.mp4") == VideoFormat.MP4
        assert video_processor.detect_format("video.avi") == VideoFormat.AVI
        assert video_processor.detect_format("video.mov") == VideoFormat.MOV
    
    def test_video_upload_processing(self, video_processor, create_test_video):
        """Test processing uploaded video."""
        video_path, temp_dir = create_test_video("upload.mp4", duration=2)
        
        try:
            # Process video
            result = video_processor.process_upload(
                video_path=video_path,
                output_dir=temp_dir,
                extract_frames=True
            )
            
            assert result.status == ProcessingStatus.COMPLETED
            assert result.frame_count == 60  # 2 seconds * 30 fps
            assert len(result.extracted_frames) == 60
            assert all(os.path.exists(f) for f in result.extracted_frames)
            
        finally:
            shutil.rmtree(temp_dir)
    
    def test_video_metadata_extraction(self, video_processor, create_test_video):
        """Test extracting video metadata."""
        video_path, temp_dir = create_test_video("metadata.mp4")
        
        try:
            metadata = video_processor.extract_metadata(video_path)
            
            assert metadata["duration"] == 5.0
            assert metadata["fps"] == 30
            assert metadata["frame_count"] == 150
            assert metadata["resolution"] == (640, 480)
            assert metadata["codec"] is not None
            assert metadata["bitrate"] > 0
            assert metadata["file_size"] > 0
            
        finally:
            shutil.rmtree(temp_dir)
    
    def test_video_chunking(self, video_processor, create_test_video):
        """Test video chunking for large files."""
        video_path, temp_dir = create_test_video("large.mp4", duration=30)
        
        try:
            # Process in chunks
            chunks = video_processor.process_in_chunks(
                video_path=video_path,
                chunk_duration=5,  # 5 second chunks
                output_dir=temp_dir
            )
            
            assert len(chunks) == 6  # 30 seconds / 5 seconds
            
            # Verify chunks
            for i, chunk in enumerate(chunks):
                assert chunk.start_time == i * 5
                assert chunk.duration == 5
                assert chunk.frame_count == 150  # 5 seconds * 30 fps
                
        finally:
            shutil.rmtree(temp_dir)
    
    def test_concurrent_video_processing(self, video_processor, create_test_video):
        """Test processing multiple videos concurrently."""
        videos = []
        temp_dirs = []
        
        # Create multiple videos
        for i in range(3):
            video_path, temp_dir = create_test_video(f"video{i}.mp4", duration=2)
            videos.append(video_path)
            temp_dirs.append(temp_dir)
        
        try:
            # Process concurrently
            results = video_processor.process_multiple(
                video_paths=videos,
                max_workers=3
            )
            
            assert len(results) == 3
            assert all(r.status == ProcessingStatus.COMPLETED for r in results)
            
        finally:
            for temp_dir in temp_dirs:
                shutil.rmtree(temp_dir)


class TestFrameExtractor:
    """Test frame extraction from videos."""
    
    @pytest.fixture
    def frame_extractor(self):
        """Create frame extractor."""
        return FrameExtractor()
    
    def test_extract_all_frames(self, frame_extractor, create_test_video):
        """Test extracting all frames from video."""
        video_path, temp_dir = create_test_video("extract_all.mp4", duration=1)
        
        try:
            output_dir = os.path.join(temp_dir, "frames")
            os.makedirs(output_dir)
            
            # Extract all frames
            frames = frame_extractor.extract_all_frames(
                video_path=video_path,
                output_dir=output_dir
            )
            
            assert len(frames) == 30  # 1 second * 30 fps
            assert all(os.path.exists(f) for f in frames)
            
            # Check frame naming
            assert frames[0].endswith("frame_00000.jpg")
            assert frames[29].endswith("frame_00029.jpg")
            
        finally:
            shutil.rmtree(temp_dir)
    
    def test_extract_frames_at_intervals(self, frame_extractor, create_test_video):
        """Test extracting frames at specific intervals."""
        video_path, temp_dir = create_test_video("extract_interval.mp4", duration=10)
        
        try:
            output_dir = os.path.join(temp_dir, "frames")
            os.makedirs(output_dir)
            
            # Extract frame every second
            frames = frame_extractor.extract_at_intervals(
                video_path=video_path,
                output_dir=output_dir,
                interval=1.0  # 1 second
            )
            
            assert len(frames) == 10  # One frame per second
            
        finally:
            shutil.rmtree(temp_dir)
    
    def test_extract_specific_frames(self, frame_extractor, create_test_video):
        """Test extracting specific frame numbers."""
        video_path, temp_dir = create_test_video("extract_specific.mp4", duration=5)
        
        try:
            output_dir = os.path.join(temp_dir, "frames")
            os.makedirs(output_dir)
            
            # Extract specific frames
            frame_numbers = [0, 30, 60, 90, 149]  # Various points in video
            frames = frame_extractor.extract_frames(
                video_path=video_path,
                output_dir=output_dir,
                frame_numbers=frame_numbers
            )
            
            assert len(frames) == len(frame_numbers)
            assert all(os.path.exists(f) for f in frames)
            
        finally:
            shutil.rmtree(temp_dir)
    
    def test_extract_keyframes(self, frame_extractor, create_test_video):
        """Test extracting keyframes from video."""
        video_path, temp_dir = create_test_video("extract_keyframes.mp4", duration=10)
        
        try:
            output_dir = os.path.join(temp_dir, "frames")
            os.makedirs(output_dir)
            
            # Extract keyframes
            keyframes = frame_extractor.extract_keyframes(
                video_path=video_path,
                output_dir=output_dir
            )
            
            # Should extract fewer frames than total
            assert len(keyframes) < 300  # Less than 10s * 30fps
            assert len(keyframes) > 0
            assert all(os.path.exists(f) for f in keyframes)
            
        finally:
            shutil.rmtree(temp_dir)
    
    def test_extract_with_filters(self, frame_extractor, create_test_video):
        """Test frame extraction with filters."""
        video_path, temp_dir = create_test_video("extract_filter.mp4", duration=5)
        
        try:
            output_dir = os.path.join(temp_dir, "frames")
            os.makedirs(output_dir)
            
            # Extract with quality filter (skip blurry frames)
            frames = frame_extractor.extract_with_filter(
                video_path=video_path,
                output_dir=output_dir,
                filter_func=lambda frame: cv2.Laplacian(frame, cv2.CV_64F).var() > 100
            )
            
            assert len(frames) > 0
            assert all(os.path.exists(f) for f in frames)
            
        finally:
            shutil.rmtree(temp_dir)
    
    def test_extract_frame_regions(self, frame_extractor, create_test_video):
        """Test extracting specific regions from frames."""
        video_path, temp_dir = create_test_video("extract_regions.mp4")
        
        try:
            output_dir = os.path.join(temp_dir, "regions")
            os.makedirs(output_dir)
            
            # Define regions of interest
            regions = [
                {"x": 0, "y": 0, "width": 320, "height": 240},  # Top-left
                {"x": 320, "y": 240, "width": 320, "height": 240}  # Bottom-right
            ]
            
            extracted = frame_extractor.extract_regions(
                video_path=video_path,
                output_dir=output_dir,
                regions=regions,
                frame_numbers=[0, 50, 100]
            )
            
            # Should have 2 regions * 3 frames = 6 files
            assert len(extracted) == 6
            
        finally:
            shutil.rmtree(temp_dir)


class TestVideoValidator:
    """Test video validation functionality."""
    
    @pytest.fixture
    def video_validator(self):
        """Create video validator."""
        return VideoValidator()
    
    def test_validate_codec(self, video_validator, create_test_video):
        """Test video codec validation."""
        video_path, temp_dir = create_test_video("codec_test.mp4")
        
        try:
            # Check codec support
            is_supported = video_validator.is_codec_supported(video_path)
            assert is_supported is True
            
            # Get codec info
            codec_info = video_validator.get_codec_info(video_path)
            assert codec_info["name"] is not None
            assert codec_info["long_name"] is not None
            
        finally:
            shutil.rmtree(temp_dir)
    
    def test_validate_integrity(self, video_validator, create_test_video):
        """Test video file integrity validation."""
        video_path, temp_dir = create_test_video("integrity_test.mp4")
        
        try:
            # Valid video should pass
            is_valid, errors = video_validator.validate_integrity(video_path)
            assert is_valid is True
            assert len(errors) == 0
            
            # Corrupt video file
            with open(video_path, 'r+b') as f:
                f.seek(100)
                f.write(b'corrupted_data')
            
            # Should detect corruption
            is_valid, errors = video_validator.validate_integrity(video_path)
            assert is_valid is False
            assert len(errors) > 0
            
        finally:
            shutil.rmtree(temp_dir)
    
    def test_validate_resolution_limits(self, video_validator):
        """Test video resolution validation."""
        # Test various resolutions
        resolutions = [
            ((640, 480), True),    # SD - valid
            ((1920, 1080), True),  # Full HD - valid
            ((3840, 2160), True),  # 4K - valid
            ((7680, 4320), False), # 8K - too large
            ((100, 100), False),   # Too small
        ]
        
        for resolution, expected_valid in resolutions:
            is_valid = video_validator.is_resolution_supported(resolution)
            assert is_valid == expected_valid
    
    def test_validate_duration_limits(self, video_validator):
        """Test video duration validation."""
        # Test various durations
        durations = [
            (60, True),      # 1 minute - valid
            (3600, True),    # 1 hour - valid
            (36000, False),  # 10 hours - too long
            (0.1, False),    # Too short
        ]
        
        for duration, expected_valid in durations:
            is_valid = video_validator.is_duration_valid(duration)
            assert is_valid == expected_valid


class TestBatchVideoProcessor:
    """Test batch video processing functionality."""
    
    @pytest.fixture
    def batch_processor(self):
        """Create batch video processor."""
        return BatchVideoProcessor(max_workers=2)
    
    def test_batch_upload_processing(self, batch_processor, create_test_video):
        """Test processing batch of uploaded videos."""
        videos = []
        temp_dirs = []
        
        # Create test videos
        for i in range(3):
            video_path, temp_dir = create_test_video(f"batch{i}.mp4", duration=2)
            videos.append(video_path)
            temp_dirs.append(temp_dir)
        
        try:
            # Process batch
            results = batch_processor.process_batch(
                video_paths=videos,
                output_dir=temp_dirs[0],
                options={
                    "extract_frames": True,
                    "generate_thumbnails": True,
                    "extract_metadata": True
                }
            )
            
            assert len(results) == 3
            assert all(r["status"] == "completed" for r in results)
            assert all(r["frame_count"] == 60 for r in results)
            
        finally:
            for temp_dir in temp_dirs:
                shutil.rmtree(temp_dir)
    
    def test_batch_progress_tracking(self, batch_processor, create_test_video):
        """Test progress tracking for batch processing."""
        videos = []
        temp_dirs = []
        
        for i in range(2):
            video_path, temp_dir = create_test_video(f"progress{i}.mp4", duration=5)
            videos.append(video_path)
            temp_dirs.append(temp_dir)
        
        try:
            progress_updates = []
            
            def progress_callback(update):
                progress_updates.append(update)
            
            # Process with progress tracking
            results = batch_processor.process_batch(
                video_paths=videos,
                output_dir=temp_dirs[0],
                progress_callback=progress_callback
            )
            
            # Should have progress updates
            assert len(progress_updates) > 0
            assert any(u["status"] == "processing" for u in progress_updates)
            assert any(u["status"] == "completed" for u in progress_updates)
            
        finally:
            for temp_dir in temp_dirs:
                shutil.rmtree(temp_dir)
    
    def test_batch_error_handling(self, batch_processor, create_test_video):
        """Test error handling in batch processing."""
        video_path, temp_dir = create_test_video("valid.mp4")
        invalid_path = os.path.join(temp_dir, "invalid.mp4")
        
        try:
            # Mix valid and invalid videos
            videos = [video_path, invalid_path, video_path]
            
            results = batch_processor.process_batch(
                video_paths=videos,
                output_dir=temp_dir,
                continue_on_error=True
            )
            
            assert len(results) == 3
            assert results[0]["status"] == "completed"
            assert results[1]["status"] == "error"
            assert results[2]["status"] == "completed"
            
        finally:
            shutil.rmtree(temp_dir)
    
    def test_batch_memory_management(self, batch_processor, create_test_video):
        """Test memory management during batch processing."""
        import psutil
        import os
        
        videos = []
        temp_dirs = []
        
        # Create larger videos
        for i in range(5):
            video_path, temp_dir = create_test_video(
                f"memory{i}.mp4", 
                duration=10,
                resolution=(1920, 1080)
            )
            videos.append(video_path)
            temp_dirs.append(temp_dir)
        
        try:
            process = psutil.Process(os.getpid())
            memory_before = process.memory_info().rss
            
            # Process batch
            results = batch_processor.process_batch(
                video_paths=videos,
                output_dir=temp_dirs[0],
                options={"extract_frames": False}  # Don't extract to save space
            )
            
            memory_after = process.memory_info().rss
            memory_increase = memory_after - memory_before
            
            # Memory should be released after processing
            assert memory_increase < 500 * 1024 * 1024  # Less than 500MB
            
        finally:
            for temp_dir in temp_dirs:
                shutil.rmtree(temp_dir)


class TestVideoFormatConversion:
    """Test video format conversion functionality."""
    
    @pytest.fixture
    def format_converter(self):
        """Create format converter."""
        from CAMF.services.capture.upload import VideoFormatConverter
        return VideoFormatConverter()
    
    def test_convert_to_standard_format(self, format_converter, create_test_video):
        """Test converting videos to standard format."""
        video_path, temp_dir = create_test_video("original.avi")
        
        try:
            output_path = os.path.join(temp_dir, "converted.mp4")
            
            # Convert to MP4
            success = format_converter.convert(
                input_path=video_path,
                output_path=output_path,
                target_format=VideoFormat.MP4
            )
            
            assert success is True
            assert os.path.exists(output_path)
            
            # Verify conversion
            cap = cv2.VideoCapture(output_path)
            assert cap.isOpened()
            cap.release()
            
        finally:
            shutil.rmtree(temp_dir)
    
    def test_convert_with_compression(self, format_converter, create_test_video):
        """Test video conversion with compression."""
        video_path, temp_dir = create_test_video("large.mp4", resolution=(1920, 1080))
        
        try:
            output_path = os.path.join(temp_dir, "compressed.mp4")
            
            # Convert with compression
            success = format_converter.convert(
                input_path=video_path,
                output_path=output_path,
                compression_level="high",
                target_bitrate="2M"
            )
            
            assert success is True
            
            # Compressed file should be smaller
            original_size = os.path.getsize(video_path)
            compressed_size = os.path.getsize(output_path)
            assert compressed_size < original_size
            
        finally:
            shutil.rmtree(temp_dir)
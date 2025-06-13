"""
Comprehensive tests for Storage service frame operations.
Tests frame storage, hybrid storage system, video conversion, and file management.
"""

import pytest
import tempfile
import shutil
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
import cv2
import numpy as np
from datetime import datetime, timedelta
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor

from CAMF.services.storage.frame_storage import (
    FrameStorage, HybridFrameStorage, VideoSegment,
    FrameCache, FrameIndex, CompressionTier
)
from CAMF.services.storage.file_utils import FileManager, StorageStats
from CAMF.common.models import Frame, Take


class TestFrameStorage:
    """Test basic frame storage operations."""
    
    @pytest.fixture
    def temp_storage_dir(self):
        """Create temporary storage directory."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def frame_storage(self, temp_storage_dir):
        """Create frame storage instance."""
        return FrameStorage(base_path=temp_storage_dir)
    
    @pytest.fixture
    def sample_frame(self):
        """Create sample frame data."""
        # Create a simple test image
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        image[100:200, 100:200] = [255, 0, 0]  # Red square
        return image
    
    def test_save_frame_jpeg(self, frame_storage, sample_frame):
        """Test saving frame as JPEG."""
        frame_path = frame_storage.save_frame(
            frame_data=sample_frame,
            take_id=1,
            frame_number=100,
            format='jpeg'
        )
        
        assert os.path.exists(frame_path)
        assert frame_path.endswith('.jpg')
        
        # Verify frame can be loaded
        loaded_frame = cv2.imread(frame_path)
        assert loaded_frame is not None
        assert loaded_frame.shape == sample_frame.shape
    
    def test_save_frame_png(self, frame_storage, sample_frame):
        """Test saving frame as PNG."""
        frame_path = frame_storage.save_frame(
            frame_data=sample_frame,
            take_id=1,
            frame_number=100,
            format='png'
        )
        
        assert os.path.exists(frame_path)
        assert frame_path.endswith('.png')
        
        # PNG should preserve exact data
        loaded_frame = cv2.imread(frame_path)
        np.testing.assert_array_equal(loaded_frame, sample_frame)
    
    def test_save_frame_with_quality(self, frame_storage, sample_frame):
        """Test saving frame with different quality settings."""
        # High quality
        high_path = frame_storage.save_frame(
            frame_data=sample_frame,
            take_id=1,
            frame_number=1,
            quality=95
        )
        
        # Low quality
        low_path = frame_storage.save_frame(
            frame_data=sample_frame,
            take_id=1,
            frame_number=2,
            quality=50
        )
        
        # High quality file should be larger
        high_size = os.path.getsize(high_path)
        low_size = os.path.getsize(low_path)
        assert high_size > low_size
    
    def test_load_frame(self, frame_storage, sample_frame):
        """Test loading saved frame."""
        # Save frame
        frame_path = frame_storage.save_frame(sample_frame, 1, 100)
        
        # Load frame
        loaded_frame = frame_storage.load_frame(frame_path)
        
        assert loaded_frame is not None
        assert loaded_frame.shape == sample_frame.shape
    
    def test_delete_frame(self, frame_storage, sample_frame):
        """Test deleting frame."""
        # Save frame
        frame_path = frame_storage.save_frame(sample_frame, 1, 100)
        assert os.path.exists(frame_path)
        
        # Delete frame
        success = frame_storage.delete_frame(frame_path)
        assert success
        assert not os.path.exists(frame_path)
    
    def test_frame_directory_structure(self, frame_storage, sample_frame):
        """Test directory structure creation."""
        # Save frames for different takes
        paths = []
        for take_id in [1, 2, 3]:
            for frame_num in range(5):
                path = frame_storage.save_frame(
                    sample_frame,
                    take_id=take_id,
                    frame_number=frame_num
                )
                paths.append(path)
        
        # Check directory structure
        take_dirs = set(str(Path(p).parent) for p in paths)
        assert len(take_dirs) == 3  # One directory per take
    
    def test_concurrent_frame_saves(self, frame_storage, sample_frame):
        """Test concurrent frame saving."""
        def save_frame_task(frame_num):
            return frame_storage.save_frame(
                sample_frame,
                take_id=1,
                frame_number=frame_num
            )
        
        # Save frames concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(save_frame_task, i) for i in range(100)]
            paths = [f.result() for f in futures]
        
        # All frames should be saved
        assert len(paths) == 100
        assert all(os.path.exists(p) for p in paths)


class TestHybridFrameStorage:
    """Test hybrid frame storage with video conversion."""
    
    @pytest.fixture
    def hybrid_storage(self, temp_storage_dir):
        """Create hybrid storage instance."""
        return HybridFrameStorage(
            base_path=temp_storage_dir,
            segment_duration=5,  # 5 second segments for testing
            conversion_threshold=10  # Convert after 10 frames
        )
    
    @pytest.fixture
    def create_test_frames(self, sample_frame):
        """Helper to create test frames."""
        def _create_frames(count, fps=30):
            frames = []
            for i in range(count):
                # Add frame number to image
                frame = sample_frame.copy()
                cv2.putText(frame, f"Frame {i}", (50, 50),
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                frames.append(frame)
            return frames
        return _create_frames
    
    def test_real_time_frame_storage(self, hybrid_storage, create_test_frames):
        """Test real-time frame storage during capture."""
        frames = create_test_frames(30)  # 1 second of frames
        
        # Store frames as if capturing
        frame_paths = []
        for i, frame in enumerate(frames):
            path = hybrid_storage.store_frame_realtime(
                frame_data=frame,
                take_id=1,
                frame_number=i,
                timestamp=i / 30.0
            )
            frame_paths.append(path)
        
        # All frames should be stored as individual files
        assert len(frame_paths) == 30
        assert all(p.endswith('.jpg') for p in frame_paths)
        assert all(os.path.exists(p) for p in frame_paths)
    
    def test_video_segment_conversion(self, hybrid_storage, create_test_frames):
        """Test conversion of frames to video segments."""
        frames = create_test_frames(150)  # 5 seconds at 30fps
        
        # Store frames
        frame_paths = []
        for i, frame in enumerate(frames):
            path = hybrid_storage.store_frame_realtime(
                frame_data=frame,
                take_id=1,
                frame_number=i,
                timestamp=i / 30.0
            )
            frame_paths.append(path)
        
        # Trigger conversion
        segments = hybrid_storage.convert_to_video_segments(
            take_id=1,
            frame_paths=frame_paths,
            fps=30
        )
        
        # Should create one 5-second segment
        assert len(segments) == 1
        assert segments[0].duration == 5.0
        assert segments[0].frame_count == 150
        assert os.path.exists(segments[0].video_path)
        
        # Original frames should be deleted
        assert not any(os.path.exists(p) for p in frame_paths)
    
    def test_multi_segment_conversion(self, hybrid_storage, create_test_frames):
        """Test conversion to multiple video segments."""
        frames = create_test_frames(450)  # 15 seconds at 30fps
        
        # Store frames
        frame_paths = []
        for i, frame in enumerate(frames):
            path = hybrid_storage.store_frame_realtime(
                frame_data=frame,
                take_id=1,
                frame_number=i,
                timestamp=i / 30.0
            )
            frame_paths.append(path)
        
        # Convert to segments
        segments = hybrid_storage.convert_to_video_segments(
            take_id=1,
            frame_paths=frame_paths,
            fps=30
        )
        
        # Should create 3 segments
        assert len(segments) == 3
        assert all(s.duration == 5.0 for s in segments)
        assert sum(s.frame_count for s in segments) == 450
    
    def test_frame_extraction_from_video(self, hybrid_storage, create_test_frames):
        """Test extracting specific frames from video segments."""
        # Create and convert frames
        frames = create_test_frames(150)
        frame_paths = []
        
        for i, frame in enumerate(frames):
            path = hybrid_storage.store_frame_realtime(frame, 1, i, i/30.0)
            frame_paths.append(path)
        
        segments = hybrid_storage.convert_to_video_segments(1, frame_paths, 30)
        
        # Extract specific frames
        extracted_frames = hybrid_storage.extract_frames_from_segment(
            segment=segments[0],
            frame_numbers=[0, 50, 100, 149]
        )
        
        assert len(extracted_frames) == 4
        assert all(f is not None for f in extracted_frames)
    
    def test_compression_tiers(self, hybrid_storage, create_test_frames):
        """Test different compression tiers."""
        frames = create_test_frames(30)
        
        # Store with different tiers
        tiers = [CompressionTier.HIGH, CompressionTier.MEDIUM, CompressionTier.LOW]
        segment_sizes = []
        
        for tier_idx, tier in enumerate(tiers):
            take_id = tier_idx + 1
            paths = []
            
            for i, frame in enumerate(frames):
                path = hybrid_storage.store_frame_realtime(
                    frame, take_id, i, i/30.0, compression_tier=tier
                )
                paths.append(path)
            
            segments = hybrid_storage.convert_to_video_segments(
                take_id, paths, 30, compression_tier=tier
            )
            
            segment_sizes.append(os.path.getsize(segments[0].video_path))
        
        # Higher quality should result in larger files
        assert segment_sizes[0] > segment_sizes[1] > segment_sizes[2]
    
    def test_seek_performance(self, hybrid_storage, create_test_frames):
        """Test seeking performance in video segments."""
        # Create longer video
        frames = create_test_frames(300)  # 10 seconds
        paths = []
        
        for i, frame in enumerate(frames):
            path = hybrid_storage.store_frame_realtime(frame, 1, i, i/30.0)
            paths.append(path)
        
        segments = hybrid_storage.convert_to_video_segments(1, paths, 30)
        
        # Test random seeks
        seek_times = []
        for target_frame in [10, 50, 100, 200, 290]:
            start_time = time.time()
            frame = hybrid_storage.seek_to_frame(segments[0], target_frame)
            seek_time = time.time() - start_time
            seek_times.append(seek_time)
            assert frame is not None
        
        # Seeks should be fast (< 100ms)
        assert all(t < 0.1 for t in seek_times)


class TestFrameCache:
    """Test frame caching functionality."""
    
    @pytest.fixture
    def frame_cache(self):
        """Create frame cache instance."""
        return FrameCache(max_size=100, ttl_seconds=60)
    
    def test_cache_basic_operations(self, frame_cache, sample_frame):
        """Test basic cache operations."""
        # Add to cache
        frame_cache.put("frame_1", sample_frame)
        
        # Retrieve from cache
        cached_frame = frame_cache.get("frame_1")
        assert cached_frame is not None
        np.testing.assert_array_equal(cached_frame, sample_frame)
        
        # Check if in cache
        assert frame_cache.contains("frame_1")
        assert not frame_cache.contains("frame_2")
    
    def test_cache_eviction_lru(self, frame_cache, sample_frame):
        """Test LRU eviction policy."""
        # Fill cache
        for i in range(100):
            frame_cache.put(f"frame_{i}", sample_frame)
        
        # Access some frames to make them recently used
        for i in range(5):
            frame_cache.get(f"frame_{i}")
        
        # Add new frame (should evict least recently used)
        frame_cache.put("frame_100", sample_frame)
        
        # Recently accessed frames should still be in cache
        for i in range(5):
            assert frame_cache.contains(f"frame_{i}")
        
        # Some middle frames should be evicted
        assert not frame_cache.contains("frame_50")
    
    def test_cache_ttl_expiration(self, frame_cache, sample_frame):
        """Test TTL-based expiration."""
        # Create cache with short TTL
        short_cache = FrameCache(max_size=100, ttl_seconds=0.1)
        
        # Add frame
        short_cache.put("frame_1", sample_frame)
        assert short_cache.contains("frame_1")
        
        # Wait for expiration
        time.sleep(0.2)
        
        # Frame should be expired
        assert short_cache.get("frame_1") is None
    
    def test_cache_memory_usage(self, frame_cache):
        """Test cache memory usage tracking."""
        # Add frames of different sizes
        small_frame = np.zeros((240, 320, 3), dtype=np.uint8)
        large_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        
        frame_cache.put("small", small_frame)
        frame_cache.put("large", large_frame)
        
        # Check memory usage
        memory_usage = frame_cache.get_memory_usage()
        assert memory_usage["small"] < memory_usage["large"]
        assert memory_usage["total"] == memory_usage["small"] + memory_usage["large"]
    
    def test_cache_concurrent_access(self, frame_cache, sample_frame):
        """Test concurrent cache access."""
        def cache_operations(thread_id):
            for i in range(10):
                # Write
                frame_cache.put(f"thread_{thread_id}_frame_{i}", sample_frame)
                # Read
                frame = frame_cache.get(f"thread_{thread_id}_frame_{i}")
                assert frame is not None
        
        # Run concurrent operations
        threads = []
        for i in range(10):
            thread = threading.Thread(target=cache_operations, args=(i,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # All frames should be accessible
        for i in range(10):
            for j in range(10):
                key = f"thread_{i}_frame_{j}"
                if frame_cache.contains(key):
                    assert frame_cache.get(key) is not None


class TestFrameIndex:
    """Test frame indexing and metadata."""
    
    @pytest.fixture
    def frame_index(self, temp_storage_dir):
        """Create frame index instance."""
        return FrameIndex(index_path=os.path.join(temp_storage_dir, "frame_index.db"))
    
    def test_index_frame_metadata(self, frame_index):
        """Test indexing frame metadata."""
        # Add frame metadata
        metadata = {
            "frame_number": 100,
            "timestamp": 3.33,
            "file_path": "/frames/frame_100.jpg",
            "file_size": 102400,
            "width": 1920,
            "height": 1080,
            "format": "jpeg",
            "segment_id": None  # Individual frame
        }
        
        frame_index.add_frame(take_id=1, **metadata)
        
        # Query frame
        frame_info = frame_index.get_frame(take_id=1, frame_number=100)
        assert frame_info is not None
        assert frame_info["timestamp"] == 3.33
        assert frame_info["width"] == 1920
    
    def test_index_video_segment(self, frame_index):
        """Test indexing video segment metadata."""
        # Add segment
        segment_metadata = {
            "segment_id": "seg_001",
            "video_path": "/segments/take_1_seg_001.mp4",
            "start_frame": 0,
            "end_frame": 149,
            "duration": 5.0,
            "fps": 30,
            "codec": "h264",
            "bitrate": 5000000
        }
        
        frame_index.add_segment(take_id=1, **segment_metadata)
        
        # Add frames in segment
        for i in range(150):
            frame_index.add_frame(
                take_id=1,
                frame_number=i,
                timestamp=i/30.0,
                segment_id="seg_001",
                segment_offset=i
            )
        
        # Query frames by segment
        segment_frames = frame_index.get_frames_in_segment("seg_001")
        assert len(segment_frames) == 150
    
    def test_index_range_queries(self, frame_index):
        """Test range queries on frame index."""
        # Add frames
        for i in range(300):
            frame_index.add_frame(
                take_id=1,
                frame_number=i,
                timestamp=i/30.0,
                file_path=f"/frames/frame_{i}.jpg"
            )
        
        # Query by timestamp range
        frames = frame_index.get_frames_by_timestamp_range(
            take_id=1,
            start_time=2.0,
            end_time=4.0
        )
        assert len(frames) == 60  # 2 seconds at 30fps
        
        # Query by frame number range
        frames = frame_index.get_frames_by_number_range(
            take_id=1,
            start_frame=100,
            end_frame=199
        )
        assert len(frames) == 100
    
    def test_index_statistics(self, frame_index):
        """Test frame index statistics."""
        # Add mixed frames and segments
        for i in range(100):
            frame_index.add_frame(
                take_id=1,
                frame_number=i,
                timestamp=i/30.0,
                file_path=f"/frames/frame_{i}.jpg" if i < 50 else None,
                segment_id=f"seg_{i//50}" if i >= 50 else None
            )
        
        # Get statistics
        stats = frame_index.get_take_statistics(take_id=1)
        assert stats["total_frames"] == 100
        assert stats["individual_frames"] == 50
        assert stats["segmented_frames"] == 50
        assert stats["duration"] == pytest.approx(100/30.0, rel=0.01)


class TestStorageOptimization:
    """Test storage optimization features."""
    
    @pytest.fixture
    def storage_optimizer(self, temp_storage_dir):
        """Create storage optimizer instance."""
        from CAMF.services.storage.maintenance import StorageOptimizer
        return StorageOptimizer(storage_path=temp_storage_dir)
    
    def test_duplicate_frame_detection(self, storage_optimizer, sample_frame):
        """Test detection of duplicate frames."""
        # Create duplicate frames
        frame1 = sample_frame.copy()
        frame2 = sample_frame.copy()
        frame3 = sample_frame.copy()
        frame3[0, 0] = [255, 255, 255]  # Slightly different
        
        # Check duplicates
        is_dup1 = storage_optimizer.is_duplicate_frame(frame1, frame2)
        is_dup2 = storage_optimizer.is_duplicate_frame(frame1, frame3)
        
        assert is_dup1 is True
        assert is_dup2 is False
    
    def test_storage_cleanup(self, storage_optimizer, temp_storage_dir):
        """Test storage cleanup operations."""
        # Create test files
        old_file = os.path.join(temp_storage_dir, "old_frame.jpg")
        new_file = os.path.join(temp_storage_dir, "new_frame.jpg")
        
        # Create with different timestamps
        with open(old_file, 'wb') as f:
            f.write(b'old')
        time.sleep(0.1)
        with open(new_file, 'wb') as f:
            f.write(b'new')
        
        # Set old file timestamp to past
        old_time = time.time() - (365 * 24 * 60 * 60)  # 1 year ago
        os.utime(old_file, (old_time, old_time))
        
        # Run cleanup
        cleaned = storage_optimizer.cleanup_old_files(max_age_days=30)
        
        assert not os.path.exists(old_file)
        assert os.path.exists(new_file)
        assert cleaned["files_removed"] == 1
    
    def test_storage_statistics(self, storage_optimizer, temp_storage_dir):
        """Test storage statistics calculation."""
        # Create test structure
        for take_id in range(3):
            take_dir = os.path.join(temp_storage_dir, f"take_{take_id}")
            os.makedirs(take_dir)
            
            for i in range(10):
                frame_file = os.path.join(take_dir, f"frame_{i}.jpg")
                with open(frame_file, 'wb') as f:
                    f.write(b'x' * (1024 * (i + 1)))  # Variable sizes
        
        # Calculate statistics
        stats = storage_optimizer.calculate_storage_stats()
        
        assert stats["total_files"] == 30
        assert stats["total_size"] > 0
        assert len(stats["by_take"]) == 3
        assert all(take["file_count"] == 10 for take in stats["by_take"].values())
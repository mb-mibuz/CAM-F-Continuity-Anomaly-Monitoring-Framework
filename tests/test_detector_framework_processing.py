"""
Comprehensive tests for detector framework processing functionality.
Tests detector wrapper, queue management, batch processing, and result handling.
"""

import pytest
import asyncio
import json
import time
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from datetime import datetime
import numpy as np
import queue
import threading
from concurrent.futures import ThreadPoolExecutor

from CAMF.services.detector_framework.detector_wrapper import DetectorWrapper
from CAMF.services.detector_framework.queue_manager import QueueManager
from CAMF.services.detector_framework.batch_processor import BatchProcessor
from CAMF.services.detector_framework.result_cache import ResultCache
from CAMF.services.detector_framework.interface import DetectorInterface


class TestDetectorWrapper:
    """Test detector wrapper functionality."""
    
    @pytest.fixture
    def mock_detector(self):
        """Create mock detector."""
        detector = MagicMock(spec=DetectorInterface)
        detector.name = "TestDetector"
        detector.version = "1.0.0"
        detector.initialize = AsyncMock(return_value=True)
        detector.process_frame = AsyncMock(return_value={
            "detected": True,
            "confidence": 0.95,
            "objects": [{"type": "test", "bbox": [0, 0, 100, 100]}]
        })
        detector.cleanup = AsyncMock()
        return detector
    
    @pytest.fixture
    def detector_wrapper(self, mock_detector):
        """Create detector wrapper."""
        return DetectorWrapper(detector=mock_detector)
    
    @pytest.mark.asyncio
    async def test_detector_initialization(self, detector_wrapper, mock_detector):
        """Test detector initialization through wrapper."""
        # Initialize
        success = await detector_wrapper.initialize()
        
        assert success is True
        assert detector_wrapper.is_initialized is True
        mock_detector.initialize.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_single_frame(self, detector_wrapper, mock_detector):
        """Test processing single frame."""
        await detector_wrapper.initialize()
        
        # Process frame
        frame_data = {
            "frame_id": 1,
            "frame_path": "/frames/frame_001.jpg",
            "timestamp": 1234567890
        }
        
        result = await detector_wrapper.process_frame(frame_data)
        
        assert result is not None
        assert result["detected"] is True
        assert result["confidence"] == 0.95
        assert "processing_time" in result
        assert result["frame_id"] == 1
    
    @pytest.mark.asyncio
    async def test_error_handling(self, detector_wrapper, mock_detector):
        """Test error handling in detector wrapper."""
        await detector_wrapper.initialize()
        
        # Simulate processing error
        mock_detector.process_frame.side_effect = Exception("Processing failed")
        
        frame_data = {"frame_id": 1, "frame_path": "/frames/frame_001.jpg"}
        result = await detector_wrapper.process_frame(frame_data)
        
        assert result is not None
        assert result["error"] is True
        assert "Processing failed" in result["error_message"]
        assert detector_wrapper.error_count == 1
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self, detector_wrapper, mock_detector):
        """Test timeout handling for slow detectors."""
        await detector_wrapper.initialize()
        
        # Simulate slow processing
        async def slow_process(*args):
            await asyncio.sleep(5)
            return {"detected": True}
        
        mock_detector.process_frame = slow_process
        detector_wrapper.timeout = 1.0  # 1 second timeout
        
        frame_data = {"frame_id": 1, "frame_path": "/frames/frame_001.jpg"}
        result = await detector_wrapper.process_frame(frame_data)
        
        assert result["error"] is True
        assert "timeout" in result["error_message"].lower()
    
    @pytest.mark.asyncio
    async def test_detector_metrics(self, detector_wrapper, mock_detector):
        """Test detector performance metrics collection."""
        await detector_wrapper.initialize()
        
        # Process multiple frames
        for i in range(10):
            frame_data = {"frame_id": i, "frame_path": f"/frames/frame_{i:03d}.jpg"}
            await detector_wrapper.process_frame(frame_data)
        
        # Get metrics
        metrics = detector_wrapper.get_metrics()
        
        assert metrics["total_processed"] == 10
        assert metrics["average_processing_time"] > 0
        assert metrics["success_rate"] == 1.0
        assert metrics["error_count"] == 0
    
    @pytest.mark.asyncio
    async def test_detector_state_management(self, detector_wrapper):
        """Test detector state transitions."""
        # Initial state
        assert detector_wrapper.state == "created"
        
        # Initialize
        await detector_wrapper.initialize()
        assert detector_wrapper.state == "initialized"
        
        # Start processing
        detector_wrapper.start()
        assert detector_wrapper.state == "running"
        
        # Pause
        detector_wrapper.pause()
        assert detector_wrapper.state == "paused"
        
        # Resume
        detector_wrapper.resume()
        assert detector_wrapper.state == "running"
        
        # Stop
        await detector_wrapper.stop()
        assert detector_wrapper.state == "stopped"


class TestQueueManager:
    """Test queue management for detector processing."""
    
    @pytest.fixture
    def queue_manager(self):
        """Create queue manager."""
        return QueueManager(max_size=100)
    
    def test_basic_queue_operations(self, queue_manager):
        """Test basic queue operations."""
        # Add items
        for i in range(10):
            item = {"frame_id": i, "priority": i % 3}
            queue_manager.put(item)
        
        assert queue_manager.size() == 10
        assert not queue_manager.is_empty()
        assert not queue_manager.is_full()
        
        # Get items
        items = []
        for _ in range(5):
            item = queue_manager.get()
            items.append(item)
        
        assert len(items) == 5
        assert queue_manager.size() == 5
    
    def test_priority_queue(self, queue_manager):
        """Test priority queue functionality."""
        # Enable priority mode
        queue_manager.enable_priority_mode()
        
        # Add items with different priorities
        queue_manager.put({"id": 1, "data": "low"}, priority=3)
        queue_manager.put({"id": 2, "data": "high"}, priority=1)
        queue_manager.put({"id": 3, "data": "medium"}, priority=2)
        
        # Should get high priority first
        item = queue_manager.get()
        assert item["id"] == 2
        assert item["data"] == "high"
    
    def test_queue_overflow_handling(self, queue_manager):
        """Test queue overflow handling."""
        # Fill queue
        for i in range(100):
            queue_manager.put({"id": i})
        
        assert queue_manager.is_full()
        
        # Try to add more (with overflow policy)
        queue_manager.set_overflow_policy("drop_oldest")
        queue_manager.put({"id": 100})
        
        # Oldest item should be dropped
        items = []
        while not queue_manager.is_empty():
            items.append(queue_manager.get())
        
        assert len(items) == 100
        assert items[0]["id"] == 1  # First item is now id=1, not id=0
        assert items[-1]["id"] == 100
    
    def test_batch_operations(self, queue_manager):
        """Test batch queue operations."""
        # Add batch
        batch = [{"id": i} for i in range(20)]
        queue_manager.put_batch(batch)
        
        assert queue_manager.size() == 20
        
        # Get batch
        retrieved_batch = queue_manager.get_batch(size=10)
        
        assert len(retrieved_batch) == 10
        assert queue_manager.size() == 10
    
    def test_queue_persistence(self, queue_manager):
        """Test queue persistence to disk."""
        with tempfile.TemporaryDirectory() as temp_dir:
            persist_file = os.path.join(temp_dir, "queue.json")
            
            # Add items
            for i in range(5):
                queue_manager.put({"id": i, "data": f"item_{i}"})
            
            # Save to disk
            queue_manager.save_to_disk(persist_file)
            assert os.path.exists(persist_file)
            
            # Create new queue and load
            new_queue = QueueManager()
            new_queue.load_from_disk(persist_file)
            
            assert new_queue.size() == 5
            item = new_queue.get()
            assert item["id"] == 0
    
    def test_concurrent_queue_access(self, queue_manager):
        """Test thread-safe queue operations."""
        errors = []
        
        def producer(start_id):
            try:
                for i in range(10):
                    queue_manager.put({"id": start_id + i})
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)
        
        def consumer(result_list):
            try:
                for _ in range(10):
                    item = queue_manager.get(timeout=1)
                    if item:
                        result_list.append(item)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)
        
        # Run producers and consumers concurrently
        results = []
        threads = []
        
        # Start producers
        for i in range(3):
            t = threading.Thread(target=producer, args=(i * 10,))
            threads.append(t)
            t.start()
        
        # Start consumers
        for _ in range(3):
            t = threading.Thread(target=consumer, args=(results,))
            threads.append(t)
            t.start()
        
        # Wait for completion
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        assert len(results) == 30


class TestBatchProcessor:
    """Test batch processing functionality."""
    
    @pytest.fixture
    def batch_processor(self):
        """Create batch processor."""
        return BatchProcessor(batch_size=10, timeout=5.0)
    
    @pytest.fixture
    def mock_detector(self):
        """Create mock detector for batch processing."""
        detector = MagicMock()
        detector.process_batch = AsyncMock(return_value=[
            {"frame_id": i, "detected": True, "confidence": 0.9}
            for i in range(10)
        ])
        return detector
    
    @pytest.mark.asyncio
    async def test_batch_accumulation(self, batch_processor):
        """Test accumulating frames into batches."""
        # Add frames
        for i in range(25):
            frame = {"frame_id": i, "path": f"/frame_{i}.jpg"}
            batch_processor.add_frame(frame)
        
        # Should have 2 complete batches and 5 pending
        batches = batch_processor.get_complete_batches()
        assert len(batches) == 2
        assert len(batches[0]) == 10
        assert len(batches[1]) == 10
        assert batch_processor.pending_count() == 5
    
    @pytest.mark.asyncio
    async def test_batch_processing(self, batch_processor, mock_detector):
        """Test processing batches with detector."""
        # Add frames
        frames = [{"frame_id": i, "path": f"/frame_{i}.jpg"} for i in range(10)]
        for frame in frames:
            batch_processor.add_frame(frame)
        
        # Process batch
        results = await batch_processor.process_batch(mock_detector)
        
        assert len(results) == 10
        assert all(r["detected"] is True for r in results)
        mock_detector.process_batch.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_batch_timeout(self, batch_processor, mock_detector):
        """Test batch timeout for incomplete batches."""
        batch_processor.timeout = 0.1  # 100ms timeout
        
        # Add partial batch
        for i in range(5):
            batch_processor.add_frame({"frame_id": i})
        
        # Wait for timeout
        await asyncio.sleep(0.2)
        
        # Should process partial batch
        results = await batch_processor.process_timeout_batches(mock_detector)
        
        assert len(results) == 5
    
    @pytest.mark.asyncio
    async def test_batch_error_handling(self, batch_processor, mock_detector):
        """Test error handling in batch processing."""
        # Simulate batch processing error
        mock_detector.process_batch.side_effect = Exception("Batch processing failed")
        
        # Add frames
        for i in range(10):
            batch_processor.add_frame({"frame_id": i})
        
        # Process with error
        results = await batch_processor.process_batch(mock_detector)
        
        assert len(results) == 10
        assert all(r.get("error") is True for r in results)
        assert all("Batch processing failed" in r.get("error_message", "") for r in results)
    
    @pytest.mark.asyncio
    async def test_dynamic_batch_sizing(self, batch_processor):
        """Test dynamic batch size adjustment."""
        batch_processor.enable_dynamic_sizing(
            min_size=5,
            max_size=20,
            target_latency=0.1  # 100ms
        )
        
        # Simulate varying processing times
        processing_times = [0.05, 0.15, 0.08, 0.20, 0.10]
        
        for proc_time in processing_times:
            batch_processor.record_processing_time(proc_time)
            new_size = batch_processor.get_optimal_batch_size()
            
            # Batch size should adjust based on latency
            if proc_time > 0.1:
                assert new_size < batch_processor.batch_size
            else:
                assert new_size >= batch_processor.batch_size


class TestResultCache:
    """Test result caching functionality."""
    
    @pytest.fixture
    def result_cache(self):
        """Create result cache."""
        return ResultCache(max_size=1000, ttl_seconds=300)
    
    def test_cache_storage_retrieval(self, result_cache):
        """Test storing and retrieving results from cache."""
        # Store result
        result = {
            "frame_id": 1,
            "detected": True,
            "confidence": 0.95,
            "timestamp": time.time()
        }
        
        cache_key = result_cache.generate_key(
            detector="TestDetector",
            frame_id=1,
            version="1.0.0"
        )
        
        result_cache.store(cache_key, result)
        
        # Retrieve result
        cached_result = result_cache.get(cache_key)
        assert cached_result is not None
        assert cached_result["detected"] is True
        assert cached_result["confidence"] == 0.95
    
    def test_cache_expiration(self, result_cache):
        """Test cache entry expiration."""
        result_cache.ttl_seconds = 0.1  # 100ms TTL
        
        # Store result
        cache_key = "test_key"
        result_cache.store(cache_key, {"data": "test"})
        
        # Should exist immediately
        assert result_cache.get(cache_key) is not None
        
        # Wait for expiration
        time.sleep(0.2)
        
        # Should be expired
        assert result_cache.get(cache_key) is None
    
    def test_cache_size_limit(self, result_cache):
        """Test cache size limiting."""
        result_cache.max_size = 10
        
        # Fill cache beyond limit
        for i in range(15):
            key = f"key_{i}"
            result_cache.store(key, {"id": i})
        
        # Cache size should not exceed limit
        assert result_cache.size() == 10
        
        # Oldest entries should be evicted
        assert result_cache.get("key_0") is None
        assert result_cache.get("key_14") is not None
    
    def test_cache_invalidation(self, result_cache):
        """Test cache invalidation."""
        # Store multiple results
        for i in range(5):
            key = f"TestDetector_frame_{i}"
            result_cache.store(key, {"frame_id": i})
        
        # Invalidate specific detector results
        result_cache.invalidate_pattern("TestDetector_*")
        
        # All TestDetector results should be removed
        for i in range(5):
            key = f"TestDetector_frame_{i}"
            assert result_cache.get(key) is None
    
    def test_cache_statistics(self, result_cache):
        """Test cache statistics tracking."""
        # Perform cache operations
        for i in range(10):
            key = f"key_{i}"
            result_cache.store(key, {"id": i})
        
        # Some hits
        for i in range(5):
            result_cache.get(f"key_{i}")
        
        # Some misses
        for i in range(10, 15):
            result_cache.get(f"key_{i}")
        
        # Get statistics
        stats = result_cache.get_statistics()
        
        assert stats["total_requests"] == 10
        assert stats["hits"] == 5
        assert stats["misses"] == 5
        assert stats["hit_rate"] == 0.5
        assert stats["size"] == 10
    
    def test_cache_persistence(self, result_cache):
        """Test persisting cache to disk."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_file = os.path.join(temp_dir, "cache.json")
            
            # Store data
            for i in range(5):
                result_cache.store(f"key_{i}", {"id": i, "data": f"value_{i}"})
            
            # Save to disk
            result_cache.save_to_disk(cache_file)
            
            # Load into new cache
            new_cache = ResultCache()
            new_cache.load_from_disk(cache_file)
            
            # Verify data
            for i in range(5):
                result = new_cache.get(f"key_{i}")
                assert result is not None
                assert result["id"] == i


class TestDetectorOrchestration:
    """Test orchestration of multiple detectors."""
    
    @pytest.fixture
    def detector_orchestrator(self):
        """Create detector orchestrator."""
        from CAMF.services.detector_framework.main import DetectorOrchestrator
        return DetectorOrchestrator()
    
    @pytest.fixture
    def mock_detectors(self):
        """Create multiple mock detectors."""
        detectors = []
        for i in range(3):
            detector = MagicMock()
            detector.name = f"Detector{i}"
            detector.process_frame = AsyncMock(return_value={
                "detected": i % 2 == 0,  # Even detectors detect
                "confidence": 0.8 + i * 0.05
            })
            detectors.append(detector)
        return detectors
    
    @pytest.mark.asyncio
    async def test_parallel_detector_processing(self, detector_orchestrator, mock_detectors):
        """Test processing frame with multiple detectors in parallel."""
        # Register detectors
        for detector in mock_detectors:
            detector_orchestrator.register_detector(detector)
        
        # Process frame
        frame_data = {"frame_id": 1, "path": "/frame_001.jpg"}
        results = await detector_orchestrator.process_frame_all_detectors(frame_data)
        
        assert len(results) == 3
        assert results["Detector0"]["detected"] is True
        assert results["Detector1"]["detected"] is False
        assert results["Detector2"]["detected"] is True
    
    @pytest.mark.asyncio
    async def test_detector_dependencies(self, detector_orchestrator, mock_detectors):
        """Test handling detector dependencies."""
        # Set dependencies
        detector_orchestrator.set_dependency("Detector2", ["Detector0", "Detector1"])
        
        # Register detectors
        for detector in mock_detectors:
            detector_orchestrator.register_detector(detector)
        
        # Process should respect dependencies
        frame_data = {"frame_id": 1}
        results = await detector_orchestrator.process_frame_all_detectors(frame_data)
        
        # Verify execution order through mock calls
        assert mock_detectors[0].process_frame.called
        assert mock_detectors[1].process_frame.called
        assert mock_detectors[2].process_frame.called
    
    @pytest.mark.asyncio
    async def test_detector_result_aggregation(self, detector_orchestrator, mock_detectors):
        """Test aggregating results from multiple detectors."""
        # Register detectors
        for detector in mock_detectors:
            detector_orchestrator.register_detector(detector)
        
        # Set aggregation rules
        detector_orchestrator.set_aggregation_rule(
            rule="majority_vote",
            min_confidence=0.8
        )
        
        # Process and aggregate
        frame_data = {"frame_id": 1}
        individual_results = await detector_orchestrator.process_frame_all_detectors(frame_data)
        aggregated = detector_orchestrator.aggregate_results(individual_results)
        
        # Majority (2/3) detected
        assert aggregated["final_detection"] is True
        assert aggregated["consensus_confidence"] > 0.8
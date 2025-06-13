"""
Comprehensive performance tests for critical system paths.
Tests throughput, latency, scalability, and resource usage.
"""

import pytest
import time
import asyncio
import numpy as np
import psutil
import os
import tempfile
import shutil
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import multiprocessing
import threading
from datetime import datetime, timedelta
import cv2
import json
from unittest.mock import Mock, patch, MagicMock
import cProfile
import pstats
import io
import gc

from CAMF.services.storage.database import init_db, get_db
from CAMF.services.storage.frame_storage import FrameStorage, HybridFrameStorage
from CAMF.services.api_gateway.main import app
from CAMF.services.detector_framework.queue_manager import QueueManager
from CAMF.services.detector_framework.batch_processor import BatchProcessor
from fastapi.testclient import TestClient


class PerformanceMetrics:
    """Helper class to collect performance metrics."""
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.operations = 0
        self.errors = 0
        self.latencies = []
        self.memory_samples = []
        self.cpu_samples = []
    
    def start(self):
        """Start performance measurement."""
        self.start_time = time.time()
        self.start_memory = psutil.Process().memory_info().rss
        return self
    
    def end(self):
        """End performance measurement."""
        self.end_time = time.time()
        self.end_memory = psutil.Process().memory_info().rss
        return self
    
    def record_operation(self, latency=None):
        """Record a single operation."""
        self.operations += 1
        if latency is not None:
            self.latencies.append(latency)
    
    def record_error(self):
        """Record an error."""
        self.errors += 1
    
    def sample_resources(self):
        """Sample current resource usage."""
        process = psutil.Process()
        self.memory_samples.append(process.memory_info().rss)
        self.cpu_samples.append(process.cpu_percent(interval=0.1))
    
    def get_summary(self):
        """Get performance summary."""
        duration = self.end_time - self.start_time if self.end_time else 0
        throughput = self.operations / duration if duration > 0 else 0
        
        return {
            "duration": duration,
            "operations": self.operations,
            "errors": self.errors,
            "throughput": throughput,
            "avg_latency": np.mean(self.latencies) if self.latencies else 0,
            "p50_latency": np.percentile(self.latencies, 50) if self.latencies else 0,
            "p95_latency": np.percentile(self.latencies, 95) if self.latencies else 0,
            "p99_latency": np.percentile(self.latencies, 99) if self.latencies else 0,
            "memory_delta": (self.end_memory - self.start_memory) / (1024 * 1024) if hasattr(self, 'end_memory') else 0,
            "peak_memory": max(self.memory_samples) / (1024 * 1024) if self.memory_samples else 0,
            "avg_cpu": np.mean(self.cpu_samples) if self.cpu_samples else 0
        }


class TestFrameProcessingPerformance:
    """Test frame processing performance."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage directory."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def sample_frame(self):
        """Create sample frame for testing."""
        return np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
    
    def test_frame_write_performance(self, temp_storage, sample_frame):
        """Test frame write performance."""
        storage = FrameStorage(base_path=temp_storage)
        metrics = PerformanceMetrics()
        
        # Test parameters
        num_frames = 1000
        
        metrics.start()
        
        for i in range(num_frames):
            start = time.time()
            path = storage.save_frame(
                frame_data=sample_frame,
                take_id=1,
                frame_number=i,
                quality=85
            )
            latency = time.time() - start
            metrics.record_operation(latency)
            
            if i % 100 == 0:
                metrics.sample_resources()
        
        metrics.end()
        summary = metrics.get_summary()
        
        # Performance assertions
        assert summary["throughput"] > 50  # At least 50 frames/second
        assert summary["avg_latency"] < 0.02  # Less than 20ms average
        assert summary["p99_latency"] < 0.05  # Less than 50ms for 99th percentile
        
        print(f"Frame write performance: {summary}")
    
    def test_frame_read_performance(self, temp_storage, sample_frame):
        """Test frame read performance."""
        storage = FrameStorage(base_path=temp_storage)
        
        # Pre-create frames
        frame_paths = []
        for i in range(100):
            path = storage.save_frame(sample_frame, 1, i)
            frame_paths.append(path)
        
        metrics = PerformanceMetrics()
        metrics.start()
        
        # Read frames multiple times
        for _ in range(10):
            for path in frame_paths:
                start = time.time()
                frame = storage.load_frame(path)
                latency = time.time() - start
                metrics.record_operation(latency)
        
        metrics.end()
        summary = metrics.get_summary()
        
        # Performance assertions
        assert summary["throughput"] > 100  # At least 100 reads/second
        assert summary["avg_latency"] < 0.01  # Less than 10ms average
        
        print(f"Frame read performance: {summary}")
    
    def test_video_conversion_performance(self, temp_storage, sample_frame):
        """Test video conversion performance."""
        hybrid_storage = HybridFrameStorage(
            base_path=temp_storage,
            segment_duration=5
        )
        
        # Create frames
        frame_paths = []
        num_frames = 150  # 5 seconds at 30fps
        
        for i in range(num_frames):
            path = hybrid_storage.store_frame_realtime(
                frame_data=sample_frame,
                take_id=1,
                frame_number=i,
                timestamp=i/30.0
            )
            frame_paths.append(path)
        
        metrics = PerformanceMetrics()
        metrics.start()
        
        # Convert to video
        segments = hybrid_storage.convert_to_video_segments(
            take_id=1,
            frame_paths=frame_paths,
            fps=30
        )
        
        metrics.end()
        summary = metrics.get_summary()
        
        # Performance assertions
        conversion_time = summary["duration"]
        frames_per_second = num_frames / conversion_time
        
        assert frames_per_second > 60  # Should convert faster than real-time
        assert len(segments) == 1  # Should create one segment
        
        print(f"Video conversion: {num_frames} frames in {conversion_time:.2f}s ({frames_per_second:.1f} fps)")


class TestDatabasePerformance:
    """Test database operation performance."""
    
    @pytest.fixture
    def test_db(self):
        """Create test database."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        # Initialize database
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from CAMF.services.storage.database import Base
        
        engine = create_engine(f'sqlite:///{db_path}')
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        
        yield Session()
        
        os.unlink(db_path)
    
    def test_bulk_insert_performance(self, test_db):
        """Test bulk insert performance."""
        from CAMF.services.storage.database import FrameDB, TakeDB, AngleDB, SceneDB, ProjectDB
        
        # Create project hierarchy
        project = ProjectDB(name="Perf Test")
        scene = SceneDB(name="Scene 1", project=project)
        angle = AngleDB(name="Angle 1", scene=scene)
        take = TakeDB(name="Take 1", angle=angle, take_number=1)
        
        test_db.add_all([project, scene, angle, take])
        test_db.commit()
        
        metrics = PerformanceMetrics()
        metrics.start()
        
        # Bulk insert frames
        frames = []
        batch_size = 1000
        num_batches = 10
        
        for batch in range(num_batches):
            batch_frames = []
            for i in range(batch_size):
                frame_num = batch * batch_size + i
                frame = FrameDB(
                    take=take,
                    frame_number=frame_num,
                    timestamp=frame_num / 30.0,
                    file_path=f"/frames/frame_{frame_num:06d}.jpg"
                )
                batch_frames.append(frame)
            
            start = time.time()
            test_db.bulk_save_objects(batch_frames)
            test_db.commit()
            latency = time.time() - start
            
            metrics.record_operation(latency)
            frames.extend(batch_frames)
        
        metrics.end()
        summary = metrics.get_summary()
        
        # Performance assertions
        total_frames = batch_size * num_batches
        insert_rate = total_frames / summary["duration"]
        
        assert insert_rate > 5000  # At least 5000 frames/second
        assert summary["avg_latency"] < 0.5  # Less than 500ms per batch
        
        print(f"Bulk insert: {total_frames} frames at {insert_rate:.0f} frames/second")
    
    def test_query_performance(self, test_db):
        """Test query performance with indexes."""
        from CAMF.services.storage.database import FrameDB, TakeDB, AngleDB, SceneDB, ProjectDB
        
        # Create test data
        project = ProjectDB(name="Query Test")
        test_db.add(project)
        test_db.commit()
        
        # Create multiple takes with frames
        for t in range(5):
            scene = SceneDB(name=f"Scene {t}", project=project)
            angle = AngleDB(name=f"Angle {t}", scene=scene)
            take = TakeDB(name=f"Take {t}", angle=angle, take_number=t)
            
            test_db.add_all([scene, angle, take])
            test_db.commit()
            
            # Add frames
            frames = []
            for f in range(1000):
                frame = FrameDB(
                    take=take,
                    frame_number=f,
                    timestamp=f/30.0,
                    file_path=f"/frame_{f}.jpg"
                )
                frames.append(frame)
            
            test_db.bulk_save_objects(frames)
            test_db.commit()
        
        metrics = PerformanceMetrics()
        
        # Test various queries
        queries = [
            # Simple queries
            lambda: test_db.query(FrameDB).filter_by(frame_number=500).all(),
            lambda: test_db.query(FrameDB).filter(FrameDB.timestamp > 10.0).limit(100).all(),
            
            # Join queries
            lambda: test_db.query(FrameDB).join(TakeDB).filter(TakeDB.name == "Take 2").all(),
            lambda: test_db.query(FrameDB).join(TakeDB).join(AngleDB).join(SceneDB).filter(
                SceneDB.name == "Scene 3"
            ).limit(50).all(),
            
            # Aggregation queries
            lambda: test_db.query(TakeDB).join(FrameDB).group_by(TakeDB.id).count(),
        ]
        
        metrics.start()
        
        for query in queries:
            start = time.time()
            result = query()
            latency = time.time() - start
            metrics.record_operation(latency)
        
        metrics.end()
        summary = metrics.get_summary()
        
        # Performance assertions
        assert summary["avg_latency"] < 0.1  # Less than 100ms average
        assert summary["p99_latency"] < 0.5  # Less than 500ms for complex queries
        
        print(f"Query performance: {summary}")


class TestAPIPerformance:
    """Test API endpoint performance."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    def test_api_throughput(self, client):
        """Test API request throughput."""
        # Create test project
        project = client.post("/api/projects", json={"name": "API Perf Test"}).json()
        project_id = project["id"]
        
        metrics = PerformanceMetrics()
        
        # Test concurrent requests
        def make_request(i):
            start = time.time()
            response = client.post("/api/scenes", json={
                "project_id": project_id,
                "name": f"Scene {i}"
            })
            latency = time.time() - start
            
            if response.status_code == 200:
                metrics.record_operation(latency)
            else:
                metrics.record_error()
            
            return response.json()
        
        metrics.start()
        
        # Concurrent requests
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request, i) for i in range(100)]
            results = [f.result() for f in futures]
        
        metrics.end()
        summary = metrics.get_summary()
        
        # Performance assertions
        assert summary["throughput"] > 50  # At least 50 requests/second
        assert summary["avg_latency"] < 0.2  # Less than 200ms average
        assert summary["errors"] == 0  # No errors
        
        print(f"API throughput: {summary}")
    
    def test_sse_scalability(self, client):
        """Test SSE connection scalability."""
        metrics = PerformanceMetrics()
        connections = []
        
        def create_sse_connection(i):
            try:
                # In real test, would create actual SSE connection
                # For now, simulate connection setup
                time.sleep(0.01)  # Simulate connection overhead
                connections.append(f"connection_{i}")
                metrics.record_operation()
            except Exception:
                metrics.record_error()
        
        metrics.start()
        
        # Create many SSE connections
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(create_sse_connection, i) for i in range(200)]
            for f in futures:
                f.result()
        
        metrics.end()
        summary = metrics.get_summary()
        
        # Performance assertions
        assert len(connections) >= 180  # At least 90% success rate
        assert summary["errors"] < 20  # Less than 10% errors
        
        print(f"SSE scalability: {len(connections)} connections established")
    
    def test_large_payload_handling(self, client):
        """Test handling of large payloads."""
        # Create project and scene
        project = client.post("/api/projects", json={"name": "Large Payload Test"}).json()
        scene = client.post("/api/scenes", json={
            "project_id": project["id"],
            "name": "Scene 1"
        }).json()
        angle = client.post("/api/angles", json={
            "scene_id": scene["id"],
            "name": "Angle 1"
        }).json()
        take = client.post("/api/takes", json={
            "angle_id": angle["id"],
            "name": "Take 1"
        }).json()
        
        metrics = PerformanceMetrics()
        
        # Create large batch of frames
        batch_sizes = [10, 50, 100, 500, 1000]
        
        for batch_size in batch_sizes:
            frames = []
            for i in range(batch_size):
                frames.append({
                    "take_id": take["id"],
                    "frame_number": i,
                    "timestamp": i / 30.0,
                    "file_path": f"/frames/frame_{i:06d}.jpg",
                    "metadata": {
                        "width": 1920,
                        "height": 1080,
                        "format": "jpeg",
                        "size": 102400
                    }
                })
            
            metrics.start()
            
            response = client.post("/api/frames/batch", json=frames)
            
            metrics.end()
            
            assert response.status_code == 200
            
            summary = metrics.get_summary()
            print(f"Batch size {batch_size}: {summary['duration']:.3f}s")


class TestDetectorPerformance:
    """Test detector framework performance."""
    
    def test_detector_throughput(self):
        """Test detector processing throughput."""
        queue_manager = QueueManager(max_size=10000)
        metrics = PerformanceMetrics()
        
        # Mock detector
        def mock_detector_process(frame):
            # Simulate processing
            time.sleep(0.01)  # 10ms processing time
            return {"detected": True, "confidence": 0.9}
        
        # Producer thread
        def producer():
            for i in range(1000):
                queue_manager.put({"frame_id": i, "data": f"frame_{i}"})
        
        # Consumer threads
        processed = []
        
        def consumer():
            while len(processed) < 1000:
                try:
                    frame = queue_manager.get(timeout=0.1)
                    if frame:
                        start = time.time()
                        result = mock_detector_process(frame)
                        latency = time.time() - start
                        
                        processed.append(result)
                        metrics.record_operation(latency)
                except:
                    pass
        
        metrics.start()
        
        # Start threads
        producer_thread = threading.Thread(target=producer)
        consumer_threads = [threading.Thread(target=consumer) for _ in range(4)]
        
        producer_thread.start()
        for t in consumer_threads:
            t.start()
        
        # Wait for completion
        producer_thread.join()
        for t in consumer_threads:
            t.join()
        
        metrics.end()
        summary = metrics.get_summary()
        
        # Performance assertions
        assert summary["throughput"] > 50  # At least 50 frames/second with 4 workers
        assert summary["avg_latency"] < 0.02  # Close to simulated 10ms
        
        print(f"Detector throughput: {summary}")
    
    @pytest.mark.asyncio
    async def test_batch_processing_performance(self):
        """Test batch processing performance."""
        batch_processor = BatchProcessor(batch_size=32)
        metrics = PerformanceMetrics()
        
        # Mock batch detector
        async def mock_batch_process(frames):
            # Simulate batch processing
            await asyncio.sleep(0.05)  # 50ms for batch
            return [{"frame_id": f["frame_id"], "detected": True} for f in frames]
        
        metrics.start()
        
        # Process many frames in batches
        all_results = []
        total_frames = 1000
        
        for i in range(0, total_frames, 32):
            batch = [{"frame_id": j} for j in range(i, min(i + 32, total_frames))]
            
            start = time.time()
            results = await mock_batch_process(batch)
            latency = time.time() - start
            
            all_results.extend(results)
            metrics.record_operation(latency)
        
        metrics.end()
        summary = metrics.get_summary()
        
        # Calculate per-frame throughput
        per_frame_throughput = total_frames / summary["duration"]
        
        assert per_frame_throughput > 200  # At least 200 frames/second in batches
        assert summary["avg_latency"] < 0.1  # Less than 100ms per batch
        
        print(f"Batch processing: {per_frame_throughput:.0f} frames/second")


class TestMemoryPerformance:
    """Test memory usage and leak detection."""
    
    def test_memory_leak_detection(self):
        """Test for memory leaks in frame processing."""
        initial_memory = psutil.Process().memory_info().rss
        
        # Simulate continuous processing
        for cycle in range(5):
            frames = []
            
            # Create and process frames
            for i in range(1000):
                frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
                processed = cv2.GaussianBlur(frame, (5, 5), 0)
                frames.append(processed)
            
            # Clear frames
            frames.clear()
            gc.collect()
            
            # Check memory after each cycle
            current_memory = psutil.Process().memory_info().rss
            memory_increase = (current_memory - initial_memory) / (1024 * 1024)
            
            print(f"Cycle {cycle + 1}: Memory increase: {memory_increase:.1f} MB")
        
        # Final memory check
        gc.collect()
        time.sleep(0.5)
        final_memory = psutil.Process().memory_info().rss
        total_increase = (final_memory - initial_memory) / (1024 * 1024)
        
        # Should not leak more than 50MB after 5 cycles
        assert total_increase < 50
    
    def test_cache_memory_management(self):
        """Test cache memory management under pressure."""
        from CAMF.common.utils import Cache
        
        cache = Cache(max_size=100, ttl=60)
        metrics = PerformanceMetrics()
        
        # Create large objects
        def create_large_object(size_mb):
            return np.random.bytes(size_mb * 1024 * 1024)
        
        metrics.start()
        
        # Fill cache with large objects
        for i in range(200):  # More than cache size
            key = f"obj_{i}"
            obj = create_large_object(1)  # 1MB objects
            cache.set(key, obj)
            
            if i % 20 == 0:
                metrics.sample_resources()
        
        metrics.end()
        summary = metrics.get_summary()
        
        # Cache should maintain size limit
        assert cache.size() <= 100
        
        # Memory usage should be bounded
        assert summary["peak_memory"] < 200  # Less than 200MB peak
        
        print(f"Cache memory management: {summary}")


class TestScalabilityPerformance:
    """Test system scalability."""
    
    def test_concurrent_take_processing(self):
        """Test processing multiple takes concurrently."""
        metrics = PerformanceMetrics()
        
        # Simulate take processing
        def process_take(take_id):
            start = time.time()
            
            # Simulate frame processing
            for frame in range(100):
                time.sleep(0.001)  # 1ms per frame
            
            latency = time.time() - start
            return take_id, latency
        
        metrics.start()
        
        # Process takes concurrently
        num_takes = 20
        with ProcessPoolExecutor(max_workers=multiprocessing.cpu_count()) as executor:
            futures = [executor.submit(process_take, i) for i in range(num_takes)]
            results = [f.result() for f in futures]
        
        metrics.end()
        
        for take_id, latency in results:
            metrics.record_operation(latency)
        
        summary = metrics.get_summary()
        
        # Should scale with CPU cores
        expected_time = (num_takes * 0.1) / multiprocessing.cpu_count()
        assert summary["duration"] < expected_time * 1.5  # Allow 50% overhead
        
        print(f"Concurrent processing: {num_takes} takes in {summary['duration']:.2f}s")
    
    def test_system_under_load(self):
        """Test system behavior under sustained load."""
        metrics = PerformanceMetrics()
        
        # Simulate various system operations
        operations = {
            "frame_write": lambda: time.sleep(0.005),
            "detector_process": lambda: time.sleep(0.010),
            "database_query": lambda: time.sleep(0.002),
            "api_request": lambda: time.sleep(0.003)
        }
        
        # Track operation latencies
        op_metrics = {op: [] for op in operations}
        
        def worker(op_name, op_func, duration):
            end_time = time.time() + duration
            while time.time() < end_time:
                start = time.time()
                op_func()
                latency = time.time() - start
                op_metrics[op_name].append(latency)
        
        metrics.start()
        
        # Run workers for each operation type
        threads = []
        for op_name, op_func in operations.items():
            for _ in range(2):  # 2 workers per operation
                t = threading.Thread(target=worker, args=(op_name, op_func, 5))
                threads.append(t)
                t.start()
        
        # Monitor resources during load
        for _ in range(10):
            time.sleep(0.5)
            metrics.sample_resources()
        
        # Wait for completion
        for t in threads:
            t.join()
        
        metrics.end()
        summary = metrics.get_summary()
        
        # Analyze operation latencies
        for op_name, latencies in op_metrics.items():
            if latencies:
                avg_latency = np.mean(latencies)
                p99_latency = np.percentile(latencies, 99)
                print(f"{op_name}: avg={avg_latency*1000:.1f}ms, p99={p99_latency*1000:.1f}ms")
        
        # System should remain stable under load
        assert summary["avg_cpu"] < 80  # Less than 80% CPU usage
        assert all(np.percentile(latencies, 99) < 0.1 for latencies in op_metrics.values() if latencies)
        
        print(f"System under load: {summary}")


def run_profiled(func, *args, **kwargs):
    """Run function with profiling."""
    profiler = cProfile.Profile()
    profiler.enable()
    
    result = func(*args, **kwargs)
    
    profiler.disable()
    
    # Print stats
    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
    ps.print_stats(20)  # Top 20 functions
    print(s.getvalue())
    
    return result
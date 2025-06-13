"""
Performance benchmarking tools for detector evaluation.
Measures key metrics like time-to-detection, throughput, and resource usage.
"""

import time
import psutil
import threading
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
import statistics

from CAMF.common.models import DetectorResult, ErrorConfidence


@dataclass
class FrameMetrics:
    """Metrics for a single frame processing."""
    frame_id: int
    start_time: float
    end_time: float
    processing_time: float
    memory_before: float
    memory_after: float
    cpu_percent: float
    errors_detected: int
    detector_results: List[Dict[str, Any]]


@dataclass
class DetectorMetrics:
    """Aggregated metrics for a detector."""
    detector_name: str
    total_frames: int = 0
    total_processing_time: float = 0.0
    min_processing_time: float = float('inf')
    max_processing_time: float = 0.0
    avg_processing_time: float = 0.0
    std_processing_time: float = 0.0
    
    total_errors_found: int = 0
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    
    avg_memory_usage: float = 0.0
    peak_memory_usage: float = 0.0
    avg_cpu_usage: float = 0.0
    
    frame_metrics: List[FrameMetrics] = field(default_factory=list)
    processing_times: List[float] = field(default_factory=list)


@dataclass
class BenchmarkSession:
    """Complete benchmark session data."""
    session_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    
    # Test parameters
    frame_count: int = 0
    frame_rate: float = 1.0
    image_quality: int = 90
    detector_count: int = 0
    
    # Aggregated results
    total_time: float = 0.0
    throughput: float = 0.0  # frames per second
    avg_latency: float = 0.0  # time from frame capture to detection
    
    detector_metrics: Dict[str, DetectorMetrics] = field(default_factory=dict)
    system_metrics: Dict[str, Any] = field(default_factory=dict)


class PerformanceBenchmark:
    """Performance benchmarking system for detectors."""
    
    def __init__(self, output_dir: Optional[str] = None):
        """Initialize benchmarking system."""
        self.output_dir = Path(output_dir) if output_dir else Path("benchmark_results")
        self.output_dir.mkdir(exist_ok=True)
        
        self.current_session: Optional[BenchmarkSession] = None
        self.is_running = False
        self._lock = threading.Lock()
        
        # System monitoring
        self.process = psutil.Process()
        
    def start_session(self, frame_count: int, frame_rate: float, 
                     image_quality: int, detector_count: int) -> str:
        """Start a new benchmark session."""
        with self._lock:
            if self.is_running:
                raise RuntimeError("Benchmark session already in progress")
            
            session_id = f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.current_session = BenchmarkSession(
                session_id=session_id,
                start_time=datetime.now(),
                frame_count=frame_count,
                frame_rate=frame_rate,
                image_quality=image_quality,
                detector_count=detector_count
            )
            
            self.is_running = True
            
            # Record initial system state
            self.current_session.system_metrics['initial'] = self._get_system_metrics()
            
            return session_id
    
    def record_frame_start(self, frame_id: int) -> Dict[str, Any]:
        """Record start of frame processing."""
        if not self.is_running:
            return {}
        
        return {
            'frame_id': frame_id,
            'start_time': time.time(),
            'memory_before': self.process.memory_info().rss / 1024 / 1024,  # MB
            'cpu_before': self.process.cpu_percent(interval=0.1)
        }
    
    def record_frame_end(self, frame_start: Dict[str, Any], 
                        detector_results: Dict[str, List[DetectorResult]]):
        """Record end of frame processing."""
        if not self.is_running or not frame_start:
            return
        
        end_time = time.time()
        processing_time = end_time - frame_start['start_time']
        
        # Create frame metrics
        frame_metrics = FrameMetrics(
            frame_id=frame_start['frame_id'],
            start_time=frame_start['start_time'],
            end_time=end_time,
            processing_time=processing_time,
            memory_before=frame_start['memory_before'],
            memory_after=self.process.memory_info().rss / 1024 / 1024,
            cpu_percent=self.process.cpu_percent(interval=0.1),
            errors_detected=sum(len(results) for results in detector_results.values()),
            detector_results=[
                {
                    'detector': detector_name,
                    'results': [r.model_dump() for r in results]
                }
                for detector_name, results in detector_results.items()
            ]
        )
        
        # Update detector metrics
        with self._lock:
            for detector_name, results in detector_results.items():
                if detector_name not in self.current_session.detector_metrics:
                    self.current_session.detector_metrics[detector_name] = DetectorMetrics(
                        detector_name=detector_name
                    )
                
                metrics = self.current_session.detector_metrics[detector_name]
                metrics.total_frames += 1
                metrics.total_processing_time += processing_time
                metrics.processing_times.append(processing_time)
                metrics.min_processing_time = min(metrics.min_processing_time, processing_time)
                metrics.max_processing_time = max(metrics.max_processing_time, processing_time)
                
                # Count errors
                error_count = len([r for r in results if r.confidence != ErrorConfidence.NO_ERROR])
                metrics.total_errors_found += error_count
                
                # Memory and CPU
                metrics.peak_memory_usage = max(metrics.peak_memory_usage, frame_metrics.memory_after)
                
                metrics.frame_metrics.append(frame_metrics)
    
    def record_false_positive(self, detector_name: str):
        """Record a false positive for a detector."""
        if not self.is_running:
            return
        
        with self._lock:
            if detector_name in self.current_session.detector_metrics:
                self.current_session.detector_metrics[detector_name].false_positives += 1
    
    def record_true_positive(self, detector_name: str):
        """Record a true positive for a detector."""
        if not self.is_running:
            return
        
        with self._lock:
            if detector_name in self.current_session.detector_metrics:
                self.current_session.detector_metrics[detector_name].true_positives += 1
    
    def end_session(self) -> Dict[str, Any]:
        """End benchmark session and calculate final metrics."""
        if not self.is_running:
            return {}
        
        with self._lock:
            self.current_session.end_time = datetime.now()
            self.current_session.total_time = (
                self.current_session.end_time - self.current_session.start_time
            ).total_seconds()
            
            # Calculate throughput
            if self.current_session.total_time > 0:
                self.current_session.throughput = (
                    self.current_session.frame_count / self.current_session.total_time
                )
            
            # Calculate detector statistics
            for metrics in self.current_session.detector_metrics.values():
                if metrics.processing_times:
                    metrics.avg_processing_time = statistics.mean(metrics.processing_times)
                    if len(metrics.processing_times) > 1:
                        metrics.std_processing_time = statistics.stdev(metrics.processing_times)
                    
                    # Memory usage
                    memory_usages = [fm.memory_after for fm in metrics.frame_metrics]
                    metrics.avg_memory_usage = statistics.mean(memory_usages)
                    
                    # CPU usage
                    cpu_usages = [fm.cpu_percent for fm in metrics.frame_metrics]
                    metrics.avg_cpu_usage = statistics.mean(cpu_usages)
            
            # Calculate average latency
            all_processing_times = []
            for metrics in self.current_session.detector_metrics.values():
                all_processing_times.extend(metrics.processing_times)
            
            if all_processing_times:
                self.current_session.avg_latency = statistics.mean(all_processing_times)
            
            # Record final system state
            self.current_session.system_metrics['final'] = self._get_system_metrics()
            
            # Save results
            self._save_results()
            
            # Prepare summary
            summary = self._generate_summary()
            
            self.is_running = False
            
            return summary
    
    def _get_system_metrics(self) -> Dict[str, Any]:
        """Get current system metrics."""
        return {
            'timestamp': time.time(),
            'cpu_count': psutil.cpu_count(),
            'cpu_percent': psutil.cpu_percent(interval=1),
            'memory_total': psutil.virtual_memory().total / 1024 / 1024 / 1024,  # GB
            'memory_available': psutil.virtual_memory().available / 1024 / 1024 / 1024,
            'memory_percent': psutil.virtual_memory().percent
        }
    
    def _save_results(self):
        """Save benchmark results to file."""
        if not self.current_session:
            return
        
        output_file = self.output_dir / f"{self.current_session.session_id}.json"
        
        # Convert to serializable format
        data = {
            'session_id': self.current_session.session_id,
            'start_time': self.current_session.start_time.isoformat(),
            'end_time': self.current_session.end_time.isoformat() if self.current_session.end_time else None,
            'parameters': {
                'frame_count': self.current_session.frame_count,
                'frame_rate': self.current_session.frame_rate,
                'image_quality': self.current_session.image_quality,
                'detector_count': self.current_session.detector_count
            },
            'results': {
                'total_time': self.current_session.total_time,
                'throughput': self.current_session.throughput,
                'avg_latency': self.current_session.avg_latency
            },
            'detector_metrics': {
                name: {
                    'total_frames': metrics.total_frames,
                    'total_processing_time': metrics.total_processing_time,
                    'avg_processing_time': metrics.avg_processing_time,
                    'std_processing_time': metrics.std_processing_time,
                    'min_processing_time': metrics.min_processing_time,
                    'max_processing_time': metrics.max_processing_time,
                    'total_errors_found': metrics.total_errors_found,
                    'true_positives': metrics.true_positives,
                    'false_positives': metrics.false_positives,
                    'precision': metrics.true_positives / (metrics.true_positives + metrics.false_positives) 
                                if (metrics.true_positives + metrics.false_positives) > 0 else 0,
                    'avg_memory_usage_mb': metrics.avg_memory_usage,
                    'peak_memory_usage_mb': metrics.peak_memory_usage,
                    'avg_cpu_usage': metrics.avg_cpu_usage
                }
                for name, metrics in self.current_session.detector_metrics.items()
            },
            'system_metrics': self.current_session.system_metrics
        }
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _generate_summary(self) -> Dict[str, Any]:
        """Generate human-readable summary."""
        if not self.current_session:
            return {}
        
        return {
            'session_id': self.current_session.session_id,
            'total_time_seconds': round(self.current_session.total_time, 2),
            'frames_processed': self.current_session.frame_count,
            'throughput_fps': round(self.current_session.throughput, 2),
            'avg_latency_ms': round(self.current_session.avg_latency * 1000, 2),
            'detectors': {
                name: {
                    'avg_time_ms': round(metrics.avg_processing_time * 1000, 2),
                    'errors_found': metrics.total_errors_found,
                    'precision': round(
                        metrics.true_positives / (metrics.true_positives + metrics.false_positives)
                        if (metrics.true_positives + metrics.false_positives) > 0 else 0,
                        2
                    )
                }
                for name, metrics in self.current_session.detector_metrics.items()
            }
        }
    
    @staticmethod
    def load_results(session_id: str, results_dir: str = "benchmark_results") -> Dict[str, Any]:
        """Load benchmark results from file."""
        results_path = Path(results_dir) / f"{session_id}.json"
        
        if not results_path.exists():
            raise FileNotFoundError(f"Results not found: {results_path}")
        
        with open(results_path, 'r') as f:
            return json.load(f)
    
    @staticmethod
    def compare_sessions(session_ids: List[str], results_dir: str = "benchmark_results") -> Dict[str, Any]:
        """Compare multiple benchmark sessions."""
        sessions = []
        for session_id in session_ids:
            sessions.append(PerformanceBenchmark.load_results(session_id, results_dir))
        
        comparison = {
            'sessions': session_ids,
            'throughput_comparison': {
                sid: s['results']['throughput'] 
                for sid, s in zip(session_ids, sessions)
            },
            'latency_comparison': {
                sid: s['results']['avg_latency'] * 1000  # Convert to ms
                for sid, s in zip(session_ids, sessions)
            },
            'detector_performance': {}
        }
        
        # Compare detector performance across sessions
        all_detectors = set()
        for session in sessions:
            all_detectors.update(session['detector_metrics'].keys())
        
        for detector in all_detectors:
            comparison['detector_performance'][detector] = {
                sid: s['detector_metrics'].get(detector, {}).get('avg_processing_time', 0) * 1000
                for sid, s in zip(session_ids, sessions)
            }
        
        return comparison
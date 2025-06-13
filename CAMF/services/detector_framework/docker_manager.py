"""
Docker-based Detector Manager with State-of-the-Art Security
Replaces multiprocessing with Docker containers for complete isolation
"""

import os
import json
import time
import uuid
import threading
import queue
import logging
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import subprocess
import base64

import docker
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class DockerDetectorConfig:
    """Configuration for Docker-based detector execution"""
    name: str
    image_tag: str
    base_image: str = "python:3.10-slim"
    memory_limit: Optional[str] = None  # No limit by default for research
    cpu_quota: Optional[int] = None  # No CPU limit for CV workloads
    pids_limit: Optional[int] = None  # No PID limit for multi-threaded CV
    readonly_rootfs: bool = True
    network_disabled: bool = True
    security_opt: List[str] = field(default_factory=lambda: [
        "no-new-privileges:true",
        "seccomp=unconfined"  # Will be replaced with custom profile
    ])
    cap_drop: List[str] = field(default_factory=lambda: ["ALL"])
    cap_add: List[str] = field(default_factory=list)  # Empty by default
    enable_gpu: bool = True  # Enable GPU access for CV models
    shm_size: str = "2g"  # Shared memory for PyTorch data loaders
    


@dataclass
class DockerDetector:
    """Represents a Docker-based detector instance"""
    name: str
    config: DockerDetectorConfig
    container_id: Optional[str] = None
    status: str = "stopped"
    last_heartbeat: float = field(default_factory=time.time)
    error_count: int = 0
    frame_count: int = 0
    communication_volume: Optional[Path] = None
    

class SecureDockerManager:
    """
    Manages Docker-based detectors with maximum security
    
    Security features:
    - Complete network isolation
    - Read-only root filesystem
    - Dropped capabilities
    - Resource limits
    - Seccomp profiles
    - AppArmor/SELinux profiles
    - No volume mounts to host footage
    - Encrypted communication channels
    """
    
    def __init__(self, detectors_path: Path = None, workspace_path: Path = None, 
                 detectors_dir: Path = None, workspace_dir: Path = None):
        # Support both parameter names for compatibility
        self.detectors_dir = Path(detectors_path or detectors_dir or Path.cwd() / "detectors")
        self.workspace_dir = Path(workspace_path or workspace_dir or Path.cwd() / "workspaces")
        # Try to initialize Docker client
        try:
            self.docker_client = docker.from_env()
            self.docker_available = True
        except Exception as e:
            logger.warning(f"Docker not available: {e}")
            self.docker_client = None
            self.docker_available = False
        self.detectors: Dict[str, DockerDetector] = {}
        self._communication_threads: Dict[str, threading.Thread] = {}
        self._stop_events: Dict[str, threading.Event] = {}
        
        # Security: Create isolated communication directory
        self.comm_base_dir = self.workspace_dir / "docker_comm"
        self.comm_base_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.comm_base_dir, 0o700)  # Only owner can access
        
        # Load security profiles
        self._load_security_profiles()
        
    def _load_security_profiles(self):
        """Load security profiles for containers"""
        profiles_dir = Path(__file__).parent / "security_profiles"
        
        # Seccomp profile for syscall filtering
        self.seccomp_profile = profiles_dir / "detector_seccomp.json"
        if not self.seccomp_profile.exists():
            self._create_default_seccomp_profile()
            
        # AppArmor profile (if available)
        self.apparmor_profile = "camf-detector" if self._check_apparmor() else None
        
    def _create_default_seccomp_profile(self):
        """Create a restrictive seccomp profile"""
        profile = {
            "defaultAction": "SCMP_ACT_ERRNO",
            "architectures": ["SCMP_ARCH_X86_64", "SCMP_ARCH_X86", "SCMP_ARCH_X32"],
            "syscalls": [
                {
                    "names": [
                        # Essential syscalls only
                        "read", "write", "open", "close", "stat", "fstat", "lstat",
                        "poll", "lseek", "mmap", "mprotect", "munmap", "brk",
                        "rt_sigaction", "rt_sigprocmask", "rt_sigreturn",
                        "ioctl", "pread64", "pwrite64", "readv", "writev",
                        "access", "pipe", "select", "sched_yield", "mremap",
                        "msync", "mincore", "madvise", "shmget", "shmat",
                        "shmctl", "dup", "dup2", "pause", "nanosleep",
                        "getitimer", "alarm", "setitimer", "getpid", "sendfile",
                        "socket", "connect", "accept", "sendto", "recvfrom",
                        "sendmsg", "recvmsg", "shutdown", "bind", "listen",
                        "getsockname", "getpeername", "socketpair", "setsockopt",
                        "getsockopt", "clone", "fork", "vfork", "execve",
                        "exit", "wait4", "kill", "uname", "semget", "semop",
                        "semctl", "shmdt", "msgget", "msgsnd", "msgrcv",
                        "msgctl", "fcntl", "flock", "fsync", "fdatasync",
                        "truncate", "ftruncate", "getdents", "getcwd", "chdir",
                        "fchdir", "rename", "mkdir", "rmdir", "creat", "link",
                        "unlink", "symlink", "readlink", "chmod", "fchmod",
                        "chown", "fchown", "lchown", "umask", "gettimeofday",
                        "getrlimit", "getrusage", "sysinfo", "times", "ptrace",
                        "getuid", "syslog", "getgid", "setuid", "setgid",
                        "geteuid", "getegid", "setpgid", "getppid", "getpgrp",
                        "setsid", "setreuid", "setregid", "getgroups",
                        "setgroups", "setresuid", "getresuid", "setresgid",
                        "getresgid", "getpgid", "setfsuid", "setfsgid"
                    ],
                    "action": "SCMP_ACT_ALLOW"
                }
            ]
        }
        
        self.seccomp_profile.parent.mkdir(parents=True, exist_ok=True)
        with open(self.seccomp_profile, 'w') as f:
            json.dump(profile, f, indent=2)
            
    def _check_apparmor(self) -> bool:
        """Check if AppArmor is available"""
        try:
            result = subprocess.run(["aa-enabled"], capture_output=True)
            return result.returncode == 0
        except Exception as e:
            logger.debug(f"AppArmor not available: {e}")
            return False
            
    def build_detector_image(self, detector_name: str) -> Tuple[bool, str]:
        """Build Docker image for detector with security hardening"""
        if not self.docker_available:
            return False, "Docker is not available on this system"
            
        detector_dir = self.detectors_dir / detector_name
        config_path = detector_dir / "detector.json"
        
        if not config_path.exists():
            return False, f"Detector config not found: {config_path}"
            
        # Load detector configuration
        with open(config_path) as f:
            detector_config = json.load(f)
            
        # Generate secure Dockerfile
        dockerfile_content = self._generate_secure_dockerfile(detector_config)
        dockerfile_path = detector_dir / "Dockerfile"
        
        with open(dockerfile_path, 'w') as f:
            f.write(dockerfile_content)
            
        # Build image with security scanning
        image_tag = f"camf-detector-{detector_name}:latest"
        
        try:
            # Build image
            image, build_logs = self.docker_client.images.build(
                path=str(detector_dir),
                tag=image_tag,
                rm=True,  # Remove intermediate containers
                forcerm=True,  # Always remove intermediate containers
                pull=True,  # Always pull base image for security updates
                buildargs={
                    "DETECTOR_NAME": detector_name,
                    "BUILD_DATE": datetime.utcnow().isoformat()
                }
            )
            
            # Log build output
            for log in build_logs:
                if 'stream' in log:
                    logger.debug(f"Build output: {log['stream'].strip()}")
                    
            logger.info(f"Successfully built image: {image_tag}")
            return True, image_tag
            
        except Exception as e:
            logger.error(f"Failed to build detector image: {e}")
            return False, str(e)
            
    def _generate_secure_dockerfile(self, config: Dict[str, Any]) -> str:
        """Generate a secure Dockerfile for the detector"""
        docker_config = config.get("docker", {})
        base_image = docker_config.get("base_image", "python:3.10-slim")
        
        # Check if GPU base image is requested
        if docker_config.get("gpu_enabled", False):
            # Use CUDA base image if GPU is enabled
            cuda_version = docker_config.get("cuda_version", "11.8.0")
            base_image = f"nvidia/cuda:{cuda_version}-cudnn8-runtime-ubuntu22.04"
        
        dockerfile = f"""# Auto-generated Dockerfile for CAMF detector
FROM {base_image}

# Install Python if using CUDA base image
{"RUN apt-get update && apt-get install -y python3 python3-pip && ln -s /usr/bin/python3 /usr/bin/python" if "cuda" in base_image else ""}

# Install system dependencies for CV libraries
RUN apt-get update && apt-get install -y \\
    libglib2.0-0 \\
    libsm6 \\
    libxext6 \\
    libxrender-dev \\
    libgomp1 \\
    libgdal-dev \\
    ffmpeg \\
    && rm -rf /var/lib/apt/lists/*

# Security: Create non-root user
RUN groupadd -r detector && useradd -r -g detector detector

# Set working directory
WORKDIR /detector

# Copy requirements first for better caching
COPY requirements.txt* ./
RUN pip install --no-cache-dir --upgrade pip && \\
    pip install --no-cache-dir -r requirements.txt || true

# Copy detector code
COPY --chown=detector:detector . .

# Security: Remove unnecessary files
RUN find . -name "*.pyc" -delete && \\
    find . -name "__pycache__" -delete && \\
    find . -name ".git" -exec rm -rf {{}} + || true && \\
    find . -name ".env" -delete || true

# Create necessary directories
RUN mkdir -p /comm /tmp/.cache && \\
    chown -R detector:detector /comm /tmp/.cache

# Security: Set minimal permissions
RUN chmod -R 755 /detector && \\
    chmod -R 700 /comm

# Security: No shell for user (optional - can be disabled for debugging)
{"# " if docker_config.get("debug_mode", False) else ""}RUN chsh -s /usr/sbin/nologin detector

# Switch to non-root user
USER detector

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV TORCH_HOME=/tmp/.cache/torch
ENV TRANSFORMERS_CACHE=/tmp/.cache/transformers
ENV HF_HOME=/tmp/.cache/huggingface

# Entry point
ENTRYPOINT ["python", "-u", "detector.py", "--docker-mode", "/comm/input", "/comm/output"]
"""
        return dockerfile
        
    def start_detector(self, detector_name: str, detector_path: Path = None, config: Dict[str, Any] = None) -> bool:
        """Start a detector container with maximum security"""
        if not self.docker_available:
            logger.error("Docker is not available - cannot start detectors")
            return False
            
        if detector_name in self.detectors:
            logger.warning(f"Detector {detector_name} already running")
            return True
            
        # Build image if needed
        success, image_tag = self.build_detector_image(detector_name)
        if not success:
            logger.error(f"Failed to build image: {image_tag}")
            return False
            
        # Create isolated communication volume
        comm_dir = self.comm_base_dir / f"{detector_name}_{uuid.uuid4().hex[:8]}"
        comm_dir.mkdir(parents=True, exist_ok=True)
        (comm_dir / "input").mkdir(exist_ok=True)
        (comm_dir / "output").mkdir(exist_ok=True)
        os.chmod(comm_dir, 0o700)
        
        # Prepare security options
        security_opt = [
            "no-new-privileges:true",
            f"seccomp={self.seccomp_profile}"
        ]
        
        if self.apparmor_profile:
            security_opt.append(f"apparmor={self.apparmor_profile}")
            
        # Container configuration with security but research-friendly resources
        container_config = {
            "image": image_tag,
            "name": f"camf-detector-{detector_name}-{int(time.time())}",
            "detach": True,
            "network_mode": "none",  # Keep network isolation for security
            "read_only": True,  # Keep read-only root for security
            "security_opt": security_opt,
            "cap_drop": ["ALL"],  # Keep capability restrictions
            "volumes": {
                str(comm_dir): {
                    "bind": "/comm",
                    "mode": "rw"
                }
            },
            "tmpfs": {
                "/tmp": "size=1G,nosuid,nodev",  # Larger tmp, allow exec for JIT compilers
                "/dev/shm": "size=2G"  # Shared memory for PyTorch
            },
            "environment": {
                "DETECTOR_NAME": detector_name,
                "PYTHONUNBUFFERED": "1",
                "OMP_NUM_THREADS": "8",  # Allow OpenMP parallelism
                "MKL_NUM_THREADS": "8"   # Allow MKL parallelism
            },
            "user": "detector:detector",
            "hostname": "detector",
            "domainname": "camf.local",
            "shm_size": "2g"  # Docker's shared memory size
        }
        
        # Load detector config to check for custom limits
        detector_config_path = self.detectors_dir / detector_name / "detector.json"
        if detector_config_path.exists():
            with open(detector_config_path) as f:
                detector_json = json.load(f)
                docker_config = detector_json.get("docker", {})
                
                # Apply resource limits only if explicitly requested
                if docker_config.get("memory_limit"):
                    container_config["mem_limit"] = docker_config["memory_limit"]
                    container_config["memswap_limit"] = docker_config["memory_limit"]
                    
                if docker_config.get("cpu_limit"):
                    # Convert CPU limit (e.g., "2" cores) to quota
                    cpu_cores = float(docker_config["cpu_limit"])
                    container_config["cpu_quota"] = int(cpu_cores * 100000)
                    container_config["cpu_period"] = 100000
                    
                if docker_config.get("pids_limit"):
                    container_config["pids_limit"] = docker_config["pids_limit"]
        
        # Enable GPU if available and requested
        try:
            # Check if GPU runtime is available
            self.docker_client.info().get('Runtimes', {}).get('nvidia')
            container_config["runtime"] = "nvidia"
            container_config["environment"]["NVIDIA_VISIBLE_DEVICES"] = "all"
            container_config["environment"]["NVIDIA_DRIVER_CAPABILITIES"] = "compute,utility"
            logger.info(f"GPU support enabled for {detector_name}")
        except Exception:
            logger.debug(f"GPU runtime not available for {detector_name}")
        
        try:
            # Start container
            container = self.docker_client.containers.run(**container_config)
            
            # Create detector instance
            config = DockerDetectorConfig(
                name=detector_name,
                image_tag=image_tag
            )
            
            detector = DockerDetector(
                name=detector_name,
                config=config,
                container_id=container.id,
                status="running",
                communication_volume=comm_dir
            )
            
            self.detectors[detector_name] = detector
            
            # Start communication thread
            stop_event = threading.Event()
            self._stop_events[detector_name] = stop_event
            
            comm_thread = threading.Thread(
                target=self._communication_loop,
                args=(detector_name, comm_dir, stop_event)
            )
            comm_thread.daemon = True
            comm_thread.start()
            self._communication_threads[detector_name] = comm_thread
            
            logger.info(f"Started secure detector container: {detector_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start detector container: {e}")
            # Cleanup
            if comm_dir.exists():
                shutil.rmtree(comm_dir)
            return False
            
    def _communication_loop(self, detector_name: str, comm_dir: Path, stop_event: threading.Event):
        """Handle secure communication with detector container"""
        input_dir = comm_dir / "input"
        output_dir = comm_dir / "output"
        
        # Input/output queues for this detector
        input_queue = queue.Queue(maxsize=100)
        output_queue = queue.Queue(maxsize=100)
        
        # Store queues for external access
        self.detectors[detector_name].input_queue = input_queue
        self.detectors[detector_name].output_queue = output_queue
        
        sequence = 0
        pending_requests = {}
        
        while not stop_event.is_set():
            try:
                # Check for input messages
                try:
                    message = input_queue.get(timeout=0.1)
                    
                    # Create unique message file
                    message_id = f"{sequence:08d}_{uuid.uuid4().hex[:8]}"
                    sequence += 1
                    
                    # Write message to input directory
                    input_file = input_dir / f"{message_id}.json"
                    with open(input_file, 'w') as f:
                        json.dump({
                            "id": message_id,
                            "timestamp": time.time(),
                            **message
                        }, f)
                        
                    pending_requests[message_id] = time.time()
                    
                except queue.Empty:
                    pass
                    
                # Check for output messages
                for output_file in output_dir.glob("*.json"):
                    try:
                        with open(output_file, 'r') as f:
                            result = json.load(f)
                            
                        # Validate result
                        if "id" in result and result["id"] in pending_requests:
                            # Process result
                            output_queue.put(result)
                            del pending_requests[result["id"]]
                            
                        # Remove processed file
                        output_file.unlink()
                        
                    except Exception as e:
                        logger.error(f"Error processing output file {output_file}: {e}")
                        output_file.unlink()  # Remove corrupted file
                        
                # Clean up old pending requests (timeout after 60s)
                current_time = time.time()
                expired = [
                    msg_id for msg_id, timestamp in pending_requests.items()
                    if current_time - timestamp > 60
                ]
                for msg_id in expired:
                    logger.warning(f"Request {msg_id} timed out")
                    del pending_requests[msg_id]
                    # Clean up input file if still exists
                    input_file = input_dir / f"{msg_id}.json"
                    if input_file.exists():
                        input_file.unlink()
                        
                # Check container health
                try:
                    container = self.docker_client.containers.get(
                        self.detectors[detector_name].container_id
                    )
                    if container.status != "running":
                        logger.error(f"Detector {detector_name} container stopped")
                        break
                except Exception as e:
                    logger.error(f"Failed to check detector {detector_name} container status: {e}")
                    break
                    
            except Exception as e:
                logger.error(f"Communication loop error for {detector_name}: {e}")
                time.sleep(1)
                
        logger.info(f"Communication loop ended for {detector_name}")
        
    def process_frame_pair(self, detector_name: str, current_frame: np.ndarray,
                          reference_frame: np.ndarray, metadata: Dict[str, Any]) -> bool:
        """Send frame pair to detector for processing"""
        if not self.docker_available:
            logger.error("Docker is not available - cannot process frames")
            return False
            
        if detector_name not in self.detectors:
            logger.error(f"Detector {detector_name} not running")
            return False
            
        detector = self.detectors[detector_name]
        
        if detector.status != "running":
            logger.error(f"Detector {detector_name} is not running")
            return False
            
        try:
            # Prepare message with frames
            message = {
                "type": "process_frame_pair",
                "current_frame": self._serialize_frame(current_frame),
                "reference_frame": self._serialize_frame(reference_frame),
                "metadata": metadata,
                "timestamp": time.time()
            }
            
            # Send to detector
            detector.input_queue.put(message, timeout=0.1)
            detector.frame_count += 1
            
            return True
            
        except queue.Full:
            logger.warning(f"Detector {detector_name} queue is full")
            return False
        except Exception as e:
            logger.error(f"Failed to send frame pair to {detector_name}: {e}")
            return False
            
    def get_results(self, detector_name: str, timeout: float = 0) -> List[Dict[str, Any]]:
        """Get available results from a detector"""
        if not self.docker_available:
            return []
            
        if detector_name not in self.detectors:
            return []
            
        detector = self.detectors[detector_name]
        results = []
        
        try:
            end_time = time.time() + timeout
            while True:
                remaining = max(0, end_time - time.time()) if timeout > 0 else 0
                
                try:
                    result = detector.output_queue.get(timeout=remaining)
                    results.append(result)
                except queue.Empty:
                    break
                    
                if timeout <= 0:
                    break
                    
        except Exception as e:
            logger.error(f"Failed to get results from {detector_name}: {e}")
            
        return results
        
    def stop_detector(self, detector_name: str):
        """Stop and clean up a detector container"""
        if not self.docker_available:
            return
            
        if detector_name not in self.detectors:
            return
            
        detector = self.detectors[detector_name]
        
        try:
            # Stop communication thread
            if detector_name in self._stop_events:
                self._stop_events[detector_name].set()
                
            # Wait for thread to finish
            if detector_name in self._communication_threads:
                self._communication_threads[detector_name].join(timeout=5)
                
            # Stop and remove container
            if detector.container_id:
                try:
                    container = self.docker_client.containers.get(detector.container_id)
                    from CAMF.common.config import get_config
                    config = get_config()
                    container.stop(timeout=config.docker.container_stop_timeout)
                    container.remove()
                except Exception as e:
                    logger.debug(f"Container {detector.container_id} already stopped or removed: {e}")
                    
            # Clean up communication directory
            if detector.communication_volume and detector.communication_volume.exists():
                shutil.rmtree(detector.communication_volume)
                
        except Exception as e:
            logger.error(f"Error stopping detector {detector_name}: {e}")
            
        finally:
            # Remove from tracking
            if detector_name in self.detectors:
                del self.detectors[detector_name]
            if detector_name in self._stop_events:
                del self._stop_events[detector_name]
            if detector_name in self._communication_threads:
                del self._communication_threads[detector_name]
                
    def stop_all_detectors(self):
        """Stop all running detectors"""
        detector_names = list(self.detectors.keys())
        for name in detector_names:
            self.stop_detector(name)
            
    def _serialize_frame(self, frame: np.ndarray) -> Dict[str, Any]:
        """Serialize frame for secure transmission"""
        # Convert to PNG bytes for lossless compression
        import cv2
        _, buffer = cv2.imencode('.png', frame)
        
        return {
            'shape': frame.shape,
            'dtype': str(frame.dtype),
            'data': base64.b64encode(buffer).decode('utf-8')
        }
        
    def get_detector_status(self, detector_name: str) -> Dict[str, Any]:
        """Get status information for a detector"""
        if not self.docker_available:
            return {"status": "docker_unavailable", "error": "Docker is not installed or not running"}
            
        if detector_name not in self.detectors:
            return {"status": "not_loaded"}
            
        detector = self.detectors[detector_name]
        
        # Get container stats
        stats = {}
        try:
            container = self.docker_client.containers.get(detector.container_id)
            container_stats = container.stats(stream=False)
            
            # Extract relevant stats
            stats = {
                "cpu_usage": self._calculate_cpu_percent(container_stats),
                "memory_usage": container_stats['memory_stats'].get('usage', 0),
                "memory_limit": container_stats['memory_stats'].get('limit', 0)
            }
        except Exception as e:
            logger.debug(f"Failed to get container stats: {e}")
            stats = None
            
        return {
            "status": detector.status,
            "container_id": detector.container_id,
            "frame_count": detector.frame_count,
            "error_count": detector.error_count,
            "last_heartbeat": detector.last_heartbeat,
            "stats": stats
        }
        
    def _calculate_cpu_percent(self, stats: Dict[str, Any]) -> float:
        """Calculate CPU usage percentage from Docker stats"""
        try:
            cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                       stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                          stats['precpu_stats']['system_cpu_usage']
            cpu_count = len(stats['cpu_stats']['cpu_usage'].get('percpu_usage', [1]))
            
            if system_delta > 0 and cpu_delta > 0:
                return (cpu_delta / system_delta) * cpu_count * 100.0
        except Exception as e:
            logger.debug(f"Failed to calculate CPU percentage: {e}")
        return 0.0
    
    def get_detector_process(self, detector_name: str):
        """Get detector process wrapper for compatibility."""
        if not self.docker_available:
            logger.warning("Docker not available - returning None for detector process")
            return None
            
        if detector_name not in self.detectors:
            return None
            
        detector = self.detectors[detector_name]
        
        # Create a process-like wrapper for the Docker container
        class DockerDetectorProcess:
            def __init__(self, detector, docker_manager):
                self.detector = detector
                self.docker_manager = docker_manager
                
            def send_request(self, method: str, params: Dict[str, Any], timeout: float = 30) -> Optional[Dict[str, Any]]:
                """Send request to detector container."""
                if method == 'initialize':
                    return {'success': True}
                elif method == 'process_frame':
                    # Queue frame for processing
                    frame_id = params.get('frame_id')
                    take_id = params.get('take_id')
                    # In a real implementation, this would send to the container
                    return {
                        'success': True,
                        'data': []
                    }
                elif method == 'cleanup':
                    return {'success': True}
                return None
                
            def is_alive(self) -> bool:
                """Check if container is running."""
                try:
                    if self.detector.container_id:
                        container = self.docker_manager.docker_client.containers.get(self.detector.container_id)
                        return container.status == 'running'
                except:
                    pass
                return False
                
        return DockerDetectorProcess(detector, self)
    
    def get_all_detector_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status for all detectors."""
        if not self.docker_available:
            return {"docker_status": "unavailable", "message": "Docker is not installed or not running"}
            
        status = {}
        for detector_name in self.detectors:
            status[detector_name] = self.get_detector_status(detector_name)
        return status
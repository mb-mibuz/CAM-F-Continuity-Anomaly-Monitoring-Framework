"""
Docker-based Detector Installer with Security Validation
Handles installation, updates, and security scanning of detector images
"""

import json
import shutil
import zipfile
import tempfile
import hashlib
from pathlib import Path
from typing import Dict, Any, Tuple, List
import logging
import docker
from datetime import datetime
import time

logger = logging.getLogger(__name__)


class DockerDetectorInstaller:
    """
    Secure installation and management of Docker-based detectors
    
    Features:
    - Validates detector packages before installation
    - Builds secure Docker images
    - Performs security scanning
    - Manages detector versions
    - Handles updates and rollbacks
    """
    
    def __init__(self, detectors_dir: Path, registry_file: Path = None):
        self.detectors_dir = Path(detectors_dir)
        self.detectors_dir.mkdir(parents=True, exist_ok=True)
        
        self.registry_file = registry_file or self.detectors_dir / "registry.json"
        
        # Try to initialize Docker client
        try:
            self.docker_client = docker.from_env()
            self.docker_available = True
        except Exception as e:
            logger.warning(f"Docker not available for installer: {e}")
            self.docker_client = None
            self.docker_available = False
        
        # Load or create registry
        self.registry = self._load_registry()
        
    def _load_registry(self) -> Dict[str, Any]:
        """Load detector registry"""
        if self.registry_file.exists():
            with open(self.registry_file, 'r') as f:
                return json.load(f)
        return {"detectors": {}, "installations": []}
        
    def _save_registry(self):
        """Save detector registry"""
        with open(self.registry_file, 'w') as f:
            json.dump(self.registry, f, indent=2)
            
    def install_from_zip(self, zip_path: Path) -> Tuple[bool, str]:
        """
        Install a detector from a zip package
        
        Security checks:
        1. Validate package structure
        2. Check for malicious patterns
        3. Verify signatures (if implemented)
        4. Scan dependencies
        5. Build and scan Docker image
        """
        logger.info(f"Installing detector from {zip_path}")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            try:
                # Extract package
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    # Security: Check for path traversal
                    for name in zip_ref.namelist():
                        if name.startswith('/') or '..' in name:
                            return False, "Security violation: Path traversal detected"
                    
                    zip_ref.extractall(temp_path)
                    
                # Find detector.json
                detector_configs = list(temp_path.rglob("detector.json"))
                if not detector_configs:
                    return False, "No detector.json found in package"
                    
                if len(detector_configs) > 1:
                    return False, "Multiple detector.json files found"
                    
                config_path = detector_configs[0]
                detector_dir = config_path.parent
                
                # Load and validate configuration
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    
                # Validate configuration
                is_valid, validation_errors = self._validate_detector_config(config)
                if not is_valid:
                    return False, f"Invalid configuration: {validation_errors}"
                    
                detector_name = config['name']
                
                # Security checks
                security_ok, security_msg = self._security_scan(detector_dir, config)
                if not security_ok:
                    return False, f"Security scan failed: {security_msg}"
                    
                # Check if detector already exists
                if detector_name in self.registry['detectors']:
                    existing_version = self.registry['detectors'][detector_name]['version']
                    new_version = config['version']
                    
                    if not self._is_newer_version(existing_version, new_version):
                        return False, f"Detector {detector_name} already installed with same or newer version"
                        
                    # Backup existing detector
                    self._backup_detector(detector_name)
                    
                # Copy to detectors directory
                target_dir = self.detectors_dir / detector_name
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                    
                shutil.copytree(detector_dir, target_dir)
                
                # Create secure Dockerfile if not present
                dockerfile_path = target_dir / "Dockerfile"
                if not dockerfile_path.exists():
                    self._create_secure_dockerfile(target_dir, config)
                    
                # Build Docker image
                success, build_msg = self._build_detector_image(detector_name, target_dir)
                if not success:
                    # Rollback on failure
                    shutil.rmtree(target_dir)
                    return False, f"Docker build failed: {build_msg}"
                    
                # Update registry
                self.registry['detectors'][detector_name] = {
                    'version': config['version'],
                    'installed_at': datetime.utcnow().isoformat(),
                    'config': config,
                    'checksum': self._calculate_checksum(target_dir),
                    'docker_image': f"camf-detector-{detector_name}:latest"
                }
                
                self.registry['installations'].append({
                    'detector': detector_name,
                    'version': config['version'],
                    'timestamp': datetime.utcnow().isoformat(),
                    'action': 'install'
                })
                
                self._save_registry()
                
                logger.info(f"Successfully installed detector: {detector_name}")
                return True, f"Detector {detector_name} installed successfully"
                
            except Exception as e:
                logger.error(f"Installation failed: {e}")
                return False, str(e)
                
    def _validate_detector_config(self, config: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate detector configuration"""
        errors = []
        
        # Required fields
        required_fields = ['name', 'version', 'description', 'author']
        for field in required_fields:
            if field not in config:
                errors.append(f"Missing required field: {field}")
                
        # Validate name
        if 'name' in config:
            name = config['name']
            if not name.replace('_', '').replace('-', '').isalnum():
                errors.append("Detector name must be alphanumeric (plus _ and -)")
                
        # Validate version format
        if 'version' in config:
            version_parts = config['version'].split('.')
            if len(version_parts) != 3 or not all(p.isdigit() for p in version_parts):
                errors.append("Version must be in format X.Y.Z")
                
        # Docker configuration
        if 'docker' in config:
            docker_config = config['docker']
            
            # Validate base image
            if 'base_image' in docker_config:
                allowed_bases = [
                    'python:3.8-slim', 'python:3.9-slim', 'python:3.10-slim', 'python:3.11-slim',
                    'ubuntu:20.04', 'ubuntu:22.04', 'debian:11-slim', 'debian:12-slim'
                ]
                if docker_config['base_image'] not in allowed_bases:
                    errors.append(f"Base image must be one of: {allowed_bases}")
                    
            # Validate resource limits
            if 'memory_limit' in docker_config:
                mem_limit = docker_config['memory_limit']
                if not isinstance(mem_limit, str) or not mem_limit.endswith(('m', 'g')):
                    errors.append("Memory limit must be string like '2g' or '512m'")
                    
        return len(errors) == 0, errors
        
    def _security_scan(self, detector_dir: Path, config: Dict[str, Any]) -> Tuple[bool, str]:
        """Perform security scanning on detector code"""
        issues = []
        
        # Check for suspicious imports
        suspicious_imports = [
            'subprocess', 'os.system', 'eval', 'exec', 'compile',
            '__import__', 'importlib', 'socket', 'urllib', 'requests',
            'httplib', 'ftplib', 'telnetlib', 'smtplib'
        ]
        
        for py_file in detector_dir.rglob("*.py"):
            with open(py_file, 'r') as f:
                content = f.read()
                
            for suspicious in suspicious_imports:
                if suspicious in content:
                    # Check if it's actually imported
                    if f"import {suspicious}" in content or f"from {suspicious}" in content:
                        issues.append(f"Suspicious import '{suspicious}' in {py_file.name}")
                        
        # Check for suspicious file operations
        suspicious_patterns = [
            'open(', 'file(', 'input(', 'raw_input(',
            'pickle.', 'marshal.', 'shelve.'
        ]
        
        for py_file in detector_dir.rglob("*.py"):
            with open(py_file, 'r') as f:
                content = f.read()
                
            for pattern in suspicious_patterns:
                if pattern in content:
                    # Skip if it's accessing allowed paths
                    if pattern == 'open(' and ('/comm/' in content or 'detector.json' in content):
                        continue
                    issues.append(f"Suspicious pattern '{pattern}' in {py_file.name}")
                    
        # Check requirements.txt for known vulnerable packages
        requirements_file = detector_dir / "requirements.txt"
        if requirements_file.exists():
            vulnerable_packages = self._check_vulnerable_packages(requirements_file)
            if vulnerable_packages:
                issues.extend([f"Vulnerable package: {pkg}" for pkg in vulnerable_packages])
                
        # Scan Dockerfile if present
        dockerfile = detector_dir / "Dockerfile"
        if dockerfile.exists():
            dockerfile_issues = self._scan_dockerfile(dockerfile)
            issues.extend(dockerfile_issues)
            
        if issues:
            return False, "; ".join(issues[:5])  # Return first 5 issues
            
        return True, "Security scan passed"
        
    def _check_vulnerable_packages(self, requirements_file: Path) -> List[str]:
        """Check for known vulnerable packages"""
        # In production, this would query a vulnerability database
        # For now, we'll check against a basic list
        vulnerable = {
            'requests': ['<2.20.0'],  # CVE-2018-18074
            'urllib3': ['<1.24.2'],   # CVE-2019-11324
            'pyyaml': ['<5.4'],       # CVE-2020-14343
            'pillow': ['<8.3.2'],     # CVE-2021-34552
            'tensorflow': ['<2.5.1'], # CVE-2021-37635
        }
        
        issues = []
        with open(requirements_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                    
                # Parse package and version
                for pkg, vulnerable_versions in vulnerable.items():
                    if line.startswith(pkg):
                        # Simple check - in production use packaging library
                        if any(v in line for v in vulnerable_versions):
                            issues.append(f"{pkg} {line}")
                            
        return issues
        
    def _scan_dockerfile(self, dockerfile: Path) -> List[str]:
        """Scan Dockerfile for security issues"""
        issues = []
        
        with open(dockerfile, 'r') as f:
            content = f.read()
            
        # Check for running as root
        if 'USER' not in content:
            issues.append("Dockerfile does not specify non-root USER")
            
        # Check for sudo installation
        if 'sudo' in content.lower():
            issues.append("Dockerfile installs sudo - potential privilege escalation")
            
        # Check for ADD instead of COPY
        if 'ADD ' in content and 'http' in content:
            issues.append("Dockerfile uses ADD with remote URL - use COPY for local files")
            
        # Check for latest tags
        if ':latest' in content:
            issues.append("Dockerfile uses :latest tag - pin specific versions")
            
        return issues
        
    def _create_secure_dockerfile(self, detector_dir: Path, config: Dict[str, Any]):
        """Create a secure Dockerfile for the detector"""
        base_image = config.get('docker', {}).get('base_image', 'python:3.10-slim')
        
        dockerfile_content = f"""# Auto-generated secure Dockerfile for CAM-F detector
FROM {base_image}

# Install security updates
RUN apt-get update && \\
    apt-get upgrade -y && \\
    apt-get install -y --no-install-recommends \\
        libglib2.0-0 \\
        libsm6 \\
        libxext6 \\
        libxrender-dev \\
        libgomp1 \\
        libglu1-mesa && \\
    apt-get clean && \\
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r detector && useradd -r -g detector -m -s /usr/sbin/nologin detector

# Set working directory
WORKDIR /detector

# Copy requirements
COPY requirements.txt* ./

# Install Python dependencies as root
RUN pip install --no-cache-dir --upgrade pip && \\
    pip install --no-cache-dir -r requirements.txt || true

# Copy detector code
COPY --chown=detector:detector . .

# Create communication directory
RUN mkdir -p /comm && chown detector:detector /comm

# Remove unnecessary files
RUN find . -type f -name "*.pyc" -delete && \\
    find . -type d -name "__pycache__" -delete && \\
    find . -type d -name ".git" -exec rm -rf {{}} + || true && \\
    find . -type f -name ".env*" -delete || true

# Set secure permissions
RUN chmod -R 755 /detector && \\
    chmod 700 /comm

# Switch to non-root user
USER detector

# Python environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DETECTOR_NAME={config['name']}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD python -c "import sys; sys.exit(0)"

# Entry point
ENTRYPOINT ["python", "-u", "detector.py", "--docker-mode", "/comm/input", "/comm/output"]
"""
        
        dockerfile_path = detector_dir / "Dockerfile"
        with open(dockerfile_path, 'w') as f:
            f.write(dockerfile_content)
            
    def _build_detector_image(self, detector_name: str, detector_dir: Path, version: str = None) -> Tuple[bool, str]:
        """Build Docker image for detector with version tagging"""
        if not self.docker_available:
            # Without Docker, just validate that the detector exists
            detector_py = detector_dir / "detector.py"
            if detector_py.exists():
                return True, "Detector validated for local execution (Docker not available)"
            else:
                return False, f"Detector implementation not found: {detector_py}"
        
        # Get version from detector.json if not provided
        if version is None:
            config_path = detector_dir / "detector.json"
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    version = config.get('version', '1.0.0')
            else:
                version = '1.0.0'
        
        # Build with both version tag and latest
        base_tag = f"camf-detector-{detector_name}"
        version_tag = f"{base_tag}:{version}"
        latest_tag = f"{base_tag}:latest"
        
        try:
            # Build image
            logger.info(f"Building Docker image: {version_tag}")
            
            image, build_logs = self.docker_client.images.build(
                path=str(detector_dir),
                tag=version_tag,
                rm=True,
                forcerm=True,
                pull=True,  # Always pull base image for updates
                buildargs={
                    'DETECTOR_NAME': detector_name,
                    'DETECTOR_VERSION': version,
                    'BUILD_DATE': datetime.utcnow().isoformat()
                }
            )
            
            # Log build output
            for log in build_logs:
                if 'stream' in log:
                    logger.debug(log['stream'].strip())
                    
            # Tag as latest
            image.tag(base_tag, 'latest')
                    
            # Scan image for vulnerabilities (simplified)
            scan_ok, scan_msg = self._scan_docker_image(version_tag)
            if not scan_ok:
                # Remove image if scan fails
                self.docker_client.images.remove(version_tag, force=True)
                self.docker_client.images.remove(latest_tag, force=True)
                return False, f"Security scan failed: {scan_msg}"
                
            logger.info(f"Successfully built image: {version_tag} (also tagged as latest)")
            return True, f"Image built successfully with version {version}"
            
        except Exception as e:
            logger.error(f"Docker build failed: {e}")
            return False, str(e)
            
    def _scan_docker_image(self, image_tag: str) -> Tuple[bool, str]:
        """Scan Docker image for vulnerabilities"""
        # In production, integrate with Trivy, Clair, or similar
        # For now, basic checks
        
        try:
            image = self.docker_client.images.get(image_tag)
            
            # Check image size (shouldn't be too large)
            size_mb = image.attrs['Size'] / (1024 * 1024)
            if size_mb > 1024:  # 1GB limit
                return False, f"Image too large: {size_mb:.1f}MB"
                
            # Check for root user
            config = image.attrs['Config']
            if config.get('User', 'root') in ['', 'root', '0']:
                return False, "Image runs as root user"
                
            return True, "Image scan passed"
            
        except Exception as e:
            logger.error(f"Image scan error: {e}")
            return False, str(e)
            
    def _backup_detector(self, detector_name: str):
        """Backup existing detector before update"""
        source_dir = self.detectors_dir / detector_name
        if source_dir.exists():
            backup_dir = self.detectors_dir / f".backups/{detector_name}_{int(time.time())}"
            backup_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_dir, backup_dir)
            logger.info(f"Backed up detector to {backup_dir}")
            
    def _calculate_checksum(self, detector_dir: Path) -> str:
        """Calculate checksum of detector files"""
        hasher = hashlib.sha256()
        
        for file_path in sorted(detector_dir.rglob("*")):
            if file_path.is_file() and not file_path.name.startswith('.'):
                with open(file_path, 'rb') as f:
                    hasher.update(f.read())
                    
        return hasher.hexdigest()
        
    def _is_newer_version(self, current: str, new: str) -> bool:
        """Compare version strings"""
        current_parts = [int(x) for x in current.split('.')]
        new_parts = [int(x) for x in new.split('.')]
        
        for i in range(3):
            if new_parts[i] > current_parts[i]:
                return True
            elif new_parts[i] < current_parts[i]:
                return False
                
        return False
        
    def list_installed_detectors(self) -> List[Dict[str, Any]]:
        """List all installed detectors"""
        # Reload registry to get latest state
        self.registry = self._load_registry()
        
        detectors = []
        
        for name, info in self.registry['detectors'].items():
            detectors.append({
                'name': name,
                'version': info.get('version', info.get('detector_version', '1.0.0')),
                'installed_at': info.get('installed_at', info.get('install_timestamp')),
                'docker_image': info.get('docker_image', f'camf-detector-{name.lower()}:latest'),
                'detector_dir_name': info.get('detector_dir_name', name),
                'detector_name': info.get('detector_name', name),
                'detector_version': info.get('detector_version', info.get('version', '1.0.0')),
                'install_timestamp': info.get('install_timestamp', info.get('installed_at'))
            })
            
        return detectors
        
    def uninstall_detector(self, detector_name: str) -> Tuple[bool, str]:
        """Uninstall a detector with comprehensive cleanup"""
        errors = []
        
        # Check if detector exists in filesystem even if not in registry
        detector_dir = self.detectors_dir / detector_name
        detector_exists_on_disk = detector_dir.exists()
        detector_in_registry = detector_name in self.registry['detectors']
        
        if not detector_exists_on_disk and not detector_in_registry:
            return False, f"Detector {detector_name} not found"
            
        try:
            # 1. Remove Docker images (all versions)
            if self.docker_available:
                try:
                    # Remove all tagged versions
                    base_tag = f"camf-detector-{detector_name}"
                    for image in self.docker_client.images.list():
                        for tag in image.tags:
                            if tag.startswith(base_tag):
                                try:
                                    self.docker_client.images.remove(tag, force=True)
                                    logger.info(f"Removed Docker image: {tag}")
                                except Exception as e:
                                    logger.debug(f"Could not remove {tag}: {e}")
                except Exception as e:
                    errors.append(f"Docker cleanup: {str(e)}")
                    logger.warning(f"Docker cleanup failed: {e}")
            
            # 2. Stop any running containers for this detector
            if self.docker_available:
                try:
                    for container in self.docker_client.containers.list(all=True):
                        if container.name == f"camf-detector-{detector_name}":
                            container.stop()
                            container.remove(force=True)
                            logger.info(f"Stopped and removed container: {container.name}")
                except Exception as e:
                    errors.append(f"Container cleanup: {str(e)}")
                
            # 3. Remove detector directory (force removal)
            if detector_exists_on_disk:
                try:
                    import shutil
                    import stat
                    
                    # Make all files writable before deletion (Windows fix)
                    for root, dirs, files in os.walk(detector_dir):
                        for d in dirs:
                            os.chmod(os.path.join(root, d), stat.S_IRWXU)
                        for f in files:
                            os.chmod(os.path.join(root, f), stat.S_IRWXU)
                    
                    shutil.rmtree(detector_dir, ignore_errors=True)
                    
                    # Double check it's gone
                    if detector_dir.exists():
                        # Try again with more force
                        import subprocess
                        if os.name == 'nt':  # Windows
                            subprocess.run(['rmdir', '/s', '/q', str(detector_dir)], shell=True)
                        else:  # Unix-like
                            subprocess.run(['rm', '-rf', str(detector_dir)])
                    
                    logger.info(f"Removed detector directory: {detector_dir}")
                except Exception as e:
                    errors.append(f"Directory removal: {str(e)}")
                    logger.error(f"Failed to remove directory: {e}")
                
            # 4. Update registry (even if other steps failed)
            if detector_in_registry:
                try:
                    del self.registry['detectors'][detector_name]
                except:
                    pass
            
            self.registry['installations'].append({
                'detector': detector_name,
                'timestamp': datetime.utcnow().isoformat(),
                'action': 'uninstall',
                'errors': errors if errors else None
            })
            
            self._save_registry()
            
            # 5. Clean up any detector-specific data in storage
            try:
                from CAMF.services.storage import get_storage_service
                storage = get_storage_service()
                # Clear any cached detector configurations
                storage.clear_detector_cache(detector_name)
            except Exception as e:
                logger.debug(f"Storage cleanup: {e}")
            
            if errors:
                logger.warning(f"Uninstalled detector {detector_name} with errors: {errors}")
                return True, f"Detector {detector_name} uninstalled with warnings: {'; '.join(errors)}"
            else:
                logger.info(f"Successfully uninstalled detector: {detector_name}")
                return True, f"Detector {detector_name} uninstalled successfully"
            
        except Exception as e:
            logger.error(f"Critical failure during uninstall: {e}")
            import traceback
            traceback.print_exc()
            return False, f"Failed to uninstall: {str(e)}"
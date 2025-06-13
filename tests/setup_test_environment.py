#!/usr/bin/env python3
"""
Automated test environment setup script for CAMF test suite.
Sets up all necessary dependencies, mock data, and configurations for testing.
"""

import os
import sys
import subprocess
import json
import shutil
import tempfile
from pathlib import Path
import venv
import platform
import sqlite3
import time

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestEnvironmentSetup:
    """Handles test environment setup and configuration."""
    
    def __init__(self):
        self.project_root = project_root
        self.tests_dir = self.project_root / "tests"
        self.temp_dir = None
        self.errors = []
        self.warnings = []
        
    def run(self):
        """Run complete setup process."""
        print("=== CAMF Test Environment Setup ===\n")
        
        steps = [
            ("Checking Python version", self.check_python_version),
            ("Creating virtual environment", self.setup_virtual_environment),
            ("Installing dependencies", self.install_dependencies),
            ("Setting up test directories", self.setup_directories),
            ("Creating test database", self.setup_test_database),
            ("Setting up mock services", self.setup_mock_services),
            ("Configuring test settings", self.setup_test_config),
            ("Validating imports", self.validate_imports),
            ("Creating test data", self.create_test_data),
            ("Setting up Docker mocks", self.setup_docker_mocks),
            ("Running sanity check", self.run_sanity_check)
        ]
        
        for step_name, step_func in steps:
            print(f"\n[*] {step_name}...")
            try:
                step_func()
                print(f"    ✓ {step_name} completed")
            except Exception as e:
                print(f"    ✗ {step_name} failed: {e}")
                self.errors.append((step_name, str(e)))
        
        self.print_summary()
        
    def check_python_version(self):
        """Check Python version compatibility."""
        version = sys.version_info
        if version < (3, 8):
            raise Exception(f"Python 3.8+ required, found {version.major}.{version.minor}")
        print(f"    Python {version.major}.{version.minor}.{version.micro} detected")
        
    def setup_virtual_environment(self):
        """Set up virtual environment for testing."""
        venv_path = self.project_root / "test_venv"
        
        if not venv_path.exists():
            print("    Creating new virtual environment...")
            venv.create(venv_path, with_pip=True)
        else:
            print("    Virtual environment already exists")
            
        # Activate instructions
        if platform.system() == "Windows":
            activate_cmd = f"{venv_path}\\Scripts\\activate"
        else:
            activate_cmd = f"source {venv_path}/bin/activate"
            
        print(f"    To activate: {activate_cmd}")
        
    def install_dependencies(self):
        """Install all required dependencies."""
        requirements_files = [
            self.project_root / "requirements.txt",
            self.tests_dir / "requirements-test.txt"
        ]
        
        for req_file in requirements_files:
            if req_file.exists():
                print(f"    Installing from {req_file.name}...")
                subprocess.run([
                    sys.executable, "-m", "pip", "install", "-r", str(req_file)
                ], capture_output=True, check=True)
            else:
                self.warnings.append(f"Requirements file not found: {req_file}")
                
    def setup_directories(self):
        """Create necessary test directories."""
        # Create temp directory for test data
        self.temp_dir = tempfile.mkdtemp(prefix="camf_test_")
        print(f"    Created temp directory: {self.temp_dir}")
        
        # Create test subdirectories
        test_dirs = [
            "storage",
            "frames",
            "exports",
            "detector_workspaces",
            "uploads",
            "cache"
        ]
        
        for dir_name in test_dirs:
            dir_path = Path(self.temp_dir) / dir_name
            dir_path.mkdir(exist_ok=True)
            
        # Create test data directory in project
        test_data_dir = self.tests_dir / "test_data"
        test_data_dir.mkdir(exist_ok=True)
        
    def setup_test_database(self):
        """Set up test database with schema."""
        db_path = Path(self.temp_dir) / "storage" / "test.db"
        
        # Create database schema
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Create tables (simplified schema for testing)
        schema = """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(255) NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS scenes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            name VARCHAR(255) NOT NULL,
            detector_configs TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        );
        
        CREATE TABLE IF NOT EXISTS angles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scene_id INTEGER NOT NULL,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scene_id) REFERENCES scenes(id)
        );
        
        CREATE TABLE IF NOT EXISTS takes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            angle_id INTEGER NOT NULL,
            name VARCHAR(255) NOT NULL,
            take_number INTEGER NOT NULL,
            is_reference BOOLEAN DEFAULT FALSE,
            status VARCHAR(50) DEFAULT 'idle',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (angle_id) REFERENCES angles(id)
        );
        
        CREATE TABLE IF NOT EXISTS frames (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            take_id INTEGER NOT NULL,
            frame_number INTEGER NOT NULL,
            timestamp REAL NOT NULL,
            file_path VARCHAR(500),
            detector_results TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (take_id) REFERENCES takes(id)
        );
        """
        
        cursor.executescript(schema)
        conn.commit()
        conn.close()
        
        print(f"    Created test database: {db_path}")
        
    def setup_mock_services(self):
        """Set up mock service configurations."""
        # Create mock service registry
        service_registry = {
            "services": {
                "storage": {
                    "host": "localhost",
                    "port": 8001,
                    "status": "healthy"
                },
                "capture": {
                    "host": "localhost", 
                    "port": 8002,
                    "status": "healthy"
                },
                "detector_framework": {
                    "host": "localhost",
                    "port": 8003,
                    "status": "healthy"
                },
                "export": {
                    "host": "localhost",
                    "port": 8004,
                    "status": "healthy"
                }
            }
        }
        
        registry_path = Path(self.temp_dir) / "service_registry.json"
        with open(registry_path, 'w') as f:
            json.dump(service_registry, f, indent=2)
            
        print(f"    Created service registry: {registry_path}")
        
    def setup_test_config(self):
        """Create test configuration file."""
        test_config = {
            "app": {
                "name": "CAMF Test",
                "version": "1.0.0",
                "debug": True
            },
            "api": {
                "host": "localhost",
                "port": 8000,
                "workers": 1
            },
            "storage": {
                "database_url": f"sqlite:///{self.temp_dir}/storage/test.db",
                "frame_storage_path": f"{self.temp_dir}/frames"
            },
            "capture": {
                "mock_mode": True,
                "mock_frame_rate": 30
            },
            "detectors": {
                "mock_mode": True,
                "docker_enabled": False,
                "timeout": 5
            },
            "test": {
                "temp_dir": self.temp_dir,
                "fast_mode": True
            }
        }
        
        config_path = self.tests_dir / "test_config.json"
        with open(config_path, 'w') as f:
            json.dump(test_config, f, indent=2)
            
        # Set environment variable
        os.environ["CAMF_TEST_CONFIG"] = str(config_path)
        print(f"    Created test config: {config_path}")
        
    def validate_imports(self):
        """Validate that all test imports work."""
        # Create a test import script
        import_test = """
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    # Test core imports
    from CAMF.common.models import Project, Scene, Angle, Take, Frame
    from CAMF.common.config import Config
    from CAMF.common.utils import Timer
    print("✓ Common imports successful")
    
    # Test service imports (may fail if not all implemented)
    try:
        from CAMF.services.api_gateway.main import app
        print("✓ API Gateway import successful")
    except ImportError as e:
        print(f"⚠ API Gateway import failed: {e}")
    
    try:
        from CAMF.services.storage.database import init_db
        print("✓ Storage import successful")
    except ImportError as e:
        print(f"⚠ Storage import failed: {e}")
        
    try:
        from CAMF.services.capture.main import CaptureService
        print("✓ Capture import successful")
    except ImportError as e:
        print(f"⚠ Capture import failed: {e}")
        
    try:
        from CAMF.services.detector_framework.main import DetectorFramework
        print("✓ Detector Framework import successful")
    except ImportError as e:
        print(f"⚠ Detector Framework import failed: {e}")
        
except Exception as e:
    print(f"✗ Import validation failed: {e}")
    sys.exit(1)
"""
        
        # Run import test
        result = subprocess.run(
            [sys.executable, "-c", import_test],
            capture_output=True,
            text=True,
            cwd=str(self.project_root)
        )
        
        print(result.stdout)
        if result.returncode != 0:
            self.warnings.append("Some imports failed - tests may need adjustment")
            
    def create_test_data(self):
        """Create sample test data files."""
        test_data_dir = self.tests_dir / "test_data"
        
        # Create sample images
        try:
            import numpy as np
            import cv2
            
            # Create test frames
            for i in range(5):
                img = np.full((480, 640, 3), i * 50, dtype=np.uint8)
                cv2.putText(img, f"Frame {i}", (50, 50), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                           
                img_path = test_data_dir / f"test_frame_{i}.jpg"
                cv2.imwrite(str(img_path), img)
                
            print("    Created test images")
        except ImportError:
            self.warnings.append("OpenCV not installed - skipping test image creation")
            
        # Create mock detector config
        detector_config = {
            "name": "TestDetector",
            "version": "1.0.0",
            "supported_formats": ["jpeg", "png"],
            "parameters": {
                "threshold": 0.8,
                "mode": "test"
            }
        }
        
        config_path = test_data_dir / "test_detector.json"
        with open(config_path, 'w') as f:
            json.dump(detector_config, f, indent=2)
            
    def setup_docker_mocks(self):
        """Set up Docker mocks for testing."""
        # Create mock Docker responses
        docker_mocks = {
            "containers": [
                {
                    "id": "mock_container_123",
                    "name": "camf_detector_test",
                    "status": "running",
                    "image": "camf/test-detector:latest"
                }
            ],
            "images": [
                {
                    "id": "mock_image_456",
                    "tags": ["camf/test-detector:latest"],
                    "size": 100 * 1024 * 1024  # 100MB
                }
            ]
        }
        
        mock_path = self.tests_dir / "test_data" / "docker_mocks.json"
        with open(mock_path, 'w') as f:
            json.dump(docker_mocks, f, indent=2)
            
    def run_sanity_check(self):
        """Run a simple sanity check test."""
        sanity_test = """
import pytest
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_sanity():
    '''Basic sanity check.'''
    assert True
    
def test_temp_dir():
    '''Check temp directory exists.'''
    import os
    temp_dir = os.environ.get('CAMF_TEST_TEMP_DIR')
    assert temp_dir is not None
    assert Path(temp_dir).exists()

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
"""
        
        # Save sanity test
        sanity_path = self.tests_dir / "test_sanity.py"
        with open(sanity_path, 'w') as f:
            f.write(sanity_test)
            
        # Set temp dir environment variable
        os.environ['CAMF_TEST_TEMP_DIR'] = self.temp_dir
        
        # Run sanity test
        result = subprocess.run(
            [sys.executable, str(sanity_path)],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("    Sanity check passed!")
        else:
            raise Exception(f"Sanity check failed:\n{result.stdout}\n{result.stderr}")
            
    def print_summary(self):
        """Print setup summary."""
        print("\n" + "="*50)
        print("SETUP SUMMARY")
        print("="*50)
        
        if not self.errors:
            print("\n✓ All setup steps completed successfully!")
        else:
            print(f"\n✗ Setup completed with {len(self.errors)} errors:")
            for step, error in self.errors:
                print(f"  - {step}: {error}")
                
        if self.warnings:
            print(f"\n⚠ {len(self.warnings)} warnings:")
            for warning in self.warnings:
                print(f"  - {warning}")
                
        print(f"\nTest environment directory: {self.temp_dir}")
        print(f"Test config: {self.tests_dir / 'test_config.json'}")
        
        print("\nNext steps:")
        print("1. Activate virtual environment (if created)")
        print("2. Run tests with: python tests/run_all_tests.py")
        print("3. Or run specific tests: pytest tests/test_common_modules.py")
        
        # Create environment file
        env_file = self.tests_dir / ".test_env"
        with open(env_file, 'w') as f:
            f.write(f"CAMF_TEST_TEMP_DIR={self.temp_dir}\n")
            f.write(f"CAMF_TEST_CONFIG={self.tests_dir / 'test_config.json'}\n")
            f.write(f"PYTHONPATH={self.project_root}\n")
            
        print(f"\nEnvironment saved to: {env_file}")
        print("Source it with: source tests/.test_env")


def main():
    """Main entry point."""
    setup = TestEnvironmentSetup()
    
    try:
        setup.run()
        return 0
    except KeyboardInterrupt:
        print("\n\nSetup interrupted by user")
        return 1
    except Exception as e:
        print(f"\n\nSetup failed with error: {e}")
        return 1
    finally:
        # Cleanup on failure
        if setup.errors and setup.temp_dir:
            print(f"\nCleaning up temp directory: {setup.temp_dir}")
            shutil.rmtree(setup.temp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
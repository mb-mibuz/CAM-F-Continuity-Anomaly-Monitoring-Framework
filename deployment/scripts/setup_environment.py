# deployment/scripts/setup_environment.py
"""
Setup development environment for CAMF.
Installs all required dependencies and prepares the system.
"""

import subprocess
import sys
import os
from pathlib import Path


def setup_environment():
    """Setup CAMF development environment."""
    print("Setting up CAMF development environment...")
    
    # Get project root
    project_root = Path(__file__).parent.parent.parent
    os.chdir(project_root)
    
    # Create virtual environment if it doesn't exist
    venv_path = project_root / "venv"
    if not venv_path.exists():
        print("Creating virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", "venv"], check=True)
    
    # Activate virtual environment
    if sys.platform == "win32":
        activate_cmd = str(venv_path / "Scripts" / "activate.bat")
        python_exe = str(venv_path / "Scripts" / "python.exe")
    else:
        activate_cmd = f"source {venv_path / 'bin' / 'activate'}"
        python_exe = str(venv_path / "bin" / "python")
    
    print(f"To activate virtual environment, run: {activate_cmd}")
    
    # Install requirements
    print("Installing Python dependencies...")
    requirements = [
        "numpy>=1.20.0",
        "opencv-python>=4.5.0",
        "pillow>=8.0.0",
        "sqlalchemy>=2.0.0",
        "pydantic>=2.0.0",
        "fastapi>=0.100.0",
        "uvicorn>=0.23.0",
        "python-multipart>=0.0.6",
        "aiofiles>=23.0.0",
        "psutil>=5.9.0",
        "GPUtil>=1.4.0",
        "mss>=9.0.0",
        "pywin32>=305; sys_platform=='win32'",
        "python-dotenv>=1.0.0",
    ]
    
    # Development dependencies
    dev_requirements = [
        "pytest>=7.0.0",
        "pytest-asyncio>=0.21.0",
        "pytest-cov>=4.0.0",
        "black>=23.0.0",
        "flake8>=6.0.0",
        "mypy>=1.0.0",
        "pyinstaller>=5.0.0",
    ]
    
    # Install production dependencies
    for req in requirements:
        subprocess.run([python_exe, "-m", "pip", "install", req], check=True)
    
    # Ask about dev dependencies
    install_dev = input("Install development dependencies? (y/n): ").lower() == 'y'
    if install_dev:
        for req in dev_requirements:
            subprocess.run([python_exe, "-m", "pip", "install", req], check=True)
    
    # Setup frontend
    frontend_path = project_root / "CAMF" / "frontend"
    if frontend_path.exists():
        print("Setting up frontend...")
        os.chdir(frontend_path)
        
        # Check if npm is installed
        try:
            subprocess.run(["npm", "--version"], check=True, capture_output=True)
            
            # Install frontend dependencies
            print("Installing frontend dependencies...")
            subprocess.run(["npm", "install"], check=True)
            
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("npm not found. Please install Node.js to build the frontend.")
    
    # Create necessary directories
    dirs_to_create = [
        "logs",
        "detectors",
        "detector_environments",
        "benchmark_results",
        "stress_test_results",
        "exports"
    ]
    
    for dir_name in dirs_to_create:
        dir_path = project_root / dir_name
        dir_path.mkdir(exist_ok=True)
        print(f"Created directory: {dir_path}")
    
    # Create .env file if it doesn't exist
    env_file = project_root / ".env"
    if not env_file.exists():
        env_content = """# CAMF Environment Configuration
DEBUG=true
STORAGE_DIR=./projects
DETECTOR_DIR=./detectors
DATABASE_URL=sqlite:///./camf_metadata.db
"""
        env_file.write_text(env_content)
        print("Created .env file")
    
    print("\nEnvironment setup complete!")
    print(f"Activate virtual environment with: {activate_cmd}")
    print("Then run: python -m CAMF.launcher")


if __name__ == "__main__":
    setup_environment()
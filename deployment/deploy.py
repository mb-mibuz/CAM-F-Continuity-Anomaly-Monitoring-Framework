#!/usr/bin/env python3
"""
CAMF Deployment Script

Comprehensive deployment and setup script for the CAMF system.
Handles environment setup, dependency installation, database initialization,
and service startup with health checks.
"""

import os
import sys
import subprocess
import shutil
import argparse
import json
import time
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import platform

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
PROJECT_ROOT = Path(__file__).parent.absolute()
VENV_NAME = "venv"
VENV_PATH = PROJECT_ROOT / VENV_NAME
PYTHON_MIN_VERSION = (3, 9)
NODE_MIN_VERSION = (16, 0)
REQUIRED_DIRS = [
    "data/storage",
    "logs",
    "detector_environments",
    "detector_cache"
]

# Service ports
SERVICE_PORTS = {
    "api_gateway": 8000,
    "frontend": 5173
}

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_colored(message: str, color: str = Colors.OKGREEN):
    """Print colored message to console."""
    print(f"{color}{message}{Colors.ENDC}")


def print_header(message: str):
    """Print section header."""
    print_colored(f"\n{'=' * 60}", Colors.HEADER)
    print_colored(f"{message.center(60)}", Colors.HEADER)
    print_colored(f"{'=' * 60}\n", Colors.HEADER)


def check_command_exists(command: str) -> bool:
    """Check if a command exists in the system PATH."""
    return shutil.which(command) is not None


def run_command(command: List[str], cwd: Optional[Path] = None, 
                capture_output: bool = False, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and handle errors."""
    try:
        logger.debug(f"Running command: {' '.join(command)}")
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=capture_output,
            text=True,
            check=check
        )
        return result
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {' '.join(command)}")
        logger.error(f"Exit code: {e.returncode}")
        if e.stdout:
            logger.error(f"stdout: {e.stdout}")
        if e.stderr:
            logger.error(f"stderr: {e.stderr}")
        raise


def check_python_version() -> bool:
    """Check if Python version meets minimum requirements."""
    current_version = sys.version_info[:2]
    if current_version < PYTHON_MIN_VERSION:
        print_colored(
            f"Python {PYTHON_MIN_VERSION[0]}.{PYTHON_MIN_VERSION[1]}+ required, "
            f"but {current_version[0]}.{current_version[1]} found.",
            Colors.FAIL
        )
        return False
    return True


def check_node_version() -> bool:
    """Check if Node.js version meets minimum requirements."""
    if not check_command_exists("node"):
        print_colored("Node.js not found. Please install Node.js 16+", Colors.FAIL)
        return False
    
    try:
        result = run_command(["node", "--version"], capture_output=True)
        version_str = result.stdout.strip().lstrip('v')
        major, minor = map(int, version_str.split('.')[:2])
        
        if (major, minor) < NODE_MIN_VERSION:
            print_colored(
                f"Node.js {NODE_MIN_VERSION[0]}.{NODE_MIN_VERSION[1]}+ required, "
                f"but {major}.{minor} found.",
                Colors.FAIL
            )
            return False
        return True
    except Exception as e:
        logger.error(f"Failed to check Node.js version: {e}")
        return False


def create_virtual_environment():
    """Create Python virtual environment."""
    print_header("Creating Virtual Environment")
    
    if VENV_PATH.exists():
        print_colored(f"Virtual environment already exists at {VENV_PATH}", Colors.WARNING)
        response = input("Do you want to recreate it? (y/N): ")
        if response.lower() != 'y':
            print("Using existing virtual environment.")
            return
        
        print("Removing existing virtual environment...")
        shutil.rmtree(VENV_PATH)
    
    print(f"Creating virtual environment at {VENV_PATH}...")
    run_command([sys.executable, "-m", "venv", str(VENV_PATH)])
    print_colored("✓ Virtual environment created successfully", Colors.OKGREEN)


def get_venv_python() -> str:
    """Get path to Python executable in virtual environment."""
    if platform.system() == "Windows":
        return str(VENV_PATH / "Scripts" / "python.exe")
    return str(VENV_PATH / "bin" / "python")


def get_venv_pip() -> str:
    """Get path to pip executable in virtual environment."""
    if platform.system() == "Windows":
        return str(VENV_PATH / "Scripts" / "pip.exe")
    return str(VENV_PATH / "bin" / "pip")


def install_python_dependencies():
    """Install Python dependencies."""
    print_header("Installing Python Dependencies")
    
    requirements_file = PROJECT_ROOT / "requirements.txt"
    if not requirements_file.exists():
        print_colored("requirements.txt not found!", Colors.FAIL)
        return False
    
    venv_pip = get_venv_pip()
    
    # Upgrade pip first
    print("Upgrading pip...")
    run_command([venv_pip, "install", "--upgrade", "pip"])
    
    # Install requirements
    print("Installing requirements...")
    run_command([venv_pip, "install", "-r", str(requirements_file)])
    
    print_colored("✓ Python dependencies installed successfully", Colors.OKGREEN)
    return True


def install_frontend_dependencies():
    """Install frontend dependencies."""
    print_header("Installing Frontend Dependencies")
    
    frontend_dir = PROJECT_ROOT / "CAMF" / "frontend"
    if not frontend_dir.exists():
        print_colored("Frontend directory not found!", Colors.FAIL)
        return False
    
    package_json = frontend_dir / "package.json"
    if not package_json.exists():
        print_colored("package.json not found!", Colors.FAIL)
        return False
    
    # Check if npm is installed
    if not check_command_exists("npm"):
        print_colored("npm not found. Please install Node.js and npm.", Colors.FAIL)
        return False
    
    print("Installing frontend dependencies...")
    run_command(["npm", "install"], cwd=frontend_dir)
    
    print_colored("✓ Frontend dependencies installed successfully", Colors.OKGREEN)
    return True


def create_directories():
    """Create required directories."""
    print_header("Creating Required Directories")
    
    for dir_path in REQUIRED_DIRS:
        full_path = PROJECT_ROOT / dir_path
        if not full_path.exists():
            full_path.mkdir(parents=True, exist_ok=True)
            print(f"Created: {dir_path}")
        else:
            print(f"Exists: {dir_path}")
    
    print_colored("✓ All directories created successfully", Colors.OKGREEN)


def create_env_files():
    """Create environment configuration files."""
    print_header("Creating Environment Files")
    
    # Backend .env file
    backend_env = PROJECT_ROOT / ".env"
    if not backend_env.exists():
        print("Creating backend .env file...")
        backend_env_content = """# CAMF Backend Configuration

# Database
DATABASE_PATH=data/metadata.db
STORAGE_PATH=data/storage

# API Settings
API_HOST=0.0.0.0
API_PORT=8000

# Capture Settings
CAPTURE_FPS=30
CAPTURE_QUALITY=95

# Performance Settings
PERFORMANCE_CACHE_SIZE=1000
PERFORMANCE_MAX_DETECTOR_PROCESSES=5
PERFORMANCE_GPU_MEMORY_FRACTION=0.8
PERFORMANCE_ENABLE_PROFILING=false

# GPU Settings
GPU_ENABLED=true
GPU_DEVICE_ID=0

# Camera Settings
CAMERA_BACKEND=auto

# Logging
LOG_LEVEL=INFO
"""
        backend_env.write_text(backend_env_content)
        print_colored("✓ Backend .env file created", Colors.OKGREEN)
    else:
        print_colored("Backend .env file already exists", Colors.WARNING)
    
    # Frontend .env file
    frontend_env = PROJECT_ROOT / "CAMF" / "frontend" / ".env.local"
    if not frontend_env.exists():
        print("Creating frontend .env.local file...")
        frontend_env_content = """# CAMF Frontend Configuration

# API Configuration
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_WEBSOCKET_URL=ws://127.0.0.1:8000

# Debug Mode
VITE_DEBUG_MODE=false
"""
        frontend_env.write_text(frontend_env_content)
        print_colored("✓ Frontend .env.local file created", Colors.OKGREEN)
    else:
        print_colored("Frontend .env.local file already exists", Colors.WARNING)


def initialize_database():
    """Initialize the database."""
    print_header("Initializing Database")
    
    venv_python = get_venv_python()
    
    # Run database initialization script
    init_script = PROJECT_ROOT / "scripts" / "init_db.py"
    if init_script.exists():
        print("Running database initialization script...")
        run_command([venv_python, str(init_script)])
        print_colored("✓ Database initialized successfully", Colors.OKGREEN)
    else:
        print_colored("Database initialization script not found, skipping...", Colors.WARNING)
    
    # Run migrations if alembic is configured
    alembic_ini = PROJECT_ROOT / "alembic.ini"
    if alembic_ini.exists():
        print("Running database migrations...")
        try:
            run_command([venv_python, "-m", "alembic", "upgrade", "head"], cwd=PROJECT_ROOT)
            print_colored("✓ Database migrations completed", Colors.OKGREEN)
        except Exception as e:
            print_colored(f"Migration failed (this might be okay): {e}", Colors.WARNING)


def check_service_health(timeout: int = 30):
    """Check if all services are healthy."""
    print_header("Checking Service Health")
    
    venv_python = get_venv_python()
    health_script = PROJECT_ROOT / "check_services_health.py"
    
    if not health_script.exists():
        print_colored("Health check script not found", Colors.WARNING)
        return True
    
    print(f"Waiting for services to be ready (timeout: {timeout}s)...")
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            result = run_command(
                [venv_python, str(health_script), "--json"],
                capture_output=True,
                check=False
            )
            
            if result.returncode == 0:
                print_colored("✓ All services are healthy", Colors.OKGREEN)
                return True
            
            # Parse JSON output if available
            try:
                health_data = json.loads(result.stdout)
                unhealthy = [s for s in health_data.get("services", {}).values() if not s.get("healthy")]
                if unhealthy:
                    print(f"Waiting for {len(unhealthy)} service(s)...")
            except:
                pass
            
            time.sleep(2)
        except Exception as e:
            logger.debug(f"Health check error: {e}")
            time.sleep(2)
    
    print_colored("⚠ Some services may not be fully ready", Colors.WARNING)
    return False


def start_services(dev_mode: bool = True):
    """Start all services."""
    print_header("Starting Services")
    
    venv_python = get_venv_python()
    
    if dev_mode:
        # Development mode - use start.py
        start_script = PROJECT_ROOT / "start.py"
        if start_script.exists():
            print("Starting all services in development mode...")
            print_colored(
                "Services will start in a new terminal. Press Ctrl+C there to stop.",
                Colors.OKCYAN
            )
            
            if platform.system() == "Windows":
                subprocess.Popen(["start", "cmd", "/k", venv_python, str(start_script)], shell=True)
            elif platform.system() == "Darwin":  # macOS
                subprocess.Popen(["osascript", "-e", f'tell app "Terminal" to do script "{venv_python} {start_script}"'])
            else:  # Linux
                subprocess.Popen(["gnome-terminal", "--", venv_python, str(start_script)])
            
            # Wait a bit for services to start
            time.sleep(5)
            
            # Check health
            check_service_health()
        else:
            print_colored("start.py not found!", Colors.FAIL)
    else:
        # Production mode - start services individually
        print("Starting services in production mode...")
        # TODO: Implement production service startup
        print_colored("Production mode not yet implemented", Colors.WARNING)


def print_summary():
    """Print deployment summary."""
    print_header("Deployment Complete!")
    
    print("CAMF has been successfully deployed.")
    print("\nService URLs:")
    print(f"  - API Gateway: http://localhost:{SERVICE_PORTS['api_gateway']}")
    print(f"  - Frontend: http://localhost:{SERVICE_PORTS['frontend']}")
    
    print("\nNext steps:")
    print("  1. Open the frontend URL in your browser")
    print("  2. Create a new project")
    print("  3. Configure detectors for your scenes")
    print("  4. Start capturing!")
    
    print("\nUseful commands:")
    print(f"  - Start services: {get_venv_python()} start.py")
    print(f"  - Check health: {get_venv_python()} check_services_health.py")
    print(f"  - Run tests: {get_venv_python()} -m pytest")
    
    print_colored("\n✓ Deployment successful!", Colors.OKGREEN)


def main():
    """Main deployment function."""
    parser = argparse.ArgumentParser(description="Deploy CAMF system")
    parser.add_argument("--skip-venv", action="store_true", help="Skip virtual environment creation")
    parser.add_argument("--skip-deps", action="store_true", help="Skip dependency installation")
    parser.add_argument("--skip-frontend", action="store_true", help="Skip frontend setup")
    parser.add_argument("--skip-db", action="store_true", help="Skip database initialization")
    parser.add_argument("--no-start", action="store_true", help="Don't start services after setup")
    parser.add_argument("--production", action="store_true", help="Deploy in production mode")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    print_colored("""
     ██████╗ █████╗ ███╗   ███╗███████╗
    ██╔════╝██╔══██╗████╗ ████║██╔════╝
    ██║     ███████║██╔████╔██║█████╗  
    ██║     ██╔══██║██║╚██╔╝██║██╔══╝  
    ╚██████╗██║  ██║██║ ╚═╝ ██║██║     
     ╚═════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝     
    
    Continuity Assistance and Monitoring Framework
    """, Colors.HEADER)
    
    try:
        # Check prerequisites
        print_header("Checking Prerequisites")
        if not check_python_version():
            return 1
        if not check_node_version():
            return 1
        print_colored("✓ All prerequisites satisfied", Colors.OKGREEN)
        
        # Create virtual environment
        if not args.skip_venv:
            create_virtual_environment()
        
        # Install dependencies
        if not args.skip_deps:
            if not install_python_dependencies():
                return 1
        
        if not args.skip_frontend:
            if not install_frontend_dependencies():
                return 1
        
        # Create directories and config files
        create_directories()
        create_env_files()
        
        # Initialize database
        if not args.skip_db:
            initialize_database()
        
        # Start services
        if not args.no_start:
            start_services(dev_mode=not args.production)
        
        # Print summary
        print_summary()
        
        return 0
        
    except KeyboardInterrupt:
        print_colored("\n\nDeployment cancelled by user", Colors.WARNING)
        return 1
    except Exception as e:
        print_colored(f"\n\nDeployment failed: {e}", Colors.FAIL)
        logger.exception("Deployment error")
        return 1


if __name__ == "__main__":
    sys.exit(main())
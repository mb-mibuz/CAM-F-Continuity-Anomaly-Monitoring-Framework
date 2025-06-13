# deployment/scripts/package_release.py
"""
Package CAMF for release.
Creates distributable packages for different platforms.
"""

import os
import sys
import shutil
import subprocess
import zipfile
from pathlib import Path
from datetime import datetime
import json


def package_release(version: str = None):
    """Create release packages for CAMF."""
    print("Packaging CAMF for release...")
    
    # Get project root
    project_root = Path(__file__).parent.parent.parent
    os.chdir(project_root)
    
    # Determine version
    if not version:
        version = input("Enter version number (e.g., 1.0.0): ")
    
    # Create release directory
    release_dir = project_root / "releases" / f"v{version}"
    release_dir.mkdir(parents=True, exist_ok=True)
    
    # Build executable
    print("Building executable...")
    build_script = project_root / "deployment" / "pyinstaller" / "build_exe.py"
    result = subprocess.run([sys.executable, str(build_script)], capture_output=True)
    
    if result.returncode != 0:
        print("Build failed!")
        return False
    
    # Create Windows installer package
    create_windows_package(project_root, release_dir, version)
    
    # Create portable package
    create_portable_package(project_root, release_dir, version)
    
    # Create source package
    create_source_package(project_root, release_dir, version)
    
    # Generate release notes
    generate_release_notes(release_dir, version)
    
    print(f"\nRelease packages created in: {release_dir}")
    return True


def create_windows_package(project_root: Path, release_dir: Path, version: str):
    """Create Windows installer package."""
    print("Creating Windows installer package...")
    
    # This would use a tool like NSIS or Inno Setup
    # For now, we'll just copy the dist folder
    
    dist_package = project_root / "dist" / "CAMF_Package"
    if dist_package.exists():
        windows_package = release_dir / f"CAMF-{version}-windows-x64.zip"
        
        with zipfile.ZipFile(windows_package, 'w', zipfile.ZIP_DEFLATED) as zf:
            for item in dist_package.rglob('*'):
                if item.is_file():
                    arcname = item.relative_to(dist_package.parent)
                    zf.write(item, arcname)
        
        print(f"Created: {windows_package}")


def create_portable_package(project_root: Path, release_dir: Path, version: str):
    """Create portable package (no installation required)."""
    print("Creating portable package...")
    
    portable_dir = release_dir / f"CAMF-{version}-portable"
    portable_dir.mkdir(exist_ok=True)
    
    # Copy executable and required files
    dist_dir = project_root / "dist" / "CAMF_Package"
    if dist_dir.exists():
        shutil.copytree(dist_dir, portable_dir, dirs_exist_ok=True)
    
    # Add batch file for easy launch
    batch_content = """@echo off
echo Starting CAMF...
start "" "%~dp0\CAMF.exe"
"""
    (portable_dir / "Start_CAMF.bat").write_text(batch_content)
    
    # Create zip
    portable_zip = release_dir / f"CAMF-{version}-portable.zip"
    with zipfile.ZipFile(portable_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for item in portable_dir.rglob('*'):
            if item.is_file():
                arcname = item.relative_to(portable_dir.parent)
                zf.write(item, arcname)
    
    # Clean up directory
    shutil.rmtree(portable_dir)
    
    print(f"Created: {portable_zip}")


def create_source_package(project_root: Path, release_dir: Path, version: str):
    """Create source code package."""
    print("Creating source package...")
    
    source_zip = release_dir / f"CAMF-{version}-source.zip"
    
    # Files to exclude
    exclude_patterns = [
        '__pycache__',
        '*.pyc',
        '.git',
        'venv',
        'build',
        'dist',
        'node_modules',
        '.pytest_cache',
        '*.egg-info',
        '.env',
        'projects/*',
        'detector_environments/*',
        'benchmark_results/*',
        'stress_test_results/*'
    ]
    
    def should_include(path: Path) -> bool:
        path_str = str(path)
        for pattern in exclude_patterns:
            if pattern in path_str:
                return False
        return True
    
    with zipfile.ZipFile(source_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for item in project_root.rglob('*'):
            if item.is_file() and should_include(item):
                arcname = f"CAMF-{version}/" + str(item.relative_to(project_root))
                zf.write(item, arcname)
    
    print(f"Created: {source_zip}")


def generate_release_notes(release_dir: Path, version: str):
    """Generate release notes."""
    print("Generating release notes...")
    
    notes = f"""# CAMF Release v{version}

Release Date: {datetime.now().strftime('%Y-%m-%d')}

## Installation

### Windows Installer
1. Download `CAMF-{version}-windows-x64.zip`
2. Extract and run the installer
3. Follow installation wizard

### Portable Version
1. Download `CAMF-{version}-portable.zip`
2. Extract to desired location
3. Run `Start_CAMF.bat` or `CAMF.exe`

### From Source
1. Download `CAMF-{version}-source.zip`
2. Extract and run:
python deployment/scripts/setup_environment.py
python -m CAMF.launcher
## System Requirements

- Windows 10 or later (64-bit)
- 8GB RAM minimum (16GB recommended)
- Python 3.8+ (for source installation)
- OpenGL 3.3+ compatible graphics
- 10GB free disk space

## What's New

### Features
- Real-time continuity monitoring
- Plugin-based detector system
- GPU acceleration support
- Performance optimization
- Automatic detector recovery
- Comprehensive stress testing

### Improvements
- Enhanced frame caching with predictive pre-loading
- Resource optimization with CPU affinity
- Professional performance monitoring
- Detector health tracking

### Bug Fixes
- Various stability improvements
- Memory leak fixes
- UI responsiveness improvements

## Known Issues

- Some detectors may require manual GPU allocation on multi-GPU systems
- High frame rates (>60 fps) may cause UI lag on slower systems

## Documentation

Full documentation available at: https://github.com/mb-mibuz/CAM-F-Continuity-Anomaly-Monitoring-Framework/wiki

## Support

Report issues at: https://github.com/mb-mibuz/CAM-F-Continuity-Anomaly-Monitoring-Framework/issues
"""
 
    notes_file = release_dir / f"RELEASE_NOTES_v{version}.md"
    notes_file.write_text(notes)
    
    print(f"Created: {notes_file}")


def create_checksums(release_dir: Path):
    """Create checksums for release files."""
    import hashlib
    
    checksum_file = release_dir / "checksums.txt"
    
    with open(checksum_file, 'w') as f:
        for file_path in release_dir.glob("*.zip"):
            # Calculate SHA256
            sha256 = hashlib.sha256()
            with open(file_path, 'rb') as file:
                for chunk in iter(lambda: file.read(4096), b""):
                    sha256.update(chunk)
            
            f.write(f"{sha256.hexdigest()}  {file_path.name}\n")
    
    print(f"Created: {checksum_file}")


if __name__ == "__main__":
    version = sys.argv[1] if len(sys.argv) > 1 else None
    package_release(version)
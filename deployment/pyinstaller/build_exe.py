# deployment/pyinstaller/build_exe.py
"""
Build executable for CAMF using PyInstaller.
Creates a standalone .exe file with all dependencies.
"""

import datetime
import os
import sys
import shutil
import subprocess
from pathlib import Path
import json


def build_executable():
    """Build CAMF executable."""
    print("Building CAMF executable...")
    
    # Get project root
    project_root = Path(__file__).parent.parent.parent
    os.chdir(project_root)
    
    # Clean previous builds
    for dir_name in ['build', 'dist']:
        dir_path = project_root / dir_name
        if dir_path.exists():
            shutil.rmtree(dir_path)
            print(f"Cleaned {dir_name} directory")
    
    # Create spec file if it doesn't exist
    spec_file = project_root / "deployment" / "pyinstaller" / "camf.spec"
    if not spec_file.exists():
        create_spec_file(spec_file, project_root)
    
    # Run PyInstaller
    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        str(spec_file),
        "--clean",
        "--noconfirm"
    ]
    
    print("Running PyInstaller...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Build failed:\n{result.stderr}")
        return False
    
    print("Build completed successfully!")
    
    # Create distribution package
    create_distribution_package(project_root)
    
    return True


def create_spec_file(spec_path: Path, project_root: Path):
    """Create PyInstaller spec file."""
    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

# Add project root to path
project_root = r"{project_root}"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

block_cipher = None

# Collect all CAMF modules
from PyInstaller.utils.hooks import collect_all
camf_datas = []
camf_binaries = []
camf_hiddenimports = []

# Collect CAMF package
datas, binaries, hiddenimports = collect_all('CAMF')
camf_datas.extend(datas)
camf_binaries.extend(binaries)
camf_hiddenimports.extend(hiddenimports)

# Add detector templates and other data files
camf_datas.extend([
    ('CAMF/detectors', 'CAMF/detectors'),
    ('CAMF/services/detector_framework/templates', 'CAMF/services/detector_framework/templates'),
])

# Hidden imports for dynamic loading
camf_hiddenimports.extend([
    'cv2',
    'numpy',
    'sqlalchemy',
    'pydantic',
    'PIL',
    'mss',
    'GPUtil',
    'psutil',
    'win32gui',
    'win32ui',
    'win32con',
])

a = Analysis(
    ['CAMF/launcher.py'],
    pathex=[project_root],
    binaries=camf_binaries,
    datas=camf_datas,
    hiddenimports=camf_hiddenimports,
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'pandas',
        'scipy',
        'notebook',
        'jupyterlab',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='CAMF',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if Path('assets/icon.ico').exists() else None,
    version='version_info.txt' if Path('version_info.txt').exists() else None,
)
'''
    
    spec_path.write_text(spec_content)
    print(f"Created spec file: {spec_path}")


def create_distribution_package(project_root: Path):
    """Create distribution package with executable and required files."""
    dist_dir = project_root / "dist"
    package_dir = dist_dir / "CAMF_Package"
    
    # Create package directory
    package_dir.mkdir(exist_ok=True)
    
    # Copy executable
    exe_path = dist_dir / "CAMF.exe"
    if exe_path.exists():
        shutil.copy2(exe_path, package_dir / "CAMF.exe")
    
    # Create directory structure
    dirs_to_create = [
        "detectors",
        "detector_environments",
        "projects",
        "logs",
        "config"
    ]
    
    for dir_name in dirs_to_create:
        (package_dir / dir_name).mkdir(exist_ok=True)
    
    # Copy detector templates
    templates_src = project_root / "CAMF" / "services" / "detector_framework" / "templates"
    if templates_src.exists():
        shutil.copytree(templates_src, package_dir / "templates", dirs_exist_ok=True)
    
    # Create default configuration
    default_config = {
        "debug": False,
        "storage": {
            "base_dir": "./projects"
        },
        "detector": {
            "detector_dir": "./detectors"
        }
    }
    
    config_file = package_dir / "config" / "default.json"
    with open(config_file, 'w') as f:
        json.dump(default_config, f, indent=2)
    
    # Create README
    readme_content = """# CAMF - Continuity Monitoring System

## Installation

1. Extract all files to your desired location
2. Run CAMF.exe to start the application

## Directory Structure

- `detectors/` - Place detector packages here
- `projects/` - Your continuity monitoring projects
- `logs/` - Application logs
- `config/` - Configuration files

## Getting Started

1. Launch CAMF.exe
2. Create a new project
3. Install detectors (drag & drop .zip files)
4. Start monitoring!

## System Requirements

- Windows 10 or later
- 8GB RAM minimum (16GB recommended)
- OpenGL 3.3+ compatible graphics
- 10GB free disk space

## Support

For issues and documentation, visit: https://github.com/mb-mibuz/CAM-F-Continuity-Anomaly-Monitoring-Framework
"""
    
    (package_dir / "README.txt").write_text(readme_content)
    
    # Create version info
    version_info = {
        "version": "1.0.0",
        "build_date": datetime.now().isoformat(),
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    }
    
    with open(package_dir / "version.json", 'w') as f:
        json.dump(version_info, f, indent=2)
    
    print(f"Distribution package created: {package_dir}")


if __name__ == "__main__":
    build_executable()
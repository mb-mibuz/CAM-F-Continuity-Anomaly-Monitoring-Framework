from setuptools import setup, find_packages
import os

# Read requirements from requirements.txt
def read_requirements():
    with open('requirements.txt') as f:
        return [line.strip() for line in f 
                if line.strip() and not line.startswith('#')]

# Read long description from README.md
def read_long_description():
    if os.path.exists('README.md'):
        with open('README.md', encoding='utf-8') as f:
            return f.read()
    return ""

setup(
    name="CAMF",
    version="0.1.0",
    author="CAMF Development Team",
    description="Continuity Assistance and Monitoring Framework",
    long_description=read_long_description(),
    long_description_content_type="text/markdown",
    url="https://github.com/your-org/CAMF",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: CC0 1.0 Universal (CC0 1.0) Public Domain Dedication",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.10,<3.13",
    install_requires=read_requirements(),
    entry_points={
        'console_scripts': [
            'camf=CAMF.launcher:main',
            'camf-detector=CAMF.detector_cli:cli',
        ],
    },
    include_package_data=True,
    package_data={
        'CAMF': [
            'frontend/dist/**/*',
            'detectors/**/*',
        ],
    },
)
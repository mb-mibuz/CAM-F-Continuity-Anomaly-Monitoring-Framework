# CAMF - Continuity Anomaly Monitoring Framework

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-CC0%201.0-green)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

CAMF is a real-time continuity monitoring system for film and television production. It's the first system designed to detect continuity errors during active filming rather than in post-production, potentially saving the film industry millions in reshoot costs.

## Overview

Continuity errors cost the film industry an estimated £620 million annually through reshoots and corrections. CAMF addresses this by providing real-time monitoring during the typical 5-minute reset periods between takes, allowing crews to catch and fix errors immediately.

### Key Features

- **Real-time Processing**: Analyzes footage at 1.2 fps during take resets
- **Modular Architecture**: Monolithic framework with process-isolated detector plugins
- **Production-Ready**: Installs in minutes on standard laptops with no technical expertise required
- **Extensible**: Community can develop specialized detectors while maintaining footage security
- **Multi-Source Capture**: Supports cameras, screens, and application windows

### Included Detectors

1. **ClockDetector**: Combines YOLOv11 object detection with ResNet50 for analog clocks and PaddleOCR for digital displays
   - Processing time: 1.92 seconds
   - Accuracy: 75.0%

2. **DifferenceDetector**: Uses co-attention networks to identify prop and scene changes
   - Processing time: 6.37 seconds
   - Accuracy: 60.7%

## Quick Start

### Prerequisites

- Python 3.10 or higher (3.10, 3.11, 3.12 supported)
- Node.js 18+ and npm (for frontend)
- Rust (for Tauri desktop app)
- 8GB RAM minimum (16GB recommended)
- 10GB free disk space

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/CAMF.git
   cd CAMF
   ```

2. **Install Python dependencies**
   ```bash
   # Create virtual environment
   python -m venv venv
   
   # Activate virtual environment
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   
   # Install dependencies
   pip install -r requirements.txt
   ```

3. **Install frontend dependencies**
   ```bash
   cd CAMF/frontend
   npm install
   cd ../..
   ```

4. **Run CAMF**
   ```bash
   # Start both backend and frontend
   python start.py
   ```

   This will:
   - Start the backend API on http://localhost:8000
   - Launch the Tauri desktop application

## Development Setup

### Project Structure

```
CAMF/
├── CAMF/                      # Main application code
│   ├── common/               # Shared utilities and models
│   ├── detectors/            # Detector plugins
│   ├── frontend/             # React/Tauri desktop app
│   └── services/             # Backend services
├── data/                     # Database and file storage
├── detector_environments/    # Isolated environments for detectors
├── logs/                     # Application logs
├── tests/                    # Test suite
└── report/                   # Project documentation
```

### Running Individual Components

**Backend only:**
```bash
python -m CAMF.launcher
```

**Frontend only:**
```bash
cd CAMF/frontend
npm run tauri dev
```

**Run tests:**
```bash
# All tests with coverage
pytest --cov=CAMF --cov-report=html

# Specific test categories
python tests/run_all_capture.py
python tests/run_all_storage.py
```

### CLI Tools

CAMF includes a detector development CLI:

```bash
# Create new detector from template
python -m CAMF.detector_cli create MyDetector

# Validate detector package
python -m CAMF.detector_cli validate path/to/detector

# Package detector for distribution
python -m CAMF.detector_cli package path/to/detector

# Compare benchmark results
python -m CAMF.detector_cli compare-benchmarks session1 session2
```

## Usage Workflow

1. **Create Project**: Start a new film production project
2. **Configure Scene**: Set up scene parameters and enable relevant detectors
3. **Capture Reference**: Record the first take as the continuity reference
4. **Monitor Takes**: System automatically compares subsequent takes to reference
5. **Review Anomalies**: Check detected issues between takes
6. **Export Reports**: Generate PDF reports of continuity issues

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
# API Configuration
API_HOST=0.0.0.0
API_PORT=8000

# Database
DATABASE_URL=sqlite:///data/camf_metadata.db

# Storage
STORAGE_PATH=data/storage
MAX_STORAGE_GB=100

# Detector Settings
DETECTOR_TIMEOUT=300
DETECTOR_MAX_MEMORY_MB=4096
```

### Detector Configuration

Each detector can be configured through the UI or by editing `detector.json`:

```json
{
  "name": "ClockDetector",
  "version": "1.0.0",
  "runtime": "python:3.10",
  "entry_point": "detector.py",
  "requirements": "requirements.txt",
  "timeout": 300,
  "memory_limit_mb": 2048
}
```

## Testing

### Unit Tests
```bash
pytest tests/unit/
```

### Integration Tests
```bash
pytest tests/integration/
```

### Performance Tests
```bash
python tests/performance/stress_testing.py
```

### Detector Evaluation
```bash
cd detector_evaluation
./run_direct_evaluations.sh
```

## Security

CAMF implements multiple security layers:

- **Process Isolation**: Detectors run in sandboxed processes
- **Resource Limits**: CPU, memory, and file descriptor constraints
- **Filesystem Isolation**: Temporary workspaces for each detector
- **Environment Sanitization**: Controlled environment variables
- **Network Isolation**: Detectors have no network access

## Performance

- **Frame Processing**: Sub-100ms distribution latency
- **Storage Efficiency**: 70% reduction via video compression
- **Session Duration**: 8+ hours continuous operation
- **Resolution Support**: Up to 4K capture
- **GPU Acceleration**: Available for ML-based detectors

## Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details.

### Developing New Detectors

1. Use the detector CLI to create from template
2. Implement the detector interface
3. Test with the validation tools
4. Submit via pull request

## License

This project is licensed under the CC0 1.0 Universal (CC0 1.0) Public Domain Dedication. See the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Imperial College London Department of Computing
- Film production professionals who provided domain expertise
- Open source communities behind PyTorch, OpenCV, and FastAPI

## Support

- **Issues**: [GitHub Issues](https://github.com/your-org/CAMF/issues)
- **Documentation**: [Full Documentation](https://docs.camf.io)
- **Email**: support@camf.io

## System Requirements

### Minimum Requirements
- **OS**: Windows 10, macOS 10.15+, Ubuntu 20.04+
- **CPU**: 4 cores, 2.4GHz
- **RAM**: 8GB
- **Storage**: 10GB available
- **GPU**: Optional (improves detector performance)

### Recommended Requirements
- **OS**: Latest versions
- **CPU**: 8+ cores, 3.0GHz+
- **RAM**: 16GB+
- **Storage**: 100GB+ SSD
- **GPU**: NVIDIA with 8GB+ VRAM

## Roadmap

- [ ] Additional detector types (costume, makeup, props)
- [ ] Cloud synchronization for multi-unit productions
- [ ] Mobile companion app for on-set notes
- [ ] AI-powered suggestion system
- [ ] Integration with professional camera systems

---

Built with care for the film production community
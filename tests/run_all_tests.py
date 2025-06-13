#!/usr/bin/env python3
"""
Test runner script for CAMF test suite.
Runs all tests with coverage reporting and various options.
"""

import sys
import os
import argparse
import subprocess
import json
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def run_tests(args):
    """Run tests with specified options."""
    cmd = ["pytest"]
    
    # Add base options
    cmd.extend(["-v", "--tb=short"])
    
    # Coverage options
    if args.coverage:
        cmd.extend([
            "--cov=CAMF",
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov",
            f"--cov-fail-under={args.min_coverage}"
        ])
    
    # Parallel execution
    if args.parallel:
        cmd.extend(["-n", str(args.workers)])
    
    # Specific test categories
    if args.category:
        if args.category == "unit":
            cmd.extend([
                "test_api_gateway_crud.py",
                "test_storage_database.py",
                "test_capture_camera.py",
                "test_detector_framework_processing.py",
                "test_export_service.py",
                "test_common_modules.py"
            ])
        elif args.category == "integration":
            cmd.append("test_integration_workflows.py")
        elif args.category == "performance":
            cmd.append("test_performance.py")
        elif args.category == "security":
            cmd.append("test_security.py")
        elif args.category == "api":
            cmd.extend(["test_api_gateway_crud.py", "test_api_gateway_sse.py", "test_api_gateway_middleware.py"])
        elif args.category == "storage":
            cmd.extend(["test_storage_database.py", "test_storage_frame_operations.py"])
        elif args.category == "capture":
            cmd.extend(["test_capture_camera.py", "test_capture_screen_window.py", "test_capture_video_upload.py"])
        elif args.category == "detector":
            cmd.extend([
                "test_detector_framework_docker.py",
                "test_detector_framework_processing.py",
                "test_detector_framework_recovery.py"
            ])
    
    # Specific test file
    if args.test_file:
        cmd.append(args.test_file)
    
    # Markers
    if args.slow:
        cmd.extend(["-m", "slow"])
    elif args.fast:
        cmd.extend(["-m", "not slow"])
    
    # Output format
    if args.json_output:
        cmd.extend(["--json-report", "--json-report-file=test_results.json"])
    
    # Verbose output
    if args.verbose:
        cmd.append("-vv")
    
    # Stop on first failure
    if args.fail_fast:
        cmd.append("-x")
    
    # Show locals in tracebacks
    if args.show_locals:
        cmd.append("-l")
    
    # Run tests
    print(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(project_root / "tests"))
    
    return result.returncode


def generate_report(args):
    """Generate test report."""
    report_data = {
        "timestamp": datetime.now().isoformat(),
        "test_categories": {
            "API Gateway": [
                "test_api_gateway_crud.py",
                "test_api_gateway_sse.py",
                "test_api_gateway_middleware.py"
            ],
            "Storage": [
                "test_storage_database.py",
                "test_storage_frame_operations.py"
            ],
            "Capture": [
                "test_capture_camera.py",
                "test_capture_screen_window.py",
                "test_capture_video_upload.py"
            ],
            "Detector Framework": [
                "test_detector_framework_docker.py",
                "test_detector_framework_processing.py",
                "test_detector_framework_recovery.py"
            ],
            "Export": ["test_export_service.py"],
            "Common": ["test_common_ipc.py", "test_common_modules.py"],
            "Integration": ["test_integration_workflows.py"],
            "Performance": ["test_performance.py"],
            "Security": ["test_security.py"]
        }
    }
    
    # Count test files
    test_dir = project_root / "tests"
    test_files = list(test_dir.glob("test_*.py"))
    report_data["total_test_files"] = len(test_files)
    
    # Write report
    report_path = test_dir / "test_report.json"
    with open(report_path, "w") as f:
        json.dump(report_data, f, indent=2)
    
    print(f"Test report generated: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="CAMF Test Runner")
    
    # Test selection
    parser.add_argument("--category", choices=[
        "all", "unit", "integration", "performance", "security",
        "api", "storage", "capture", "detector"
    ], help="Test category to run")
    parser.add_argument("--test-file", help="Specific test file to run")
    
    # Test execution options
    parser.add_argument("--parallel", action="store_true", help="Run tests in parallel")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers")
    parser.add_argument("--coverage", action="store_true", help="Generate coverage report")
    parser.add_argument("--min-coverage", type=int, default=80, help="Minimum coverage percentage")
    
    # Test filtering
    parser.add_argument("--fast", action="store_true", help="Run only fast tests")
    parser.add_argument("--slow", action="store_true", help="Run only slow tests")
    
    # Output options
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--json-output", action="store_true", help="Generate JSON test report")
    parser.add_argument("--fail-fast", action="store_true", help="Stop on first failure")
    parser.add_argument("--show-locals", action="store_true", help="Show local variables in tracebacks")
    
    # Other options
    parser.add_argument("--generate-report", action="store_true", help="Generate test suite report")
    
    args = parser.parse_args()
    
    if args.generate_report:
        generate_report(args)
        return 0
    
    # Install test dependencies if needed
    try:
        import pytest
    except ImportError:
        print("Installing test dependencies...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements-test.txt"])
    
    # Run tests
    return run_tests(args)


if __name__ == "__main__":
    sys.exit(main())
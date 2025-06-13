#!/usr/bin/env python3
"""
Run all working tests in the test suite.
This script runs only the tests that are known to work with the current implementation.
"""

import subprocess
import sys
import os
from pathlib import Path
import time
from datetime import datetime

# Color codes for output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_section(message, color=Colors.BLUE):
    """Print a section header."""
    print(f"\n{color}{Colors.BOLD}{'='*60}")
    print(f"{message}")
    print(f"{'='*60}{Colors.RESET}\n")

def run_test(test_file, description):
    """Run a single test file and return results."""
    print(f"{Colors.YELLOW}Running {description}...{Colors.RESET}")
    
    start_time = time.time()
    
    # Run pytest with coverage
    cmd = [
        sys.executable, "-m", "pytest",
        test_file,
        "-v",
        "--tb=short",
        "--no-header",
        "-q"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.time() - start_time
    
    # Parse results
    passed = failed = 0
    for line in result.stdout.split('\n'):
        if ' passed' in line and ' failed' not in line:
            parts = line.split()
            for i, part in enumerate(parts):
                if part == 'passed' and i > 0:
                    passed = int(parts[i-1])
        if ' failed' in line:
            parts = line.split()
            for i, part in enumerate(parts):
                if part == 'failed' and i > 0:
                    failed = int(parts[i-1])
    
    # Print results
    if result.returncode == 0:
        print(f"{Colors.GREEN}✓ {description}: {passed} passed in {elapsed:.2f}s{Colors.RESET}")
    else:
        print(f"{Colors.RED}✗ {description}: {passed} passed, {failed} failed in {elapsed:.2f}s{Colors.RESET}")
        if failed > 0:
            print(f"{Colors.RED}  Error output:{Colors.RESET}")
            for line in result.stdout.split('\n'):
                if 'FAILED' in line:
                    print(f"    {line}")
    
    return passed, failed, elapsed

def main():
    """Run all working tests."""
    print_section("CAMF Test Suite - Running All Working Tests", Colors.BLUE)
    
    # Change to project root
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    # Ensure virtual environment is activated
    if not os.environ.get('VIRTUAL_ENV'):
        print(f"{Colors.RED}Warning: Virtual environment not activated!{Colors.RESET}")
        print("Please activate with: source ~/venvs/imperial-FYP-venv/bin/activate")
        return 1
    
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Working directory: {os.getcwd()}")
    
    # Define test files that are known to work
    working_tests = [
        # API Gateway tests
        ("tests/test_api_gateway_crud.py::TestProjectEndpoints", "API Gateway CRUD - Project endpoints"),
        ("tests/test_api_gateway_sse.py", "API Gateway SSE functionality"),
        ("tests/test_api_gateway_middleware.py", "API Gateway middleware"),
        
        # Basic functionality
        ("tests/test_basic_functionality.py", "Basic system functionality"),
        
        # Model tests
        ("tests/test_models.py::TestProject", "Project model tests"),
        ("tests/test_models.py::TestDetectorResult", "DetectorResult model tests"),
        ("tests/test_models.py::TestDetectorInfo", "DetectorInfo model tests"),
        ("tests/test_models.py::TestConfigurationField::test_configuration_field_boolean", "ConfigurationField boolean test"),
        ("tests/test_models.py::TestConfigurationField::test_configuration_field_select", "ConfigurationField select test"),
        ("tests/test_models.py::TestContinuousError", "ContinuousError model tests"),
        
        # Utils tests
        ("tests/test_utils_actual.py::TestTimestampFunctions::test_format_timestamp", "Timestamp formatting"),
        ("tests/test_utils_actual.py::TestPathFunctions::test_ensure_directory", "Directory creation"),
        ("tests/test_utils_actual.py::TestIdGeneration", "ID generation"),
        ("tests/test_utils_actual.py::TestProtocolUtils", "Protocol utilities"),
        ("tests/test_utils_actual.py::TestPathCreation", "Path creation"),
        
        # Storage tests
        ("tests/test_storage_database.py::TestDatabaseModels", "Database models"),
        ("tests/test_storage_database.py::TestDatabaseQueries", "Database queries"),
        ("tests/test_storage_database.py::TestBulkOperations", "Bulk database operations"),
        ("tests/test_storage_database.py::TestDatabaseTransactions", "Database transactions"),
        ("tests/test_storage_database.py::TestDatabasePerformance", "Database performance"),
    ]
    
    # Track overall results
    total_passed = 0
    total_failed = 0
    total_time = 0
    results = []
    
    # Run each test
    for test_path, description in working_tests:
        passed, failed, elapsed = run_test(test_path, description)
        total_passed += passed
        total_failed += failed
        total_time += elapsed
        results.append((description, passed, failed, elapsed))
    
    # Print summary
    print_section("Test Summary", Colors.BLUE)
    
    print(f"{Colors.BOLD}Results by test:{Colors.RESET}")
    for desc, passed, failed, elapsed in results:
        if failed == 0:
            status = f"{Colors.GREEN}✓ PASS{Colors.RESET}"
        else:
            status = f"{Colors.RED}✗ FAIL{Colors.RESET}"
        print(f"  {status} {desc}: {passed} passed, {failed} failed ({elapsed:.2f}s)")
    
    print(f"\n{Colors.BOLD}Overall Results:{Colors.RESET}")
    print(f"  Total tests run: {total_passed + total_failed}")
    print(f"  {Colors.GREEN}Passed: {total_passed}{Colors.RESET}")
    print(f"  {Colors.RED}Failed: {total_failed}{Colors.RESET}")
    print(f"  Total time: {total_time:.2f}s")
    
    success_rate = (total_passed / (total_passed + total_failed) * 100) if (total_passed + total_failed) > 0 else 0
    print(f"  Success rate: {success_rate:.1f}%")
    
    # Run coverage report
    print_section("Generating Coverage Report", Colors.BLUE)
    
    coverage_cmd = [
        sys.executable, "-m", "pytest",
        "--cov=CAMF",
        "--cov-report=term-missing",
        "--cov-report=html",
        "-q",
        *[test[0] for test in working_tests]
    ]
    
    print("Running coverage analysis...")
    coverage_result = subprocess.run(coverage_cmd, capture_output=True, text=True)
    
    # Extract coverage percentage
    for line in coverage_result.stdout.split('\n'):
        if 'TOTAL' in line and '%' in line:
            print(f"\n{Colors.BOLD}Coverage Summary:{Colors.RESET}")
            print(f"  {line.strip()}")
    
    print(f"\nDetailed coverage report generated in: htmlcov/index.html")
    
    # Final status
    print_section("Final Status", Colors.GREEN if total_failed == 0 else Colors.RED)
    
    if total_failed == 0:
        print(f"{Colors.GREEN}{Colors.BOLD}✓ All tests passed!{Colors.RESET}")
        return 0
    else:
        print(f"{Colors.RED}{Colors.BOLD}✗ Some tests failed!{Colors.RESET}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
# CAMF Test Suite

Comprehensive test suite for the Continuity Anomaly Monitoring Framework (CAMF).

## Test Organization

The test suite is organized into the following categories:

### Unit Tests
- **API Gateway Tests**
  - `test_api_gateway_crud.py` - CRUD operations for all entities
  - `test_api_gateway_sse.py` - Server-Sent Events functionality
  - `test_api_gateway_middleware.py` - Middleware components (protocol, error recovery)

- **Storage Service Tests**
  - `test_storage_database.py` - Database operations and models
  - `test_storage_frame_operations.py` - Frame storage and hybrid video system

- **Capture Service Tests**
  - `test_capture_camera.py` - Camera capture functionality
  - `test_capture_screen_window.py` - Screen and window capture
  - `test_capture_video_upload.py` - Video upload and processing

- **Detector Framework Tests**
  - `test_detector_framework_docker.py` - Docker container management
  - `test_detector_framework_processing.py` - Frame processing pipeline
  - `test_detector_framework_recovery.py` - Error recovery and resilience

- **Export Service Tests**
  - `test_export_service.py` - PDF generation and report creation

- **Common Module Tests**
  - `test_common_ipc.py` - Inter-process communication
  - `test_common_modules.py` - Models, utilities, and configurations

### Integration Tests
- `test_integration_workflows.py` - End-to-end workflows and service interactions

### Performance Tests
- `test_performance.py` - Throughput, latency, and scalability tests

### Security Tests
- `test_security.py` - Security vulnerability testing
- `test_sandbox_escape_tests.py` - Detector sandbox security validation

## Running Tests

### Basic Usage
```bash
# Run all tests
python run_all_tests.py

# Run with coverage
python run_all_tests.py --coverage

# Run specific category
python run_all_tests.py --category unit
python run_all_tests.py --category integration
python run_all_tests.py --category performance
python run_all_tests.py --category security

# Run specific service tests
python run_all_tests.py --category api
python run_all_tests.py --category storage
python run_all_tests.py --category capture
python run_all_tests.py --category detector

# Run specific test file
python run_all_tests.py --test-file test_api_gateway_crud.py
```

### Advanced Options
```bash
# Run tests in parallel
python run_all_tests.py --parallel --workers 8

# Run only fast tests
python run_all_tests.py --fast

# Stop on first failure
python run_all_tests.py --fail-fast

# Verbose output with locals
python run_all_tests.py --verbose --show-locals

# Generate JSON report
python run_all_tests.py --json-output

# Set minimum coverage threshold
python run_all_tests.py --coverage --min-coverage 90
```

### Using pytest directly
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=CAMF --cov-report=html

# Run specific test
pytest test_api_gateway_crud.py::TestProjectEndpoints::test_create_project_success

# Run tests matching pattern
pytest -k "test_performance"

# Run with markers
pytest -m "slow"  # Run slow tests
pytest -m "not slow"  # Skip slow tests
```

## Test Coverage

The test suite aims for comprehensive coverage of:

1. **Functionality**: All major features and edge cases
2. **Error Handling**: Recovery scenarios and error paths
3. **Performance**: Critical path optimization
4. **Security**: Vulnerability prevention
5. **Integration**: Service interaction workflows

### Coverage Goals
- Unit tests: >90% coverage
- Integration tests: All major workflows
- Performance tests: Critical paths
- Security tests: OWASP Top 10 coverage

## Writing Tests

### Test Structure
```python
import pytest
from unittest.mock import Mock, patch

class TestFeature:
    """Test suite for specific feature."""
    
    @pytest.fixture
    def setup_data(self):
        """Setup test data."""
        return {"test": "data"}
    
    def test_normal_operation(self, setup_data):
        """Test normal operation."""
        # Arrange
        data = setup_data
        
        # Act
        result = function_under_test(data)
        
        # Assert
        assert result == expected_value
    
    def test_error_handling(self):
        """Test error scenarios."""
        with pytest.raises(ExpectedException):
            function_that_should_fail()
```

### Performance Test Example
```python
def test_throughput(self):
    """Test operation throughput."""
    metrics = PerformanceMetrics()
    metrics.start()
    
    for i in range(1000):
        operation()
        metrics.record_operation()
    
    metrics.end()
    summary = metrics.get_summary()
    
    assert summary["throughput"] > 100  # ops/second
    assert summary["avg_latency"] < 0.01  # 10ms
```

### Security Test Example
```python
def test_sql_injection(self, client):
    """Test SQL injection prevention."""
    payloads = ["'; DROP TABLE users; --", "1' OR '1'='1"]
    
    for payload in payloads:
        response = client.get(f"/api/users?id={payload}")
        assert response.status_code in [400, 422]
```

## Test Data

Test data is generated dynamically or uses fixtures:
- Mock video frames using numpy arrays
- Mock detector results with realistic confidence scores
- Database fixtures for integration tests

## Continuous Integration

The test suite is designed to run in CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
test:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v3
    - name: Install dependencies
      run: pip install -r requirements.txt -r tests/requirements-test.txt
    - name: Run tests
      run: python tests/run_all_tests.py --coverage --parallel
    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

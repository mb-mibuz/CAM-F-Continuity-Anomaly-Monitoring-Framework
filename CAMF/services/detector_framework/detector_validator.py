"""
Static analysis and validation for detector code security.

This module provides comprehensive validation of detector code to identify
potential security risks before execution.
"""

import ast
import json
import re
import logging
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when detector validation fails."""


class DetectorValidator:
    """
    Validates detector code and configuration for security compliance.
    
    Features:
    - Static code analysis
    - Import validation
    - Pattern detection for suspicious code
    - Configuration schema validation
    - Dependency checking
    """
    
    # Dangerous imports that should be blocked
    DANGEROUS_IMPORTS = {
        'os', 'sys', 'subprocess', 'socket', 'urllib', 'requests',
        'shutil', 'glob', 'pathlib', '__builtin__', '__builtins__',
        'compile', 'eval', 'exec', 'execfile', 'file', 'input',
        'open', 'raw_input', 'reload', 'import', '__import__',
        'importlib', 'multiprocessing', 'threading', 'ctypes',
        'pickle', 'marshal', 'shelve', 'tempfile', 'commands',
        'popen', 'fdopen', 'tmpfile', 'fchmod', 'fchown',
        'flock', 'fcntl', 'msvcrt', 'pwd', 'grp', 'crypt',
        'pty', 'tty', 'termios', 'select', 'signal', 'resource',
        'gc', 'weakref', 'atexit', 'traceback', 'inspect',
        'ast', 'compiler', 'code', 'codeop', 'types', 'copy_reg',
        'new', 'platform', 'warnings', 'contextlib', 'functools',
        'operator', 'collections', 'itertools', 'heapq', 'bisect',
        'array', 'sets', 'sched', 'mutex', 'queue', 'thread',
        'dummy_thread', 'dummy_threading', 'local', 'threading_local',
    }
    
    # Allowed safe imports
    ALLOWED_IMPORTS = {
        'numpy', 'cv2', 'torch', 'tensorflow', 'PIL', 'skimage',
        'matplotlib', 'pandas', 'scipy', 'sklearn', 'json', 'math',
        'random', 'datetime', 'time', 'collections', 'itertools',
        'functools', 'logging', 're', 'string', 'base64', 'hashlib',
        'typing', 'dataclasses', 'enum', 'abc', 'copy', 'statistics',
        'decimal', 'fractions', 'numbers', 'io', 'struct', 'uuid',
    }
    
    # Suspicious code patterns
    SUSPICIOUS_PATTERNS = [
        (r'eval\s*\(', 'Use of eval() is forbidden'),
        (r'exec\s*\(', 'Use of exec() is forbidden'),
        (r'compile\s*\(', 'Use of compile() is forbidden'),
        (r'__import__\s*\(', 'Use of __import__() is forbidden'),
        (r'globals\s*\(\s*\)', 'Access to globals() is forbidden'),
        (r'locals\s*\(\s*\)', 'Access to locals() is forbidden'),
        (r'vars\s*\(\s*\)', 'Access to vars() is forbidden'),
        (r'dir\s*\(\s*\)', 'Use of dir() is restricted'),
        (r'getattr\s*\(', 'Dynamic attribute access is restricted'),
        (r'setattr\s*\(', 'Dynamic attribute setting is forbidden'),
        (r'delattr\s*\(', 'Dynamic attribute deletion is forbidden'),
        (r'open\s*\(', 'Direct file access is forbidden'),
        (r'file\s*\(', 'Direct file access is forbidden'),
        (r'input\s*\(', 'User input is forbidden'),
        (r'raw_input\s*\(', 'User input is forbidden'),
        (r'\.__.*__', 'Access to dunder attributes is restricted'),
        (r'lambda\s*:', 'Lambda functions require review'),
        (r'type\s*\(', 'Type manipulation is restricted'),
        (r'super\s*\(', 'Super calls require review'),
        (r'property\s*\(', 'Property decorators require review'),
        (r'staticmethod\s*\(', 'Static methods require review'),
        (r'classmethod\s*\(', 'Class methods require review'),
        (r'subprocess', 'Process execution is forbidden'),
        (r'os\.', 'OS module access is forbidden'),
        (r'sys\.', 'Sys module access is forbidden'),
        (r'socket', 'Network access is forbidden'),
        (r'urllib', 'Network access is forbidden'),
        (r'requests', 'Network access is forbidden'),
        (r'pickle', 'Serialization is restricted'),
        (r'marshal', 'Serialization is restricted'),
        (r'shelve', 'Serialization is restricted'),
    ]
    
    def __init__(self):
        self.validation_results: List[Dict[str, Any]] = []
        
    def validate_detector(self, detector_path: Path) -> Dict[str, Any]:
        """
        Perform comprehensive validation of a detector.
        
        Returns a validation report with any issues found.
        """
        results = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'info': []
        }
        
        # Validate directory structure
        self._validate_structure(detector_path, results)
        
        # Validate detector.json
        if (detector_path / 'detector.json').exists():
            self._validate_config(detector_path / 'detector.json', results)
        else:
            results['errors'].append('Missing detector.json configuration file')
            results['valid'] = False
            
        # Check for Dockerfile (Docker-based detector)
        if (detector_path / 'Dockerfile').exists():
            results['info'].append('Docker-based detector detected')
            self._validate_dockerfile(detector_path / 'Dockerfile', results)
            
        # Validate Python code
        if (detector_path / 'detector.py').exists():
            self._validate_python_code(detector_path / 'detector.py', results)
        else:
            results['errors'].append('Missing detector.py implementation file')
            results['valid'] = False
            
        # Validate requirements
        if (detector_path / 'requirements.txt').exists():
            self._validate_requirements(detector_path / 'requirements.txt', results)
            
        # Check for additional Python files
        for py_file in detector_path.glob('**/*.py'):
            if py_file.name != 'detector.py':
                self._validate_python_code(py_file, results)
                
        return results
        
    def _validate_structure(self, detector_path: Path, results: Dict[str, Any]):
        """Validate detector directory structure."""
        required_files = ['detector.py', 'detector.json']
        
        for file in required_files:
            if not (detector_path / file).exists():
                results['errors'].append(f'Missing required file: {file}')
                results['valid'] = False
                
        # Check for suspicious files
        suspicious_extensions = ['.sh', '.bat', '.exe', '.dll', '.so', '.dylib']
        for file in detector_path.rglob('*'):
            if file.suffix in suspicious_extensions:
                results['warnings'].append(f'Suspicious file found: {file.name}')
                
    def _validate_config(self, config_path: Path, results: Dict[str, Any]):
        """Validate detector.json configuration."""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                
            # Required fields
            required_fields = ['name', 'version', 'author', 'description', 'interface_version']
            for field in required_fields:
                if field not in config:
                    results['errors'].append(f'Missing required field in detector.json: {field}')
                    results['valid'] = False
                    
            # Validate interface version
            if config.get('interface_version') != '1.0':
                results['warnings'].append(f"Unsupported interface version: {config.get('interface_version')}")
                
            # Validate configuration schema if present
            if 'configuration_schema' in config:
                self._validate_schema(config['configuration_schema'], results)
                
        except json.JSONDecodeError as e:
            results['errors'].append(f'Invalid JSON in detector.json: {e}')
            results['valid'] = False
        except Exception as e:
            results['errors'].append(f'Error reading detector.json: {e}')
            results['valid'] = False
            
    def _validate_schema(self, schema: Dict[str, Any], results: Dict[str, Any]):
        """Validate configuration schema."""
        if not isinstance(schema, dict):
            results['errors'].append('Configuration schema must be a dictionary')
            return
            
        if 'properties' not in schema:
            results['warnings'].append('Configuration schema missing properties field')
            
    def _validate_python_code(self, code_path: Path, results: Dict[str, Any]):
        """Validate Python code for security issues."""
        try:
            with open(code_path, 'r') as f:
                code = f.read()
                
            # Parse AST
            try:
                tree = ast.parse(code)
                self._analyze_ast(tree, code_path.name, results)
            except SyntaxError as e:
                results['errors'].append(f'Syntax error in {code_path.name}: {e}')
                results['valid'] = False
                return
                
            # Check for suspicious patterns
            self._check_patterns(code, code_path.name, results)
            
            # Check imports
            self._check_imports(tree, code_path.name, results)
            
            # Check for dangerous constructs
            self._check_dangerous_constructs(tree, code_path.name, results)
            
        except Exception as e:
            results['errors'].append(f'Error analyzing {code_path.name}: {e}')
            results['valid'] = False
            
    def _analyze_ast(self, tree: ast.AST, filename: str, results: Dict[str, Any]):
        """Analyze AST for security issues."""
        for node in ast.walk(tree):
            # Check for eval/exec
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in ['eval', 'exec', 'compile', '__import__']:
                        results['errors'].append(
                            f'Forbidden function {node.func.id}() in {filename}'
                        )
                        results['valid'] = False
                        
            # Check for file operations
            elif isinstance(node, ast.With):
                for item in node.items:
                    if isinstance(item.context_expr, ast.Call):
                        if isinstance(item.context_expr.func, ast.Name):
                            if item.context_expr.func.id == 'open':
                                results['errors'].append(
                                    f'Direct file access via open() in {filename}'
                                )
                                results['valid'] = False
                                
    def _check_patterns(self, code: str, filename: str, results: Dict[str, Any]):
        """Check for suspicious code patterns."""
        for pattern, message in self.SUSPICIOUS_PATTERNS:
            if re.search(pattern, code, re.IGNORECASE):
                results['warnings'].append(f'{message} in {filename}')
                
    def _check_imports(self, tree: ast.AST, filename: str, results: Dict[str, Any]):
        """Check imports for security issues."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.split('.')[0]
                    if module_name in self.DANGEROUS_IMPORTS:
                        results['errors'].append(
                            f'Forbidden import: {alias.name} in {filename}'
                        )
                        results['valid'] = False
                    elif module_name not in self.ALLOWED_IMPORTS:
                        results['warnings'].append(
                            f'Unknown import: {alias.name} in {filename} (requires review)'
                        )
                        
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module.split('.')[0]
                    if module_name in self.DANGEROUS_IMPORTS:
                        results['errors'].append(
                            f'Forbidden import: from {node.module} in {filename}'
                        )
                        results['valid'] = False
                    elif module_name not in self.ALLOWED_IMPORTS:
                        results['warnings'].append(
                            f'Unknown import: from {node.module} in {filename} (requires review)'
                        )
                        
    def _check_dangerous_constructs(self, tree: ast.AST, filename: str, results: Dict[str, Any]):
        """Check for dangerous code constructs."""
        for node in ast.walk(tree):
            # Check for class inheritance manipulation
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    if isinstance(base, ast.Attribute):
                        if base.attr.startswith('__'):
                            results['warnings'].append(
                                f'Suspicious class inheritance in {filename}'
                            )
                            
            # Check for global/nonlocal
            elif isinstance(node, ast.Global):
                results['warnings'].append(
                    f'Use of global statement in {filename}'
                )
            elif isinstance(node, ast.Nonlocal):
                results['warnings'].append(
                    f'Use of nonlocal statement in {filename}'
                )
                
            # Check for dynamic code execution
            elif isinstance(node, ast.Expr):
                if isinstance(node.value, ast.Call):
                    if isinstance(node.value.func, ast.Attribute):
                        if node.value.func.attr in ['eval', 'exec']:
                            results['errors'].append(
                                f'Dynamic code execution in {filename}'
                            )
                            results['valid'] = False
                            
    def _validate_requirements(self, requirements_path: Path, results: Dict[str, Any]):
        """Validate requirements.txt for security issues."""
        try:
            with open(requirements_path, 'r') as f:
                requirements = f.readlines()
                
            # Known problematic packages
            problematic_packages = {
                'requests': 'Network access capability',
                'urllib3': 'Network access capability',
                'socket': 'Network access capability',
                'paramiko': 'SSH access capability',
                'fabric': 'Remote execution capability',
                'ansible': 'Remote execution capability',
                'subprocess32': 'Process execution capability',
            }
            
            for line in requirements:
                line = line.strip()
                if line and not line.startswith('#'):
                    package = line.split('==')[0].split('>=')[0].split('<=')[0].strip()
                    if package in problematic_packages:
                        results['warnings'].append(
                            f'Package {package} has {problematic_packages[package]}'
                        )
                        
        except Exception as e:
            results['warnings'].append(f'Error reading requirements.txt: {e}')
            
    def _validate_dockerfile(self, dockerfile_path: Path, results: Dict[str, Any]):
        """Validate Dockerfile for security issues."""
        try:
            with open(dockerfile_path, 'r') as f:
                dockerfile_content = f.read()
                
            # Check for security issues in Dockerfile
            security_issues = [
                (r'--privileged', 'Privileged mode is forbidden'),
                (r'--cap-add', 'Adding capabilities is restricted'),
                (r'--security-opt\s+seccomp=unconfined', 'Disabling seccomp is forbidden'),
                (r'--network\s+host', 'Host network mode is forbidden'),
                (r'--pid\s+host', 'Host PID namespace is forbidden'),
                (r'--ipc\s+host', 'Host IPC namespace is forbidden'),
                (r'USER\s+root', 'Running as root is discouraged'),
                (r'sudo\s+', 'Use of sudo is discouraged'),
            ]
            
            for pattern, message in security_issues:
                if re.search(pattern, dockerfile_content, re.IGNORECASE):
                    results['warnings'].append(f'Dockerfile: {message}')
                    
            # Check for CAMF labels
            if 'LABEL camf.detector=' not in dockerfile_content:
                results['warnings'].append('Dockerfile missing CAMF detector label')
                
            # Check for non-root user
            if not re.search(r'USER\s+(?!root)', dockerfile_content):
                results['warnings'].append('Dockerfile should switch to non-root user')
                
            # Check base image
            if re.search(r'FROM\s+.*:latest', dockerfile_content):
                results['warnings'].append('Dockerfile should use specific image tags, not :latest')
                
        except Exception as e:
            results['warnings'].append(f'Error reading Dockerfile: {e}')
            
    def generate_report(self, results: Dict[str, Any]) -> str:
        """Generate a human-readable validation report."""
        report = []
        report.append("=== Detector Validation Report ===\n")
        
        if results['valid']:
            report.append("✓ Detector passed validation\n")
        else:
            report.append("✗ Detector FAILED validation\n")
            
        if results['errors']:
            report.append("\nERRORS:")
            for error in results['errors']:
                report.append(f"  ✗ {error}")
                
        if results['warnings']:
            report.append("\nWARNINGS:")
            for warning in results['warnings']:
                report.append(f"  ⚠ {warning}")
                
        if results['info']:
            report.append("\nINFO:")
            for info in results['info']:
                report.append(f"  ℹ {info}")
                
        return '\n'.join(report)
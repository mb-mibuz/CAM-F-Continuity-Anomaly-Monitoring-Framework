"""
Detector validation tools for ensuring detectors meet requirements.
"""

import ast
import importlib.util
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import json
import zipfile
import tempfile

from CAMF.common.models import (
    BaseDetector, DetectorConfigurationSchema, ConfigurationField
)


def validate_detector_config(config: Dict[str, Any], schema: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[str]]:
    """
    Validate detector configuration against schema.
    
    Args:
        config: Configuration dictionary to validate
        schema: Optional schema to validate against
        
    Returns:
        (is_valid, error_message)
    """
    # Basic validation - just check if config is a dictionary
    if not isinstance(config, dict):
        return False, "Configuration must be a dictionary"
    
    # If no schema provided, accept any valid dictionary
    if schema is None:
        return True, None
    
    # Validate against schema if provided
    for field_name, field_schema in schema.items():
        if field_schema.get('required', False) and field_name not in config:
            return False, f"Required field '{field_name}' is missing"
        
        if field_name in config:
            value = config[field_name]
            field_type = field_schema.get('type', 'string')
            
            # Basic type validation
            if field_type == 'string' and not isinstance(value, str):
                return False, f"Field '{field_name}' must be a string"
            elif field_type == 'number' and not isinstance(value, (int, float)):
                return False, f"Field '{field_name}' must be a number"
            elif field_type == 'boolean' and not isinstance(value, bool):
                return False, f"Field '{field_name}' must be a boolean"
            elif field_type == 'array' and not isinstance(value, list):
                return False, f"Field '{field_name}' must be an array"
            elif field_type == 'object' and not isinstance(value, dict):
                return False, f"Field '{field_name}' must be an object"
    
    return True, None


class DetectorValidator:
    """Validates detector packages for compliance with framework requirements."""
    
    # Required methods for all detectors
    REQUIRED_METHODS = [
        'get_info',
        'get_configuration_schema',
        'initialize',
        'process_frame'
    ]
    
    # Optional but recommended methods
    OPTIONAL_METHODS = [
        'cleanup',
        'validate_configuration'
    ]
    
    def __init__(self):
        self.validation_results = {}
    
    def validate_detector_package(self, detector_path: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Validate a detector package (directory or zip).
        
        Returns:
            (is_valid, validation_report)
        """
        detector_path = Path(detector_path)
        
        if detector_path.is_file() and detector_path.suffix == '.zip':
            return self._validate_zip_package(detector_path)
        elif detector_path.is_dir():
            return self._validate_directory_package(detector_path)
        else:
            return False, {
                'error': 'Invalid detector package: must be directory or .zip file'
            }
    
    def _validate_zip_package(self, zip_path: Path) -> Tuple[bool, Dict[str, Any]]:
        """Validate a zipped detector package."""
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Extract zip
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                
                # Find detector directory
                temp_path = Path(temp_dir)
                detector_dirs = [d for d in temp_path.iterdir() if d.is_dir()]
                
                if len(detector_dirs) == 1:
                    return self._validate_directory_package(detector_dirs[0])
                else:
                    # Check if files are in root
                    return self._validate_directory_package(temp_path)
            
            except Exception as e:
                return False, {'error': f'Failed to extract zip: {str(e)}'}
    
    def _validate_directory_package(self, detector_dir: Path) -> Tuple[bool, Dict[str, Any]]:
        """Validate a detector directory."""
        report = {
            'path': str(detector_dir),
            'structure': {},
            'code_validation': {},
            'requirements': {},
            'metadata': {},
            'warnings': [],
            'errors': []
        }
        
        # Check directory structure
        structure_valid, structure_report = self._validate_structure(detector_dir)
        report['structure'] = structure_report
        
        if not structure_valid:
            report['errors'].append('Invalid directory structure')
            return False, report
        
        # Find main detector file
        detector_file = None
        for filename in ['detector.py', 'main.py', '__init__.py']:
            if (detector_dir / filename).exists():
                detector_file = detector_dir / filename
                break
        
        if not detector_file:
            report['errors'].append('No detector file found')
            return False, report
        
        # Validate code
        code_valid, code_report = self._validate_detector_code(detector_file)
        report['code_validation'] = code_report
        
        if not code_valid:
            report['errors'].extend(code_report.get('errors', []))
        
        # Check requirements.txt
        req_valid, req_report = self._validate_requirements(detector_dir)
        report['requirements'] = req_report
        
        # Try to load and instantiate detector
        instance_valid, instance_report = self._validate_detector_instance(detector_dir, detector_file)
        report['metadata'] = instance_report
        
        if not instance_valid:
            report['errors'].extend(instance_report.get('errors', []))
        
        # Overall validation
        is_valid = structure_valid and code_valid and instance_valid
        report['is_valid'] = is_valid
        
        return is_valid, report
    
    def _validate_structure(self, detector_dir: Path) -> Tuple[bool, Dict[str, Any]]:
        """Validate directory structure."""
        structure = {
            'has_detector_file': False,
            'has_metadata': False,
            'has_requirements': False,
            'has_readme': False,
            'files': []
        }
        
        # Check for required files
        for filename in ['detector.py', 'main.py', '__init__.py']:
            if (detector_dir / filename).exists():
                structure['has_detector_file'] = True
                structure['detector_file'] = filename
                break
        
        # Check for detector.json metadata
        if (detector_dir / 'detector.json').exists():
            structure['has_metadata'] = True
        elif (detector_dir / 'metadata.json').exists():
            structure['has_metadata'] = True
            structure['metadata_file'] = 'metadata.json'
        else:
            structure['metadata_file'] = 'detector.json'
        
        structure['has_requirements'] = (detector_dir / 'requirements.txt').exists()
        structure['has_readme'] = (detector_dir / 'README.md').exists()
        
        # List all files
        for item in detector_dir.iterdir():
            if item.is_file():
                structure['files'].append(item.name)
        
        # Validation requires both detector file and metadata
        is_valid = structure['has_detector_file'] and structure['has_metadata']
        
        if not structure['has_metadata']:
            structure['error'] = 'Missing detector.json metadata file'
        
        if not structure['has_requirements']:
            structure['warning'] = 'No requirements.txt found'
        
        return is_valid, structure

    def _validate_metadata(self, detector_dir: Path) -> Tuple[bool, Dict[str, Any]]:
        """Validate detector.json metadata."""
        report = {
            'has_metadata': False,
            'metadata_valid': False,
            'metadata': {},
            'errors': []
        }
        
        # Look for metadata file
        metadata_file = detector_dir / 'detector.json'
        if not metadata_file.exists():
            metadata_file = detector_dir / 'metadata.json'
        
        if not metadata_file.exists():
            report['errors'].append('No detector.json found')
            return False, report
        
        report['has_metadata'] = True
        
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            report['metadata'] = metadata
            
            # Validate required fields
            required_fields = ['name', 'version']
            for field in required_fields:
                if field not in metadata:
                    report['errors'].append(f"Missing required field: {field}")
            
            # Validate schema if present
            if 'schema' in metadata:
                schema = metadata['schema']
                if not isinstance(schema, dict):
                    report['errors'].append("Schema must be an object")
                elif 'fields' not in schema:
                    report['errors'].append("Schema missing 'fields' property")
                else:
                    # Validate each field
                    for field_name, field_data in schema['fields'].items():
                        if not isinstance(field_data, dict):
                            report['errors'].append(f"Schema field '{field_name}' must be an object")
                            continue
                        
                        if 'field_type' not in field_data:
                            report['errors'].append(f"Schema field '{field_name}' missing 'field_type'")
                        
                        # Validate field type
                        valid_types = ['text', 'number', 'boolean', 'file', 'file_multiple']
                        if field_data.get('field_type') not in valid_types:
                            report['errors'].append(
                                f"Schema field '{field_name}' has invalid type: {field_data.get('field_type')}"
                            )
            
            report['metadata_valid'] = len(report['errors']) == 0
            
        except json.JSONDecodeError as e:
            report['errors'].append(f"Invalid JSON: {str(e)}")
        except Exception as e:
            report['errors'].append(f"Error reading metadata: {str(e)}")
        
        return report['metadata_valid'], report

    def _validate_detector_code(self, detector_file: Path) -> Tuple[bool, Dict[str, Any]]:
        """Validate detector code structure."""
        report = {
            'syntax_valid': False,
            'has_detector_class': False,
            'inherits_base': False,
            'required_methods': {},
            'optional_methods': {},
            'errors': []
        }
        
        try:
            # Read and parse code
            with open(detector_file, 'r', encoding='utf-8') as f:
                code = f.read()
            
            # Check syntax
            try:
                tree = ast.parse(code)
                report['syntax_valid'] = True
            except SyntaxError as e:
                report['errors'].append(f'Syntax error: {str(e)}')
                return False, report
            
            # Find detector class
            detector_classes = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # Check if inherits from BaseDetector
                    for base in node.bases:
                        if isinstance(base, ast.Name) and base.id == 'BaseDetector':
                            detector_classes.append(node)
                            report['has_detector_class'] = True
                            report['detector_class_name'] = node.name
                            break
            
            if not detector_classes:
                report['errors'].append('No class inheriting from BaseDetector found')
                return False, report
            
            # Check methods in detector class
            detector_class = detector_classes[0]
            class_methods = [n.name for n in detector_class.body if isinstance(n, ast.FunctionDef)]
            
            # Check required methods
            for method in self.REQUIRED_METHODS:
                report['required_methods'][method] = method in class_methods
            
            # Check optional methods
            for method in self.OPTIONAL_METHODS:
                report['optional_methods'][method] = method in class_methods
            
            # Validate all required methods exist
            missing_methods = [m for m, exists in report['required_methods'].items() if not exists]
            if missing_methods:
                report['errors'].append(f'Missing required methods: {", ".join(missing_methods)}')
                return False, report
            
            return True, report
        
        except Exception as e:
            report['errors'].append(f'Code validation error: {str(e)}')
            return False, report
    
    def _validate_requirements(self, detector_dir: Path) -> Tuple[bool, Dict[str, Any]]:
        """Validate requirements.txt."""
        report = {
            'exists': False,
            'dependencies': [],
            'warnings': []
        }
        
        req_file = detector_dir / 'requirements.txt'
        if not req_file.exists():
            report['warnings'].append('No requirements.txt found')
            return True, report  # Not required
        
        report['exists'] = True
        
        try:
            with open(req_file, 'r') as f:
                lines = f.readlines()
            
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    report['dependencies'].append(line)
            
            # Check for problematic dependencies
            problematic = ['tensorflow-gpu', 'torch']  # Large dependencies
            for dep in report['dependencies']:
                for prob in problematic:
                    if prob in dep.lower():
                        report['warnings'].append(
                            f'Large dependency detected: {dep}. '
                            'Consider making it optional.'
                        )
            
            return True, report
        
        except Exception as e:
            report['warnings'].append(f'Failed to parse requirements.txt: {str(e)}')
            return True, report
    
    def _validate_detector_instance(self, detector_dir: Path, detector_file: Path) -> Tuple[bool, Dict[str, Any]]:
        """Try to instantiate detector and validate its metadata."""
        report = {
            'can_instantiate': False,
            'info': {},
            'schema': {},
            'errors': []
        }
        
        # Add detector directory to path temporarily
        sys.path.insert(0, str(detector_dir))
        
        try:
            # Load module
            spec = importlib.util.spec_from_file_location("temp_detector", detector_file)
            if not spec or not spec.loader:
                report['errors'].append('Failed to create module spec')
                return False, report
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Find detector class
            detector_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, BaseDetector) and 
                    attr != BaseDetector):
                    detector_class = attr
                    break
            
            if not detector_class:
                report['errors'].append('No detector class found')
                return False, report
            
            # Instantiate detector
            detector = detector_class()
            report['can_instantiate'] = True
            
            # Validate get_info()
            try:
                info = detector.get_info()
                report['info'] = {
                    'name': info.name,
                    'description': info.description,
                    'version': info.version,
                    'author': info.author,
                    'requires_reference': info.requires_reference,
                    'min_frames_required': info.min_frames_required
                }
                
                # Validate info fields
                if not info.name:
                    report['errors'].append('Detector name is empty')
                if not info.version:
                    report['errors'].append('Detector version is empty')
                
            except Exception as e:
                report['errors'].append(f'get_info() failed: {str(e)}')
            
            # Validate get_configuration_schema()
            try:
                schema = detector.get_configuration_schema()
                report['schema'] = {
                    'field_count': len(schema.fields),
                    'fields': {
                        name: {
                            'type': field.field_type,
                            'required': field.required,
                            'title': field.title
                        }
                        for name, field in schema.fields.items()
                    }
                }
                
                # Validate field types
                valid_types = ['text', 'number', 'boolean', 'file', 'file_multiple']
                for name, field in schema.fields.items():
                    if field.field_type not in valid_types:
                        report['errors'].append(
                            f'Invalid field type "{field.field_type}" for field "{name}"'
                        )
                
            except Exception as e:
                report['errors'].append(f'get_configuration_schema() failed: {str(e)}')
            
            # Test initialize (with mock frame provider)
            try:
                class MockFrameProvider:
                    pass
                
                result = detector.initialize({}, MockFrameProvider())
                if not isinstance(result, bool):
                    report['errors'].append('initialize() must return bool')
            except Exception as e:
                report['errors'].append(f'initialize() failed: {str(e)}')
            
            return len(report['errors']) == 0, report
        
        except Exception as e:
            report['errors'].append(f'Failed to load detector: {str(e)}')
            return False, report
        
        finally:
            # Remove from path
            if str(detector_dir) in sys.path:
                sys.path.remove(str(detector_dir))
    
    def generate_validation_report(self, detector_path: str, output_file: Optional[str] = None) -> str:
        """Generate a detailed validation report."""
        is_valid, report = self.validate_detector_package(detector_path)
        
        # Create readable report
        lines = []
        lines.append("=" * 60)
        lines.append("DETECTOR VALIDATION REPORT")
        lines.append("=" * 60)
        lines.append(f"Path: {report.get('path', detector_path)}")
        lines.append(f"Valid: {'✓' if is_valid else '✗'}")
        lines.append("")
        
        # Structure
        lines.append("STRUCTURE:")
        structure = report.get('structure', {})
        lines.append(f"  - Detector file: {'✓' if structure.get('has_detector_file') else '✗'}")
        lines.append(f"  - Requirements: {'✓' if structure.get('has_requirements') else '✗'}")
        lines.append(f"  - README: {'✓' if structure.get('has_readme') else '✗'}")
        lines.append("")
        
        # Code validation
        lines.append("CODE VALIDATION:")
        code = report.get('code_validation', {})
        lines.append(f"  - Syntax valid: {'✓' if code.get('syntax_valid') else '✗'}")
        lines.append(f"  - Has detector class: {'✓' if code.get('has_detector_class') else '✗'}")
        
        if code.get('required_methods'):
            lines.append("  - Required methods:")
            for method, exists in code['required_methods'].items():
                lines.append(f"    - {method}: {'✓' if exists else '✗'}")
        lines.append("")
        
        # Metadata
        if report.get('metadata', {}).get('info'):
            lines.append("DETECTOR INFO:")
            info = report['metadata']['info']
            lines.append(f"  - Name: {info.get('name', 'N/A')}")
            lines.append(f"  - Version: {info.get('version', 'N/A')}")
            lines.append(f"  - Author: {info.get('author', 'N/A')}")
            lines.append("")
        
        # Errors
        if report.get('errors'):
            lines.append("ERRORS:")
            for error in report['errors']:
                lines.append(f"  - {error}")
            lines.append("")
        
        # Warnings
        if report.get('warnings'):
            lines.append("WARNINGS:")
            for warning in report['warnings']:
                lines.append(f"  - {warning}")
        
        report_text = '\n'.join(lines)
        
        # Save to file if requested
        if output_file:
            # Use UTF-8 encoding to handle Unicode characters
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report_text)
        
        return report_text


class ConfigurationValidator:
    """Validates and migrates detector configurations."""
    
    def validate_config(
        self, 
        config: Dict[str, Any], 
        schema: DetectorConfigurationSchema
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Validate configuration against schema.
        
        Returns:
            (is_valid, errors, cleaned_config)
        """
        errors = []
        cleaned_config = {}
        
        # Check required fields
        for field_name, field_schema in schema.fields.items():
            if field_schema.required and field_name not in config:
                errors.append(f"Required field '{field_name}' is missing")
                continue
            
            if field_name in config:
                # Validate field type and constraints
                value = config[field_name]
                validated_value, field_errors = self._validate_field(value, field_schema)
                
                if field_errors:
                    errors.extend([f"{field_name}: {err}" for err in field_errors])
                else:
                    cleaned_config[field_name] = validated_value
            elif field_schema.default is not None:
                # Use default value
                cleaned_config[field_name] = field_schema.default
        
        # Check for unknown fields
        unknown_fields = set(config.keys()) - set(schema.fields.keys())
        if unknown_fields:
            errors.append(f"Unknown fields: {', '.join(unknown_fields)}")
        
        return len(errors) == 0, errors, cleaned_config
    
    def _validate_field(
        self, 
        value: Any, 
        field_schema: ConfigurationField
    ) -> Tuple[Any, List[str]]:
        """Validate individual field value."""
        errors = []
        
        # Type validation
        if field_schema.field_type == "number":
            try:
                value = float(value)
                if field_schema.minimum is not None and value < field_schema.minimum:
                    errors.append(f"Value {value} is below minimum {field_schema.minimum}")
                if field_schema.maximum is not None and value > field_schema.maximum:
                    errors.append(f"Value {value} is above maximum {field_schema.maximum}")
            except (TypeError, ValueError):
                errors.append(f"Expected number, got {type(value).__name__}")
        
        elif field_schema.field_type == "boolean":
            if not isinstance(value, bool):
                errors.append(f"Expected boolean, got {type(value).__name__}")
        
        elif field_schema.field_type == "text":
            if not isinstance(value, str):
                errors.append(f"Expected string, got {type(value).__name__}")
            if field_schema.options and value not in field_schema.options:
                errors.append(f"Value must be one of: {', '.join(field_schema.options)}")
        
        elif field_schema.field_type in ["file", "file_multiple"]:
            if field_schema.field_type == "file":
                if not isinstance(value, str):
                    errors.append("Expected file path string")
            else:  # file_multiple
                if not isinstance(value, list):
                    errors.append("Expected list of file paths")
                elif not all(isinstance(v, str) for v in value):
                    errors.append("All file paths must be strings")
        
        return value, errors
    
    def migrate_config(
        self,
        old_config: Dict[str, Any],
        new_schema: DetectorConfigurationSchema,
        keep_unknown: bool = False
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Migrate old configuration to new schema.
        
        Returns:
            (migrated_config, warnings)
        """
        migrated_config = {}
        warnings = []
        
        # Process known fields
        for field_name, field_schema in new_schema.fields.items():
            if field_name in old_config:
                value = old_config[field_name]
                validated_value, field_errors = self._validate_field(value, field_schema)
                
                if field_errors:
                    warnings.append(f"Field '{field_name}' has invalid value, using default")
                    if field_schema.default is not None:
                        migrated_config[field_name] = field_schema.default
                else:
                    migrated_config[field_name] = validated_value
            elif field_schema.default is not None:
                migrated_config[field_name] = field_schema.default
        
        # Handle unknown fields
        unknown_fields = set(old_config.keys()) - set(new_schema.fields.keys())
        if unknown_fields:
            if keep_unknown:
                for field in unknown_fields:
                    migrated_config[field] = old_config[field]
                warnings.append(f"Kept unknown fields: {', '.join(unknown_fields)}")
            else:
                warnings.append(f"Removed unknown fields: {', '.join(unknown_fields)}")
        
        return migrated_config, warnings
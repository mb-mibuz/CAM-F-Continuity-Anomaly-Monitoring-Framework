"""
Auto-documentation generator for detectors and API.
"""

import inspect
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from CAMF.common.models import BaseDetector
from .interface import DetectorLoader


class DocumentationGenerator:
    """Generates documentation for detectors and the framework API."""
    
    def __init__(self, detectors_path: str):
        self.detectors_path = Path(detectors_path)
        self.loader = DetectorLoader(detectors_path)
    
    def generate_detector_docs(self, output_dir: str = "docs/detectors"):
        """Generate documentation for all installed detectors."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Discover detectors
        detector_names = self.loader.discover_detectors()
        
        # Generate index
        index_content = self._generate_detector_index(detector_names)
        (output_path / "index.md").write_text(index_content)
        
        # Generate individual detector docs
        for detector_name in detector_names:
            doc_content = self._generate_detector_doc(detector_name)
            if doc_content:
                filename = detector_name.lower().replace(' ', '_') + '.md'
                (output_path / filename).write_text(doc_content)
        
        print(f"Generated documentation for {len(detector_names)} detectors in {output_path}")
    
    def _generate_detector_index(self, detector_names: List[str]) -> str:
        """Generate index page for detectors."""
        lines = [
            "# Available Detectors",
            "",
            f"*Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
            "",
            "## Detector List",
            ""
        ]
        
        for name in sorted(detector_names):
            filename = name.lower().replace(' ', '_') + '.md'
            lines.append(f"- [{name}]({filename})")
        
        return '\n'.join(lines)
    
    def _generate_detector_doc(self, detector_name: str) -> Optional[str]:
        """Generate documentation for a single detector."""
        # Get metadata instead of importing
        metadata = self.loader.registry.get_detector_metadata(detector_name)
        if not metadata:
            return None
        
        try:
            lines = [
                f"# {metadata['name']}",
                "",
                f"**Version:** {metadata.get('version', '1.0.0')}",
                f"**Author:** {metadata.get('author', 'Unknown')}",
                "",
                "## Description",
                "",
                metadata.get('description', 'No description available'),
                "",
                "## Requirements",
                "",
                f"- Requires reference frame: {'Yes' if metadata.get('requires_reference', True) else 'No'}",
                f"- Minimum frames required: {metadata.get('min_frames_required', 1)}",
                ""
            ]
            
            # Configuration from schema
            schema = metadata.get('schema', {})
            if schema.get('fields'):
                lines.extend([
                    "## Configuration",
                    "",
                    "| Field | Type | Required | Description |",
                    "|-------|------|----------|-------------|"
                ])
                
                for field_name, field in schema['fields'].items():
                    required = "Yes" if field.get('required', False) else "No"
                    lines.append(
                        f"| {field_name} | {field.get('field_type', 'text')} | {required} | {field.get('description', '')} |"
                    )
                
                lines.append("")
            
            # Note about implementation
            lines.extend([
                "## Implementation",
                "",
                "See `detector.py` for the implementation details.",
                ""
            ])
            
            return '\n'.join(lines)
            
        except Exception as e:
            print(f"Failed to generate docs for {detector_name}: {e}")
            return None
    
    def generate_api_docs(self, output_file: str = "docs/api.md"):
        """Generate API documentation for detector developers."""
        lines = [
            "# Detector Framework API Documentation",
            "",
            f"*Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
            "",
            "## Overview",
            "",
            "This document describes the API available to detector developers.",
            "",
            "## Base Classes",
            "",
            "### BaseDetector",
            "",
            "All detectors must inherit from `BaseDetector` and implement the required methods.",
            "",
            "```python",
            "from CAMF.common.models import BaseDetector",
            "",
            "class MyDetector(BaseDetector):",
            "    pass",
            "```",
            "",
            "#### Required Methods",
            ""
        ]
        
        # Document BaseDetector methods
        for method_name in ['get_info', 'get_configuration_schema', 'initialize', 'process_frame']:
            method = getattr(BaseDetector, method_name)
            signature = inspect.signature(method)
            doc = inspect.getdoc(method)
            
            lines.extend([
                f"##### {method_name}{signature}",
                "",
                doc or "No documentation available.",
                ""
            ])
        
        # Frame Provider API
        lines.extend([
            "## Frame Provider API",
            "",
            "The frame provider is passed to the detector's `initialize` method.",
            "",
            "### Available Methods",
            "",
            "```python",
            "# Get current frame",
            "frame = self.frame_provider.get_current_frame()",
            "",
            "# Get specific frame",
            "frame = self.frame_provider.get_frame(frame_id)",
            "",
            "# Get reference frame",
            "ref_frame = self.frame_provider.get_reference_frame(frame_id)",
            "",
            "# Get frame range",
            "frames = self.frame_provider.get_frame_range(start=0, end=10)",
            "```",
            ""
        ])
        
        # Models
        lines.extend([
            "## Data Models",
            "",
            "### DetectorInfo",
            "",
            "```python",
            "from CAMF.common.models import DetectorInfo",
            "",
            "DetectorInfo(",
            "    name='My Detector',",
            "    description='Detects something',",
            "    version='1.0.0',",
            "    author='Your Name',",
            "    requires_reference=True,",
            "    min_frames_required=1",
            ")",
            "```",
            "",
            "### DetectorResult",
            "",
            "```python",
            "from CAMF.common.models import DetectorResult, ErrorConfidence",
            "",
            "DetectorResult(",
            "    confidence=ErrorConfidence.CONFIRMED_ERROR,",
            "    description='Error description',",
            "    frame_id=frame_id,",
            "    detector_name=self.get_info().name,",
            "    bounding_boxes=[",
            "        {'x': 100, 'y': 100, 'width': 50, 'height': 50}",
            "    ],",
            "    metadata={'custom': 'data'}",
            ")",
            "```",
            "",
            "### Configuration Schema",
            "",
            "```python",
            "from CAMF.common.models import DetectorConfigurationSchema, ConfigurationField",
            "",
            "DetectorConfigurationSchema(",
            "    fields={",
            "        'sensitivity': ConfigurationField(",
            "            field_type='number',",
            "            title='Sensitivity',",
            "            description='Detection sensitivity',",
            "            required=True,",
            "            minimum=0.0,",
            "            maximum=1.0,",
            "            default=0.5",
            "        )",
            "    }",
            ")",
            "```",
            ""
        ])
        
        # Save to file
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text('\n'.join(lines))
        
        print(f"Generated API documentation: {output_path}")


def generate_all_documentation(detectors_path: str = "detectors", output_dir: str = "docs"):
    """Generate all documentation."""
    generator = DocumentationGenerator(detectors_path)
    
    # Generate detector docs
    generator.generate_detector_docs(f"{output_dir}/detectors")
    
    # Generate API docs
    generator.generate_api_docs(f"{output_dir}/api.md")
    
    print(f"Documentation generation complete! Check {output_dir}/")
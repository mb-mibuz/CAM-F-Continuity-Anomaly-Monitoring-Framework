"""
Version control system for detectors.
Implements semantic versioning and migration support.
"""

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from enum import Enum
import semver
import hashlib
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


class VersionChange(Enum):
    """Types of version changes."""
    MAJOR = "major"  # Breaking changes
    MINOR = "minor"  # New features, backward compatible
    PATCH = "patch"  # Bug fixes


@dataclass
class DetectorVersion:
    """Represents a detector version."""
    version: str
    release_date: datetime
    changelog: str
    manifest_hash: str
    is_stable: bool = True
    deprecated: bool = False
    migration_from: Optional[str] = None
    breaking_changes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'version': self.version,
            'release_date': self.release_date.isoformat(),
            'changelog': self.changelog,
            'manifest_hash': self.manifest_hash,
            'is_stable': self.is_stable,
            'deprecated': self.deprecated,
            'migration_from': self.migration_from,
            'breaking_changes': self.breaking_changes
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DetectorVersion':
        data['release_date'] = datetime.fromisoformat(data['release_date'])
        return cls(**data)


class DetectorVersionControl:
    """Manages detector versions and migrations."""
    
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.versions_dir = self.base_path / ".versions"
        self.versions_dir.mkdir(exist_ok=True)
        self.version_index_file = self.versions_dir / "index.json"
        self._load_version_index()
        
        # Try to initialize Docker client
        try:
            import docker
            self.docker_client = docker.from_env()
        except Exception as e:
            logger.warning(f"Failed to initialize Docker client: {e}")
            self.docker_client = None
    
    def _load_version_index(self):
        """Load version index from disk."""
        if self.version_index_file.exists():
            with open(self.version_index_file, 'r') as f:
                data = json.load(f)
                self.version_index = {
                    name: {
                        v: DetectorVersion.from_dict(info)
                        for v, info in versions.items()
                    }
                    for name, versions in data.items()
                }
        else:
            self.version_index = {}
    
    def _save_version_index(self):
        """Save version index to disk."""
        data = {
            name: {
                v: version.to_dict()
                for v, version in versions.items()
            }
            for name, versions in self.version_index.items()
        }
        with open(self.version_index_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def create_version(self, detector_name: str, detector_path: Path, 
                      change_type: VersionChange, changelog: str,
                      breaking_changes: List[str] = None) -> str:
        """Create a new version of a detector."""
        # Get current version
        current_version = self.get_latest_version(detector_name)
        
        if current_version:
            # Calculate new version
            ver = semver.VersionInfo.parse(current_version.version)
            if change_type == VersionChange.MAJOR:
                new_version = str(ver.bump_major())
            elif change_type == VersionChange.MINOR:
                new_version = str(ver.bump_minor())
            else:
                new_version = str(ver.bump_patch())
        else:
            new_version = "1.0.0"
        
        # Create version directory
        version_dir = self.versions_dir / detector_name / new_version
        version_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy detector files
        shutil.copytree(detector_path, version_dir / "detector", dirs_exist_ok=True)
        
        # Update detector.json with new version
        detector_json_path = version_dir / "detector" / "detector.json"
        if detector_json_path.exists():
            with open(detector_json_path, 'r') as f:
                detector_config = json.load(f)
            detector_config['version'] = new_version
            with open(detector_json_path, 'w') as f:
                json.dump(detector_config, f, indent=2)
        
        # Calculate manifest hash
        manifest_hash = self._calculate_detector_hash(detector_path)
        
        # Create version metadata
        version_info = DetectorVersion(
            version=new_version,
            release_date=datetime.now(),
            changelog=changelog,
            manifest_hash=manifest_hash,
            migration_from=current_version.version if current_version else None,
            breaking_changes=breaking_changes or []
        )
        
        # Update index
        if detector_name not in self.version_index:
            self.version_index[detector_name] = {}
        self.version_index[detector_name][new_version] = version_info
        self._save_version_index()
        
        # Build Docker image with version tag
        self._build_versioned_docker_image(detector_name, detector_path, new_version)
        
        # Create migration script template if major version
        if change_type == VersionChange.MAJOR and current_version:
            self._create_migration_template(detector_name, current_version.version, new_version)
        
        return new_version
    
    def _calculate_detector_hash(self, detector_path: Path) -> str:
        """Calculate hash of detector files."""
        hasher = hashlib.sha256()
        
        for file_path in sorted(detector_path.rglob('*')):
            if file_path.is_file() and not file_path.name.startswith('.'):
                with open(file_path, 'rb') as f:
                    hasher.update(f.read())
                hasher.update(str(file_path.relative_to(detector_path)).encode())
        
        return hasher.hexdigest()
    
    def _create_migration_template(self, detector_name: str, from_version: str, to_version: str):
        """Create a migration script template."""
        migration_dir = self.versions_dir / detector_name / to_version / "migrations"
        migration_dir.mkdir(exist_ok=True)
        
        migration_file = migration_dir / f"migrate_from_{from_version}.py"
        
        template = f'''"""
Migration script from {detector_name} v{from_version} to v{to_version}

This migration handles breaking changes between major versions.
"""

from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


def migrate_configuration(old_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrate configuration from v{from_version} to v{to_version}.
    
    Args:
        old_config: Configuration from v{from_version}
        
    Returns:
        Migrated configuration for v{to_version}
    """
    new_config = old_config.copy()
    
    # TODO: Implement configuration migration logic
    # Common examples:
    
    # 1. Field renamed
    # if 'sensitivity' in new_config:
    #     new_config['detection_sensitivity'] = new_config.pop('sensitivity')
    
    # 2. Structure changed (flat to nested)
    # if 'threshold' in new_config:
    #     new_config['detection'] = {{
    #         'threshold': new_config.pop('threshold'),
    #         'mode': 'auto'  # New field with default
    #     }}
    
    # 3. Type changed
    # if 'enabled' in new_config and isinstance(new_config['enabled'], str):
    #     new_config['enabled'] = new_config['enabled'].lower() == 'true'
    
    # 4. Removed deprecated field
    # new_config.pop('deprecated_field', None)
    
    # 5. Add new required fields with sensible defaults
    # if 'new_required_field' not in new_config:
    #     new_config['new_required_field'] = 'default_value'
    
    logger.info(f"Migrated configuration from v{from_version} to v{to_version}")
    return new_config


def migrate_data(old_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrate stored data from v{from_version} to v{to_version}.
    
    Args:
        old_data: Data from v{from_version}
        
    Returns:
        Migrated data for v{to_version}
    """
    if not old_data:
        return {{}}
        
    new_data = old_data.copy()
    
    # TODO: Implement data migration logic
    # Examples:
    
    # 1. Update data structure
    # if 'calibration_values' in new_data:
    #     new_data['calibration'] = {{
    #         'values': new_data.pop('calibration_values'),
    #         'version': 2
    #     }}
    
    return new_data


def validate_migration(config: Dict[str, Any], data: Dict[str, Any]) -> bool:
    """
    Validate migrated configuration and data.
    
    Returns:
        True if migration is valid
    """
    # TODO: Implement validation logic
    # Examples:
    
    # 1. Check required fields exist
    # required_fields = ['detection_sensitivity', 'enabled']
    # for field in required_fields:
    #     if field not in config:
    #         logger.error(f"Missing required field: {{field}}")
    #         return False
    
    # 2. Validate field types
    # if not isinstance(config.get('enabled'), bool):
    #     logger.error("Field 'enabled' must be boolean")
    #     return False
    
    # 3. Validate value ranges
    # sensitivity = config.get('detection_sensitivity', 0)
    # if not (0.0 <= sensitivity <= 1.0):
    #     logger.error("detection_sensitivity must be between 0.0 and 1.0")
    #     return False
    
    return True
'''
        
        with open(migration_file, 'w') as f:
            f.write(template)
    
    def get_version(self, detector_name: str, version: str) -> Optional[DetectorVersion]:
        """Get specific version of a detector."""
        return self.version_index.get(detector_name, {}).get(version)
    
    def get_latest_version(self, detector_name: str) -> Optional[DetectorVersion]:
        """Get latest stable version of a detector."""
        versions = self.version_index.get(detector_name, {})
        if not versions:
            return None
        
        # Filter stable versions
        stable_versions = {
            v: info for v, info in versions.items() 
            if info.is_stable and not info.deprecated
        }
        
        if not stable_versions:
            return None
        
        # Sort by semantic version
        sorted_versions = sorted(
            stable_versions.keys(),
            key=lambda v: semver.VersionInfo.parse(v),
            reverse=True
        )
        
        return stable_versions[sorted_versions[0]]
    
    def list_versions(self, detector_name: str) -> List[DetectorVersion]:
        """List all versions of a detector."""
        versions = self.version_index.get(detector_name, {})
        return sorted(
            versions.values(),
            key=lambda v: semver.VersionInfo.parse(v.version),
            reverse=True
        )
    
    def install_version(self, detector_name: str, version: str, target_path: Path) -> bool:
        """Install specific version of a detector."""
        version_info = self.get_version(detector_name, version)
        if not version_info:
            return False
        
        version_path = self.versions_dir / detector_name / version / "detector"
        if not version_path.exists():
            return False
        
        # Copy detector files
        shutil.copytree(version_path, target_path, dirs_exist_ok=True)
        
        # Write version info
        version_file = target_path / ".version"
        with open(version_file, 'w') as f:
            json.dump({
                'detector_name': detector_name,
                'version': version,
                'installed_at': datetime.now().isoformat()
            }, f)
        
        return True
    
    def check_compatibility(self, detector_name: str, from_version: str, 
                          to_version: str) -> Tuple[bool, List[str]]:
        """Check compatibility between versions."""
        from_ver = semver.VersionInfo.parse(from_version)
        to_ver = semver.VersionInfo.parse(to_version)
        
        issues = []
        
        # Major version change indicates breaking changes
        if to_ver.major > from_ver.major:
            to_version_info = self.get_version(detector_name, to_version)
            if to_version_info and to_version_info.breaking_changes:
                issues.extend(to_version_info.breaking_changes)
        
        # Check if migration path exists
        if issues:
            migration_path = self._find_migration_path(detector_name, from_version, to_version)
            if not migration_path:
                issues.append(f"No migration path from {from_version} to {to_version}")
        
        return len(issues) == 0, issues
    
    def _find_migration_path(self, detector_name: str, from_version: str, 
                           to_version: str) -> Optional[List[str]]:
        """Find migration path between versions."""
        # Simple implementation - could be enhanced with graph search
        versions = self.list_versions(detector_name)
        
        path = []
        current = from_version
        
        for version in versions:
            if version.migration_from == current:
                path.append(version.version)
                if version.version == to_version:
                    return path
                current = version.version
        
        return None if path else None
    
    def run_migration(self, detector_name: str, from_version: str, to_version: str,
                     current_config: Dict[str, Any], current_data: Optional[Dict[str, Any]] = None) -> Tuple[bool, Dict[str, Any], Optional[Dict[str, Any]], str]:
        """
        Run migration scripts to upgrade configuration and data.
        
        Args:
            detector_name: Name of the detector
            from_version: Current version
            to_version: Target version
            current_config: Current detector configuration
            current_data: Current detector data (if any)
            
        Returns:
            Tuple of (success, migrated_config, migrated_data, error_message)
        """
        import importlib.util
        import sys
        
        # Find migration path
        migration_path = self._find_migration_path(detector_name, from_version, to_version)
        if not migration_path:
            # No migration needed for minor/patch versions
            from_ver = semver.VersionInfo.parse(from_version)
            to_ver = semver.VersionInfo.parse(to_version)
            if to_ver.major == from_ver.major:
                return True, current_config, current_data, ""
            else:
                return False, current_config, current_data, f"No migration path from {from_version} to {to_version}"
        
        # Run migrations in sequence
        migrated_config = current_config.copy()
        migrated_data = current_data.copy() if current_data else None
        
        for version in migration_path:
            migration_file = self.versions_dir / detector_name / version / "migrations" / f"migrate_from_{from_version}.py"
            
            if not migration_file.exists():
                # Try to find any migration file for this version
                migration_dir = self.versions_dir / detector_name / version / "migrations"
                if migration_dir.exists():
                    migration_files = list(migration_dir.glob("migrate_from_*.py"))
                    if migration_files:
                        migration_file = migration_files[0]
                    else:
                        continue  # Skip if no migration file
                else:
                    continue
            
            try:
                # Load migration module
                spec = importlib.util.spec_from_file_location(f"migration_{detector_name}_{version}", migration_file)
                if spec and spec.loader:
                    migration_module = importlib.util.module_from_spec(spec)
                    sys.modules[spec.name] = migration_module
                    spec.loader.exec_module(migration_module)
                    
                    # Run configuration migration
                    if hasattr(migration_module, 'migrate_configuration'):
                        migrated_config = migration_module.migrate_configuration(migrated_config)
                    
                    # Run data migration if data exists
                    if migrated_data is not None and hasattr(migration_module, 'migrate_data'):
                        migrated_data = migration_module.migrate_data(migrated_data)
                    
                    # Validate migration
                    if hasattr(migration_module, 'validate_migration'):
                        if not migration_module.validate_migration(migrated_config, migrated_data or {}):
                            return False, current_config, current_data, f"Migration validation failed for version {version}"
                    
                    # Update from_version for next iteration
                    from_version = version
                    
                else:
                    return False, current_config, current_data, f"Failed to load migration module for version {version}"
                    
            except Exception as e:
                import logging
                logging.error(f"Migration error for {detector_name} v{version}: {e}")
                return False, current_config, current_data, f"Migration failed: {str(e)}"
        
        return True, migrated_config, migrated_data, ""
    
    def _build_versioned_docker_image(self, detector_name: str, detector_path: Path, version: str):
        """Build Docker image with version tag"""
        if not self.docker_client:
            import logging
            logging.warning("Docker client not available, skipping image build")
            return
            
        try:
            # Build with version tag
            base_tag = f"camf-detector-{detector_name}"
            version_tag = f"{base_tag}:{version}"
            
            self.docker_client.images.build(
                path=str(detector_path),
                tag=version_tag,
                rm=True,
                forcerm=True,
                buildargs={
                    'DETECTOR_NAME': detector_name,
                    'DETECTOR_VERSION': version,
                    'BUILD_DATE': datetime.utcnow().isoformat()
                }
            )
            
            # Also tag as latest if this is the latest version
            latest = self.get_latest_version(detector_name)
            if latest and latest.version == version:
                image = self.docker_client.images.get(version_tag)
                image.tag(base_tag, 'latest')
                
        except Exception as e:
            import logging
            logging.error(f"Failed to build Docker image for {detector_name} v{version}: {e}")
    
    def deprecate_version(self, detector_name: str, version: str, reason: str):
        """Mark a version as deprecated."""
        version_info = self.get_version(detector_name, version)
        if version_info:
            version_info.deprecated = True
            version_info.changelog += f"\n\nDEPRECATED: {reason}"
            self._save_version_index()


class VersionedDetectorLoader:
    """Loads versioned detectors with migration support."""
    
    def __init__(self, version_control: DetectorVersionControl):
        self.version_control = version_control
    
    def load_detector(self, detector_name: str, version: Optional[str] = None,
                     target_path: Path = None) -> bool:
        """Load a specific version of a detector."""
        if version is None:
            version_info = self.version_control.get_latest_version(detector_name)
            if not version_info:
                return False
            version = version_info.version
        
        if target_path is None:
            target_path = Path(f"detectors/{detector_name}")
        
        return self.version_control.install_version(detector_name, version, target_path)
    
    def upgrade_detector(self, detector_name: str, current_version: str,
                        target_version: Optional[str] = None,
                        current_config: Optional[Dict[str, Any]] = None) -> Tuple[bool, List[str], Optional[Dict[str, Any]]]:
        """
        Upgrade detector to a newer version with migration support.
        
        Args:
            detector_name: Name of the detector
            current_version: Current installed version
            target_version: Target version (None for latest)
            current_config: Current detector configuration to migrate
            
        Returns:
            Tuple of (success, issues, migrated_config)
        """
        if target_version is None:
            latest = self.version_control.get_latest_version(detector_name)
            if not latest:
                return False, ["No versions available"], None
            target_version = latest.version
        
        # Check compatibility
        compatible, issues = self.version_control.check_compatibility(
            detector_name, current_version, target_version
        )
        
        if not compatible and not self._can_migrate(issues):
            return False, issues, None
        
        # Run migrations if config provided
        migrated_config = current_config
        if current_config is not None:
            success, migrated_config, _, error = self.version_control.run_migration(
                detector_name, current_version, target_version, current_config
            )
            if not success:
                return False, [f"Migration failed: {error}"], None
        
        # Install new version
        success = self.version_control.install_version(
            detector_name, target_version, Path(f"detectors/{detector_name}")
        )
        
        if not success:
            return False, ["Failed to install new version"], None
        
        return True, [], migrated_config
    
    def _can_migrate(self, issues: List[str]) -> bool:
        """Check if issues are just breaking changes that can be migrated."""
        # If the only issue is "No migration path", that's a real blocker
        if any("No migration path" in issue for issue in issues):
            return False
        # Other issues are just breaking changes that migration will handle
        return True
# CAMF/services/storage/filesystem_names.py
"""
Filesystem operations using project/scene/angle/take names instead of IDs.
This module replaces the ID-based filesystem.py with name-based operations.
"""

from pathlib import Path
import os
import shutil
from typing import List, Optional
import json
import numpy as np
import re
import unicodedata
import platform
import ctypes
import logging
import time
from pathlib import Path

from CAMF.common.utils import ensure_directory
from CAMF.common.config import get_config
from .file_utils import safe_json_update, safe_folder_rename

# Set up logging
logger = logging.getLogger(__name__)


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """
    Sanitize a filename to be safe across all operating systems.
    Prevents path traversal and other security issues.
    
    Args:
        name: The name to sanitize
        max_length: Maximum length of the filename
    
    Returns:
        A filesystem-safe version of the name
    """
    # Input validation
    if not isinstance(name, str):
        raise ValueError("Name must be a string")
    if max_length < 1 or max_length > 255:
        raise ValueError("Max length must be between 1 and 255")
    
    # Remove leading/trailing whitespace
    name = name.strip()
    
    # Prevent path traversal attacks - remove any path components
    # Remove any ../ or ..\  patterns
    name = re.sub(r'\.\.[\\/]', '', name)
    name = re.sub(r'\.\.', '', name)
    
    # Remove any absolute path indicators
    name = re.sub(r'^[/\\]+', '', name)
    name = re.sub(r'^[a-zA-Z]:[/\\]', '', name)  # Windows absolute paths
    
    # Normalize unicode characters
    name = unicodedata.normalize('NFKD', name)
    name = name.encode('ascii', 'ignore').decode('ascii')
    
    # Replace path separators and forbidden characters with underscores
    forbidden_chars = '/\\<>:"|?*'
    for char in forbidden_chars:
        name = name.replace(char, '_')
    
    # Remove control characters and null bytes
    name = ''.join(char for char in name if ord(char) >= 32 and char != '\x00')
    
    # Replace multiple spaces/underscores with single underscore
    name = re.sub(r'[\s_]+', '_', name)
    
    # If the name ended with special characters, we might have trailing underscores
    # Keep them instead of stripping to match test expectations
    name = name.strip('. ')  # Only strip dots and spaces, not underscores
    
    # Handle reserved Windows names
    reserved_names = {
        'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 'COM5',
        'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 'LPT3', 'LPT4',
        'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }
    
    if name.upper() in reserved_names or name.upper().split('.')[0] in reserved_names:
        name = f"_{name}"
    
    # Ensure the name is not empty
    if not name:
        name = "unnamed"
    
    # Truncate to max length
    if len(name) > max_length:
        name = name[:max_length]
    
    return name

def set_file_hidden(file_path: Path):
    """Set a file as hidden on Windows."""
    if platform.system() == 'Windows':
        try:
            # Use Windows API to set hidden attribute
            FILE_ATTRIBUTE_HIDDEN = 0x02
            ctypes.windll.kernel32.SetFileAttributesW(str(file_path), FILE_ATTRIBUTE_HIDDEN)
        except Exception as e:
            logger.debug(f"Could not set file as hidden: {e}")
            
def make_unique_folder_name(parent_path: Path, base_name: str, entity_id: int) -> str:
    """
    Create a unique folder name by appending ID.
    Format: "Name_ID" (e.g., "MyProject_123")
    If a folder with this name already exists, append a counter.
    """
    safe_name = sanitize_filename(base_name)
    base_folder_name = f"{safe_name}_{entity_id}"
    
    # Check if folder already exists
    if not (parent_path / base_folder_name).exists():
        return base_folder_name
    
    # If it exists, append a counter
    counter = 1
    while True:
        folder_name = f"{safe_name}_{entity_id}_{counter}"
        if not (parent_path / folder_name).exists():
            return folder_name
        counter += 1


def get_folder_id_from_name(folder_name: str) -> Optional[int]:
    """Extract the ID from a folder name like 'ProjectName_123'."""
    match = re.search(r'_(\d+)$', folder_name)
    if match:
        return int(match.group(1))
    return None


def initialize_storage():
    """Initialize the storage system."""
    base_dir = get_config().storage.base_dir
    ensure_directory(Path(base_dir))


def create_project_directory(project_id: int, project_name: str) -> Path:
    """Create a directory for a project using its name."""
    base_dir = Path(get_config().storage.base_dir)
    folder_name = make_unique_folder_name(base_dir, project_name, project_id)
    project_path = base_dir / folder_name
    ensure_directory(project_path)
    
    # Store metadata about the project
    metadata_file = project_path / ".camf_metadata.json"
    metadata = {
        "id": project_id,
        "name": project_name,
        "type": "project"
    }
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f)
    
    # Make the metadata file hidden on Windows
    set_file_hidden(metadata_file)
    
    return project_path


def create_scene_directory(project_path: Path, scene_id: int, scene_name: str) -> Path:
    """Create a directory for a scene using its name."""
    folder_name = make_unique_folder_name(project_path, scene_name, scene_id)
    scene_path = project_path / folder_name
    ensure_directory(scene_path)
    
    # Store metadata
    metadata_file = scene_path / ".camf_metadata.json"
    metadata = {
        "id": scene_id,
        "name": scene_name,
        "type": "scene"
    }
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f)
    
    # Make the metadata file hidden on Windows
    set_file_hidden(metadata_file)
    
    return scene_path


def create_angle_directory(scene_path: Path, angle_id: int, angle_name: str) -> Path:
    """Create a directory for an angle using its name."""
    folder_name = make_unique_folder_name(scene_path, angle_name, angle_id)
    angle_path = scene_path / folder_name
    ensure_directory(angle_path)
    
    # Store metadata
    metadata_file = angle_path / ".camf_metadata.json"
    metadata = {
        "id": angle_id,
        "name": angle_name,
        "type": "angle"
    }
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f)
    
    # Make the metadata file hidden on Windows
    set_file_hidden(metadata_file)
    
    return angle_path


def create_take_directory(angle_path: Path, take_id: int, take_name: str) -> Path:
    """Create a directory for a take using its name."""
    folder_name = make_unique_folder_name(angle_path, take_name, take_id)
    take_path = angle_path / folder_name
    ensure_directory(take_path)
    
    # Store metadata
    metadata_file = take_path / ".camf_metadata.json"
    metadata = {
        "id": take_id,
        "name": take_name,
        "type": "take"
    }
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f)
    
    # Make the metadata file hidden on Windows
    set_file_hidden(metadata_file)
    
    return take_path


def find_project_folder(project_id: int) -> Optional[Path]:
    """Find a project folder by ID."""
    base_dir = Path(get_config().storage.base_dir)
    
    # Look for folders with the ID suffix
    for folder in base_dir.iterdir():
        if folder.is_dir() and get_folder_id_from_name(folder.name) == project_id:
            return folder
    
    # Fallback: check metadata files
    for folder in base_dir.iterdir():
        if folder.is_dir():
            metadata_file = folder / ".camf_metadata.json"
            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                        if metadata.get('id') == project_id and metadata.get('type') == 'project':
                            return folder
                except Exception as e:
                    logger.debug(f"Failed to read metadata file {metadata_file}: {e}")
    
    return None


def find_scene_folder(project_path: Path, scene_id: int) -> Optional[Path]:
    """Find a scene folder by ID within a project."""
    for folder in project_path.iterdir():
        if folder.is_dir() and get_folder_id_from_name(folder.name) == scene_id:
            return folder
    
    # Fallback: check metadata files
    for folder in project_path.iterdir():
        if folder.is_dir():
            metadata_file = folder / ".camf_metadata.json"
            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                        if metadata.get('id') == scene_id and metadata.get('type') == 'scene':
                            return folder
                except Exception as e:
                    logger.debug(f"Failed to read metadata file {metadata_file}: {e}")
    
    return None


def find_angle_folder(scene_path: Path, angle_id: int) -> Optional[Path]:
    """Find an angle folder by ID within a scene."""
    for folder in scene_path.iterdir():
        if folder.is_dir() and get_folder_id_from_name(folder.name) == angle_id:
            return folder
    
    # Fallback: check metadata files
    for folder in scene_path.iterdir():
        if folder.is_dir():
            metadata_file = folder / ".camf_metadata.json"
            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                        if metadata.get('id') == angle_id and metadata.get('type') == 'angle':
                            return folder
                except Exception as e:
                    logger.debug(f"Failed to read metadata file {metadata_file}: {e}")
    
    return None


def find_take_folder(angle_path: Path, take_id: int) -> Optional[Path]:
    """Find a take folder by ID within an angle."""
    for folder in angle_path.iterdir():
        if folder.is_dir() and get_folder_id_from_name(folder.name) == take_id:
            return folder
    
    # Fallback: check metadata files
    for folder in angle_path.iterdir():
        if folder.is_dir():
            metadata_file = folder / ".camf_metadata.json"
            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                        if metadata.get('id') == take_id and metadata.get('type') == 'take':
                            return folder
                except Exception as e:
                    logger.debug(f"Failed to read metadata file {metadata_file}: {e}")
    
    return None


def rename_project_folder(project_id: int, new_name: str) -> bool:
    """Rename a project folder."""
    logger.debug(f"Starting rename for project {project_id} to '{new_name}'")
    
    project_path = find_project_folder(project_id)
    if not project_path:
        logger.error(f"Project folder not found for ID {project_id}")
        return False
    
    logger.debug(f"Current path: {project_path}")
    
    try:
        # Create new folder name
        base_dir = project_path.parent
        new_folder_name = make_unique_folder_name(base_dir, new_name, project_id)
        new_path = base_dir / new_folder_name
        
        logger.debug(f"New folder name: {new_folder_name}")
        logger.debug(f"New path: {new_path}")
        
        # If it's the same path, just update metadata
        if project_path == new_path:
            logger.debug(f"Path unchanged, updating metadata only")
            metadata_file = project_path / ".camf_metadata.json"
            if metadata_file.exists():
                # Use safe JSON update
                success = safe_json_update(metadata_file, {'name': new_name})
                if success:
                    set_file_hidden(metadata_file)
                    logger.debug(f"Metadata updated successfully")
                else:
                    logger.error(f"Failed to update metadata")
                return success
            return True
        
        # Try to rename the folder using safe rename
        logger.debug(f"Attempting to rename folder...")
        rename_success = safe_folder_rename(project_path, new_path)
        
        if rename_success:
            logger.debug(f"Folder renamed successfully")
            # Update metadata in the new location
            metadata_file = new_path / ".camf_metadata.json"
            if metadata_file.exists():
                success = safe_json_update(metadata_file, {'name': new_name})
                if success:
                    set_file_hidden(metadata_file)
                    logger.debug(f"Metadata in new location updated")
            return True
        else:
            # If rename fails, at least try to update the metadata
            logger.warning(f"Could not rename folder from {project_path} to {new_path}")
            metadata_file = project_path / ".camf_metadata.json"
            if metadata_file.exists():
                success = safe_json_update(metadata_file, {'name': new_name})
                if success:
                    set_file_hidden(metadata_file)
                    logger.info(f"Updated metadata file with new name: {new_name}")
                else:
                    logger.error(f"Failed to update metadata file")
            return False
            
    except Exception as e:
        logger.error(f"Exception during project rename: {e}", exc_info=True)
        return False


def rename_scene_folder(project_id: int, scene_id: int, new_name: str) -> bool:
    """Rename a scene folder."""
    project_path = find_project_folder(project_id)
    if not project_path:
        return False
    
    scene_path = find_scene_folder(project_path, scene_id)
    if not scene_path:
        return False
    
    try:
        # Create new folder name
        new_folder_name = make_unique_folder_name(project_path, new_name, scene_id)
        new_path = project_path / new_folder_name
        
        # If it's the same path, just update metadata
        if scene_path == new_path:
            metadata_file = scene_path / ".camf_metadata.json"
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                metadata['name'] = new_name
                with open(metadata_file, 'w') as f:
                    json.dump(metadata, f)
                # Ensure it's still hidden
                set_file_hidden(metadata_file)
            return True
        
        # Rename the folder
        scene_path.rename(new_path)
        
        # Update metadata
        metadata_file = new_path / ".camf_metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            metadata['name'] = new_name
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f)
            # Ensure it's still hidden
            set_file_hidden(metadata_file)
        
        return True
    except Exception as e:
        logger.error(f"Failed to rename scene folder: {e}")
        return False


def rename_angle_folder(project_id: int, scene_id: int, angle_id: int, new_name: str) -> bool:
    """Rename an angle folder."""
    project_path = find_project_folder(project_id)
    if not project_path:
        return False
    
    scene_path = find_scene_folder(project_path, scene_id)
    if not scene_path:
        return False
    
    angle_path = find_angle_folder(scene_path, angle_id)
    if not angle_path:
        return False
    
    try:
        # Create new folder name
        new_folder_name = make_unique_folder_name(scene_path, new_name, angle_id)
        new_path = scene_path / new_folder_name
        
        # If it's the same path, just update metadata
        if angle_path == new_path:
            metadata_file = angle_path / ".camf_metadata.json"
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                metadata['name'] = new_name
                with open(metadata_file, 'w') as f:
                    json.dump(metadata, f)
                # Ensure it's still hidden
                set_file_hidden(metadata_file)
            return True
        
        # Rename the folder
        angle_path.rename(new_path)
        
        # Update metadata
        metadata_file = new_path / ".camf_metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            metadata['name'] = new_name
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f)
            # Ensure it's still hidden
            set_file_hidden(metadata_file)
        
        return True
    except Exception as e:
        logger.error(f"Failed to rename angle folder: {e}")
        return False


def rename_take_folder(project_id: int, scene_id: int, angle_id: int, take_id: int, new_name: str) -> bool:
    """Rename a take folder."""
    project_path = find_project_folder(project_id)
    if not project_path:
        return False
    
    scene_path = find_scene_folder(project_path, scene_id)
    if not scene_path:
        return False
    
    angle_path = find_angle_folder(scene_path, angle_id)
    if not angle_path:
        return False
    
    take_path = find_take_folder(angle_path, take_id)
    if not take_path:
        return False
    
    try:
        # Create new folder name
        new_folder_name = make_unique_folder_name(angle_path, new_name, take_id)
        new_path = angle_path / new_folder_name
        
        # If it's the same path, just update metadata
        if take_path == new_path:
            metadata_file = take_path / ".camf_metadata.json"
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                metadata['name'] = new_name
                with open(metadata_file, 'w') as f:
                    json.dump(metadata, f)
                # Ensure it's still hidden
                set_file_hidden(metadata_file)
            return True
        
        # Rename the folder
        take_path.rename(new_path)
        
        # Update metadata
        metadata_file = new_path / ".camf_metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            metadata['name'] = new_name
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f)
            # Ensure it's still hidden
            set_file_hidden(metadata_file)
        
        return True
    except Exception as e:
        logger.error(f"Failed to rename take folder: {e}")
        return False


# Frame storage functions removed - now using video storage system


# Frame loading functions removed - now using video storage system


def delete_project(project_id: int) -> bool:
    """Delete a project and all its data."""
    project_path = find_project_folder(project_id)
    if project_path and project_path.exists():
        shutil.rmtree(project_path)
        return True
    return False


def delete_scene(project_id: int, scene_id: int) -> bool:
    """Delete a scene directory and all its contents."""
    project_path = find_project_folder(project_id)
    if not project_path:
        return False
    
    scene_path = find_scene_folder(project_path, scene_id)
    if scene_path and scene_path.exists():
        shutil.rmtree(scene_path)
        return True
    return False


def delete_angle(project_id: int, scene_id: int, angle_id: int) -> bool:
    """Delete an angle directory and all its contents."""
    project_path = find_project_folder(project_id)
    if not project_path:
        return False
    
    scene_path = find_scene_folder(project_path, scene_id)
    if not scene_path:
        return False
    
    angle_path = find_angle_folder(scene_path, angle_id)
    if angle_path and angle_path.exists():
        shutil.rmtree(angle_path)
        return True
    return False


def delete_take(project_id: int, scene_id: int, angle_id: int, take_id: int) -> bool:
    """Delete a take directory and all its contents."""
    project_path = find_project_folder(project_id)
    if not project_path:
        return False
    
    scene_path = find_scene_folder(project_path, scene_id)
    if not scene_path:
        return False
    
    angle_path = find_angle_folder(scene_path, angle_id)
    if not angle_path:
        return False
    
    take_path = find_take_folder(angle_path, take_id)
    if take_path and take_path.exists():
        # Check if there's an active upload for this take
        from CAMF.services.api_gateway.endpoints.capture import process_uploaded_video
        if hasattr(process_uploaded_video, 'active_uploads') and take_id in process_uploaded_video.active_uploads:
            logger.warning(f"Cannot delete take {take_id} - video upload in progress")
            return False
            
        # Try to delete with retries for Windows file locking
        max_retries = 5
        retry_delay = 0.5
        
        for attempt in range(max_retries):
            try:
                shutil.rmtree(take_path)
                return True
            except PermissionError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Failed to delete take {take_id} (attempt {attempt + 1}/{max_retries}): {e}")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(f"Failed to delete take {take_id} after {max_retries} attempts: {e}")
                    return False
            except Exception as e:
                logger.error(f"Error deleting take {take_id}: {e}")
                return False
    return False


def get_project_storage_size(project_id: int) -> int:
    """Calculate total storage size for a project in bytes."""
    project_path = find_project_folder(project_id)
    if not project_path or not project_path.exists():
        return 0
    
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(project_path):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            try:
                total_size += os.path.getsize(filepath)
            except OSError:
                pass
    
    return total_size


def get_project_location(project_id: int) -> Optional[str]:
    """Get the full path to a project folder."""
    project_path = find_project_folder(project_id)
    return str(project_path) if project_path else None


# Keep compatibility functions for detector configs
def save_detector_config_file(
    project_id: int,
    scene_id: int,
    detector_name: str,
    file_name: str,
    file_data: bytes
) -> str:
    """Save a configuration file for a detector."""
    project_path = find_project_folder(project_id)
    if not project_path:
        raise ValueError(f"Project folder not found for ID {project_id}")
    
    scene_path = find_scene_folder(project_path, scene_id)
    if not scene_path:
        raise ValueError(f"Scene folder not found for ID {scene_id}")
    
    config_dir = scene_path / "detector_configs" / detector_name
    ensure_directory(config_dir)
    
    file_path = config_dir / file_name
    with open(file_path, 'wb') as f:
        f.write(file_data)
    
    return f"detector_configs/{detector_name}/{file_name}"


def get_detector_config_file_path(
    project_id: int,
    scene_id: int,
    detector_name: str,
    file_name: str
) -> Optional[Path]:
    """Get the full path to a detector configuration file."""
    project_path = find_project_folder(project_id)
    if not project_path:
        return None
    
    scene_path = find_scene_folder(project_path, scene_id)
    if not scene_path:
        return None
    
    return scene_path / "detector_configs" / detector_name / file_name


def save_detector_result_image(
    image: np.ndarray,
    project_id: int,
    scene_id: int,
    angle_id: int,
    take_id: int,
    frame_id: int,
    detector_name: str
) -> str:
    """Save a detector result image (with bounding boxes) to disk."""
    # Find the take folder
    project_path = find_project_folder(project_id)
    if not project_path:
        raise ValueError(f"Project folder not found for ID {project_id}")
    
    scene_path = find_scene_folder(project_path, scene_id)
    if not scene_path:
        raise ValueError(f"Scene folder not found for ID {scene_id}")
    
    angle_path = find_angle_folder(scene_path, angle_id)
    if not angle_path:
        raise ValueError(f"Angle folder not found for ID {angle_id}")
    
    take_path = find_take_folder(angle_path, take_id)
    if not take_path:
        raise ValueError(f"Take folder not found for ID {take_id}")
    
    result_path = take_path / "results" / detector_name
    ensure_directory(result_path)
    
    file_path = result_path / f"frame_{frame_id:08d}.jpg"
    
    # Try to import cv2 and save as image, fall back to numpy if not available
    try:
        import cv2
        cv2.imwrite(str(file_path), image)
        return str(file_path)
    except ImportError:
        # Save as numpy array if cv2 not available
        np_path = file_path.with_suffix('.npy')
        np.save(str(np_path), image)
        logger.warning("cv2 not available - saving detector result as numpy array instead of image")
        return str(np_path)


def list_detector_config_files(
    project_id: int,
    scene_id: int,
    detector_name: str
) -> List[str]:
    """List all configuration files for a detector."""
    project_path = find_project_folder(project_id)
    if not project_path:
        return []
    
    scene_path = find_scene_folder(project_path, scene_id)
    if not scene_path:
        return []
    
    config_dir = scene_path / "detector_configs" / detector_name
    
    if not config_dir.exists():
        return []
    
    return [f.name for f in config_dir.iterdir() if f.is_file()]


def delete_detector_config_files(
    project_id: int,
    scene_id: int,
    detector_name: str
):
    """Delete all configuration files for a detector."""
    project_path = find_project_folder(project_id)
    if not project_path:
        return
    
    scene_path = find_scene_folder(project_path, scene_id)
    if not scene_path:
        return
    
    config_dir = scene_path / "detector_configs" / detector_name
    
    if config_dir.exists():
        shutil.rmtree(config_dir)


def delete_detector_results(project_id: int, scene_id: int, angle_id: int, take_id: int) -> bool:
    """Delete all detector result images for a take."""
    project_path = find_project_folder(project_id)
    if not project_path:
        return False
    
    scene_path = find_scene_folder(project_path, scene_id)
    if not scene_path:
        return False
    
    angle_path = find_angle_folder(scene_path, angle_id)
    if not angle_path:
        return False
    
    take_path = find_take_folder(angle_path, take_id)
    if not take_path:
        return False
    
    results_path = take_path / "results"
    
    if results_path.exists():
        shutil.rmtree(results_path)
        return True
    return False
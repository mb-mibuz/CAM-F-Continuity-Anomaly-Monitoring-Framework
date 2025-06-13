"""
Utility functions for file operations with better error handling
"""

import os
import sys
import time
import shutil
import tempfile
from pathlib import Path
from typing import Callable
import json
import logging

# Set up logging
logger = logging.getLogger(__name__)


def safe_file_operation(operation: Callable, max_retries: int = 3, retry_delay: float = 0.1) -> bool:
    """
    Safely execute a file operation with retries on Windows.
    
    Args:
        operation: Function to execute
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds
        
    Returns:
        True if operation succeeded, False otherwise
    """
    for attempt in range(max_retries):
        try:
            operation()
            return True
        except (PermissionError, OSError) as e:
            if attempt < max_retries - 1:
                if sys.platform == 'win32':
                    # On Windows, file might be locked by antivirus or explorer
                    time.sleep(retry_delay * (attempt + 1))
                continue
            else:
                logger.error(f"Operation failed after {max_retries} attempts: {e}")
                return False
        except Exception as e:
            logger.error(f"Unexpected error in file operation: {e}")
            return False
    
    return False


def safe_json_update(file_path: Path, updates: dict) -> bool:
    """
    Safely update a JSON file with atomic writes.
    
    Args:
        file_path: Path to JSON file
        updates: Dictionary of updates to apply
        
    Returns:
        True if update succeeded, False otherwise
    """
    try:
        # Read existing data
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {}
        
        # Apply updates
        data.update(updates)
        
        # Write to temporary file
        temp_fd, temp_path = tempfile.mkstemp(dir=file_path.parent, suffix='.tmp')
        try:
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            # Atomic rename
            temp_file = Path(temp_path)
            
            if sys.platform == 'win32':
                # Windows doesn't support atomic rename if target exists
                if file_path.exists():
                    backup_path = file_path.with_suffix('.bak')
                    try:
                        # Create backup
                        shutil.copy2(file_path, backup_path)
                        # Remove original
                        file_path.unlink()
                        # Rename temp to original
                        temp_file.rename(file_path)
                        # Remove backup
                        backup_path.unlink()
                    except Exception:
                        # Restore backup if something went wrong
                        if backup_path.exists() and not file_path.exists():
                            backup_path.rename(file_path)
                        raise
                else:
                    temp_file.rename(file_path)
            else:
                # Unix supports atomic rename
                temp_file.rename(file_path)
            
            return True
            
        except Exception:
            # Clean up temp file
            if Path(temp_path).exists():
                Path(temp_path).unlink()
            raise
            
    except Exception as e:
        logger.error(f"Failed to update JSON file {file_path}: {e}")
        return False


def safe_folder_rename(old_path: Path, new_path: Path, max_retries: int = 3) -> bool:
    """
    Safely rename a folder with retries and fallback options.
    
    Args:
        old_path: Current folder path
        new_path: New folder path
        max_retries: Maximum number of retry attempts
        
    Returns:
        True if rename succeeded, False otherwise
    """
    if old_path == new_path:
        return True
    
    # Check if target already exists
    if new_path.exists():
        logger.error(f"Target path already exists: {new_path}")
        return False
    
    for attempt in range(max_retries):
        try:
            old_path.rename(new_path)
            return True
        except PermissionError as e:
            if attempt < max_retries - 1:
                if sys.platform == 'win32':
                    # On Windows, folder might be open in Explorer or locked by antivirus
                    logger.info(f"Rename attempt {attempt + 1} failed, retrying...")
                    time.sleep(0.5 * (attempt + 1))
                    
                    # Try to close any file handles
                    try:
                        import gc
                        gc.collect()
                    except:
                        pass
                continue
            else:
                logger.error(f"Failed to rename folder after {max_retries} attempts: {e}")
                return False
        except Exception as e:
            logger.error(f"Unexpected error renaming folder: {e}")
            return False
    
    return False


def ensure_file_closed(file_path: Path) -> None:
    """
    Attempt to ensure a file is not locked (Windows specific).
    """
    if sys.platform == 'win32' and file_path.exists():
        try:
            # Try to open the file exclusively
            with open(file_path, 'r+b') as f:
                pass
        except:
            # File might be locked, wait a bit
            time.sleep(0.1)
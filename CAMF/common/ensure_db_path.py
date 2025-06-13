# common/ensure_db_path.py
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def ensure_db_directory():
    """Ensure the database directory exists."""
    from CAMF.common.config import get_config
    
    config = get_config()
    # Get the directory portion of the database URL
    if config.storage.database_url.startswith('sqlite:///'):
        db_path = config.storage.database_url.replace('sqlite:///', '')
        
        # Handle relative paths
        if db_path.startswith('./'):
            # Convert relative path to absolute
            db_path = os.path.abspath(db_path)
        
        # Normalize path for the current OS
        db_path = os.path.normpath(db_path)
        db_dir = os.path.dirname(db_path)
        
        # Create the directory if it doesn't exist
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
            logger.info(f"Ensured database directory exists: {db_dir}")
            
        # Also ensure the database file exists if it's SQLite
        if not os.path.exists(db_path):
            try:
                # Create empty file
                Path(db_path).touch()
                logger.info(f"Created empty database file: {db_path}")
            except Exception as e:
                logger.error(f"Failed to create database file {db_path}: {e}")
                # Try alternative method
                try:
                    with open(db_path, 'a'):
                        pass
                    logger.info(f"Created empty database file using alternative method: {db_path}")
                except Exception as e2:
                    logger.error(f"Failed to create database file with alternative method: {e2}")
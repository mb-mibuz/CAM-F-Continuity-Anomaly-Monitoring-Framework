from CAMF.services.storage.filesystem_names import initialize_storage
from .main import get_storage_service
from .database import init_db

# Initialize storage components
def initialize():
    """Initialize the storage components."""
    init_db()
    initialize_storage()

# Export key functions
__all__ = [
    'get_storage_service',
    'initialize',
]
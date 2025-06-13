# __init__.py
from .main import get_capture_service
from .upload import VideoUploadProcessor

# Resolution presets from main.py for convenient access
from .main import RESOLUTION_PRESETS

__all__ = ['get_capture_service', 'VideoUploadProcessor', 'RESOLUTION_PRESETS']
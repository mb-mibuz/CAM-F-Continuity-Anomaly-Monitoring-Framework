"""Resolution utilities for CAMF."""

from typing import Tuple
import cv2
import numpy as np

# Resolution definitions (width, height)
RESOLUTIONS = {
    "4K": (3840, 2160),
    "1440p": (2560, 1440),
    "1080p": (1920, 1080),
    "720p": (1280, 720),
    "480p": (854, 480),
    "360p": (640, 360),
    "240p": (426, 240)
}

# Resolution order for comparison (highest to lowest)
RESOLUTION_ORDER = ["4K", "1440p", "1080p", "720p", "480p", "360p", "240p"]


def get_resolution_dimensions(resolution_name: str) -> Tuple[int, int]:
    """Get dimensions for a resolution name.
    
    Args:
        resolution_name: Name like "1080p", "720p", etc.
        
    Returns:
        Tuple of (width, height)
    """
    return RESOLUTIONS.get(resolution_name, RESOLUTIONS["1080p"])


def compare_resolutions(res1: str, res2: str) -> int:
    """Compare two resolutions.
    
    Args:
        res1: First resolution name
        res2: Second resolution name
        
    Returns:
        -1 if res1 < res2, 0 if equal, 1 if res1 > res2
    """
    try:
        idx1 = RESOLUTION_ORDER.index(res1)
        idx2 = RESOLUTION_ORDER.index(res2)
        
        if idx1 < idx2:  # res1 is higher quality (lower index)
            return 1
        elif idx1 > idx2:  # res1 is lower quality (higher index)
            return -1
        else:
            return 0
    except ValueError:
        # If resolution not found, default to comparing as equal
        return 0


def should_downscale(source_resolution: Tuple[int, int], target_resolution: str) -> bool:
    """Check if source should be downscaled to target resolution.
    
    Args:
        source_resolution: Source (width, height)
        target_resolution: Target resolution name
        
    Returns:
        True if downscaling is needed
    """
    target_width, target_height = get_resolution_dimensions(target_resolution)
    source_width, source_height = source_resolution
    
    # If source is larger than target in either dimension, downscale
    return source_width > target_width or source_height > target_height


def get_closest_resolution(width: int, height: int) -> str:
    """Get the closest standard resolution name for given dimensions.
    
    Args:
        width: Frame width
        height: Frame height
        
    Returns:
        Closest resolution name
    """
    min_diff = float('inf')
    closest_res = "1080p"
    
    for res_name, (res_width, res_height) in RESOLUTIONS.items():
        # Calculate difference in pixels
        diff = abs(width * height - res_width * res_height)
        if diff < min_diff:
            min_diff = diff
            closest_res = res_name
    
    return closest_res


def downscale_frame(frame: np.ndarray, target_resolution: str, 
                   maintain_aspect: bool = True) -> np.ndarray:
    """Downscale a frame to target resolution.
    
    Args:
        frame: Input frame as numpy array
        target_resolution: Target resolution name
        maintain_aspect: Whether to maintain aspect ratio
        
    Returns:
        Downscaled frame
    """
    target_width, target_height = get_resolution_dimensions(target_resolution)
    source_height, source_width = frame.shape[:2]
    
    # Check if downscaling is needed
    if not should_downscale((source_width, source_height), target_resolution):
        return frame
    
    if maintain_aspect:
        # Calculate scaling factor to fit within target resolution
        scale_x = target_width / source_width
        scale_y = target_height / source_height
        scale = min(scale_x, scale_y)
        
        new_width = int(source_width * scale)
        new_height = int(source_height * scale)
    else:
        new_width = target_width
        new_height = target_height
    
    # Use INTER_AREA for downscaling (best quality)
    resized = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)
    
    # If maintaining aspect ratio, pad to exact target size if needed
    if maintain_aspect and (new_width != target_width or new_height != target_height):
        # Create black canvas of target size
        canvas = np.zeros((target_height, target_width, 3), dtype=np.uint8)
        
        # Calculate position to center the resized image
        y_offset = (target_height - new_height) // 2
        x_offset = (target_width - new_width) // 2
        
        # Place resized image on canvas
        canvas[y_offset:y_offset + new_height, x_offset:x_offset + new_width] = resized
        return canvas
    
    return resized


def get_capture_resolution(source_resolution: Tuple[int, int], 
                         scene_resolution: str) -> Tuple[int, int]:
    """Determine the actual capture resolution based on source and scene settings.
    
    According to requirements:
    - If scene resolution < source resolution: downscale to scene resolution
    - If scene resolution >= source resolution: keep source resolution (no upscaling)
    
    Args:
        source_resolution: Source (width, height)
        scene_resolution: Scene resolution setting
        
    Returns:
        Actual capture resolution (width, height)
    """
    if should_downscale(source_resolution, scene_resolution):
        # Source is larger than scene setting, use scene resolution
        return get_resolution_dimensions(scene_resolution)
    else:
        # Source is smaller or equal, keep source resolution
        return source_resolution
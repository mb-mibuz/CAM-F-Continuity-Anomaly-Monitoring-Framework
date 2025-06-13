# CAMF/services/api_gateway/endpoints/crud.py
"""
Consolidated CRUD endpoints for projects, scenes, angles, and takes.
"""

from fastapi import APIRouter, HTTPException, Response
from typing import List, Dict, Any
import logging
import cv2
import numpy as np

from CAMF.services.storage import get_storage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["crud"])

# ==================== HELPER FUNCTIONS ====================

def resize_to_aspect_ratio(image: np.ndarray, target_width: int, target_height: int) -> np.ndarray:
    """
    Resize image to fit target dimensions while maintaining 16:9 aspect ratio.
    Will crop the image to fill the entire area (zoom to fit).
    """
    img_height, img_width = image.shape[:2]
    target_aspect = target_width / target_height
    img_aspect = img_width / img_height
    
    if img_aspect > target_aspect:
        # Image is wider than target - crop width
        new_height = target_height
        new_width = int(target_height * img_aspect)
        # Resize to match height
        resized = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)
        # Crop width to center
        x_offset = (new_width - target_width) // 2
        cropped = resized[:, x_offset:x_offset + target_width]
    else:
        # Image is taller than target - crop height
        new_width = target_width
        new_height = int(target_width / img_aspect)
        # Resize to match width
        resized = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)
        # Crop height to center
        y_offset = (new_height - target_height) // 2
        cropped = resized[y_offset:y_offset + target_height, :]
    
    return cropped

# ==================== PROJECT ENDPOINTS ====================

@router.get("/projects")
async def list_projects() -> List[Dict[str, Any]]:
    """List all projects."""
    storage = get_storage_service()
    projects = storage.list_projects()
    
    return [
        {
            "id": p.id,
            "name": p.name,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "scene_count": len(storage.list_scenes(p.id))
        }
        for p in projects
    ]

@router.post("/projects")
async def create_project(request: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new project."""
    storage = get_storage_service()
    
    name = request.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required")
    
    project = storage.create_project(name=name)
    
    return {
        "id": project.id,
        "name": project.name,
        "created_at": project.created_at.isoformat() if project.created_at else None
    }

@router.get("/projects/{project_id}")
async def get_project(project_id: int) -> Dict[str, Any]:
    """Get project details."""
    storage = get_storage_service()
    
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    scenes = storage.list_scenes(project_id)
    
    return {
        "id": project.id,
        "name": project.name,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "scenes": [
            {
                "id": s.id,
                "name": s.name,
                "frame_rate": s.frame_rate,
                "angle_count": len(storage.list_angles(s.id))
            }
            for s in scenes
        ]
    }

@router.put("/projects/{project_id}")
async def update_project(project_id: int, request: Dict[str, Any]) -> Dict[str, Any]:
    """Update project details."""
    storage = get_storage_service()
    
    name = request.get("name")
    if name:
        storage.update_project(project_id, name=name)
    
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return {
        "id": project.id,
        "name": project.name,
        "created_at": project.created_at.isoformat() if project.created_at else None
    }

@router.delete("/projects/{project_id}")
async def delete_project(project_id: int):
    """Delete a project."""
    storage = get_storage_service()
    
    success = storage.delete_project(project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return {"message": "Project deleted successfully"}

@router.get("/projects/{project_id}/location")
async def get_project_location(project_id: int) -> Dict[str, Any]:
    """Get the filesystem location of a project."""
    storage = get_storage_service()
    
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get the storage path from config
    import os
    
    storage_base = os.environ.get("CAMF_STORAGE_PATH", "data/storage")
    
    # Try different naming conventions
    # 1. Original name
    project_path = os.path.join(storage_base, project.name)
    if os.path.exists(project_path):
        return {"location": os.path.abspath(project_path)}
    
    # 2. Name with spaces replaced by underscores
    safe_name = project.name.replace(' ', '_')
    project_path = os.path.join(storage_base, safe_name)
    if os.path.exists(project_path):
        return {"location": os.path.abspath(project_path)}
    
    # 3. Safe name with ID suffix
    project_path_with_id = os.path.join(storage_base, f"{safe_name}_{project_id}")
    if os.path.exists(project_path_with_id):
        return {"location": os.path.abspath(project_path_with_id)}
    
    # 4. Original name with ID suffix
    project_path_with_id = os.path.join(storage_base, f"{project.name}_{project_id}")
    if os.path.exists(project_path_with_id):
        return {"location": os.path.abspath(project_path_with_id)}
    
    return {"location": None}

# NOTE: This endpoint was moved to line 731 to avoid duplication
# The version at line 731 is more sophisticated (uses latest frame, includes resizing)
# @router.get("/projects/{project_id}/thumbnail")
# async def get_project_thumbnail(project_id: int):
#     """Get thumbnail for a project."""
#     storage = get_storage_service()
#     
#     project = storage.get_project(project_id)
#     if not project:
#         raise HTTPException(status_code=404, detail="Project not found")
#     
#     # Try to find a frame from the project to use as thumbnail
#     scenes = storage.list_scenes(project_id)
#     
#     for scene in scenes:
#         angles = storage.list_angles(scene.id)
#         for angle in angles:
#             takes = storage.list_takes(angle.id)
#             for take in takes:
#                 # Try to get the first frame of this take
#                 try:
#                     # Get frame array directly
#                     frame_array = storage.get_frame_array(take.id, 0)
#                     if frame_array is not None:
#                         # Encode to JPEG
#                         _, buffer = cv2.imencode('.jpg', frame_array)
#                         
#                         # Return the image data directly
#                         return Response(
#                             content=buffer.tobytes(),
#                             media_type="image/jpeg",
#                             headers={
#                                 "Cache-Control": "public, max-age=3600",
#                                 "X-Frame-Info": f"take_{take.id}_frame_0"
#                             }
#                         )
#                 except Exception as e:
#                     logger.debug(f"Could not get frame for take {take.id}: {e}")
#                     continue
#     
#     # If no frame found, return a default gray image
#     import numpy as np
#     
#     # Create a gray image
#     gray_image = np.full((201, 357, 3), 128, dtype=np.uint8)
#     
#     # Encode as JPEG
#     _, buffer = cv2.imencode('.jpg', gray_image)
#     
#     return Response(
#         content=buffer.tobytes(),
#         media_type="image/jpeg",
#         headers={
#             "Cache-Control": "public, max-age=3600",
#             "X-Frame-Info": "default_thumbnail"
#         }
#     )

@router.get("/system/storage-path")
async def get_storage_path() -> Dict[str, str]:
    """Get the base storage path for all projects."""
    import os
    storage_base = os.environ.get("CAMF_STORAGE_PATH", "data/storage")
    return {"path": os.path.abspath(storage_base)}

# ==================== SCENE ENDPOINTS ====================

@router.get("/projects/{project_id}/scenes")
async def list_scenes(project_id: int) -> List[Dict[str, Any]]:
    """List scenes in a project."""
    storage = get_storage_service()
    
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    scenes = storage.list_scenes(project_id)
    
    return [
        {
            "id": s.id,
            "name": s.name,
            "frame_rate": s.frame_rate,
            "resolution": s.resolution,
            "image_quality": getattr(s, 'image_quality', 90),
            "detector_configurations": s.detector_settings,
            "angle_count": len(storage.list_angles(s.id)),
            "created_at": s.created_at.isoformat() if s.created_at else None
        }
        for s in scenes
    ]

@router.post("/projects/{project_id}/scenes")
async def create_scene(project_id: int, request: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new scene."""
    storage = get_storage_service()
    
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    name = request.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Scene name is required")
    
    # Get all scene parameters including detector configuration
    frame_rate = request.get("frame_rate", 24)
    resolution = request.get("resolution", "1920x1080")
    image_quality = request.get("image_quality", 90)
    enabled_detectors = request.get("enabled_detectors", [])
    detector_settings = request.get("detector_settings", {})
    
    # Clean detector settings - remove None values
    cleaned_detector_settings = {}
    if detector_settings:
        for detector_name, settings in detector_settings.items():
            if settings and isinstance(settings, dict):
                cleaned_settings = {k: v for k, v in settings.items() if v is not None}
                if cleaned_settings:
                    cleaned_detector_settings[detector_name] = cleaned_settings
    
    # Create scene with all parameters
    scene = storage.create_scene(
        project_id=project_id,
        name=name,
        frame_rate=frame_rate,
        resolution=resolution,
        image_quality=image_quality
    )
    
    # Build detector configurations dict
    detector_configurations = {}
    
    # Update scene with detector configurations if provided
    if enabled_detectors or cleaned_detector_settings:
        for detector in enabled_detectors:
            detector_configurations[detector] = {
                "enabled": True,
                **(cleaned_detector_settings.get(detector, {}))
            }
        
        storage.update_scene(
            scene.id,
            enabled_detectors=enabled_detectors,
            detector_settings=detector_configurations
        )
    
    return {
        "id": scene.id,
        "name": scene.name,
        "frame_rate": scene.frame_rate,
        "resolution": scene.resolution,
        "image_quality": scene.image_quality,
        "detector_configurations": detector_configurations,
        "created_at": scene.created_at.isoformat() if scene.created_at else None
    }

@router.get("/scenes/{scene_id}")
async def get_scene(scene_id: int) -> Dict[str, Any]:
    """Get scene details."""
    storage = get_storage_service()
    
    scene = storage.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    
    angles = storage.list_angles(scene_id)
    
    return {
        "id": scene.id,
        "name": scene.name,
        "frame_rate": scene.frame_rate,
        "resolution": scene.resolution,
        "image_quality": getattr(scene, 'image_quality', 90),
        "detector_configurations": scene.detector_settings,
        "created_at": scene.created_at.isoformat() if scene.created_at else None,
        "angles": [
            {
                "id": a.id,
                "name": a.name,
                "reference_take_id": a.reference_take_id,
                "take_count": len(storage.list_takes(a.id))
            }
            for a in angles
        ]
    }

@router.put("/scenes/{scene_id}")
async def update_scene(scene_id: int, request: Dict[str, Any]) -> Dict[str, Any]:
    """Update scene details."""
    storage = get_storage_service()
    
    updates = {}
    if "name" in request:
        updates["name"] = request["name"]
    if "frame_rate" in request:
        updates["frame_rate"] = request["frame_rate"]
    if "resolution" in request:
        updates["resolution"] = request["resolution"]
    if "image_quality" in request:
        updates["image_quality"] = request["image_quality"]
    if "detector_configurations" in request:
        updates["detector_settings"] = request["detector_configurations"]
    if "detector_settings" in request:
        updates["detector_settings"] = request["detector_settings"]
    if "enabled_detectors" in request:
        updates["enabled_detectors"] = request["enabled_detectors"]
    
    if updates:
        storage.update_scene(scene_id, **updates)
    
    scene = storage.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    
    return {
        "id": scene.id,
        "name": scene.name,
        "frame_rate": scene.frame_rate,
        "resolution": scene.resolution,
        "image_quality": getattr(scene, 'image_quality', 90),
        "detector_configurations": scene.detector_settings
    }

@router.delete("/scenes/{scene_id}")
async def delete_scene(scene_id: int):
    """Delete a scene."""
    storage = get_storage_service()
    
    success = storage.delete_scene(scene_id)
    if not success:
        raise HTTPException(status_code=404, detail="Scene not found")
    
    return {"message": "Scene deleted successfully"}

@router.get("/scenes/{scene_id}/location")
async def get_scene_location(scene_id: int) -> Dict[str, str]:
    """Get the filesystem location of a scene."""
    storage = get_storage_service()
    
    scene = storage.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    
    # Get the scene folder path
    scene_path = storage.get_scene_folder(scene_id)
    
    return {"location": scene_path}

# ==================== ANGLE ENDPOINTS ====================

@router.get("/scenes/{scene_id}/angles")
async def list_angles(scene_id: int) -> List[Dict[str, Any]]:
    """List angles in a scene."""
    storage = get_storage_service()
    
    scene = storage.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    
    angles = storage.list_angles(scene_id)
    
    return [
        {
            "id": a.id,
            "name": a.name,
            "reference_take_id": a.reference_take_id,
            "take_count": len(storage.list_takes(a.id)),
            "has_reference": a.reference_take_id is not None
        }
        for a in angles
    ]

@router.post("/scenes/{scene_id}/angles")
async def create_angle(scene_id: int, request: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new angle."""
    storage = get_storage_service()
    
    scene = storage.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    
    name = request.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Angle name is required")
    
    angle = storage.create_angle(
        scene_id=scene_id,
        name=name
    )
    
    return {
        "id": angle.id,
        "name": angle.name,
        "reference_take_id": angle.reference_take_id
    }

@router.get("/angles/{angle_id}")
async def get_angle(angle_id: int) -> Dict[str, Any]:
    """Get angle details."""
    storage = get_storage_service()
    
    angle = storage.get_angle(angle_id)
    if not angle:
        raise HTTPException(status_code=404, detail="Angle not found")
    
    takes = storage.list_takes(angle_id)
    
    return {
        "id": angle.id,
        "name": angle.name,
        "reference_take_id": angle.reference_take_id,
        "takes": [
            {
                "id": t.id,
                "name": t.name,
                "frame_count": storage.get_take_frame_count(t.id),
                "is_reference": t.id == angle.reference_take_id,
                "created_at": t.created_at.isoformat() if t.created_at else None
            }
            for t in takes
        ]
    }

@router.put("/angles/{angle_id}")
async def update_angle(angle_id: int, request: Dict[str, Any]) -> Dict[str, Any]:
    """Update angle details."""
    storage = get_storage_service()
    
    updates = {}
    if "name" in request:
        updates["name"] = request["name"]
    if "reference_take_id" in request:
        updates["reference_take_id"] = request["reference_take_id"]
    
    if updates:
        storage.update_angle(angle_id, **updates)
    
    angle = storage.get_angle(angle_id)
    if not angle:
        raise HTTPException(status_code=404, detail="Angle not found")
    
    return {
        "id": angle.id,
        "name": angle.name,
        "reference_take_id": angle.reference_take_id
    }

@router.delete("/angles/{angle_id}")
async def delete_angle(angle_id: int):
    """Delete an angle."""
    storage = get_storage_service()
    
    success = storage.delete_angle(angle_id)
    if not success:
        raise HTTPException(status_code=404, detail="Angle not found")
    
    return {"message": "Angle deleted successfully"}

@router.get("/angles/{angle_id}/reference-take")
async def get_reference_take(angle_id: int) -> Dict[str, Any]:
    """Get reference take for an angle."""
    storage = get_storage_service()
    
    angle = storage.get_angle(angle_id)
    if not angle:
        raise HTTPException(status_code=404, detail="Angle not found")
    
    if not angle.reference_take_id:
        return {"reference_take": None}
    
    take = storage.get_take(angle.reference_take_id)
    if not take:
        return {"reference_take": None}
    
    frame_count = storage.get_frame_count(take.id)
    
    return {
        "reference_take": {
            "id": take.id,
            "name": take.name,
            "frame_count": frame_count,
            "created_at": take.created_at.isoformat() if hasattr(take, 'created_at') and take.created_at else None
        }
    }

@router.post("/angles/{angle_id}/set-reference-take")
async def set_reference_take(angle_id: int, request: Dict[str, Any]) -> Dict[str, Any]:
    """Set reference take for an angle."""
    storage = get_storage_service()
    
    take_id = request.get("take_id")
    if not take_id:
        raise HTTPException(status_code=400, detail="take_id is required")
    
    # Verify angle exists
    angle = storage.get_angle(angle_id)
    if not angle:
        raise HTTPException(status_code=404, detail="Angle not found")
    
    # Verify take exists and belongs to this angle
    take = storage.get_take(take_id)
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")
    
    if take.angle_id != angle_id:
        raise HTTPException(status_code=400, detail="Take does not belong to this angle")
    
    # Update angle with reference take
    storage.update_angle(angle_id, reference_take_id=take_id)
    
    return {
        "message": "Reference take set successfully",
        "angle_id": angle_id,
        "reference_take_id": take_id
    }

# ==================== TAKE ENDPOINTS ====================

@router.get("/angles/{angle_id}/takes")
async def list_takes(angle_id: int) -> List[Dict[str, Any]]:
    """List takes in an angle."""
    storage = get_storage_service()
    
    angle = storage.get_angle(angle_id)
    if not angle:
        raise HTTPException(status_code=404, detail="Angle not found")
    
    takes = storage.list_takes(angle_id)
    
    return [
        {
            "id": t.id,
            "name": t.name,
            "frame_count": storage.get_take_frame_count(t.id),
            "is_reference": t.id == angle.reference_take_id,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "processed_at": getattr(t, 'processed_at', None).isoformat() if getattr(t, 'processed_at', None) else None,
            "notes": getattr(t, 'notes', '')
        }
        for t in takes
    ]

@router.post("/angles/{angle_id}/takes")
async def create_take(angle_id: int, request: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new take."""
    storage = get_storage_service()
    
    angle = storage.get_angle(angle_id)
    if not angle:
        raise HTTPException(status_code=404, detail="Angle not found")
    
    name = request.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Take name is required")
    
    take = storage.create_take(
        angle_id=angle_id,
        name=name,
        is_reference=request.get("is_reference", False)
    )
    
    # If this is marked as reference, update the angle
    if request.get("is_reference", False):
        storage.update_angle(angle_id, reference_take_id=take.id)
    
    return {
        "id": take.id,
        "name": take.name,
        "frame_count": getattr(take, 'frame_count', 0),  # Default to 0 if not present
        "is_reference": request.get("is_reference", False)
    }

@router.get("/takes/{take_id}")
async def get_take(take_id: int) -> Dict[str, Any]:
    """Get take details."""
    storage = get_storage_service()
    
    take = storage.get_take(take_id)
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")
    
    angle = storage.get_angle(take.angle_id)
    
    # Get frame count
    frame_count = storage.get_frame_count(take_id)
    
    # Get detector results summary
    detector_results = storage.get_detector_results_summary(take_id)
    
    return {
        "id": take.id,
        "name": take.name,
        "angle_id": take.angle_id,
        "frame_count": frame_count,
        "is_reference": angle.reference_take_id == take.id if angle else False,
        "created_at": take.created_at.isoformat() if hasattr(take, 'created_at') and take.created_at else None,
        "processed_at": getattr(take, 'processed_at', None).isoformat() if hasattr(take, 'processed_at') and getattr(take, 'processed_at', None) else None,
        "detector_results": detector_results,
        "notes": getattr(take, 'notes', '')
    }

@router.put("/takes/{take_id}")
async def update_take(take_id: int, request: Dict[str, Any]) -> Dict[str, Any]:
    """Update take details."""
    storage = get_storage_service()
    
    updates = {}
    if "name" in request:
        updates["name"] = request["name"]
    if "notes" in request:
        updates["notes"] = request["notes"]
    
    if updates:
        storage.update_take(take_id, **updates)
    
    # Handle reference take update
    if request.get("is_reference", False):
        take = storage.get_take(take_id)
        if take:
            storage.update_angle(take.angle_id, reference_take_id=take_id)
    
    take = storage.get_take(take_id)
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")
    
    angle = storage.get_angle(take.angle_id)
    
    # Get frame count from storage
    frame_count = storage.get_frame_count(take_id)
    
    return {
        "id": take.id,
        "name": take.name,
        "frame_count": frame_count,
        "is_reference": angle.reference_take_id == take.id if angle else False,
        "notes": getattr(take, 'notes', '')
    }

@router.delete("/takes/{take_id}")
async def delete_take(take_id: int):
    """Delete a take."""
    storage = get_storage_service()
    
    # Check if it's a reference take
    take = storage.get_take(take_id)
    if take:
        try:
            angle = storage.get_angle(take.angle_id)
            if angle and hasattr(angle, 'reference_take_id') and angle.reference_take_id == take_id:
                # Check if it's a temporal take (contains "_temp_" in the name)
                if "_temp_" in take.name:
                    # Clear the reference take for temporal takes
                    storage.update_angle(angle.id, reference_take_id=None)
                else:
                    raise HTTPException(
                        status_code=400, 
                        detail="Cannot delete reference take. Set another take as reference first."
                    )
        except Exception as e:
            # Log the error but allow deletion to proceed if there's an issue checking reference status
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Error checking reference status for take {take_id}: {e}")
    
    success = storage.delete_take(take_id)
    if not success:
        raise HTTPException(status_code=404, detail="Take not found")
    
    return {"message": "Take deleted successfully"}

@router.post("/takes/{take_id}/set_reference")
async def set_reference_take(take_id: int):
    """Set a take as the reference for its angle."""
    storage = get_storage_service()
    
    take = storage.get_take(take_id)
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")
    
    storage.update_angle(take.angle_id, reference_take_id=take_id)
    
    return {"message": "Reference take updated successfully"}

# ==================== THUMBNAIL ENDPOINTS ====================

@router.get("/projects/{project_id}/thumbnail")
async def get_project_thumbnail(project_id: int):
    """Get the latest frame from any take in the project as a thumbnail."""
    storage = get_storage_service()
    
    # Get all scenes in the project
    scenes = storage.list_scenes(project_id)
    if not scenes:
        # Return gray placeholder if no scenes
        placeholder = np.full((201, 357, 3), 230, dtype=np.uint8)  # 16:9 aspect ratio (357x201)
        _, buffer = cv2.imencode('.jpg', placeholder, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return Response(
            content=buffer.tobytes(),
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=300",
                "Content-Disposition": f"inline; filename=project_{project_id}_placeholder.jpg"
            }
        )
    
    latest_take = None
    latest_timestamp = None
    
    # Find the most recent take across all scenes and angles
    for scene in scenes:
        angles = storage.get_angles_for_scene(scene.id)
        for angle in angles:
            takes = storage.get_takes_for_angle(angle.id)
            for take in takes:
                if take.created_at and (latest_timestamp is None or take.created_at > latest_timestamp):
                    # Check if take has frames
                    frame_count = storage.get_frame_count(take.id)
                    if frame_count > 0:
                        latest_take = take
                        latest_timestamp = take.created_at
    
    if not latest_take:
        # Return gray placeholder if no frames found
        placeholder = np.full((201, 357, 3), 230, dtype=np.uint8)  # 16:9 aspect ratio (357x201)
        _, buffer = cv2.imencode('.jpg', placeholder, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return Response(
            content=buffer.tobytes(),
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=300",
                "Content-Disposition": f"inline; filename=project_{project_id}_placeholder.jpg"
            }
        )
    
    # Try to get frame data - first from database, then from filesystem
    frame_data = None
    
    # Method 1: Try database approach
    latest_frame_id = storage.get_latest_frame_id(latest_take.id)
    if latest_frame_id is not None:
        try:
            frame_data = storage.get_frame_array(latest_take.id, latest_frame_id)
        except Exception as e:
            logger.debug(f"Failed to get frame {latest_frame_id} from database for take {latest_take.id}: {e}")
    
    # Method 2: If database approach failed, try filesystem approach
    if frame_data is None:
        try:
            frame_data = storage.get_latest_frame_from_filesystem(latest_take.id)
            if frame_data is not None:
                logger.info(f"Successfully retrieved frame from filesystem for take {latest_take.id}")
        except Exception as e:
            logger.debug(f"Failed to get frame from filesystem for take {latest_take.id}: {e}")
    
    # If still no frame data, return placeholder
    if frame_data is None:
        placeholder = np.full((201, 357, 3), 230, dtype=np.uint8)  # 16:9 aspect ratio (357x201)
        _, buffer = cv2.imencode('.jpg', placeholder, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return Response(
            content=buffer.tobytes(),
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=300",
                "Content-Disposition": f"inline; filename=project_{project_id}_placeholder.jpg"
            }
        )
    
    # Resize to 16:9 aspect ratio (357x201 for project cards)
    frame_data = resize_to_aspect_ratio(frame_data, 357, 201)
    
    # Encode as JPEG
    _, buffer = cv2.imencode('.jpg', frame_data, [cv2.IMWRITE_JPEG_QUALITY, 85])
    
    return Response(
        content=buffer.tobytes(),
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=300",
            "Content-Disposition": f"inline; filename=project_{project_id}_thumbnail.jpg"
        }
    )

@router.get("/scenes/{scene_id}/thumbnail")
async def get_scene_thumbnail(scene_id: int):
    """Get the latest frame from any take in the scene as a thumbnail."""
    storage = get_storage_service()
    
    # Get all angles in the scene
    angles = storage.get_angles_for_scene(scene_id)
    if not angles:
        # Return gray placeholder if no angles
        placeholder = np.full((54, 96, 3), 230, dtype=np.uint8)  # 16:9 aspect ratio (96x54)
        _, buffer = cv2.imencode('.jpg', placeholder, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return Response(
            content=buffer.tobytes(),
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=300",
                "Content-Disposition": f"inline; filename=scene_{scene_id}_placeholder.jpg"
            }
        )
    
    latest_take = None
    latest_timestamp = None
    
    # Find the most recent take across all angles
    for angle in angles:
        takes = storage.get_takes_for_angle(angle.id)
        for take in takes:
            if take.created_at and (latest_timestamp is None or take.created_at > latest_timestamp):
                # Check if take has frames
                frame_count = storage.get_frame_count(take.id)
                if frame_count > 0:
                    latest_take = take
                    latest_timestamp = take.created_at
    
    if not latest_take:
        # Return gray placeholder if no frames found
        placeholder = np.full((54, 96, 3), 230, dtype=np.uint8)  # 16:9 aspect ratio (96x54)
        _, buffer = cv2.imencode('.jpg', placeholder, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return Response(
            content=buffer.tobytes(),
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=300",
                "Content-Disposition": f"inline; filename=scene_{scene_id}_placeholder.jpg"
            }
        )
    
    # Try to get frame data - first from database, then from filesystem
    frame_data = None
    
    # Method 1: Try database approach
    latest_frame_id = storage.get_latest_frame_id(latest_take.id)
    if latest_frame_id is not None:
        try:
            frame_data = storage.get_frame_array(latest_take.id, latest_frame_id)
        except Exception as e:
            logger.debug(f"Failed to get frame {latest_frame_id} from database for take {latest_take.id}: {e}")
    
    # Method 2: If database approach failed, try filesystem approach
    if frame_data is None:
        try:
            frame_data = storage.get_latest_frame_from_filesystem(latest_take.id)
            if frame_data is not None:
                logger.info(f"Successfully retrieved frame from filesystem for take {latest_take.id}")
        except Exception as e:
            logger.debug(f"Failed to get frame from filesystem for take {latest_take.id}: {e}")
    
    # If still no frame data, return placeholder
    if frame_data is None:
        placeholder = np.full((54, 96, 3), 230, dtype=np.uint8)  # 16:9 aspect ratio (96x54)
        _, buffer = cv2.imencode('.jpg', placeholder, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return Response(
            content=buffer.tobytes(),
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=300",
                "Content-Disposition": f"inline; filename=scene_{scene_id}_placeholder.jpg"
            }
        )
    
    # Resize to 16:9 aspect ratio (96x54 for scene thumbnails)
    frame_data = resize_to_aspect_ratio(frame_data, 96, 54)
    
    # Encode as JPEG
    _, buffer = cv2.imencode('.jpg', frame_data, [cv2.IMWRITE_JPEG_QUALITY, 85])
    
    return Response(
        content=buffer.tobytes(),
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=300",
            "Content-Disposition": f"inline; filename=scene_{scene_id}_thumbnail.jpg"
        }
    )
# CAMF/services/api_gateway/endpoints/capture.py
"""
Consolidated endpoints for capture operations, frame management, and video upload.
"""

import asyncio
import base64
import tempfile
import time
import uuid
import os
import cv2
from fastapi import APIRouter, HTTPException, File, UploadFile, Response, BackgroundTasks, Form
from typing import Dict, Any, Optional
from pydantic import BaseModel
import aiofiles
import numpy as np

from CAMF.services.capture import get_capture_service
from CAMF.services.storage import get_storage_service
from CAMF.services.detector_framework import get_detector_framework_service
from ..sse_integration import SSEManager as manager
from ..sse_handler import send_to_take, broadcast_system_event

router = APIRouter(tags=["capture"])

# ==================== REQUEST MODELS ====================

class CaptureStartRequest(BaseModel):
    frame_count_limit: Optional[int] = None
    is_monitoring_mode: bool = False
    reference_take_id: Optional[int] = None
    skip_detectors: bool = False

# ==================== CAPTURE SOURCE MANAGEMENT ====================

@router.get("/api/capture/sources/cameras")
async def list_cameras():
    """List available cameras."""
    capture_service = get_capture_service()
    cameras = capture_service.get_available_cameras()
    
    return {
        "cameras": [
            {
                "id": cam["id"],
                "name": cam["name"],
                "resolution": {
                    "width": cam["resolution"][0],
                    "height": cam["resolution"][1]
                }
            }
            for cam in cameras
        ]
    }

@router.get("/api/capture/sources/screens")
async def list_screens():
    """List available screens for capture."""
    capture_service = get_capture_service()
    screens = capture_service.get_available_screens()
    
    return {
        "screens": [
            {
                "id": screen["id"],
                "name": screen["name"],
                "resolution": {
                    "width": screen["resolution"][0],
                    "height": screen["resolution"][1]
                },
                "position": {
                    "x": screen["position"][0],
                    "y": screen["position"][1]
                }
            }
            for screen in screens
        ]
    }

@router.get("/api/capture/sources/monitors")
async def list_monitors():
    """List available monitors for capture."""
    capture_service = get_capture_service()
    monitors = capture_service.get_available_monitors()
    
    return {
        "monitors": [
            {
                "id": monitor["id"],
                "name": monitor.get("name", f"Monitor {monitor['id']}"),
                "resolution": monitor.get("resolution", [1920, 1080]),
                "is_primary": monitor.get("is_primary", False)
            }
            for monitor in monitors
        ]
    }

@router.get("/api/capture/sources/windows")
async def list_windows():
    """List available windows for capture."""
    capture_service = get_capture_service()
    windows = capture_service.get_available_windows()
    
    return {
        "windows": [
            {
                "id": window["handle"],  # Use handle as id
                "title": window.get("title", f"Window {window.get('handle', 'Unknown')}"),
                "process": window.get("process_name", "Unknown"),
                "visible": not window.get("is_minimized", False),
                "resolution": window.get("resolution", [0, 0])
            }
            for window in windows
        ]
    }

@router.get("/api/capture/preview/{source_type}/{source_id}")
async def get_preview_frame_by_source(source_type: str, source_id: int, quality: int = 85):
    """Get a preview frame from a specific source."""
    capture_service = get_capture_service()
    storage = get_storage_service()
    
    if source_type not in ["camera", "screen", "window"]:
        raise HTTPException(status_code=400, detail="Invalid source type")
    
    # If we're currently capturing, return the latest saved frame instead of accessing camera
    if capture_service.is_capturing:
        # Get the active take being captured
        active_take_id = capture_service.active_take_id
        if active_take_id:
            # Get the latest frame from storage
            latest_frame_id = storage.get_latest_frame_id(active_take_id)
            if latest_frame_id is not None:
                frame = storage.get_frame_array(active_take_id, latest_frame_id)
                if frame is not None:
                    # Encode and return the saved frame
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
                    frame_base64 = base64.b64encode(buffer.tobytes()).decode('utf-8')
                    return {
                        "frame": frame_base64,
                        "source_type": source_type,
                        "source_id": source_id,
                        "from_storage": True
                    }
    
    # Only access the camera directly if we're NOT capturing
    # This ensures only one process accesses the camera at a time
    if source_type == "camera" and capture_service.is_capturing:
        # Don't access camera during capture - return null frame
        return {"frame": None, "message": "Camera in use by capture process"}
    
    # Get preview frame from the specified source (only when not capturing)
    frame = capture_service.get_preview_frame_from_source(source_type, source_id)
    
    if frame is None:
        # Return empty response instead of 404 to avoid errors
        return {"frame": None}
    
    # Encode frame as JPEG with specified quality
    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    
    # Convert to base64 and return as JSON
    frame_base64 = base64.b64encode(buffer.tobytes()).decode('utf-8')
    
    return {
        "frame": frame_base64,
        "source_type": source_type,
        "source_id": source_id
    }

@router.post("/api/capture/set-source")  # Changed from set_source to set-source
async def set_capture_source(request: Dict[str, Any]):
    """Set the capture source."""
    capture_service = get_capture_service()
    
    source_type = request.get("type")
    source_id = request.get("id")
    
    if not source_type or source_id is None:
        raise HTTPException(status_code=400, detail="Source type and ID are required")
    
    if source_type not in ["camera", "screen", "window"]:
        raise HTTPException(status_code=400, detail="Invalid source type")
    
    success = capture_service.set_source(source_type, source_id)
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to set capture source")
    
    return {"message": "Capture source set successfully"}

@router.get("/api/capture/current_source")
async def get_current_source():
    """Get the currently selected capture source."""
    capture_service = get_capture_service()
    
    source_info = capture_service.get_current_source_info()
    
    if not source_info:
        return {"source": None}
    
    return {"source": source_info}

# ==================== CAPTURE CONTROL ====================

@router.post("/api/capture/start/{take_id}")
async def start_capture(take_id: int, request: CaptureStartRequest = CaptureStartRequest()):
    """Start capturing frames for a take."""
    capture_service = get_capture_service()
    storage = get_storage_service()
    detector_framework = get_detector_framework_service()
    
    take = storage.get_take(take_id)
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")
    
    if not capture_service.source:
        raise HTTPException(status_code=400, detail="No capture source selected")
    
    # Get scene settings for the take
    angle = storage.get_angle(take.angle_id)
    scene = storage.get_scene(angle.scene_id) if angle else None
    
    scene_settings = {}
    if scene:
        scene_settings = {
            'frame_rate': scene.frame_rate or 1.0,
            'resolution': scene.resolution or '1080p'
        }
    
    # Set monitoring mode if specified
    if request.is_monitoring_mode and request.reference_take_id:
        capture_service.set_monitoring_mode(True, request.reference_take_id)
    
    # Enable detectors if not skipped AND in monitoring mode
    if not request.skip_detectors and scene and request.is_monitoring_mode:
        # Set the context for the detector framework
        detector_framework.set_context(
            scene_id=scene.id,
            angle_id=angle.id,
            take_id=take_id
        )
        
        # Enable detectors configured for this scene
        if hasattr(scene, 'detector_settings') and scene.detector_settings:
            print(f"[API] Enabling detectors for monitoring mode - scene {scene.id}: {list(scene.detector_settings.keys())}")
            for detector_name, config in scene.detector_settings.items():
                if config.get('enabled', True):
                    print(f"[API] Enabling detector: {detector_name} with config: {config}")
                    # Make sure detector is actually enabled
                    success = detector_framework.enable_detector(detector_name, config)
                    if success:
                        print(f"[API] Successfully enabled detector: {detector_name}")
                    else:
                        print(f"[API] Failed to enable detector: {detector_name}")
        else:
            print(f"[API] No detector settings found for scene {scene.id}")
    
    success = capture_service.start_capture(
        take_id, 
        frame_count_limit=request.frame_count_limit,
        scene_settings=scene_settings
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to start capture")
    
    return {"message": "Capture started successfully", "take_id": take_id}

@router.post("/api/capture/stop")
async def stop_capture():
    """Stop the current capture."""
    capture_service = get_capture_service()
    
    frame_count = capture_service.stop_capture()
    
    return {
        "message": "Capture stopped successfully",
        "frame_count": frame_count
    }

@router.get("/api/capture/status")
async def get_capture_status():
    """Get current capture status."""
    capture_service = get_capture_service()
    
    return capture_service.get_capture_status()

@router.get("/api/capture/progress/{take_id}")
async def get_capture_progress(take_id: int):
    """Get capture progress for a specific take."""
    capture_service = get_capture_service()
    
    status = capture_service.get_capture_status()
    
    # Check if we're capturing the requested take
    if status.get("active_take_id") == take_id and status.get("is_capturing"):
        return {
            "frame_count": status.get("frame_count", 0),
            "is_capturing": True,
            "elapsed_time": time.time() - capture_service.capture_start_time if capture_service.capture_start_time else 0
        }
    else:
        # Not capturing this take, return frame count from storage
        storage = get_storage_service()
        frame_count = storage.get_frame_count(take_id)
        return {
            "frame_count": frame_count,
            "is_capturing": False,
            "elapsed_time": 0
        }

@router.get("/api/capture/preview")
async def get_preview_frame(quality: int = 85):
    """Get a preview frame from the current source."""
    capture_service = get_capture_service()
    storage = get_storage_service()
    
    if not capture_service.source:
        raise HTTPException(status_code=400, detail="No capture source selected")
    
    # If we're currently capturing, return the latest saved frame instead of accessing camera
    if capture_service.is_capturing:
        # Get the active take being captured
        active_take_id = capture_service.active_take_id
        if active_take_id:
            # Get the latest frame from storage
            latest_frame_id = storage.get_latest_frame_id(active_take_id)
            if latest_frame_id is not None:
                frame = storage.get_frame_array(active_take_id, latest_frame_id)
                if frame is not None:
                    # Encode and return the saved frame
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
                    frame_base64 = base64.b64encode(buffer.tobytes()).decode('utf-8')
                    return {
                        "frame": frame_base64,
                        "source_type": capture_service.source_type,
                        "source_id": getattr(capture_service.source, 'camera_id', None) or 
                                     getattr(capture_service.source, 'monitor_id', None) or 
                                     getattr(capture_service.source, 'window_handle', None),
                        "from_storage": True
                    }
    
    # Only access the camera directly if we're NOT capturing
    # This ensures only one process accesses the camera at a time
    if capture_service.source_type == "camera" and capture_service.is_capturing:
        # Don't access camera during capture - return null frame
        return {"frame": None, "message": "Camera in use by capture process"}
    
    # Use the correct method name
    frame = capture_service.get_current_preview_frame()
    
    if frame is None:
        # Return empty response instead of 404 to avoid errors
        return {"frame": None}
    
    # Encode frame as JPEG with specified quality
    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    
    # Convert to base64 and return as JSON (same format as the other preview endpoint)
    frame_base64 = base64.b64encode(buffer.tobytes()).decode('utf-8')
    
    return {
        "frame": frame_base64,
        "source_type": capture_service.source_type,
        "source_id": getattr(capture_service.source, 'camera_id', None) or 
                     getattr(capture_service.source, 'monitor_id', None) or 
                     getattr(capture_service.source, 'window_handle', None)
    }

# ==================== FRAME ACCESS ====================

@router.get("/api/frames/take/{take_id}/frame/{frame_id}")
async def get_frame(take_id: int, frame_id: int):
    """Get a specific frame as JPEG."""
    print(f"[get_frame] Request for take_id={take_id}, frame_id={frame_id}")
    storage = get_storage_service()
    
    frame = storage.get_frame(take_id, frame_id)
    
    if frame is None:
        print(f"[get_frame] Frame metadata not found for take_id={take_id}, frame_id={frame_id}")
        raise HTTPException(status_code=404, detail="Frame not found")
    
    # Get frame data as numpy array
    frame_data = storage.get_frame_array(take_id, frame_id)
    
    if frame_data is None:
        print(f"[get_frame] Frame data not found for take_id={take_id}, frame_id={frame_id}")
        raise HTTPException(status_code=404, detail="Frame data not found")
    
    print(f"[get_frame] Successfully retrieved frame {frame_id} for take {take_id}, shape: {frame_data.shape}")
    
    # Encode frame as JPEG
    _, buffer = cv2.imencode('.jpg', frame_data)
    
    return Response(
        content=buffer.tobytes(),
        media_type="image/jpeg",
        headers={
            "Cache-Control": "max-age=3600",
            "Content-Disposition": f"inline; filename=frame_{frame_id}.jpg"
        }
    )

@router.get("/api/frames/take/{take_id}/latest")
async def get_latest_frame(take_id: int):
    """Get the latest frame from a take."""
    storage = get_storage_service()
    
    latest_frame_id = storage.get_latest_frame_id(take_id)
    
    if latest_frame_id is None:
        raise HTTPException(status_code=404, detail="No frames found")
    
    return await get_frame(take_id, latest_frame_id)

@router.get("/api/frames/take/{take_id}/count")
async def get_frame_count(take_id: int):
    """Get frame count for a take."""
    storage = get_storage_service()
    
    count = storage.get_frame_count(take_id)
    print(f"[get_frame_count] Take {take_id} has {count} frames")
    
    return {"take_id": take_id, "frame_count": count}

@router.get("/api/frames/take/{take_id}/range")
async def get_frame_range(take_id: int, start: int = 0, end: Optional[int] = None):
    """Get metadata for a range of frames."""
    storage = get_storage_service()
    
    frames = storage.get_frames_in_range(take_id, start, end)
    
    return {
        "take_id": take_id,
        "frames": [
            {
                "id": f.id,
                "frame_number": f.frame_number,
                "timestamp": f.timestamp,
                "path": f.path
            }
            for f in frames
        ]
    }

@router.get("/api/frames/take/{take_id}/frame/{frame_id}/with-bounding-boxes")
async def get_frame_with_bounding_boxes(take_id: int, frame_id: int):
    """Get a frame with detector bounding boxes overlaid."""
    storage = get_storage_service()
    
    # Get the frame
    frame = storage.get_frame(take_id, frame_id)
    if not frame:
        raise HTTPException(status_code=404, detail="Frame not found")
    
    # Get detector results for this frame
    results = storage.get_detector_results_for_frame(frame_id)
    
    # Read the frame image
    import cv2
    
    # Get frame as numpy array
    img = storage.get_frame_array(take_id, frame_id)
    if img is None:
        raise HTTPException(status_code=404, detail="Frame data not found")
    
    # Draw bounding boxes
    for result in results:
        if result.bounding_boxes:
            # Handle multiple bounding boxes per result
            for bbox in result.bounding_boxes:
                x, y, w, h = bbox.get('x', 0), bbox.get('y', 0), bbox.get('width', 0), bbox.get('height', 0)
                
                # Draw rectangle
                cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 255), 2)
                
                # Add label
                label = f"{result.detector_name}: {result.description}"
                cv2.putText(img, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
    
    # Encode back to JPEG
    _, buffer = cv2.imencode('.jpg', img)
    
    return Response(
        content=buffer.tobytes(),
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Disposition": f"inline; filename=frame_{frame_id}_annotated.jpg"
        }
    )

# ==================== VIDEO UPLOAD ====================

@router.post("/api/upload/video/{take_id}")
async def upload_video(
    take_id: int, 
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None
):
    """Upload a video file for a take."""
    
    # Validate file type
    allowed_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.webm']
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid file type. Allowed formats: {', '.join(allowed_extensions)}"
        )
    
    # Check file size (max 2GB)
    max_size = 2 * 1024 * 1024 * 1024
    if file.size and file.size > max_size:
        raise HTTPException(
            status_code=400,
            detail="File size too large. Maximum size is 2GB."
        )
    
    # Get services
    get_capture_service()
    storage_service = get_storage_service()
    
    # Verify take exists
    take = storage_service.get_take(take_id)
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")
    
    # Save uploaded file temporarily
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, f"upload_{uuid.uuid4()}{file_ext}")
    
    async with aiofiles.open(temp_path, 'wb') as f:
        content = await file.read()
        await f.write(content)
    
    # Process video in background
    if background_tasks:
        background_tasks.add_task(
            process_uploaded_video,
            take_id,
            temp_path,
            file.filename
        )
    else:
        # Process synchronously if no background tasks
        await process_uploaded_video(take_id, temp_path, file.filename)
    
    return {
        "message": "Video upload started",
        "take_id": take_id,
        "filename": file.filename
    }

async def process_uploaded_video(take_id: int, video_path: str, filename: str):
    """Process uploaded video file."""
    try:
        capture_service = get_capture_service()
        detector_framework = get_detector_framework_service()
        
        # Track active uploads
        if not hasattr(process_uploaded_video, 'active_uploads'):
            process_uploaded_video.active_uploads = {}
        
        process_uploaded_video.active_uploads[take_id] = True
        
        # Send start event
        send_to_take(
            take_id,
            {
                "take_id": take_id,
                "filename": filename,
                "timestamp": time.time()
            },
            event_type="upload_started"
        )
        
        # Process video frames
        frame_count = await asyncio.to_thread(
            capture_service.process_video_upload,
            take_id,
            video_path
        )
        
        print(f"[process_uploaded_video] Extracted {frame_count} frames from video")
        
        # Send completion event
        send_to_take(
            take_id,
            {
                "take_id": take_id,
                "frame_count": frame_count,
                "filename": filename
            },
            event_type="upload_completed"
        )
        
        print(f"[process_uploaded_video] Sent upload_completed event with frame_count={frame_count}")
        
        # Start processing if detectors are available
        if detector_framework:
            detector_framework.start_processing(take_id)
            
    except Exception as e:
        # Send error event
        send_to_take(
            take_id,
            {
                "take_id": take_id,
                "error": str(e),
                "filename": filename
            },
            event_type="upload_error"
        )
    finally:
        # Clean up active upload tracking
        if hasattr(process_uploaded_video, 'active_uploads'):
            process_uploaded_video.active_uploads.pop(take_id, None)
            
        # Clean up temp file
        if os.path.exists(video_path):
            try:
                os.unlink(video_path)
            except Exception as e:
                print(f"[process_uploaded_video] Error deleting temp file: {e}")

@router.get("/api/upload/status/{take_id}")
async def get_upload_status(take_id: int):
    """Get video upload status for a take."""
    capture_service = get_capture_service()
    
    status = capture_service.get_video_upload_status(take_id)
    
    if not status:
        raise HTTPException(status_code=404, detail="No upload in progress")
    
    return status

# ==================== CAPTURE PREVIEW ====================

@router.post("/api/capture/reference/{take_id}")
async def capture_reference_frame(
    take_id: int,
    file: Optional[UploadFile] = None,
    camera_frame: Optional[str] = Form(None)
):
    """Capture or upload a reference frame for comparison."""
    storage = get_storage_service()
    
    take = storage.get_take(take_id)
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")
    
    frame_data = None
    
    # Handle file upload
    if file:
        content = await file.read()
        nparr = np.frombuffer(content, np.uint8)
        frame_data = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
    # Handle base64 camera capture
    elif camera_frame:
        # Remove data URL prefix if present
        if ',' in camera_frame:
            camera_frame = camera_frame.split(',')[1]
        
        # Decode base64
        img_data = base64.b64decode(camera_frame)
        nparr = np.frombuffer(img_data, np.uint8)
        frame_data = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if frame_data is None:
        raise HTTPException(status_code=400, detail="No valid frame data provided")
    
    # Save as first frame of the take
    frame_id = storage.save_frame(take_id, frame_data, frame_number=0)
    
    if frame_id is None:
        raise HTTPException(status_code=500, detail="Failed to save reference frame")
    
    return {
        "message": "Reference frame captured successfully",
        "take_id": take_id,
        "frame_id": frame_id
    }

# ==================== BATCH PROCESSING ====================

@router.post("/api/capture/batch/process")
async def process_video_batch(request: Dict[str, Any]):
    """Process a video file using batch processing."""
    detector_framework = get_detector_framework_service()
    
    video_path = request.get("video_path")
    take_id = request.get("take_id")
    detector_names = request.get("detector_names")
    
    if not video_path or not take_id:
        raise HTTPException(status_code=400, detail="video_path and take_id are required")
    
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video file not found")
    
    # Start batch processing
    results = detector_framework.process_video_batch(
        video_path=video_path,
        take_id=take_id,
        detector_names=detector_names
    )
    
    return results

@router.get("/api/capture/batch/progress/{batch_id}")
async def get_batch_progress(batch_id: str):
    """Get progress of batch processing."""
    detector_framework = get_detector_framework_service()
    
    progress = detector_framework.get_batch_progress(batch_id)
    
    return progress

@router.put("/api/capture/batch/config")
async def configure_batch_processing(config: Dict[str, Any]):
    """Update batch processing configuration."""
    detector_framework = get_detector_framework_service()
    
    detector_framework.configure_batch_processing(config)
    
    return {"message": "Batch processing configuration updated"}

# ==================== CAPTURE SETTINGS ====================

@router.get("/api/capture/settings")
async def get_capture_settings():
    """Get current capture settings."""
    capture_service = get_capture_service()
    
    return capture_service.get_settings()

@router.put("/api/capture/settings")
async def update_capture_settings(settings: Dict[str, Any]):
    """Update capture settings."""
    capture_service = get_capture_service()
    
    capture_service.update_settings(settings)
    
    return {"message": "Capture settings updated successfully"}
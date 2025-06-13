# CAMF/services/api_gateway/endpoints/detectors.py
"""
Consolidated endpoints for detector management, configuration, status, and debugging.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks
from typing import List, Dict, Any, Optional
import json
import tempfile
import os

from CAMF.services.detector_framework import get_detector_framework_service
from CAMF.services.storage import get_storage_service

router = APIRouter(prefix="/api/detectors", tags=["detectors"])

# ==================== DETECTOR LIFECYCLE MANAGEMENT ====================

@router.post("/start-for-scene/{scene_id}")
async def start_detectors_for_scene(scene_id: int, request: Dict[str, Any] = {}) -> Dict[str, Any]:
    """Start all enabled detectors for a scene."""
    storage = get_storage_service()
    detector_framework = get_detector_framework_service()
    
    scene = storage.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    
    # Get angle and take IDs from request if provided (for better context)
    angle_id = request.get("angle_id")
    take_id = request.get("take_id")
    
    # Set context for the detector framework
    detector_framework.set_context(scene_id=scene_id, angle_id=angle_id, take_id=take_id)
    
    started_detectors = []
    failed_detectors = []
    
    if hasattr(scene, 'detector_settings') and scene.detector_settings:
        for detector_name, settings in scene.detector_settings.items():
            if settings.get('enabled', False):
                try:
                    success = detector_framework.enable_detector(detector_name, settings)
                    if success:
                        started_detectors.append(detector_name)
                    else:
                        failed_detectors.append({"name": detector_name, "error": "Failed to enable"})
                except Exception as e:
                    failed_detectors.append({"name": detector_name, "error": str(e)})
    
    return {
        "started": started_detectors,
        "failed": failed_detectors,
        "total_started": len(started_detectors)
    }

@router.post("/stop-all")
async def stop_all_detectors() -> Dict[str, Any]:
    """Stop all active detectors."""
    detector_framework = get_detector_framework_service()
    
    active_detectors = list(detector_framework.active_detectors.keys())
    stopped_detectors = []
    failed_detectors = []
    
    for detector_name in active_detectors:
        try:
            success = detector_framework.disable_detector(detector_name)
            if success:
                stopped_detectors.append(detector_name)
            else:
                failed_detectors.append({"name": detector_name, "error": "Failed to disable"})
        except Exception as e:
            failed_detectors.append({"name": detector_name, "error": str(e)})
    
    return {
        "stopped": stopped_detectors,
        "failed": failed_detectors,
        "total_stopped": len(stopped_detectors)
    }

@router.post("/{detector_name}/start")
async def start_detector(detector_name: str, request: Dict[str, Any]) -> Dict[str, Any]:
    """Start a specific detector with configuration."""
    detector_framework = get_detector_framework_service()
    
    scene_id = request.get("scene_id")
    config = request.get("config", {})
    
    if scene_id:
        detector_framework.set_context(scene_id=scene_id, angle_id=None, take_id=None)
    
    try:
        success = detector_framework.enable_detector(detector_name, config)
        if success:
            return {
                "status": "started",
                "detector": detector_name,
                "message": f"Detector {detector_name} started successfully"
            }
        else:
            raise HTTPException(status_code=500, detail=f"Failed to start detector {detector_name}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{detector_name}/stop")
async def stop_detector(detector_name: str) -> Dict[str, Any]:
    """Stop a specific detector."""
    detector_framework = get_detector_framework_service()
    
    try:
        success = detector_framework.disable_detector(detector_name)
        if success:
            return {
                "status": "stopped",
                "detector": detector_name,
                "message": f"Detector {detector_name} stopped successfully"
            }
        else:
            raise HTTPException(status_code=500, detail=f"Failed to stop detector {detector_name}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== DETECTOR DISCOVERY & INFO ====================

@router.get("")
async def list_detectors() -> Dict[str, Any]:
    """List all available detectors."""
    try:
        detector_framework = get_detector_framework_service()
        
        detectors = detector_framework.get_available_detectors()
        
        return {
            "detectors": [
                {
                    "name": d.name,
                    "description": d.description,
                    "version": d.version,
                    "author": d.author,
                    "category": d.category,
                    "enabled": d.name in detector_framework.active_detectors,
                    "status": detector_framework.get_detector_status(d.name).__dict__ if d.name in detector_framework.active_detectors else None
                }
                for d in detectors
            ]
        }
    except Exception as e:
        # Log the error for debugging
        import logging
        logging.error(f"Error listing detectors: {str(e)}", exc_info=True)
        
        # Return empty list instead of failing
        return {"detectors": []}

# Removed duplicate /installed endpoint - the proper one is defined later in the file

@router.get("/refresh")
async def refresh_detectors() -> Dict[str, Any]:
    """Refresh the list of available detectors."""
    detector_framework = get_detector_framework_service()
    
    discovered = detector_framework.refresh_detectors()
    
    return {
        "message": "Detectors refreshed successfully",
        "discovered": discovered,
        "count": len(discovered)
    }

@router.post("/cleanup")
async def cleanup_orphaned_detectors() -> Dict[str, Any]:
    """Clean up orphaned detector directories that are not properly installed."""
    import os
    import shutil
    from pathlib import Path
    
    detector_framework = get_detector_framework_service()
    installer = detector_framework.installer
    
    cleaned = []
    errors = []
    
    # Get detector directory path
    detectors_path = Path(os.path.join(os.path.dirname(__file__), "../../../detectors"))
    
    if detectors_path.exists():
        # Get list of properly installed detectors from registry
        installed_detectors = set(installer.registry.get('detectors', {}).keys())
        
        # Check each directory
        for detector_dir in detectors_path.iterdir():
            if detector_dir.is_dir() and detector_dir.name not in ['.', '..', 'detector_template']:
                # If directory exists but not in registry, it's orphaned
                if detector_dir.name not in installed_detectors:
                    try:
                        # Validate if it's actually a detector directory
                        if (detector_dir / "detector.json").exists():
                            # It's a detector directory but not in registry - remove it
                            shutil.rmtree(detector_dir, ignore_errors=True)
                            cleaned.append(detector_dir.name)
                            
                            # Also try to remove any Docker images
                            if installer.docker_available:
                                try:
                                    base_tag = f"camf-detector-{detector_dir.name}"
                                    for image in installer.docker_client.images.list():
                                        for tag in image.tags:
                                            if tag.startswith(base_tag):
                                                installer.docker_client.images.remove(tag, force=True)
                                except:
                                    pass
                    except Exception as e:
                        errors.append({
                            "detector": detector_dir.name,
                            "error": str(e)
                        })
    
    # Refresh detector list after cleanup
    detector_framework.refresh_detectors()
    
    return {
        "message": "Cleanup completed",
        "cleaned": cleaned,
        "errors": errors,
        "total_cleaned": len(cleaned)
    }

@router.get("/installed")
async def list_installed_detectors_with_metadata() -> Dict[str, Any]:
    """List all installed detectors with installation metadata."""
    try:
        import logging
        logging.info("Getting installed detectors with metadata...")
        
        detector_framework = get_detector_framework_service()
        
        # Get the installed detectors with metadata
        installed = detector_framework.list_installed_detectors()
        logging.info(f"Found {len(installed)} installed detectors")
        
        # Get available detectors for additional info
        available = detector_framework.get_available_detectors()
        available_dict = {d.name: d for d in available}
        
        # Merge the information
        detectors = []
        for inst in installed:
            detector_name = inst.get('detector_dir_name', inst.get('detector_name', ''))
            detector_info = available_dict.get(detector_name)
            
            detector_data = {
                "name": detector_name,
                "display_name": inst.get('detector_name', detector_name),
                "directory_name": detector_name,
                "version": inst.get('detector_version', inst.get('version', '1.0.0')),
                "install_timestamp": inst.get('install_timestamp'),
                "description": detector_info.description if detector_info else '',
                "author": detector_info.author if detector_info else 'Unknown',
                "category": detector_info.category if detector_info else 'general',
                "enabled": detector_name in detector_framework.active_detectors
            }
            detectors.append(detector_data)
        
        return {"detectors": detectors}
        
    except Exception as e:
        import logging
        logging.error(f"Error listing installed detectors: {str(e)}", exc_info=True)
        return {"detectors": []}

@router.get("/{detector_name}/location")
async def get_detector_location(detector_name: str) -> Dict[str, Any]:
    """Get the filesystem location of a detector."""
    import os
    
    detector_framework = get_detector_framework_service()
    
    # Check if detector exists
    info = detector_framework.get_detector_info(detector_name)
    if not info:
        raise HTTPException(status_code=404, detail="Detector not found")
    
    # Get the detectors base path - the detectors are in CAMF/detectors
    detectors_base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "detectors"))
    detector_path = os.path.join(detectors_base, detector_name)
    
    return {
        "detector_name": detector_name,
        "location": detector_path,
        "exists": os.path.exists(detector_path)
    }

@router.get("/{detector_name}")
async def get_detector_info(detector_name: str) -> Dict[str, Any]:
    """Get detailed information about a specific detector."""
    detector_framework = get_detector_framework_service()
    
    info = detector_framework.get_detector_info(detector_name)
    
    if not info:
        raise HTTPException(status_code=404, detail="Detector not found")
    
    # Get status if active
    status = detector_framework.get_detector_status(detector_name)
    
    # Get version info
    version_info = detector_framework.check_detector_updates(detector_name)
    
    return {
        "name": info.name,
        "description": info.description,
        "version": info.version,
        "author": info.author,
        "category": info.category,
        "enabled": detector_name in detector_framework.active_detectors,
        "status": status.__dict__ if status else None,
        "version_info": version_info
    }

@router.get("/{detector_name}/schema")
async def get_detector_schema(detector_name: str) -> Dict[str, Any]:
    """Get the configuration schema for a specific detector."""
    detector_framework = get_detector_framework_service()
    
    # Get detector info to ensure it exists
    info = detector_framework.get_detector_info(detector_name)
    if not info:
        raise HTTPException(status_code=404, detail="Detector not found")
    
    # Get the schema
    try:
        schema = detector_framework.get_detector_schema(detector_name)
        if schema:
            return {"schema": schema}
        else:
            # Return a default empty schema if none is provided
            return {
                "schema": {
                    "fields": {}
                }
            }
    except Exception as e:
        # Log the error and return empty schema
        import logging
        logging.error(f"Error getting schema for detector {detector_name}: {e}")
        return {
            "schema": {
                "fields": {}
            }
        }

# ==================== DETECTOR CONFIGURATION ====================

@router.get("/scene/{scene_id}/configurations")
async def get_scene_detector_configurations(scene_id: int) -> Dict[str, Any]:
    """Get detector configurations for a scene."""
    storage = get_storage_service()
    
    scene = storage.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    
    return {
        "scene_id": scene_id,
        "configurations": scene.detector_settings or {},
        "enabled_detectors": scene.enabled_detectors or [],
        "detector_settings": scene.detector_settings or {}
    }

@router.put("/scene/{scene_id}/configurations")
async def update_scene_detector_configurations(scene_id: int, configurations: Dict[str, Any]) -> Dict[str, Any]:
    """Update detector configurations for a scene."""
    storage = get_storage_service()
    detector_framework = get_detector_framework_service()
    
    scene = storage.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    
    # Validate configurations
    for detector_name, config in configurations.items():
        if not detector_framework.get_detector_info(detector_name):
            raise HTTPException(status_code=400, detail=f"Unknown detector: {detector_name}")
    
    # Update scene configurations
    storage.update_scene(scene_id, detector_settings=configurations)
    
    # Set detector framework context
    angle = storage.list_angles(scene_id)[0] if storage.list_angles(scene_id) else None
    if angle:
        take = storage.list_takes(angle.id)[0] if storage.list_takes(angle.id) else None
        if take:
            detector_framework.set_context(scene.id, angle.id, take.id)
    
    # Enable/disable detectors based on configuration
    current_active = set(detector_framework.active_detectors.keys())
    
    for detector_name, config in configurations.items():
        if config.get("enabled", False):
            if detector_name not in current_active:
                detector_framework.enable_detector(detector_name, config)
        else:
            if detector_name in current_active:
                detector_framework.disable_detector(detector_name)
    
    return {
        "scene_id": scene_id,
        "configurations": configurations,
        "active_detectors": list(detector_framework.active_detectors.keys())
    }

@router.get("/scene/{scene_id}/detector/{detector_name}/config")
async def get_detector_config(scene_id: int, detector_name: str) -> Dict[str, Any]:
    """Get configuration for a specific detector in a scene."""
    storage = get_storage_service()
    
    scene = storage.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    
    configs = scene.detector_settings or {}
    config = configs.get(detector_name, {})
    
    return {
        "scene_id": scene_id,
        "detector_name": detector_name,
        "config": config,
        "enabled": config.get("enabled", False)
    }

@router.put("/scene/{scene_id}/detector/{detector_name}/config")
async def update_detector_config(scene_id: int, detector_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Update configuration for a specific detector in a scene."""
    storage = get_storage_service()
    detector_framework = get_detector_framework_service()
    
    scene = storage.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    
    # Validate detector exists
    if not detector_framework.get_detector_info(detector_name):
        raise HTTPException(status_code=400, detail=f"Unknown detector: {detector_name}")
    
    # Update configuration
    configs = scene.detector_settings or {}
    configs[detector_name] = config
    storage.update_scene(scene_id, detector_settings=configs)
    
    # Update detector state if context is set
    if detector_framework.current_scene_id == scene_id:
        if config.get("enabled", False):
            detector_framework.enable_detector(detector_name, config)
        else:
            detector_framework.disable_detector(detector_name)
    
    return {
        "scene_id": scene_id,
        "detector_name": detector_name,
        "config": config
    }

# ==================== DETECTOR STATUS & CONTROL ====================

@router.get("/status")
async def get_all_detector_statuses() -> Dict[str, Any]:
    """Get status of all active detectors."""
    detector_framework = get_detector_framework_service()
    
    statuses = detector_framework.get_all_detector_statuses()
    
    return {
        "active_count": len(statuses),
        "detectors": {
            name: {
                "enabled": status.enabled,
                "running": status.running,
                "total_processed": status.total_processed,
                "total_errors_found": status.total_errors_found,
                "average_processing_time": status.average_processing_time,
                "last_error": status.last_error,
                "last_error_time": status.last_error_time.isoformat() if status.last_error_time else None
            }
            for name, status in statuses.items()
        }
    }

@router.get("/{detector_name}/status")
async def get_detector_status(detector_name: str) -> Dict[str, Any]:
    """Get status of a specific detector."""
    detector_framework = get_detector_framework_service()
    
    status = detector_framework.get_detector_status(detector_name)
    
    if not status:
        raise HTTPException(status_code=404, detail="Detector not active")
    
    return {
        "name": detector_name,
        "enabled": status.enabled,
        "running": status.running,
        "total_processed": status.total_processed,
        "total_errors_found": status.total_errors_found,
        "average_processing_time": status.average_processing_time,
        "current_timeout": getattr(status, 'current_timeout', None),
        "last_error": status.last_error,
        "last_error_time": status.last_error_time.isoformat() if status.last_error_time else None
    }

@router.post("/{detector_name}/enable")
async def enable_detector(detector_name: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Enable a detector."""
    detector_framework = get_detector_framework_service()
    
    if not detector_framework.current_scene_id:
        raise HTTPException(status_code=400, detail="No scene context set")
    
    success = detector_framework.enable_detector(detector_name, config or {})
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to enable detector")
    
    return {
        "message": f"Detector {detector_name} enabled successfully",
        "status": detector_framework.get_detector_status(detector_name).__dict__
    }

@router.post("/{detector_name}/disable")
async def disable_detector(detector_name: str) -> Dict[str, Any]:
    """Disable a detector."""
    detector_framework = get_detector_framework_service()
    
    success = detector_framework.disable_detector(detector_name)
    
    if not success:
        raise HTTPException(status_code=404, detail="Detector not active")
    
    return {
        "message": f"Detector {detector_name} disabled successfully"
    }

# ==================== DETECTOR DEBUGGING ====================

@router.get("/{detector_name}/health")
async def get_detector_health(detector_name: str) -> Dict[str, Any]:
    """Get health status of a detector."""
    detector_framework = get_detector_framework_service()
    
    health = detector_framework.get_detector_health()
    detector_health = health.get(detector_name)
    
    if not detector_health:
        raise HTTPException(status_code=404, detail="Detector not found or not active")
    
    return detector_health

@router.get("/{detector_name}/gpu")
async def get_detector_gpu_status(detector_name: str) -> Dict[str, Any]:
    """Get GPU status for a detector."""
    detector_framework = get_detector_framework_service()
    
    gpu_status = detector_framework.get_detector_gpu_status(detector_name)
    
    if not gpu_status:
        return {
            "detector_name": detector_name,
            "gpu_available": False,
            "message": "GPU not available or detector not using GPU"
        }
    
    return gpu_status

@router.post("/{detector_name}/repair")
async def repair_detector(detector_name: str) -> Dict[str, Any]:
    """Attempt to repair a detector."""
    detector_framework = get_detector_framework_service()
    
    success, message = detector_framework.repair_detector(detector_name)
    
    if not success:
        raise HTTPException(status_code=500, detail=message)
    
    return {
        "message": message,
        "detector_name": detector_name
    }

# ==================== DETECTOR INSTALLATION ====================

@router.post("/install")
async def install_detector(
    file: UploadFile = File(...),
    force_reinstall: bool = False,
    background_tasks: BackgroundTasks = None
):
    """Install a detector from a ZIP file."""
    detector_framework = get_detector_framework_service()
    
    # Validate file type
    if not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="Only ZIP files are supported")
    
    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        tmp_path = tmp_file.name
    
    try:
        # Install detector
        success, message = detector_framework.install_detector_from_zip(tmp_path, force_reinstall)
        
        if not success:
            raise HTTPException(status_code=500, detail=message)
        
        # Refresh detectors after installation
        detector_framework.refresh_detectors()
        
        return {
            "message": message,
            "filename": file.filename
        }
        
    finally:
        # Clean up temp file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

@router.delete("/uninstall/{detector_name}")
async def uninstall_detector(detector_name: str) -> Dict[str, Any]:
    """Uninstall a detector."""
    detector_framework = get_detector_framework_service()
    
    success, message = detector_framework.uninstall_detector(detector_name)
    
    if not success:
        raise HTTPException(status_code=500, detail=message)
    
    # Refresh detectors after uninstallation
    detector_framework.refresh_detectors()
    
    return {
        "message": message,
        "detector_name": detector_name
    }

# ==================== DETECTOR VERSIONS ====================

@router.get("/{detector_name}/versions")
async def get_detector_versions(detector_name: str) -> List[Dict[str, Any]]:
    """Get all versions of a detector."""
    detector_framework = get_detector_framework_service()
    
    versions = detector_framework.get_detector_versions(detector_name)
    
    if not versions:
        raise HTTPException(status_code=404, detail="Detector not found")
    
    return versions

@router.post("/{detector_name}/versions")
async def create_detector_version(
    detector_name: str,
    request: Dict[str, Any]
) -> Dict[str, Any]:
    """Create a new version of a detector."""
    detector_framework = get_detector_framework_service()
    
    change_type = request.get("change_type", "PATCH")
    changelog = request.get("changelog", "")
    breaking_changes = request.get("breaking_changes", [])
    
    success, message = detector_framework.create_detector_version(
        detector_name, change_type, changelog, breaking_changes
    )
    
    if not success:
        raise HTTPException(status_code=500, detail=message)
    
    return {
        "message": message,
        "detector_name": detector_name
    }

@router.post("/{detector_name}/versions/{version}/install")
async def install_detector_version(detector_name: str, version: str) -> Dict[str, Any]:
    """Install a specific version of a detector with automatic migration."""
    detector_framework = get_detector_framework_service()
    
    success, message = detector_framework.install_detector_version(detector_name, version)
    
    if not success:
        raise HTTPException(status_code=500, detail=message)
    
    return {
        "message": message,
        "detector_name": detector_name,
        "version": version,
        "migration_note": "Scene configurations automatically migrated if needed"
    }

# ==================== DETECTOR CACHE MANAGEMENT ====================

@router.get("/cache/stats")
async def get_cache_stats() -> Dict[str, Any]:
    """Get detector result cache statistics."""
    detector_framework = get_detector_framework_service()
    
    return detector_framework.get_cache_stats()

@router.delete("/cache")
async def clear_cache() -> Dict[str, Any]:
    """Clear all detector result caches."""
    detector_framework = get_detector_framework_service()
    
    detector_framework.clear_all_cache()
    
    return {"message": "Cache cleared successfully"}

@router.delete("/cache/{detector_name}")
async def clear_detector_cache(detector_name: str) -> Dict[str, Any]:
    """Clear cache for a specific detector."""
    detector_framework = get_detector_framework_service()
    
    detector_framework.invalidate_detector_cache(detector_name)
    
    return {
        "message": f"Cache cleared for detector {detector_name}",
        "detector_name": detector_name
    }

# ==================== DETECTOR PERFORMANCE ====================

@router.get("/performance/metrics")
async def get_performance_metrics() -> Dict[str, Any]:
    """Get comprehensive performance metrics."""
    detector_framework = get_detector_framework_service()
    
    return detector_framework.get_performance_metrics()

@router.post("/performance/benchmark")
async def start_benchmark(request: Dict[str, Any]) -> Dict[str, Any]:
    """Start a performance benchmark session."""
    detector_framework = get_detector_framework_service()
    
    frame_count = request.get("frame_count", 100)
    frame_rate = request.get("frame_rate", 24)
    image_quality = request.get("image_quality", 90)
    
    session_id = detector_framework.start_benchmark_session(
        frame_count, frame_rate, image_quality
    )
    
    return {
        "session_id": session_id,
        "frame_count": frame_count,
        "frame_rate": frame_rate,
        "image_quality": image_quality
    }

@router.post("/performance/benchmark/end")
async def end_benchmark() -> Dict[str, Any]:
    """End benchmark session and get results."""
    detector_framework = get_detector_framework_service()
    
    results = detector_framework.end_benchmark_session()
    
    return results

# ==================== DETECTOR TEMPLATE ====================

@router.get("/template/{detector_name}")
async def download_detector_template(detector_name: str):
    """Download a detector template as a ZIP file."""
    import zipfile
    from fastapi.responses import StreamingResponse
    import io
    
    # Sanitize detector name for filesystem
    safe_name = detector_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
    
    # Create an in-memory ZIP file
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Create detector.json
        detector_json = {
            "name": detector_name,
            "version": "1.0.0",
            "description": f"Checks for {detector_name.lower()} continuity issues",
            "author": "Your Name",
            "category": "general",
            "requires_reference": True,
            "language": "python",
            "entry_point": "detector.py",
            "docker": {
                "base_image": "python:3.10-slim",
                "gpu_enabled": False,
                "cuda_version": "11.8.0",
                "comment": "Resource limits are optional - only set if your detector has specific requirements",
                "memory_limit": None,
                "cpu_limit": None,
                "pids_limit": None,
                "debug_mode": False
            },
            "platform_requirements": {
                "os": ["windows", "linux", "darwin"],
                "python_version": ">=3.8",
                "notes": "Runs in Docker container for consistent environment across platforms."
            },
            "runtime_requirements": {
                "min_memory_gb": 1.0,
                "recommended_memory_gb": 2.0,
                "min_cpus": 1,
                "requires_gpu": False
            },
            "dependencies": {
                "python": ">=3.8",
                "packages": [
                    "numpy>=1.20.0",
                    "opencv-python>=4.5.0",
                    "pillow>=8.0.0"
                ]
            },
            "schema": {
                "fields": {
                    "enabled": {
                        "field_type": "checkbox",
                        "title": "Enable Detector",
                        "description": "Whether this detector should be active",
                        "required": False,
                        "default": True
                    },
                    "confidence_threshold": {
                        "field_type": "slider",
                        "title": "Confidence Threshold",
                        "description": "Minimum confidence for reporting errors (0.0 = report all, 1.0 = only very certain)",
                        "required": False,
                        "default": 0.5,
                        "minimum": 0.0,
                        "maximum": 1.0
                    },
                    "custom_parameter": {
                        "field_type": "text",
                        "title": "Custom Parameter",
                        "description": "A custom parameter for your detector",
                        "required": False,
                        "default": ""
                    }
                }
            }
        }
        zip_file.writestr(f"{safe_name}/detector.json", json.dumps(detector_json, indent=2))
        
        # Create detector.py
        detector_py_content = f'''"""
{detector_name} Detector for CAMF
Docker-based detector with Linux library support.
"""

import os
import sys
import numpy as np
from typing import Dict, Any, List, Optional
import cv2
import logging
from pathlib import Path

# Add parent directory to path to import DockerDetector base class
parent_dir = Path(__file__).parent.parent.parent / "services" / "detector_framework"
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

try:
    from docker_detector_base import DockerDetector, ContinuityError
except ImportError:
    # Fallback for local development
    print("Warning: Could not import DockerDetector base class")
    DockerDetector = object
    ContinuityError = None


class {safe_name.replace('_', '')}Detector(DockerDetector):
    """Detector for {detector_name.lower()} continuity checking."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the detector with configuration."""
        # Initialize base class
        if DockerDetector != object:
            super().__init__(config)
        
        self.name = "{detector_name}"
        self.version = "1.0.0"
        self.config = config or {{}}
        
        # Default configuration
        self.enabled = self.config.get('enabled', True)
        self.confidence_threshold = self.config.get('confidence_threshold', 0.5)
        self.custom_parameter = self.config.get('custom_parameter', '')
        
        self.logger = logging.getLogger(self.name)
        
    def initialize(self):
        """Initialize the detector components."""
        try:
            self.logger.info(f"Initializing {{{{self.name}}}}...")
            
            # TODO: Initialize your detector components here
            # For example:
            # - Load ML models
            # - Initialize image processing pipelines
            # - Set up any required resources
            
            self.is_initialized = True
            self.logger.info(f"{{{{self.name}}}} initialization complete")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize detector: {{{{e}}}}")
            raise
            
    def process_frame_pair(self, current_frame: np.ndarray, 
                          reference_frame: np.ndarray,
                          metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Process a frame pair and detect continuity errors.
        
        Args:
            current_frame: Current frame as numpy array (BGR)
            reference_frame: Reference frame as numpy array (BGR)
            metadata: Additional metadata about the frames
            
        Returns:
            List of detected continuity errors
        """
        if not self.enabled:
            return []
            
        if not self.is_initialized:
            self.initialize()
            
        results = []
        
        try:
            # TODO: Implement your detection logic here
            # This is where you compare the current and reference frames
            # and detect any continuity errors
            
            # Example: Simple difference detection
            # Convert to grayscale
            gray_current = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
            gray_reference = cv2.cvtColor(reference_frame, cv2.COLOR_BGR2GRAY)
            
            # Calculate absolute difference
            diff = cv2.absdiff(gray_current, gray_reference)
            
            # Threshold the difference
            _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
            
            # Find contours
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Process contours
            for contour in contours:
                area = cv2.contourArea(contour)
                if area < 100:  # Skip small areas
                    continue
                    
                # Get bounding box
                x, y, w, h = cv2.boundingRect(contour)
                
                # Calculate confidence based on area
                confidence = min(area / 10000.0, 1.0)  # Normalize to 0-1
                
                if confidence >= self.confidence_threshold:
                    error = ContinuityError(
                        error_type="visual_change",
                        confidence=confidence,
                        location={{{{'x': int(x), 'y': int(y), 'w': int(w), 'h': int(h))}}}},
                        description=f"Visual change detected in region ({{{{x}}}}, {{{{y}}}}, {{{{w}}}}x{{{{h}}}})",
                        details={{{{
                            'area': int(area),
                            'custom_parameter': self.custom_parameter
                        }}}}
                    )
                    
                    results.append(error.to_dict())
                    
        except Exception as e:
            self.logger.error(f"Error processing frame pair: {{{{e}}}}")
            # Return error result
            error = ContinuityError(
                error_type="detector_failed",
                confidence=0.0,
                description=f"Processing failed: {{{{str(e)}}}}",
                details={{{{'error': str(e)}}}}
            )
            results.append(error.to_dict())
            
        return results
        
    def cleanup(self):
        """Cleanup resources."""
        # TODO: Clean up any resources your detector uses
        # For example:
        # - Release models from memory
        # - Close file handles
        # - Clear caches
        pass


# For Docker mode execution
if __name__ == "__main__":
    detector = {safe_name.replace('_', '')}Detector()
    detector.run()
'''
        zip_file.writestr(f"{safe_name}/detector.py", detector_py_content)
        
        # Create requirements.txt
        requirements_content = """# Core dependencies (usually provided by CAMF)
numpy>=1.19.0
opencv-python>=4.5.0
Pillow>=8.0.0

# Add your detector-specific dependencies below
# tensorflow>=2.6.0
# torch>=1.9.0
# scikit-image>=0.18.0
"""
        zip_file.writestr(f"{safe_name}/requirements.txt", requirements_content)
        
        # Create Dockerfile
        dockerfile_content = f"""# Dockerfile for {detector_name}
# Auto-generated for CAMF detector - modify as needed

FROM python:3.10-slim

# Install system dependencies for CV libraries
RUN apt-get update && apt-get install -y \\
    libglib2.0-0 \\
    libsm6 \\
    libxext6 \\
    libxrender-dev \\
    libgomp1 \\
    libgdal-dev \\
    ffmpeg \\
    && rm -rf /var/lib/apt/lists/*

# Security: Create non-root user
RUN groupadd -r detector && useradd -r -g detector detector

# Set working directory
WORKDIR /detector

# Copy requirements first for better caching
COPY requirements.txt* ./
RUN pip install --no-cache-dir --upgrade pip && \\
    pip install --no-cache-dir -r requirements.txt || true

# Copy detector code
COPY --chown=detector:detector . .

# Security: Remove unnecessary files
RUN find . -name "*.pyc" -delete && \\
    find . -name "__pycache__" -delete && \\
    find . -name ".git" -exec rm -rf {{{{}}}} + || true && \\
    find . -name ".env" -delete || true

# Create necessary directories
RUN mkdir -p /comm /tmp/.cache && \\
    chown -R detector:detector /comm /tmp/.cache

# Security: Set minimal permissions
RUN chmod -R 755 /detector && \\
    chmod -R 700 /comm

# Security: No shell for user (can be commented out for debugging)
RUN chsh -s /usr/sbin/nologin detector

# Switch to non-root user
USER detector

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV TORCH_HOME=/tmp/.cache/torch
ENV TRANSFORMERS_CACHE=/tmp/.cache/transformers
ENV HF_HOME=/tmp/.cache/huggingface

# Entry point
ENTRYPOINT ["python", "-u", "detector.py", "--docker-mode", "/comm/input", "/comm/output"]
"""
        zip_file.writestr(f"{safe_name}/Dockerfile", dockerfile_content)
        
        # Create README.md
        safe_name_lower = safe_name.lower()
        readme_content = f"# {detector_name} Detector\n\n"
        readme_content += "## Description\n"
        readme_content += f"This detector checks for {detector_name.lower()} continuity issues in film production.\n"
        readme_content += "Runs in a secure Docker container with support for Linux-based libraries.\n\n"
        readme_content += """## Configuration Options
- **enabled** (boolean): Whether this detector should be active
- **confidence_threshold** (0.0-1.0): Minimum confidence for reporting errors
- **custom_parameter** (text): A custom parameter for your detector

## Development Guide

### 1. Implement Detection Logic
Edit `detector.py` and implement the `process_frame_pair` method:
```python
def process_frame_pair(self, current_frame: np.ndarray, 
                      reference_frame: np.ndarray,
                      metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Your detection logic here
    pass
```

### 2. Update Metadata
Edit `detector.json` to:
- Update the description
- Add configuration fields
- Set author information
- Configure Docker settings
- Add Linux-specific dependencies

### 3. Add Dependencies
- Python packages: Add to `requirements.txt`
- System packages: Add to `additional_packages` in `detector.json`
- Update Dockerfile if needed for complex dependencies

### 4. Test Your Detector Locally
```bash
# Build Docker image
docker build -t {safe_name_lower} .

# Test locally (outside Docker for development)
python detector.py
```

## Docker Configuration
The detector runs in a secure Docker container with:
- Non-root user for security
- No default resource limits (research-friendly)
- Optional resource limits via detector.json configuration
- File-based IPC for secure communication
- GPU support available (set gpu_enabled: true in detector.json)
- Linux environment for specialized libraries
- Large shared memory (2GB) for PyTorch data loaders
- 1GB temp space with execution allowed for JIT compilers

### Resource Configuration (Optional)
To set resource limits, add to your detector.json:
```json
"docker": {
    "memory_limit": "8g",  // Optional memory limit
    "cpu_limit": "4",      // Optional CPU cores limit
    "pids_limit": 200      // Optional process limit
}
```

### GPU Configuration
For GPU support, update detector.json:
```json
"docker": {
    "gpu_enabled": true,
    "cuda_version": "11.8.0",
    "base_image": "nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04"
}
```

## Installation
1. Zip this directory
2. Upload via CAMF's Manage Plugins interface
3. The framework will build and manage the Docker container

## API Reference
- `current_frame`: Current take frame (numpy array, BGR format)
- `reference_frame`: Reference take frame (numpy array, BGR format)
- `metadata`: Additional frame information
  - `frame_id`: Current frame ID
  - `reference_frame_id`: Reference frame ID
  - `take_id`: Current take ID
  - `scene_id`: Scene ID
  - `angle_id`: Angle ID
  - `project_id`: Project ID

Return `ContinuityError` objects for any detected errors.

## Linux Library Support
This detector template is configured to run in a Linux Docker container,
allowing you to use Linux-specific libraries that may not be available
on Windows or macOS. Add any required system packages to the 
`additional_packages` list in `detector.json`.
""".format(safe_name_lower=safe_name_lower)
        zip_file.writestr(f"{safe_name}/README.md", readme_content)
    
    # Reset buffer position
    zip_buffer.seek(0)
    
    # Return as downloadable file
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={safe_name}_template.zip"
        }
    )
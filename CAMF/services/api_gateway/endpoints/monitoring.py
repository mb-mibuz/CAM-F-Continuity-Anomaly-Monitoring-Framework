# CAMF/services/api_gateway/endpoints/monitoring.py
"""
Consolidated endpoints for real-time monitoring, SSE, polling, and error handling.
"""

import asyncio
import json
import time
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import Dict, Any, Optional

from CAMF.services.storage import get_storage_service
from CAMF.services.detector_framework import get_detector_framework_service
from ..sse_handler import sse_manager as manager

router = APIRouter(tags=["monitoring"])

# ==================== SERVER-SENT EVENTS (SSE) ====================

@router.get("/api/sse/stream")
async def sse_stream(
    client_id: Optional[str] = Query(None, description="Client ID for the SSE connection"),
    channels: Optional[str] = Query(None, description="Comma-separated list of channels to subscribe to")
):
    """SSE endpoint for real-time updates."""
    import uuid
    
    # Generate client ID if not provided
    if not client_id:
        client_id = str(uuid.uuid4())
    
    # Parse channels
    channel_set = set()
    if channels:
        channel_set = set(channels.split(','))
    else:
        channel_set = {'system'}
    
    # Connect client
    connection = manager.connect(client_id, channel_set)
    
    async def event_generator():
        """Generate SSE events for the client."""
        try:
            # Send initial connection event
            yield f"event: connected\ndata: {json.dumps({'client_id': client_id, 'type': 'connected'})}\n\n"
            
            # Send events from queue
            while connection.active:
                try:
                    # Wait for event with timeout for heartbeat
                    event = await asyncio.wait_for(
                        connection.event_queue.get(), 
                        timeout=30.0
                    )
                    
                    # Format SSE event
                    event_info = event.get('event', {})
                    if isinstance(event_info, dict):
                        event_name = event_info.get('event', 'message')
                        data = event_info.get('data', {})
                    else:
                        event_name = event_info if isinstance(event_info, str) else 'message'
                        data = event.get('data', {})
                    
                    # Include channel and type in the data for proper routing on the frontend
                    if 'channel' in event:
                        data['channel'] = event['channel']
                    data['type'] = event_name
                    
                    event_data_json = json.dumps(data)
                    yield f"event: {event_name}\ndata: {event_data_json}\n\n"
                    
                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield f"event: heartbeat\ndata: {json.dumps({'type': 'heartbeat', 'timestamp': time.time()})}\n\n"
                    connection.last_heartbeat = time.time()
                
        except asyncio.CancelledError:
            pass  # Normal disconnection
        except Exception as e:
            print(f"Error in SSE connection for client {client_id}: {e}")
        finally:
            # Disconnect client
            manager.disconnect(client_id)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@router.post("/api/sse/broadcast")
async def broadcast_event(event: Dict[str, Any]):
    """Broadcast an event to SSE clients."""
    channel = event.get("channel", "system")
    
    manager.queue_broadcast(event, channel)
    
    return {"message": "Event broadcasted", "channel": channel}

# ==================== POLLING ENDPOINTS ====================

@router.get("/api/polling/status")
async def get_system_status():
    """Get current system status for polling."""
    get_storage_service()
    detector_framework = get_detector_framework_service()
    
    # Get capture status
    from CAMF.services.capture import get_capture_service
    capture_service = get_capture_service()
    capture_status = capture_service.get_capture_status()
    
    # Get processing status
    processing_status = detector_framework.get_processing_status()
    
    # Get detector statuses
    detector_statuses = detector_framework.get_all_detector_statuses()
    
    return {
        "timestamp": time.time(),
        "capture": capture_status,
        "processing": processing_status,
        "detectors": {
            name: {
                "enabled": status.enabled,
                "running": status.running,
                "total_processed": status.total_processed,
                "total_errors_found": status.total_errors_found
            }
            for name, status in detector_statuses.items()
        }
    }

@router.get("/api/polling/updates/{last_timestamp}")
async def get_updates_since(last_timestamp: float):
    """Get updates since the last timestamp."""
    get_storage_service()
    
    # Convert timestamp to datetime
    datetime.fromtimestamp(last_timestamp)
    current_time = datetime.now()
    
    # Get recent detector results
    recent_results = []
    
    # In a real implementation, you would query for results since the timestamp
    # For now, return empty list
    
    return {
        "timestamp": current_time.timestamp(),
        "updates": {
            "detector_results": recent_results,
            "system_events": []
        }
    }

@router.get("/api/polling/take/{take_id}/status")
async def get_take_status(take_id: int):
    """Get detailed status for a specific take."""
    storage = get_storage_service()
    detector_framework = get_detector_framework_service()
    
    take = storage.get_take(take_id)
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")
    
    # Get frame count
    frame_count = storage.get_frame_count(take_id)
    
    # Get processing status if this take is being processed
    processing_status = detector_framework.get_processing_status()
    is_processing = processing_status.get("current_take_id") == take_id
    
    # Get detector results summary
    results_summary = storage.get_detector_results_summary(take_id)
    
    return {
        "take_id": take_id,
        "frame_count": frame_count,
        "is_processing": is_processing,
        "processing_progress": processing_status if is_processing else None,
        "detector_results": results_summary,
        "last_updated": time.time()
    }

# ==================== ERROR HANDLING & RECOVERY ====================

@router.get("/api/errors/take/{take_id}")
async def get_take_errors(take_id: int):
    """Get all detector errors for a specific take."""
    storage = get_storage_service()
    
    # Get all detector results for this take
    results = storage.get_detector_results(take_id)
    
    # Filter to only errors (confidence > 0)
    errors = [
        {
            "id": getattr(result, 'id', None),
            "frame_id": result.frame_id,
            "detector_name": result.detector_name,
            "confidence": result.confidence,
            "description": result.description,
            "bounding_boxes": result.bounding_boxes or [],
            "metadata": result.meta_data if hasattr(result, 'meta_data') else getattr(result, 'metadata', {}),
            "is_false_positive": getattr(result, 'is_false_positive', False)
        }
        for result in results
        if result.confidence > 0  # Only include actual errors
    ]
    
    return {"errors": errors}

@router.get("/api/errors/grouped/{take_id}")
async def get_grouped_errors(take_id: int, include_false_positives: bool = False):
    """Get detector errors grouped into continuous errors."""
    storage = get_storage_service()
    
    # Get grouped errors using the new optimized method
    grouped_errors = storage.get_grouped_detector_results(take_id)
    
    # Filter out false positives if requested
    if not include_false_positives:
        grouped_errors = [
            error for error in grouped_errors 
            if not error.get('is_false_positive', False)
        ]
    
    return {"errors": grouped_errors}

@router.get("/api/errors/recent")
async def get_recent_errors(
    limit: int = 100,
    detector_name: Optional[str] = None
):
    """Get recent errors from detectors."""
    detector_framework = get_detector_framework_service()
    
    all_statuses = detector_framework.get_all_detector_statuses()
    
    errors = []
    for name, status in all_statuses.items():
        if detector_name and name != detector_name:
            continue
            
        if status.last_error:
            errors.append({
                "detector_name": name,
                "error": status.last_error,
                "timestamp": status.last_error_time.isoformat() if status.last_error_time else None,
                "total_processed": status.total_processed
            })
    
    # Sort by timestamp (most recent first)
    errors.sort(key=lambda x: x["timestamp"] or "", reverse=True)
    
    return errors[:limit]

@router.post("/api/errors/recover/{detector_name}")
async def recover_detector(detector_name: str):
    """Attempt to recover a failed detector."""
    detector_framework = get_detector_framework_service()
    
    # Get current status
    status = detector_framework.get_detector_status(detector_name)
    if not status:
        raise HTTPException(status_code=404, detail="Detector not found")
    
    # Disable and re-enable the detector
    detector_framework.disable_detector(detector_name)
    await asyncio.sleep(1)  # Brief pause
    
    # Get config from current scene
    if detector_framework.current_scene_id:
        storage = get_storage_service()
        scene = storage.get_scene(detector_framework.current_scene_id)
        if scene and scene.detector_configurations:
            config = scene.detector_configurations.get(detector_name, {})
            success = detector_framework.enable_detector(detector_name, config)
            
            if success:
                return {"message": f"Detector {detector_name} recovered successfully"}
    
    raise HTTPException(status_code=500, detail="Failed to recover detector")

@router.get("/api/errors/continuous/{take_id}")
async def get_continuous_errors(take_id: int):
    """Get continuous errors for a take."""
    storage = get_storage_service()
    
    continuous_errors = storage.get_continuous_errors_for_take(take_id)
    
    return {
        "take_id": take_id,
        "continuous_errors": [
            {
                "id": error.id,
                "detector_name": error.detector_name,
                "description": error.description,
                "confidence": error.average_confidence,
                "occurrence_count": error.occurrence_count,
                "start_frame": error.start_frame,
                "end_frame": error.end_frame,
                "resolved": error.resolved
            }
            for error in continuous_errors
        ]
    }

@router.post("/api/errors/continuous/{error_id}/resolve")
async def resolve_continuous_error(error_id: int):
    """Mark a continuous error as resolved."""
    storage = get_storage_service()
    
    success = storage.resolve_continuous_error(error_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Continuous error not found")
    
    return {"message": "Continuous error resolved successfully"}

# ==================== TAKE ERROR ENDPOINTS ====================

@router.get("/api/errors/take/{take_id}")
async def get_take_errors(
    take_id: int,
    detector_name: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 100
):
    """Get errors for a specific take."""
    storage = get_storage_service()
    
    # Get detector results for the take
    results = storage.get_detector_results_for_take(take_id)
    
    # Filter by detector name if specified
    if detector_name:
        results = [r for r in results if r.detector_name == detector_name]
    
    # Filter by severity if specified
    if severity:
        results = [r for r in results if r.severity == severity]
    
    # Limit results
    results = results[:limit]
    
    return {
        "errors": [
            {
                "id": f"{r.detector_name}_{r.frame_id}_{r.timestamp}",  # Generate ID from available fields
                "frame_id": r.frame_id,
                "detector_name": r.detector_name,
                "description": r.description,
                "confidence": r.confidence,
                "severity": "critical" if r.confidence > 0.8 else ("failure" if r.confidence == -1.0 else ("warning" if r.confidence > 0.5 else "low")),
                "bounding_boxes": r.bounding_boxes,  # Use correct field name
                "metadata": r.meta_data if hasattr(r, 'meta_data') else getattr(r, 'metadata', {}),
                "timestamp": r.timestamp,
                "error_type": r.error_type
            }
            for r in results
        ]
    }

# ==================== FALSE POSITIVE MANAGEMENT ====================

@router.post("/api/errors/false-positive")
async def mark_false_positive(request: Dict[str, Any]):
    """Mark a detector result as false positive."""
    storage = get_storage_service()
    
    # Extract parameters
    take_id = request.get("take_id")
    detector_name = request.get("detector_name")
    frame_id = request.get("frame_id")
    error_id = request.get("error_id")
    reason = request.get("reason", "")
    marked_by = request.get("marked_by", "user")
    
    # Log the incoming request for debugging
    # Mark false positive request received
    
    # Validate required fields - frame_id is optional if we have error_id
    if not all([take_id, detector_name]) or not (frame_id or error_id):
        raise HTTPException(
            status_code=400, 
            detail="take_id and detector_name are required, plus either frame_id or error_id"
        )
    
    # Use storage service to mark as false positive
    # We need to find the detector result and update it
    from CAMF.services.storage.database import get_session, DetectorResultDB
    
    session = get_session()
    try:
        # Try to extract description from request for group-based matching
        description = request.get("description")
        
        # Check if error_id looks like a group ID (UUID or timestamp-based)
        is_group_id = error_id and isinstance(error_id, str) and (
            '-' in str(error_id) or  # UUID format
            (len(str(error_id)) > 10 and not str(error_id).isdigit())  # Long non-numeric ID
        )
        
        # Marking false positive
        
        # For grouped errors, we match by description which is how they're grouped
        if description:
            # This is a group - find all errors with same description
            # Looking for errors with description
            query = session.query(DetectorResultDB).filter(
                DetectorResultDB.take_id == take_id,
                DetectorResultDB.detector_name == detector_name,
                DetectorResultDB.description == description
            )
        elif is_group_id:
            # Try by group ID
            # Looking for errors with group_id
            query = session.query(DetectorResultDB).filter(
                DetectorResultDB.take_id == take_id,
                DetectorResultDB.detector_name == detector_name,
                DetectorResultDB.error_group_id == error_id
            )
        else:
            # Regular query by frame_id
            # Looking for single error with frame_id
            query = session.query(DetectorResultDB).filter(
                DetectorResultDB.take_id == take_id,
                DetectorResultDB.detector_name == detector_name
            )
            
            if frame_id is not None:
                query = query.filter(DetectorResultDB.frame_id == frame_id)
            
            # If error_id is numeric, use it as database ID
            if error_id and str(error_id).isdigit():
                query = query.filter(DetectorResultDB.id == int(error_id))
        
        results = query.all()
        
        # Debug: Log how many results were found
        # Found matching detector results
        
        if not results:
            # Try a broader query for debugging
            all_results = session.query(DetectorResultDB).filter(
                DetectorResultDB.take_id == take_id,
                DetectorResultDB.detector_name == detector_name
            ).limit(10).all()
            # Sample results for debugging
            for r in all_results:
                pass  # Debug output removed
            
            raise HTTPException(
                status_code=404,
                detail="No matching detector results found"
            )
        
        # Mark all matching results as false positive
        updated_count = 0
        for result in results:
            result.is_false_positive = True
            result.false_positive_reason = f"{reason} (marked by {marked_by})"
            updated_count += 1
            # Marked result as false positive
        
        session.commit()
        
        # Invalidate cache for this take
        from CAMF.services.storage.error_cache import get_error_cache
        cache = get_error_cache()
        cache.invalidate(take_id)
        
        return {
            "message": "Marked as false positive successfully",
            "updated_count": updated_count
        }
        
    except HTTPException:
        session.rollback()
        raise  # Re-raise HTTPException as-is
    except Exception as e:
        session.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to mark as false positive: {str(e)}"
        )
    finally:
        session.close()

@router.get("/api/errors/false-positives/{detector_name}")
async def get_false_positives(detector_name: str, limit: int = 100):
    """Get false positives for a detector."""
    from CAMF.services.storage.false_positive_manager import FalsePositiveManager
    fp_manager = FalsePositiveManager()
    
    false_positives = fp_manager.get_false_positives(
        detector_name=detector_name,
        limit=limit
    )
    
    return {
        "detector_name": detector_name,
        "false_positives": false_positives
    }

# ==================== PERFORMANCE MONITORING ====================

@router.get("/api/monitoring/performance")
async def get_performance_metrics():
    """Get system performance metrics."""
    detector_framework = get_detector_framework_service()
    
    metrics = detector_framework.get_performance_metrics()
    
    # Add storage metrics
    storage = get_storage_service()
    storage_stats = storage.get_storage_statistics()
    
    metrics["storage"] = storage_stats
    
    return metrics

@router.get("/api/monitoring/health")
async def health_check():
    """System health check endpoint."""
    try:
        # Check services
        storage = get_storage_service()
        detector_framework = get_detector_framework_service()
        
        # Basic health checks
        storage_healthy = storage is not None
        detector_healthy = detector_framework is not None
        
        # Get detector health
        detector_health = detector_framework.get_detector_health() if detector_healthy else {}
        
        return {
            "status": "healthy" if storage_healthy and detector_healthy else "degraded",
            "timestamp": time.time(),
            "services": {
                "storage": "healthy" if storage_healthy else "unhealthy",
                "detector_framework": "healthy" if detector_healthy else "unhealthy",
                "detectors": detector_health
            }
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "timestamp": time.time(),
            "error": str(e)
        }

# ==================== PROCESSING MONITORING ====================

@router.get("/api/processing/status")
async def get_processing_status():
    """Get current processing status."""
    detector_framework = get_detector_framework_service()
    
    status = detector_framework.get_processing_status()
    
    # Workaround: Check if processing just completed and send event
    if (not status['is_processing'] and 
        status.get('processed_frames', 0) > 0 and 
        status.get('processed_frames', 0) == status.get('total_frames', 0) and
        status.get('current_take_id')):
        
        # Check if we need to send completion event
        if not hasattr(get_processing_status, '_last_completed_take'):
            get_processing_status._last_completed_take = None
            
        take_id = status['current_take_id']
        if take_id != get_processing_status._last_completed_take:
            # Processing just completed for this take, send event
            get_processing_status._last_completed_take = take_id
            
            # Import here to avoid circular dependency
            from ..sse_handler import broadcast_system_event, send_to_take
            
            event_data = {
                'takeId': take_id,
                'summary': {
                    'total_frames': status['total_frames'],
                    'processed_frames': status['processed_frames'],
                    'failed_frames': status.get('failed_frames', 0),
                    'duration': status.get('elapsed_time', 0)
                },
                'timestamp': time.time()
            }
            
            # Send processing complete event
            broadcast_system_event('processing_complete', event_data)
            send_to_take(take_id, {
                'type': 'processing_complete',
                'data': event_data
            }, event_type="processing_complete")
            
            # Sent processing_complete event (workaround)
    
    return status

@router.post("/api/processing/start")
async def start_processing(request: Dict[str, Any]):
    """Start processing frames for a take."""
    detector_framework = get_detector_framework_service()
    storage = get_storage_service()
    
    take_id = request.get("take_id")
    if not take_id:
        raise HTTPException(status_code=400, detail="Take ID is required")
    
    reference_take_id = request.get("reference_take_id")
    
    take = storage.get_take(take_id)
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")
    
    # Get angle and scene for detector configuration
    angle = storage.get_angle(take.angle_id)
    if not angle:
        raise HTTPException(status_code=404, detail="Angle not found")
        
    scene = storage.get_scene(angle.scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    
    # Set the context for the detector framework
    detector_framework.set_context(
        scene_id=scene.id,
        angle_id=angle.id,
        take_id=take_id
    )
    
    # Enable detectors configured for this scene
    if hasattr(scene, 'detector_settings') and scene.detector_settings:
        # Enable detectors for scene
        for detector_name, config in scene.detector_settings.items():
            if config.get('enabled', True):
                # Enable detector with config
                detector_framework.enable_detector(detector_name, config)
    else:
        # No detector settings found for scene
        pass
    
    success = detector_framework.start_processing(take_id, reference_take_id)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to start processing")
    
    return {
        "message": "Processing started successfully",
        "take_id": take_id
    }

@router.post("/api/processing/stop")
async def stop_processing():
    """Stop current processing."""
    detector_framework = get_detector_framework_service()
    
    detector_framework.stop_processing()
    
    return {
        "message": "Processing stopped"
    }

@router.post("/api/processing/restart")
async def restart_processing(request: Dict[str, Any]):
    """Restart processing for a take (redo detection)."""
    detector_framework = get_detector_framework_service()
    storage = get_storage_service()
    
    take_id = request.get("take_id")
    if not take_id:
        raise HTTPException(status_code=400, detail="Take ID is required")
    
    reference_take_id = request.get("reference_take_id")
    
    # Log the restart request
    # Processing restart requested
    
    # Verify take exists
    take = storage.get_take(take_id)
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")
    
    # Get angle and scene for detector configuration
    angle = storage.get_angle(take.angle_id)
    if not angle:
        raise HTTPException(status_code=404, detail="Angle not found")
        
    scene = storage.get_scene(angle.scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    
    # Stop any current processing
    detector_framework.stop_processing()
    
    # Set the context for the detector framework
    detector_framework.set_context(
        scene_id=scene.id,
        angle_id=angle.id,
        take_id=take_id
    )
    
    # Enable detectors configured for this scene
    if hasattr(scene, 'detector_settings') and scene.detector_settings:
        # Enable detectors for scene
        for detector_name, config in scene.detector_settings.items():
            if config.get('enabled', True):
                # Enable detector with config
                detector_framework.enable_detector(detector_name, config)
    else:
        # No detector settings found for scene
        pass
    
    # Clear previous results for this take (including false positive flags)
    cleared_count = storage.clear_take_detector_results(take_id)
    # Cleared previous detector results
    
    # Start processing again
    success = detector_framework.start_processing(take_id, reference_take_id)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to restart processing")
    
    # Broadcast events
    await manager.broadcast(
        event="detector_results_cleared",
        data={
            "take_id": take_id,
            "cleared_count": cleared_count
        },
        channel="processing_events"
    )
    
    await manager.broadcast(
        event="processing_restarted",
        data={
            "take_id": take_id,
            "reference_take_id": reference_take_id
        },
        channel="processing_events"
    )
    
    return {
        "message": "Processing restarted successfully",
        "take_id": take_id,
        "reference_take_id": reference_take_id
    }

# ==================== SESSION MANAGEMENT ====================

@router.get("/api/sessions/current")
async def get_current_session():
    """Get current session information."""
    storage = get_storage_service()
    
    context = storage.get_frame_context()
    
    return {
        "session_id": str(id(storage)),  # Simple session ID
        "context": context,
        "timestamp": time.time()
    }

@router.post("/api/sessions/context")
async def update_session_context(context: Dict[str, Any]):
    """Update session context."""
    storage = get_storage_service()
    detector_framework = get_detector_framework_service()
    
    # Update storage context
    storage.set_frame_context(
        project_id=context.get("project_id"),
        scene_id=context.get("scene_id"),
        angle_id=context.get("angle_id"),
        take_id=context.get("take_id")
    )
    
    # Update detector framework context
    if all(k in context for k in ["scene_id", "angle_id", "take_id"]):
        detector_framework.set_context(
            scene_id=context["scene_id"],
            angle_id=context["angle_id"],
            take_id=context["take_id"]
        )
    
    return {"message": "Context updated successfully"}
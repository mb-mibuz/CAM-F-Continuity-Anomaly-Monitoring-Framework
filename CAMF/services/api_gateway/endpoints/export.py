# CAMF/services/api_gateway/endpoints/export.py
"""
Consolidated endpoints for export operations, notes, and miscellaneous features.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from typing import List, Dict, Any, Optional
import os
from datetime import datetime

from CAMF.services.storage import get_storage_service
from CAMF.services.export import get_export_service
from CAMF.services.detector_framework import get_detector_framework_service

router = APIRouter(tags=["export"])

# ==================== EXPORT ENDPOINTS ====================

@router.post("/api/export/take/{take_id}/pdf")
async def export_take_pdf(
    take_id: int,
    background_tasks: BackgroundTasks,
    request: Dict[str, Any] = {}
):
    """Export a take as PDF report."""
    storage = get_storage_service()
    export_service = get_export_service()
    
    take = storage.get_take(take_id)
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")
    
    # Options
    request.get("include_all_frames", False)
    request.get("include_notes", True)
    request.get("include_detector_results", True)
    
    # Generate PDF in a temporary file
    import tempfile
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    output_path = temp_file.name
    temp_file.close()
    
    # Call the correct method name
    result = export_service.export_take_report(
        take_id=take_id,
        output_path=output_path
    )
    
    if not result:
        raise HTTPException(status_code=500, detail="Export service returned None")
    
    if not os.path.exists(output_path):
        raise HTTPException(status_code=500, detail=f"PDF file not found at {output_path}")
    
    # Check file size
    file_size = os.path.getsize(output_path)
    if file_size == 0:
        raise HTTPException(status_code=500, detail="Generated PDF is empty")
    
    # Schedule cleanup after response
    def cleanup_temp_file():
        try:
            os.unlink(output_path)
        except:
            pass
    
    background_tasks.add_task(cleanup_temp_file)
    
    # Return file
    return FileResponse(
        output_path,
        media_type="application/pdf",
        filename=f"take_{take.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    )

@router.post("/api/export/scene/{scene_id}/pdf")
async def export_scene_pdf(
    scene_id: int,
    background_tasks: BackgroundTasks,
    request: Dict[str, Any] = {}
):
    """Export a scene summary as PDF."""
    storage = get_storage_service()
    export_service = get_export_service()
    
    scene = storage.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    
    # Generate PDF in a temporary file
    import tempfile
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    output_path = temp_file.name
    temp_file.close()
    
    # Call the correct method name
    result = export_service.export_scene_report(
        scene_id=scene_id,
        output_path=output_path
    )
    
    if not output_path or not os.path.exists(output_path):
        raise HTTPException(status_code=500, detail="Failed to generate PDF")
    
    return FileResponse(
        output_path,
        media_type="application/pdf",
        filename=f"scene_{scene.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        background=background_tasks
    )

@router.post("/api/export/project/{project_id}/pdf")
async def export_project_pdf(
    project_id: int,
    background_tasks: BackgroundTasks,
    request: Dict[str, Any] = {}
):
    """Export a project summary as PDF."""
    storage = get_storage_service()
    export_service = get_export_service()
    
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Generate PDF in a temporary file
    import tempfile
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    output_path = temp_file.name
    temp_file.close()
    
    # Call the project report method - if not exists, create a simple summary
    try:
        # Try to call project report if it exists
        result = export_service.export_project_report(
            project_id=project_id,
            output_path=output_path
        )
    except AttributeError:
        # Method doesn't exist, create a simple project summary
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch
        
        doc = SimpleDocTemplate(output_path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        story.append(Paragraph(f"Project Report: {project.name}", styles['Title']))
        story.append(Spacer(1, 0.3*inch))
        story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        story.append(Spacer(1, 0.5*inch))
        
        # Project info
        story.append(Paragraph("Project Summary", styles['Heading1']))
        story.append(Paragraph(f"Project ID: {project.id}", styles['Normal']))
        story.append(Paragraph(f"Created: {project.created_at}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        # List scenes
        scenes = storage.list_scenes(project_id)
        story.append(Paragraph(f"Total Scenes: {len(scenes)}", styles['Normal']))
        story.append(Spacer(1, 0.2*inch))
        
        for scene in scenes:
            story.append(Paragraph(f"Scene: {scene.name}", styles['Heading2']))
            angles = storage.list_angles(scene.id)
            story.append(Paragraph(f"  - Angles: {len(angles)}", styles['Normal']))
            
            total_takes = 0
            for angle in angles:
                takes = storage.list_takes(angle.id)
                total_takes += len(takes)
            
            story.append(Paragraph(f"  - Total Takes: {total_takes}", styles['Normal']))
            story.append(Paragraph(f"  - Frame Rate: {scene.frame_rate} fps", styles['Normal']))
            story.append(Paragraph(f"  - Resolution: {scene.resolution}", styles['Normal']))
            story.append(Spacer(1, 0.2*inch))
        
        doc.build(story)
    
    if not output_path or not os.path.exists(output_path):
        raise HTTPException(status_code=500, detail="Failed to generate PDF")
    
    return FileResponse(
        output_path,
        media_type="application/pdf",
        filename=f"project_{project.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        background=background_tasks
    )

@router.post("/api/export/detector-report")
async def export_detector_report(
    request: Dict[str, Any],
    background_tasks: BackgroundTasks
):
    """Export detector performance report."""
    detector_framework = get_detector_framework_service()
    
    duration_hours = request.get("duration_hours", 1.0)
    output_dir = request.get("output_dir", "reports")
    
    report_paths = detector_framework.export_performance_report(
        duration_hours=duration_hours,
        output_dir=output_dir
    )
    
    if not report_paths or "error" in report_paths:
        raise HTTPException(
            status_code=500,
            detail=report_paths.get("error", "Failed to generate report")
        )
    
    # Return the main report file
    main_report = report_paths.get("summary_report")
    if main_report and os.path.exists(main_report):
        return FileResponse(
            main_report,
            media_type="application/pdf",
            filename=f"detector_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            background=background_tasks
        )
    
    return report_paths

# ==================== NOTE MANAGEMENT ====================

@router.get("/api/takes/{take_id}/notes")
async def get_take_notes(take_id: int):
    """Get notes for a take."""
    storage = get_storage_service()
    
    take = storage.get_take(take_id)
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")
    
    notes_data = storage.get_notes_for_take(take_id)
    
    return notes_data

@router.post("/api/takes/{take_id}/notes")
async def create_note(take_id: int, request: Dict[str, Any]):
    """Create a note for a take."""
    storage = get_storage_service()
    
    take = storage.get_take(take_id)
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")
    
    text = request.get("text")
    if not text:
        raise HTTPException(status_code=400, detail="Note text is required")
    
    try:
        note_data = storage.create_note(
            take_id=take_id,
            text=text,
            frame_id=request.get("frame_id"),
            detector_name=request.get("detector_name"),
            tags=request.get("tags", [])
        )
        return note_data
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/api/notes/{note_id}")
async def update_note(note_id: int, request: Dict[str, Any]):
    """Update a note."""
    storage = get_storage_service()
    
    # Since individual notes aren't supported, return appropriate response
    result = storage.update_note(note_id, **request)
    
    if not result.get("success"):
        raise HTTPException(
            status_code=501, 
            detail=result.get("error", "Individual note updates not supported")
        )
    
    return result

@router.delete("/api/notes/{note_id}")
async def delete_note(note_id: int):
    """Delete a note."""
    storage = get_storage_service()
    
    # Since individual notes aren't supported, return appropriate response
    success = storage.delete_note(note_id)
    
    if not success:
        raise HTTPException(
            status_code=501,
            detail="Individual note deletion not supported. Use update_take to modify notes."
        )
    
    return {"message": "Note deleted successfully"}

@router.get("/api/notes/search")
async def search_notes(
    query: str,
    take_id: Optional[int] = None,
    detector_name: Optional[str] = None,
    tags: Optional[List[str]] = None
):
    """Search notes."""
    storage = get_storage_service()
    
    results = storage.search_notes(
        query=query,
        take_id=take_id,
        detector_name=detector_name,
        tags=tags
    )
    
    return {
        "query": query,
        "results": results
    }

# ==================== VERSION & PROTOCOL ====================

@router.get("/api/version")
async def get_version():
    """Get API version information."""
    return {
        "version": "1.0.0",
        "api_version": "v1",
        "build": "2024.1",
        "features": {
            "sse": True,
            "batch_processing": True,
            "gpu_support": True,
            "multi_language_detectors": True
        }
    }

@router.get("/api/protocol/negotiation")
async def negotiate_protocol(accept: str = "application/json"):
    """Negotiate communication protocol."""
    supported_protocols = ["application/json", "application/msgpack"]
    
    if accept in supported_protocols:
        return {
            "protocol": accept,
            "supported": supported_protocols
        }
    
    return {
        "protocol": "application/json",
        "supported": supported_protocols,
        "message": "Requested protocol not supported, defaulting to JSON"
    }

# ==================== MAINTENANCE & UTILITIES ====================

@router.post("/api/maintenance/cleanup")
async def cleanup_orphaned_data():
    """Clean up orphaned data in the system."""
    storage = get_storage_service()
    
    # Clean up orphaned frames
    orphaned_frames = storage.cleanup_orphaned_frames()
    
    # Clean up orphaned detector results
    orphaned_results = storage.cleanup_orphaned_detector_results()
    
    # Vacuum database
    storage.vacuum_database()
    
    return {
        "message": "Cleanup completed",
        "orphaned_frames_removed": orphaned_frames,
        "orphaned_results_removed": orphaned_results
    }

@router.post("/api/maintenance/optimize")
async def optimize_database():
    """Optimize database performance."""
    storage = get_storage_service()
    
    storage.analyze_database()
    storage.vacuum_database()
    
    return {"message": "Database optimization completed"}

@router.get("/api/storage/statistics")
async def get_storage_statistics():
    """Get storage usage statistics."""
    storage = get_storage_service()
    
    stats = storage.get_storage_statistics()
    
    return stats

@router.post("/api/storage/migrate")
async def migrate_storage_format(request: Dict[str, Any]):
    """Migrate storage format (e.g., frames to video)."""
    get_storage_service()
    
    take_id = request.get("take_id")
    if not take_id:
        raise HTTPException(status_code=400, detail="take_id is required")
    
    # This would trigger frame-to-video conversion
    # For now, return not implemented
    raise HTTPException(
        status_code=501,
        detail="Storage migration not yet implemented"
    )

# ==================== DETECTOR TEMPLATE ====================

@router.post("/api/detectors/template")
async def create_detector_template(request: Dict[str, Any]):
    """Create a new detector template."""
    detector_framework = get_detector_framework_service()
    
    detector_name = request.get("name")
    output_path = request.get("output_path")
    
    if not detector_name:
        raise HTTPException(status_code=400, detail="Detector name is required")
    
    success = detector_framework.create_detector_template(
        detector_name=detector_name,
        output_path=output_path
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create detector template")
    
    return {
        "message": "Detector template created successfully",
        "detector_name": detector_name,
        "output_path": output_path or f"detectors/{detector_name.lower().replace(' ', '_')}"
    }

# ==================== DOCUMENTATION ====================

@router.post("/api/documentation/generate")
async def generate_documentation(request: Dict[str, Any] = {}):
    """Generate documentation for all detectors."""
    detector_framework = get_detector_framework_service()
    
    output_dir = request.get("output_dir", "docs")
    
    detector_framework.generate_documentation(output_dir)
    
    return {
        "message": "Documentation generated successfully",
        "output_dir": output_dir
    }

# ==================== BENCHMARKING ====================

@router.post("/api/benchmark/detector/{detector_name}")
async def benchmark_detector(
    detector_name: str,
    request: Dict[str, Any] = {}
):
    """Benchmark a specific detector."""
    detector_framework = get_detector_framework_service()
    
    # Validate detector exists
    if not detector_framework.get_detector_info(detector_name):
        raise HTTPException(status_code=404, detail="Detector not found")
    
    # Validate detector package (includes performance tests)
    is_valid, validation_result = detector_framework.validate_detector_package(
        f"detectors/{detector_name}"
    )
    
    if not is_valid:
        raise HTTPException(
            status_code=400,
            detail=f"Detector validation failed: {validation_result}"
        )
    
    return {
        "detector_name": detector_name,
        "validation_result": validation_result,
        "performance_tests": validation_result.get("performance_tests", {})
    }
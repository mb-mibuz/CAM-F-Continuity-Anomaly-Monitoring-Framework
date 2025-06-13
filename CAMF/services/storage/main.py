from pathlib import Path
from typing import List, Dict, Any, Optional
import datetime
import json
import cv2
import time
from contextlib import contextmanager
import logging

from sqlalchemy import desc

# Set up logging
logger = logging.getLogger(__name__)

from CAMF.common.models import Project, Scene, Angle, Take, Frame, DetectorResult, ErrorConfidence
from CAMF.common.config import get_config

from .database import (
    get_session, 
    init_db, 
    ProjectDB,
    SceneDB, 
    AngleDB, 
    TakeDB, 
    FrameDB, 
    DetectorResultDB, 
    bulk_insert_detector_results
)

from .filesystem_names import (
    initialize_storage,
    create_project_directory,
    create_scene_directory,
    create_angle_directory,
    create_take_directory,
    save_detector_result_image,
    delete_project as fs_delete_project,
    delete_scene,
    delete_angle, 
    delete_take,
    delete_detector_results,
    rename_project_folder,
    rename_scene_folder,
    rename_angle_folder,
    rename_take_folder,
    find_project_folder,
    find_scene_folder,
    find_angle_folder,
    get_project_location
)

from .frame_storage import FrameStorage
from .maintenance import get_maintenance_scheduler
from .detector_grouping import DetectorResultGrouping
from .error_cache import get_error_cache

import numpy as np
import threading
import re
from enum import Enum
from dataclasses import dataclass


# Note Management Classes (simplified from the archived service)
class NoteType(Enum):
    """Types of notes that can be created."""
    GENERAL = "general"
    ERROR = "error"
    REMINDER = "reminder"
    CONTINUITY = "continuity"
    TECHNICAL = "technical"


@dataclass
class ParsedNote:
    """Represents a parsed note with extracted frame references."""
    raw_text: str
    segments: List[Dict[str, Any]]  # List of text and frame reference segments
    frame_references: List[int]  # List of all referenced frame IDs
    note_type: NoteType
    
    def has_frame_references(self) -> bool:
        """Check if note contains frame references."""
        return len(self.frame_references) > 0


class NoteParser:
    """Simple parser for notes with frame references."""
    
    # Patterns for parsing
    FRAME_REFERENCE_PATTERN = re.compile(r'frame\s*#(\d+)', re.IGNORECASE)
    NOTE_TYPE_PATTERN = re.compile(r'^(ERROR|REMINDER|CONTINUITY|TECHNICAL):\s*', re.IGNORECASE)
    
    def parse_note(self, note_text: str) -> ParsedNote:
        """Parse note text and extract all components."""
        if not note_text:
            return ParsedNote(
                raw_text="",
                segments=[],
                frame_references=[],
                note_type=NoteType.GENERAL
            )
        
        # Detect note type
        note_type = self._detect_note_type(note_text)
        
        # Parse segments
        segments = self._parse_segments(note_text)
        
        # Extract frame references
        frame_references = self._extract_frame_references(segments)
        
        return ParsedNote(
            raw_text=note_text,
            segments=segments,
            frame_references=frame_references,
            note_type=note_type
        )
    
    def _detect_note_type(self, note_text: str) -> NoteType:
        """Detect the type of note based on prefix."""
        match = self.NOTE_TYPE_PATTERN.match(note_text)
        if match:
            type_str = match.group(1).upper()
            try:
                return NoteType[type_str]
            except KeyError:
                pass
        return NoteType.GENERAL
    
    def _parse_segments(self, note_text: str) -> List[Dict[str, Any]]:
        """Parse note into segments of text and references."""
        segments = []
        last_end = 0
        
        # Find all frame references
        for match in self.FRAME_REFERENCE_PATTERN.finditer(note_text):
            # Add text before this match
            if match.start() > last_end:
                text_segment = note_text[last_end:match.start()]
                if text_segment:
                    segments.append({
                        'type': 'text',
                        'content': text_segment
                    })
            
            # Add frame reference
            frame_id = int(match.group(1))
            segments.append({
                'type': 'frame',
                'frame_id': frame_id,
                'original': match.group(0),
                'start': match.start(),
                'end': match.end()
            })
            
            last_end = match.end()
        
        # Add remaining text
        if last_end < len(note_text):
            remaining_text = note_text[last_end:]
            if remaining_text:
                segments.append({
                    'type': 'text',
                    'content': remaining_text
                })
        
        return segments
    
    def _extract_frame_references(self, segments: List[Dict[str, Any]]) -> List[int]:
        """Extract all frame references from segments."""
        frame_refs = []
        for segment in segments:
            if segment['type'] == 'frame':
                frame_refs.append(segment['frame_id'])
        return frame_refs


class StorageService:
    """Service for managing storage of projects, scenes, angles, takes, and frames."""
    
    def __init__(self):
        """Initialize the storage service."""
        # Initialize database
        init_db()
        
        # Initialize filesystem storage
        initialize_storage()
        
        # Storage directory
        self.storage_dir = Path(get_config().storage.base_dir)
        
        # Initialize frame storage
        self.frame_storage = FrameStorage(str(self.storage_dir))
        # Set storage service reference for hierarchical paths
        self.frame_storage.set_storage_service(self)
        
        # Start maintenance scheduler
        self.maintenance_scheduler = get_maintenance_scheduler()
        self.maintenance_scheduler.start()
        
        # Frame provider integration
        self._frame_cache: Dict[str, np.ndarray] = {}
        self._cache_size = 100
        self._cache_lock = threading.RLock()
        
        # Frame provider context
        self._current_project_id = None
        self._current_scene_id = None
        self._current_angle_id = None
        self._current_take_id = None
        self._context_lock = threading.RLock()
        
        # Initialize note parser
        self.note_parser = NoteParser()
    
    @contextmanager
    def session_scope(self):
        """Provide a transactional scope for database operations."""
        session = get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def _db_project_to_model(self, db_project: ProjectDB) -> Project:
        return Project(
            id=db_project.id,
            name=db_project.name,
            created_at=db_project.created_at,
            last_modified=db_project.last_modified,
            metadata=db_project.meta_data,  # Changed to meta_data
            scenes=[]
        )
    
    def clear_take_frames(self, take_id: int) -> int:
        """Clear all frames for a take"""
        with self.session_scope() as session:
            # Get take info for file deletion
            take = session.query(TakeDB).filter_by(id=take_id).first()
            if not take:
                return 0
                
            # Delete frame files from filesystem
            angle = session.query(AngleDB).filter_by(id=take.angle_id).first()
            scene = session.query(SceneDB).filter_by(id=angle.scene_id).first()
            
            frame_count = session.query(FrameDB).filter_by(take_id=take_id).count()
            
            # Delete all frame records
            session.query(FrameDB).filter_by(take_id=take_id).delete()
            session.commit()
            
            # Video segments will be deleted when take is deleted
            # No individual frame files to remove with video storage
            
            return frame_count

    def clear_take_detector_results(self, take_id: int) -> int:
        """Clear all detector results for a take"""
        with self.session_scope() as session:
            result_count = session.query(DetectorResultDB).filter_by(take_id=take_id).count()
            
            # Delete all detector results
            session.query(DetectorResultDB).filter_by(take_id=take_id).delete()
            session.commit()
            
            # You might also want to delete detector result images
            # This would be similar to frame file deletion
            
            return result_count

    def clear_take_continuous_errors(self, take_id: int) -> int:
        """Clear all continuous errors for a take - DEPRECATED"""
        # This functionality is now handled by clear_take_detector_results
        # since we moved to error grouping instead of separate continuous error tables
        return 0
    
    def _db_scene_to_model(self, db_scene: SceneDB) -> Scene:
        """Convert a database Scene to a model Scene."""
        # Extract image_quality and enabled_detectors from metadata if needed
        meta_data = db_scene.meta_data or {}
        image_quality = meta_data.get('image_quality', 85)
        enabled_detectors = meta_data.get('enabled_detectors', [])
        
        return Scene(
            id=db_scene.id,
            project_id=db_scene.project_id,
            name=db_scene.name,
            frame_rate=db_scene.frame_rate,
            image_quality=image_quality,
            resolution=getattr(db_scene, 'resolution', '1080p'),  # Handle old DB entries
            enabled_detectors=enabled_detectors,
            detector_settings=db_scene.detector_settings,
            created_at=db_scene.created_at,
            metadata=meta_data,
            angles=[]  # Angles are loaded separately for efficiency
        )
    
    def _db_angle_to_model(self, db_angle: AngleDB) -> Angle:
        """Convert a database Angle to a model Angle."""
        # Get reference take ID from takes with is_reference=True
        session = get_session()
        try:
            reference_take = session.query(TakeDB).filter(
                TakeDB.angle_id == db_angle.id,
                TakeDB.is_reference == True
            ).first()
            reference_take_id = reference_take.id if reference_take else None
        finally:
            session.close()
        
        return Angle(
            id=db_angle.id,
            scene_id=db_angle.scene_id,
            name=db_angle.name,
            reference_take_id=reference_take_id,
            metadata=db_angle.meta_data,
            takes=[]  # Takes are loaded separately for efficiency
        )
    
    def _db_take_to_model(self, db_take: TakeDB) -> Take:
        """Convert a database Take to a model Take."""
        return Take(
            id=db_take.id,
            angle_id=db_take.angle_id,
            name=db_take.name,
            created_at=db_take.created_at,
            is_reference=db_take.is_reference,
            notes=db_take.notes,
            metadata=db_take.meta_data
        )
    
    def _db_frame_to_model(self, db_frame: FrameDB) -> Frame:
        """Convert a database Frame to a model Frame."""
        return Frame(
            id=db_frame.frame_number,  # Use frame_number as the id
            take_id=db_frame.take_id,
            timestamp=db_frame.timestamp,
            filepath=db_frame.path,  # Use actual path from DB
            width=0,  # Not stored in current schema
            height=0,  # Not stored in current schema
            file_size=0,  # Not stored in current schema
            metadata={}
        )
    
    def _db_detector_result_to_model(self, db_result: DetectorResultDB) -> DetectorResult:
        """Convert a database DetectorResult to a model DetectorResult."""
        # Handle both new float confidence (0.0-1.0) and legacy enum values
        confidence_value = db_result.confidence
        if isinstance(confidence_value, (int, float)):
            # Already a float/int, use directly
            confidence = float(confidence_value)
        else:
            # Legacy enum value, convert to float
            try:
                confidence = float(ErrorConfidence(confidence_value).value)
            except:
                confidence = 0.0  # Default if conversion fails
                
        return DetectorResult(
            id=db_result.id,
            confidence=confidence,
            description=db_result.description,
            frame_id=db_result.frame_id,
            bounding_boxes=db_result.bounding_boxes,
            detector_name=db_result.detector_name,
            metadata=db_result.meta_data,
            is_false_positive=db_result.is_false_positive,
            false_positive_reason=db_result.false_positive_reason
        )
        
    # Project CRUD operations
    
    def create_project(self, name: str, metadata: Dict[str, Any] = None) -> Project:
        """Create a new project."""
        if metadata is None:
            metadata = {}
            
        session = get_session()
        try:
            # Create database entry
            db_project = ProjectDB(
                name=name,
                meta_data=metadata
            )
            session.add(db_project)
            session.commit()
            
            # Create filesystem directory with name
            create_project_directory(db_project.id, name)
            
            # Return model
            return self._db_project_to_model(db_project)
        finally:
            session.close()
    
    def get_project(self, project_id: int) -> Optional[Project]:
        """Get a project by ID."""
        session = get_session()
        try:
            db_project = session.query(ProjectDB).filter(ProjectDB.id == project_id).first()
            if db_project is None:
                return None
            
            return self._db_project_to_model(db_project)
        finally:
            session.close()
    
    def get_all_projects(self) -> List[Project]:
        """Get all projects."""
        session = get_session()
        try:
            db_projects = session.query(ProjectDB).order_by(desc(ProjectDB.last_modified)).all()
            return [self._db_project_to_model(p) for p in db_projects]
        finally:
            session.close()
    
    def update_project(self, project_id: int, name: str = None, metadata: Dict[str, Any] = None) -> Optional[Project]:
        """Update a project."""
        session = get_session()
        try:
            db_project = session.query(ProjectDB).filter(ProjectDB.id == project_id).first()
            if db_project is None:
                return None
            
            # If name is changing, rename the folder
            if name is not None and name != db_project.name:
                # Try to rename the folder
                folder_renamed = rename_project_folder(project_id, name)
                if not folder_renamed:
                    # Log warning but continue with database update
                    logger.warning(f"Could not rename project folder for project {project_id}, but database will be updated")
                
                # Always update the database name regardless of folder rename success
                db_project.name = name
            
            if metadata is not None:
                db_project.meta_data = metadata
                
            db_project.last_modified = datetime.datetime.now()
            
            session.commit()
            return self._db_project_to_model(db_project)
        finally:
            session.close()
    
    def delete_project(self, project_id: int) -> bool:
        """Delete a project."""
        session = get_session()
        try:
            db_project = session.query(ProjectDB).filter(ProjectDB.id == project_id).first()
            if db_project is None:
                return False
            
            # Delete from database
            session.delete(db_project)
            session.commit()
            
            # Delete from filesystem
            fs_delete_project(project_id)
            
            return True
        finally:
            session.close()
    
    # Scene CRUD operations
    
    def create_scene(self, 
                 project_id: int, 
                 name: str, 
                 frame_rate: float = 1.0, 
                 image_quality: int = 90,
                 resolution: str = "1080p",
                 enabled_detectors: List[str] = None,
                 detector_settings: Dict[str, Any] = None,
                 metadata: Dict[str, Any] = None) -> Optional[Scene]:
        """Create a new scene."""
        if enabled_detectors is None:
            enabled_detectors = []
        if detector_settings is None:
            detector_settings = {}
        if metadata is None:
            metadata = {}
            
        session = get_session()
        try:
            # Verify project exists
            db_project = session.query(ProjectDB).filter(ProjectDB.id == project_id).first()
            if db_project is None:
                return None
            
            # Create database entry
            scene_kwargs = {
                'project_id': project_id,
                'name': name,
                'frame_rate': frame_rate,
                'resolution': resolution,
                'detector_settings': detector_settings,
                'meta_data': metadata
            }
            
            # Add image_quality and enabled_detectors to metadata if provided
            if image_quality is not None:
                if metadata is None:
                    metadata = {}
                metadata['image_quality'] = image_quality
            if enabled_detectors is not None:
                if metadata is None:
                    metadata = {}
                metadata['enabled_detectors'] = enabled_detectors
                scene_kwargs['meta_data'] = metadata
                
            db_scene = SceneDB(**scene_kwargs)
            session.add(db_scene)
            session.commit()
            
            # Find project folder and create scene directory
            project_path = find_project_folder(project_id)
            if project_path:
                create_scene_directory(project_path, db_scene.id, name)
            
            # Update project last_modified
            db_project.last_modified = datetime.datetime.now()
            session.commit()
            
            # Return model
            return self._db_scene_to_model(db_scene)
        finally:
            session.close()
    
    def get_scene(self, scene_id: int) -> Optional[Scene]:
        """Get a scene by ID."""
        session = get_session()
        try:
            db_scene = session.query(SceneDB).filter(SceneDB.id == scene_id).first()
            if db_scene is None:
                return None
            
            return self._db_scene_to_model(db_scene)
        finally:
            session.close()
    
    def get_scenes_for_project(self, project_id: int) -> List[Scene]:
        """Get all scenes for a project."""
        session = get_session()
        try:
            db_scenes = session.query(SceneDB).filter(SceneDB.project_id == project_id).all()
            return [self._db_scene_to_model(s) for s in db_scenes]
        finally:
            session.close()
    
    def update_scene(self, 
                 scene_id: int, 
                 name: str = None,
                 frame_rate: float = None,
                 resolution: str = None,
                 image_quality: int = None,
                 enabled_detectors: List[str] = None,
                 detector_settings: Dict[str, Any] = None,
                 metadata: Dict[str, Any] = None) -> Optional[Scene]:
        """Update a scene."""
        from sqlalchemy.orm.attributes import flag_modified
        
        session = get_session()
        try:
            db_scene = session.query(SceneDB).filter(SceneDB.id == scene_id).first()
            if db_scene is None:
                return None
            
            # If name is changing, rename the folder
            if name is not None and name != db_scene.name:
                if not rename_scene_folder(db_scene.project_id, scene_id, name):
                    logger.warning(f"Failed to rename scene folder for scene {scene_id}")
                db_scene.name = name
            
            if frame_rate is not None:
                db_scene.frame_rate = frame_rate
                
            if resolution is not None:
                db_scene.resolution = resolution
                
            if image_quality is not None:
                db_scene.image_quality = image_quality
                
            if enabled_detectors is not None:
                # Store enabled_detectors in meta_data
                if db_scene.meta_data is None:
                    db_scene.meta_data = {}
                db_scene.meta_data['enabled_detectors'] = enabled_detectors
                # Mark the object as modified to ensure SQLAlchemy detects the change
                flag_modified(db_scene, 'meta_data')
                
            if detector_settings is not None:
                db_scene.detector_settings = detector_settings
                # Mark the object as modified to ensure SQLAlchemy detects the change
                flag_modified(db_scene, 'detector_settings')
            
            if metadata is not None:
                # Merge with existing metadata to preserve other fields
                if db_scene.meta_data is None:
                    db_scene.meta_data = {}
                db_scene.meta_data.update(metadata)
                # Mark the object as modified to ensure SQLAlchemy detects the change
                flag_modified(db_scene, 'meta_data')
            
            # Update project last_modified
            db_project = session.query(ProjectDB).filter(ProjectDB.id == db_scene.project_id).first()
            if db_project:
                db_project.last_modified = datetime.datetime.now()
            
            session.commit()
            return self._db_scene_to_model(db_scene)
        finally:
            session.close()
    
    def get_scene_folder(self, scene_id: int) -> Optional[str]:
        """Get the filesystem path for a scene."""
        scene = self.get_scene(scene_id)
        if not scene:
            return None
            
        project = self.get_project(scene.project_id)
        if not project:
            return None
            
        # Find the scene folder in the hierarchical structure
        project_path = filesystem_names.find_project_folder(project.id)
        if not project_path:
            return None
            
        scene_path = filesystem_names.find_scene_folder(project_path, scene.id)
        if not scene_path:
            return None
            
        return str(scene_path)
    
    def delete_scene(self, scene_id: int) -> bool:
        """Delete a scene."""
        session = get_session()
        try:
            db_scene = session.query(SceneDB).filter(SceneDB.id == scene_id).first()
            if db_scene is None:
                return False
            
            project_id = db_scene.project_id
            
            # Delete from database (cascade will delete related angles, takes, etc.)
            session.delete(db_scene)
            
            # Update project last_modified
            db_project = session.query(ProjectDB).filter(ProjectDB.id == project_id).first()
            if db_project:
                db_project.last_modified = datetime.datetime.now()
            
            session.commit()
            
            # Delete from filesystem
            delete_scene(project_id, scene_id)
            
            return True
        finally:
            session.close()
    
    # Angle CRUD operations
    
    def create_angle(self, 
                 scene_id: int, 
                 name: str,
                 metadata: Dict[str, Any] = None) -> Optional[Angle]:
        """Create a new angle."""
        if metadata is None:
            metadata = {}
            
        session = get_session()
        try:
            # Verify scene exists
            db_scene = session.query(SceneDB).filter(SceneDB.id == scene_id).first()
            if db_scene is None:
                return None
            
            # Create database entry
            db_angle = AngleDB(
                scene_id=scene_id,
                name=name,
                meta_data=metadata
            )
            session.add(db_angle)
            session.commit()
            
            # Find scene folder and create angle directory
            project_path = find_project_folder(db_scene.project_id)
            if project_path:
                scene_path = find_scene_folder(project_path, scene_id)
                if scene_path:
                    create_angle_directory(scene_path, db_angle.id, name)
            
            # Update project last_modified
            db_project = session.query(ProjectDB).filter(ProjectDB.id == db_scene.project_id).first()
            if db_project:
                db_project.last_modified = datetime.datetime.now()
                session.commit()
            
            # Return model
            return self._db_angle_to_model(db_angle)
        finally:
            session.close()
    
    def get_angle(self, angle_id: int) -> Optional[Angle]:
        """Get an angle by ID."""
        session = get_session()
        try:
            db_angle = session.query(AngleDB).filter(AngleDB.id == angle_id).first()
            if db_angle is None:
                return None
            
            return self._db_angle_to_model(db_angle)
        finally:
            session.close()
    
    def get_angles_for_scene(self, scene_id: int) -> List[Angle]:
        """Get all angles for a scene."""
        session = get_session()
        try:
            db_angles = session.query(AngleDB).filter(AngleDB.scene_id == scene_id).all()
            return [self._db_angle_to_model(a) for a in db_angles]
        finally:
            session.close()
    
    def update_angle(self, 
                 angle_id: int, 
                 name: str = None,
                 reference_take_id: int = None,
                 metadata: Dict[str, Any] = None) -> Optional[Angle]:
        """Update an angle."""
        session = get_session()
        try:
            db_angle = session.query(AngleDB).filter(AngleDB.id == angle_id).first()
            if db_angle is None:
                return None
            
            # Get scene and project info for folder operations
            db_scene = session.query(SceneDB).filter(SceneDB.id == db_angle.scene_id).first()
            if db_scene:
                # If name is changing, rename the folder
                if name is not None and name != db_angle.name:
                    if not rename_angle_folder(db_scene.project_id, db_scene.id, angle_id, name):
                        logger.warning(f"Failed to rename angle folder for angle {angle_id}")
                    db_angle.name = name
            
            # Update reference take ID if provided
            if reference_take_id is not None:
                # First, unset is_reference flag on any existing reference take
                existing_ref_take = session.query(TakeDB).filter(
                    TakeDB.angle_id == angle_id,
                    TakeDB.is_reference == True
                ).first()
                if existing_ref_take and existing_ref_take.id != reference_take_id:
                    existing_ref_take.is_reference = False
                
                # Set the new reference take
                new_ref_take = session.query(TakeDB).filter(
                    TakeDB.id == reference_take_id,
                    TakeDB.angle_id == angle_id
                ).first()
                if new_ref_take:
                    new_ref_take.is_reference = True
                    db_angle.reference_take_id = reference_take_id
                else:
                    logger.warning(f"Take {reference_take_id} not found or doesn't belong to angle {angle_id}")
            
            if metadata is not None:
                db_angle.meta_data = metadata
            
            # Update project last_modified
            if db_scene:
                db_project = session.query(ProjectDB).filter(ProjectDB.id == db_scene.project_id).first()
                if db_project:
                    db_project.last_modified = datetime.datetime.now()
            
            session.commit()
            return self._db_angle_to_model(db_angle)
        finally:
            session.close()
    
    def delete_angle(self, angle_id: int) -> bool:
        """Delete an angle."""
        session = get_session()
        try:
            db_angle = session.query(AngleDB).filter(AngleDB.id == angle_id).first()
            if db_angle is None:
                return False
            
            # Get scene and project for updating last_modified
            scene_id = db_angle.scene_id
            db_scene = session.query(SceneDB).filter(SceneDB.id == scene_id).first()
            project_id = db_scene.project_id if db_scene else None
            
            # Delete from database (cascade will delete related takes, etc.)
            session.delete(db_angle)
            
            # Update project last_modified
            if project_id:
                db_project = session.query(ProjectDB).filter(ProjectDB.id == project_id).first()
                if db_project:
                    db_project.last_modified = datetime.datetime.now()
            
            session.commit()
            
            # Delete from filesystem
            if project_id and scene_id:
                delete_angle(project_id, scene_id, angle_id)
            
            return True
        finally:
            session.close()
    
    # Take CRUD operations
    
    def create_take(self, 
                angle_id: int, 
                name: str,
                is_reference: bool = False,
                notes: str = "",
                metadata: Dict[str, Any] = None) -> Optional[Take]:
        """Create a new take."""
        if metadata is None:
            metadata = {}
            
        session = get_session()
        try:
            # Verify angle exists
            db_angle = session.query(AngleDB).filter(AngleDB.id == angle_id).first()
            if db_angle is None:
                return None
            
            # Get scene and project
            db_scene = session.query(SceneDB).filter(SceneDB.id == db_angle.scene_id).first()
            if db_scene is None:
                return None
            
            # If this is the first take for the angle, make it the reference
            existing_takes = session.query(TakeDB).filter(TakeDB.angle_id == angle_id).count()
            if existing_takes == 0:
                is_reference = True
            elif is_reference:
                # If this is marked as reference, unmark any existing reference takes
                existing_ref_takes = session.query(TakeDB).filter(
                    TakeDB.angle_id == angle_id,
                    TakeDB.is_reference == True
                ).all()
                for ref_take in existing_ref_takes:
                    ref_take.is_reference = False
            
            # Create database entry
            db_take = TakeDB(
                angle_id=angle_id,
                name=name,
                is_reference=is_reference,
                notes=notes,
                meta_data=metadata
            )
            session.add(db_take)
            session.commit()
            
            # Find angle folder and create take directory
            project_path = find_project_folder(db_scene.project_id)
            if project_path:
                scene_path = find_scene_folder(project_path, db_scene.id)
                if scene_path:
                    angle_path = find_angle_folder(scene_path, angle_id)
                    if angle_path:
                        create_take_directory(angle_path, db_take.id, name)
                        # Frame storage will automatically create directory on first frame
            
            # Update project last_modified
            db_project = session.query(ProjectDB).filter(ProjectDB.id == db_scene.project_id).first()
            if db_project:
                db_project.last_modified = datetime.datetime.now()
                session.commit()
            
            # Return model
            return self._db_take_to_model(db_take)
        finally:
            session.close()
    
    def get_take(self, take_id: int) -> Optional[Take]:
        """Get a take by ID."""
        session = get_session()
        try:
            db_take = session.query(TakeDB).filter(TakeDB.id == take_id).first()
            if db_take is None:
                return None
            
            return self._db_take_to_model(db_take)
        finally:
            session.close()
    
    def get_takes_for_angle(self, angle_id: int) -> List[Take]:
        """Get all takes for an angle."""
        session = get_session()
        try:
            db_takes = session.query(TakeDB).filter(TakeDB.angle_id == angle_id).all()
            return [self._db_take_to_model(t) for t in db_takes]
        finally:
            session.close()
    
    def get_reference_take_for_angle(self, angle_id: int) -> Optional[Take]:
        """Get the reference take for an angle."""
        session = get_session()
        try:
            db_take = session.query(TakeDB).filter(
                TakeDB.angle_id == angle_id,
                TakeDB.is_reference == True
            ).first()
            if db_take is None:
                return None
            
            return self._db_take_to_model(db_take)
        finally:
            session.close()
    
    def update_take(self, 
                take_id: int, 
                name: str = None,
                is_reference: bool = None,
                notes: str = None,
                metadata: Dict[str, Any] = None) -> Optional[Take]:
        """Update a take."""
        session = get_session()
        try:
            db_take = session.query(TakeDB).filter(TakeDB.id == take_id).first()
            if db_take is None:
                return None
            
            # Get angle, scene, and project info for folder operations
            db_angle = session.query(AngleDB).filter(AngleDB.id == db_take.angle_id).first()
            if db_angle:
                db_scene = session.query(SceneDB).filter(SceneDB.id == db_angle.scene_id).first()
                if db_scene:
                    # If name is changing, rename the folder
                    if name is not None and name != db_take.name:
                        if not rename_take_folder(db_scene.project_id, db_scene.id, db_angle.id, take_id, name):
                            logger.warning(f"Failed to rename take folder for take {take_id}")
                        db_take.name = name
            
            if is_reference is not None:
                if is_reference and not db_take.is_reference:
                    # If setting as reference, unmark any existing reference takes
                    existing_ref_takes = session.query(TakeDB).filter(
                        TakeDB.angle_id == db_take.angle_id,
                        TakeDB.is_reference == True
                    ).all()
                    for ref_take in existing_ref_takes:
                        ref_take.is_reference = False
                
                db_take.is_reference = is_reference
            
            if notes is not None:
                db_take.notes = notes
            
            if metadata is not None:
                db_take.meta_data = metadata
            
            # Update project last_modified
            if db_angle and db_scene:
                db_project = session.query(ProjectDB).filter(ProjectDB.id == db_scene.project_id).first()
                if db_project:
                    db_project.last_modified = datetime.datetime.now()
            
            session.commit()
            return self._db_take_to_model(db_take)
        finally:
            session.close()
    
    def delete_take(self, take_id: int) -> bool:
        """Delete a take."""
        session = get_session()
        try:
            db_take = session.query(TakeDB).filter(TakeDB.id == take_id).first()
            if db_take is None:
                return False
            
            # Get angle, scene, and project for updating last_modified
            angle_id = db_take.angle_id
            db_angle = session.query(AngleDB).filter(AngleDB.id == angle_id).first()
            scene_id = db_angle.scene_id if db_angle else None
            
            if scene_id:
                db_scene = session.query(SceneDB).filter(SceneDB.id == scene_id).first()
                project_id = db_scene.project_id if db_scene else None
            else:
                project_id = None
            
            # Check if this is a reference take
            is_reference = db_take.is_reference
            
            # Delete from database (cascade will delete related frames, etc.)
            session.delete(db_take)
            
            # If this was a reference take, set a new one if available
            if is_reference:
                another_take = session.query(TakeDB).filter(TakeDB.angle_id == angle_id).first()
                if another_take:
                    another_take.is_reference = True
            
            # Update project last_modified
            if project_id:
                db_project = session.query(ProjectDB).filter(ProjectDB.id == project_id).first()
                if db_project:
                    db_project.last_modified = datetime.datetime.now()
            
            session.commit()
            
            # Delete frame storage for this take
            self.frame_storage.delete_take(take_id)
            
            # Delete from filesystem
            if project_id and scene_id and angle_id:
                delete_take(project_id, scene_id, angle_id, take_id)
            
            return True
        finally:
            session.close()
    
    # Frame operations
    
    def add_frame(self,
                  take_id: int,
                  frame: np.ndarray,
                  frame_id: int,
                  timestamp: float,
                  metadata: Dict[str, Any] = None) -> Optional[Frame]:
        """Add a frame to a take."""
        if metadata is None:
            metadata = {}
        
        logger.info(f"[StorageService] add_frame: take_id={take_id}, frame_id={frame_id}, timestamp={timestamp:.2f}")
        
        session = get_session()
        try:
            # Verify take exists
            db_take = session.query(TakeDB).filter(TakeDB.id == take_id).first()
            if db_take is None:
                logger.error(f"Take {take_id} not found")
                return None
            
            # Get angle, scene, and project
            db_angle = session.query(AngleDB).filter(AngleDB.id == db_take.angle_id).first()
            if db_angle is None:
                return None
            
            db_scene = session.query(SceneDB).filter(SceneDB.id == db_angle.scene_id).first()
            if db_scene is None:
                return None
            
            project_id = db_scene.project_id
            db_scene.id
            db_angle.id
            
            # Check if frame already exists in database
            existing_frame = session.query(FrameDB).filter(
                FrameDB.take_id == take_id,
                FrameDB.frame_number == frame_id
            ).first()
            
            if existing_frame:
                logger.warning(f"Frame {frame_id} already exists for take {take_id}, skipping")
                return None  # Return None to indicate frame was not saved (already exists)
            
            # Store frame directly with lossless compression
            success = self.frame_storage.store_frame(
                take_id, frame_id, frame, timestamp, metadata
            )
            if not success:
                logger.error(f"Failed to store frame {frame_id}")
                return None
            
            # Get the frame path from frame storage
            frame_path = self.frame_storage.get_frame_path(take_id, frame_id)
            
            # Create frame entry with actual database fields
            db_frame = FrameDB(
                take_id=take_id,
                frame_number=frame_id,  # Use frame_number field
                timestamp=timestamp,
                path=frame_path  # Store the actual file path
            )
            session.add(db_frame)
            
            # Update project last_modified
            db_project = session.query(ProjectDB).filter(ProjectDB.id == project_id).first()
            if db_project:
                db_project.last_modified = datetime.datetime.now()
            
            session.commit()
            
            # Return model
            return self._db_frame_to_model(db_frame)
        finally:
            session.close()
    
    def get_frame(self, take_id: int, frame_id: int) -> Optional[Frame]:
        """Get a frame metadata by take ID and frame ID."""
        # Get frame metadata from database
        return self.get_frame_metadata(take_id, frame_id)
    
    def get_frame_array(self, take_id: int, frame_id: int) -> Optional[np.ndarray]:
        """Get a frame as numpy array by take ID and frame ID."""
        # Get frame directly from frame storage
        return self.frame_storage.get_frame(take_id, frame_id)
    
    def get_latest_frame_from_filesystem(self, take_id: int) -> Optional[np.ndarray]:
        """Get the latest frame directly from the filesystem without database lookup.
        
        This method bypasses the database and reads directly from the filesystem,
        which can be useful for real-time operations where the database might not
        be fully up-to-date yet.
        
        Args:
            take_id: Take ID to get the latest frame from
            
        Returns:
            Latest frame as numpy array, or None if no frames exist
        """
        # Get the take directory
        take_dir = self.frame_storage.get_take_directory(take_id)
        if not take_dir or not take_dir.exists():
            logger.warning(f"Take directory not found for take {take_id}")
            return None
        
        # Find all frame files in the directory
        frame_files = list(take_dir.glob('frame_*.png'))
        if not frame_files:
            logger.debug(f"No frame files found in {take_dir}")
            return None
        
        # Sort by frame number to get the latest
        try:
            # Extract frame numbers and sort
            frame_files_with_numbers = []
            for f in frame_files:
                try:
                    # Extract frame number from filename (frame_XXXXXX.png)
                    frame_num = int(f.stem.split('_')[1])
                    frame_files_with_numbers.append((frame_num, f))
                except (ValueError, IndexError):
                    logger.warning(f"Invalid frame filename: {f}")
                    continue
            
            if not frame_files_with_numbers:
                return None
            
            # Sort by frame number and get the latest
            frame_files_with_numbers.sort(key=lambda x: x[0])
            latest_frame_num, latest_frame_path = frame_files_with_numbers[-1]
            
            logger.debug(f"Latest frame for take {take_id}: frame {latest_frame_num} at {latest_frame_path}")
            
            # Read the frame directly
            frame = cv2.imread(str(latest_frame_path), cv2.IMREAD_UNCHANGED)
            if frame is None:
                logger.error(f"Failed to read frame from {latest_frame_path}")
                return None
            
            # Ensure BGR format (PNG might have alpha channel)
            if len(frame.shape) == 3 and frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            
            return frame
            
        except Exception as e:
            logger.error(f"Error getting latest frame for take {take_id}: {e}")
            return None
    
    def save_frame(self, take_id: int, frame: np.ndarray, frame_number: int = None) -> Optional[int]:
        """Save a frame to a take. API compatibility wrapper for add_frame.
        
        Args:
            take_id: Take ID
            frame: Frame data as numpy array
            frame_number: Optional frame number (defaults to next available)
            
        Returns:
            Frame ID if successful, None otherwise
        """
        # If no frame number specified, get the next available
        if frame_number is None:
            frame_count = self.get_frame_count(take_id)
            frame_number = frame_count
        
        # Add the frame
        stored_frame = self.add_frame(
            take_id=take_id,
            frame=frame,
            frame_id=frame_number,
            timestamp=time.time(),
            metadata={}
        )
        
        if stored_frame:
            return stored_frame.id
        return None
    
    def get_frame_metadata(self, take_id: int, frame_id: int) -> Optional[Frame]:
        """Get a frame's metadata by take ID and frame ID."""
        session = get_session()
        try:
            db_frame = session.query(FrameDB).filter(
                FrameDB.take_id == take_id,
                FrameDB.frame_number == frame_id
            ).first()
            
            if db_frame is None:
                return None
            
            # Return minimal frame info
            return Frame(
                id=db_frame.frame_number,
                take_id=db_frame.take_id,
                timestamp=db_frame.timestamp,
                filepath=db_frame.path,
                width=0,  # Not stored in current schema
                height=0,  # Not stored in current schema
                file_size=0,  # Not stored in current schema
                metadata={}
            )
        finally:
            session.close()
    
    def get_frame_range(self, take_id: int, start_frame: int, end_frame: int) -> List[np.ndarray]:
        """Get a range of frames by take ID and frame IDs."""
        frames = []
        
        # Get frames directly from frame storage
        for frame_id in range(start_frame, end_frame + 1):
            frame = self.frame_storage.get_frame(take_id, frame_id)
            if frame is not None:
                frames.append(frame)
            
        return frames
    
    def get_frame_count(self, take_id: int) -> int:
        """Get the number of frames in a take."""
        session = get_session()
        try:
            return session.query(FrameDB).filter(FrameDB.take_id == take_id).count()
        finally:
            session.close()
    
    def get_take_frame_count(self, take_id: int) -> int:
        """Alias for get_frame_count for API compatibility."""
        return self.get_frame_count(take_id)
    
    def get_frames_in_range(self, take_id: int, start: int, end: Optional[int] = None) -> List[Frame]:
        """Get frames in the specified range."""
        with self.session_scope() as session:
            query = session.query(FrameDB).filter(
                FrameDB.take_id == take_id,
                FrameDB.frame_number >= start
            )
            
            if end is not None:
                query = query.filter(FrameDB.frame_number <= end)
            
            db_frames = query.order_by(FrameDB.frame_number).all()
            
            return [self._db_frame_to_model(db_frame) for db_frame in db_frames]
    
    def get_latest_frame_id(self, take_id: int) -> Optional[int]:
        """Get the ID of the latest frame in a take."""
        session = get_session()
        try:
            latest_frame = session.query(FrameDB).filter(
                FrameDB.take_id == take_id
            ).order_by(desc(FrameDB.frame_number)).first()
            
            if latest_frame is None:
                return None
            
            return latest_frame.id
        finally:
            session.close()
    
    # Detector result operations
    
    def add_detector_result(self,
                            take_id: int,
                            frame_id: int,
                            detector_name: str,
                            confidence: ErrorConfidence,
                            description: str,
                            bounding_boxes: List[Dict[str, Any]] = None,
                            result_image: np.ndarray = None,
                            metadata: Dict[str, Any] = None) -> bool:
        """Add a detector result."""
        if bounding_boxes is None:
            bounding_boxes = []
        if metadata is None:
            metadata = {}
            
        session = get_session()
        try:
            # Verify take exists
            db_take = session.query(TakeDB).filter(TakeDB.id == take_id).first()
            if db_take is None:
                return False
            
            # Get angle, scene, and project
            db_angle = session.query(AngleDB).filter(AngleDB.id == db_take.angle_id).first()
            if db_angle is None:
                return False
            
            db_scene = session.query(SceneDB).filter(SceneDB.id == db_angle.scene_id).first()
            if db_scene is None:
                return False
            
            project_id = db_scene.project_id
            scene_id = db_scene.id
            angle_id = db_angle.id
            
            # Save result image if provided
            if result_image is not None:
                result_filepath = save_detector_result_image(
                    result_image,
                    project_id,
                    scene_id,
                    angle_id,
                    take_id,
                    frame_id,
                    detector_name
                )
                metadata["result_image_path"] = result_filepath
            
            # Check if a result already exists for this take, frame, and detector
            existing_result = session.query(DetectorResultDB).filter(
                DetectorResultDB.take_id == take_id,
                DetectorResultDB.frame_id == frame_id,
                DetectorResultDB.detector_name == detector_name
            ).first()
            
            if existing_result:
                # Update existing result
                existing_result.confidence = confidence if isinstance(confidence, (int, float)) else confidence.value
                existing_result.description = description
                existing_result.bounding_boxes = bounding_boxes
                existing_result.meta_data = metadata
                # Keep existing group ID
            else:
                # Create database entry with group ID assignment
                db_result = DetectorResultDB(
                    take_id=take_id,
                    frame_id=frame_id,
                    detector_name=detector_name,
                    confidence=confidence if isinstance(confidence, (int, float)) else confidence.value,
                    description=description,
                    bounding_boxes=bounding_boxes,
                    meta_data=metadata
                )
                
                # Assign group ID by checking existing results for spatial/temporal proximity
                # Get recent results from same detector and take to check for grouping
                recent_results = session.query(DetectorResultDB).filter(
                    DetectorResultDB.take_id == take_id,
                    DetectorResultDB.detector_name == detector_name,
                    DetectorResultDB.frame_id >= frame_id - 5,  # Within 5 frames
                    DetectorResultDB.frame_id < frame_id,
                    DetectorResultDB.error_group_id.isnot(None)
                ).order_by(DetectorResultDB.frame_id.desc()).limit(10).all()
                
                # Check if this result should be grouped with a recent one
                group_id = None
                for recent in recent_results:
                    # Check spatial proximity using bounding boxes
                    # Create simple grouping check (same detector, similar description, close frames)
                    if (recent.detector_name == detector_name and
                        recent.description == description and
                        abs(recent.frame_id - frame_id) <= 5):
                        group_id = recent.error_group_id
                        break
                
                # If no group found, generate new group ID
                if not group_id:
                    import hashlib
                    group_id = hashlib.md5(
                        f"{detector_name}_{description}_{take_id}_{frame_id}_{time.time()}".encode()
                    ).hexdigest()[:16]
                    db_result.is_continuous_start = True
                
                db_result.error_group_id = group_id
                session.add(db_result)
            
            # Update project last_modified
            db_project = session.query(ProjectDB).filter(ProjectDB.id == project_id).first()
            if db_project:
                db_project.last_modified = datetime.datetime.now()
            
            session.commit()
            
            # Invalidate cache for this take
            cache = get_error_cache()
            cache.invalidate(take_id)
            
            return True
        finally:
            session.close()
    
    def get_detector_results(self, take_id: int, frame_id: int = None) -> List[DetectorResult]:
        """Get detector results for a take and optionally a specific frame."""
        session = get_session()
        try:
            query = session.query(DetectorResultDB).filter(DetectorResultDB.take_id == take_id)
            
            if frame_id is not None:
                query = query.filter(DetectorResultDB.frame_id == frame_id)
            
            db_results = query.all()
            return [self._db_detector_result_to_model(r) for r in db_results]
        finally:
            session.close()
    
    def get_detector_result_image(self, take_id: int, frame_id: int, detector_name: str) -> Optional[np.ndarray]:
        """Get a detector result image."""
        session = get_session()
        try:
            # Get detector result
            db_result = session.query(DetectorResultDB).filter(
                DetectorResultDB.take_id == take_id,
                DetectorResultDB.frame_id == frame_id,
                DetectorResultDB.detector_name == detector_name
            ).first()
            
            if db_result is None or "result_image_path" not in db_result.meta_data:
                return None
            
            # Load image from filesystem
            image_path = db_result.meta_data["result_image_path"]
            return cv2.imread(image_path)
        finally:
            session.close()
    
    def get_detector_results_for_frame(self, frame_id: int) -> List[DetectorResult]:
        """Get all detector results for a specific frame."""
        session = get_session()
        try:
            db_results = session.query(DetectorResultDB).filter(
                DetectorResultDB.frame_id == frame_id
            ).all()
            return [self._db_detector_result_to_model(r) for r in db_results]
        finally:
            session.close()
    
    def get_detector_results_for_take(self, take_id: int) -> List[DetectorResult]:
        """Get all detector results for a take."""
        return self.get_detector_results(take_id)
    
    def get_frame_data(self, frame_id: int) -> Optional[bytes]:
        """Get raw frame data (JPEG bytes)."""
        frame = self.get_frame(frame_id)
        if not frame:
            return None
        
        # Use frame storage to get the actual frame data
        frame_data = self.frame_storage.get_frame(frame.path)
        if frame_data is not None:
            # Encode to JPEG if numpy array
            if isinstance(frame_data, np.ndarray):
                _, buffer = cv2.imencode('.jpg', frame_data)
                return buffer.tobytes()
            # Already bytes
            return frame_data
        
        return None
    
    def get_grouped_detector_results(self, take_id: int, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Get detector results grouped into continuous errors.
        
        Args:
            take_id: Take ID
            use_cache: Whether to use caching (default: True)
            
        Returns:
            List of continuous error groups with instances
        """
        # Get all detector results for the take
        results = self.get_detector_results(take_id)
        
        if not results:
            return []
            
        # Convert to dict format
        result_dicts = []
        false_positive_count = 0
        for r in results:
            is_fp = getattr(r, 'is_false_positive', False)
            if is_fp:
                false_positive_count += 1
            result_dicts.append({
                'id': getattr(r, 'id', None),
                'frame_id': r.frame_id,
                'detector_name': r.detector_name,
                'description': r.description,
                'confidence': r.confidence,
                'bounding_boxes': r.bounding_boxes or [],
                'is_false_positive': is_fp,
                'metadata': getattr(r, 'metadata', {}) or {}
            })
        
        logger.debug(f"Take {take_id}: {len(results)} total results, {false_positive_count} marked as false positive")
        
        # Check cache if enabled
        cache = get_error_cache()
        if use_cache:
            cached_results = cache.get(take_id, result_dicts)
            if cached_results is not None:
                logger.debug(f"Using cached grouped results for take {take_id}")
                return cached_results
        
        # Group the results
        grouped_results = DetectorResultGrouping.group_detector_results(
            result_dicts, 
            use_spatial=True  # Use sophisticated spatial grouping
        )
        
        # Get summary
        summary = DetectorResultGrouping.get_continuous_error_summary(grouped_results)
        
        # Cache the results
        if use_cache:
            cache.set(take_id, result_dicts, summary)
            
        return summary
    
    def get_detector_results_summary(self, take_id: int) -> Dict[str, Any]:
        """Get a summary of detector results for a take."""
        session = get_session()
        try:
            # Get all results for the take
            results = session.query(DetectorResultDB).filter(
                DetectorResultDB.take_id == take_id
            ).all()
            
            # Group by detector
            summary = {}
            for result in results:
                if result.detector_name not in summary:
                    summary[result.detector_name] = {
                        "total_errors": 0,
                        "by_severity": {},
                        "by_confidence": {"high": 0, "medium": 0, "low": 0}
                    }
                
                summary[result.detector_name]["total_errors"] += 1
                
                # Count by severity - we'll use confidence levels as proxy for severity
                # High confidence (0.8+) = high severity
                # Medium confidence (0.5-0.8) = medium severity  
                # Low confidence (<0.5) = low severity
                if result.confidence >= 0.8:
                    severity = "high"
                elif result.confidence >= 0.5:
                    severity = "medium"
                else:
                    severity = "low"
                    
                if severity not in summary[result.detector_name]["by_severity"]:
                    summary[result.detector_name]["by_severity"][severity] = 0
                summary[result.detector_name]["by_severity"][severity] += 1
                
                # Count by confidence level
                if result.confidence >= 0.8:
                    summary[result.detector_name]["by_confidence"]["high"] += 1
                elif result.confidence >= 0.5:
                    summary[result.detector_name]["by_confidence"]["medium"] += 1
                else:
                    summary[result.detector_name]["by_confidence"]["low"] += 1
            
            return summary
        finally:
            session.close()
    
    def delete_detector_results(self, take_id: int) -> bool:
        """Delete all detector results for a take."""
        session = get_session()
        try:
            # Get take info for filesystem deletion
            db_take = session.query(TakeDB).filter(TakeDB.id == take_id).first()
            if db_take:
                db_angle = session.query(AngleDB).filter(AngleDB.id == db_take.angle_id).first()
                if db_angle:
                    db_scene = session.query(SceneDB).filter(SceneDB.id == db_angle.scene_id).first()
                    if db_scene:
                        project_id = db_scene.project_id
                        scene_id = db_scene.id
                        angle_id = db_angle.id
                        
                        # Delete result images from filesystem
                        delete_detector_results(project_id, scene_id, angle_id, take_id)
            
            # Delete from database
            session.query(DetectorResultDB).filter(
                DetectorResultDB.take_id == take_id
            ).delete()
            
            session.commit()
            return True
        finally:
            session.close()
            
    # CAMF/services/storage/main.py - Add these methods to StorageService class

    # These methods are deprecated - continuous errors are now handled via error grouping
    def create_continuous_error(self, *args, **kwargs) -> int:
        """DEPRECATED - Use add_detector_result with error grouping instead."""
        return 0

    def add_error_occurrence(self, *args, **kwargs):
        """DEPRECATED - Use add_detector_result instead."""
        pass

    def update_continuous_error_last_frame(self, *args, **kwargs):
        """DEPRECATED - Error grouping is handled automatically."""
        pass

    def get_active_continuous_errors(self, take_id: int) -> List[Any]:
        """DEPRECATED - Use get_grouped_detector_results instead."""
        return []

    def mark_continuous_error_inactive(self, *args, **kwargs):
        """DEPRECATED - No longer needed with new error grouping."""
        pass

    def mark_occurrence_false_positive(self, occurrence_id: int, marked_by: str = None):
        """Mark a detector result as false positive."""
        # This now works on detector results instead of occurrences
        session = get_session()
        try:
            # Assume occurrence_id is actually a detector_result_id
            db_result = session.query(DetectorResultDB).filter(
                DetectorResultDB.id == occurrence_id
            ).first()
            
            if db_result:
                db_result.is_false_positive = True
                db_result.false_positive_reason = f"Marked by {marked_by}" if marked_by else "User marked"
                session.commit()
        finally:
            session.close()

    def get_continuous_errors_for_ui(self, take_id: int) -> List[Dict[str, Any]]:
        """DEPRECATED - Use get_grouped_detector_results instead."""
        # This now redirects to the new grouped results method
        return self.get_grouped_detector_results(take_id)
    def get_project_location(self, project_id: int) -> Optional[str]:
        """Get the full path to a project folder."""
        return get_project_location(project_id)
    
    # Batch operations for better performance
    def add_frames_batch(self, frames_data: List[Dict[str, Any]]) -> bool:
        """Add multiple frames in a single batch operation.
        
        Args:
            frames_data: List of dictionaries containing frame data:
                - take_id: int
                - frame: np.ndarray
                - frame_id: int  
                - timestamp: float
                - metadata: dict (optional)
                
        Returns:
            bool: True if successful, False otherwise
        """
        session = get_session()
        try:
            # Get take info for validation
            take_ids = set(f['take_id'] for f in frames_data)
            takes_info = {}
            
            for take_id in take_ids:
                db_take = session.query(TakeDB).filter(TakeDB.id == take_id).first()
                if not db_take:
                    raise ValueError(f"Take {take_id} not found")
                    
                db_angle = session.query(AngleDB).filter(AngleDB.id == db_take.angle_id).first()
                db_scene = session.query(SceneDB).filter(SceneDB.id == db_angle.scene_id).first()
                
                takes_info[take_id] = {
                    'project_id': db_scene.project_id,
                    'scene_id': db_scene.id,
                    'angle_id': db_angle.id,
                    'quality': db_scene.image_quality
                }
            
            # Process and save frames using hybrid storage
            db_frames = []
            for frame_data in frames_data:
                take_id = frame_data['take_id']
                takes_info[take_id]
                
                # Save frame using direct frame storage
                success = self.frame_storage.store_frame(
                    take_id,
                    frame_data['frame_id'],
                    frame_data['frame'],
                    frame_data['timestamp'],
                    frame_data.get('metadata', {})
                )
                
                if not success:
                    logger.error(f"Failed to store frame {frame_data['frame_id']} for take {take_id}")
                    continue
                
                # Prepare database entry with dummy segment info (will be updated after conversion)
                db_frames.append({
                    'take_id': take_id,
                    'frame_id': frame_data['frame_id'],
                    'timestamp': frame_data['timestamp'],
                    'segment_id': 0,  # Will be updated after conversion
                    'segment_offset': frame_data['timestamp']
                })
            
            # Bulk insert to database using optimized schema
            if db_frames:
                session = get_session()
                try:
                    for frame in db_frames:
                        db_frame = FrameDB(**frame)
                        session.add(db_frame)
                    session.commit()
                    return True
                except Exception as e:
                    session.rollback()
                    logger.error(f"Failed to insert frame records: {e}")
                    return False
                finally:
                    session.close()
            
            return True
            
        except Exception as e:
            logger.error(f"Batch frame insertion failed: {e}")
            return False
        finally:
            session.close()
    
    def add_detector_results_batch(self, results_data: List[Dict[str, Any]]) -> bool:
        """Add multiple detector results in a single batch operation.
        
        Args:
            results_data: List of dictionaries containing:
                - take_id: int
                - frame_id: int
                - detector_name: str
                - confidence: ErrorConfidence
                - description: str
                - bounding_boxes: list (optional)
                - metadata: dict (optional)
                
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Group results by take_id for efficient processing
            results_by_take = {}
            for result in results_data:
                take_id = result['take_id']
                if take_id not in results_by_take:
                    results_by_take[take_id] = []
                results_by_take[take_id].append(result)
            
            session = get_session()
            try:
                for take_id, take_results in results_by_take.items():
                    # Get existing results for this take to check for grouping
                    existing_results = session.query(DetectorResultDB).filter(
                        DetectorResultDB.take_id == take_id
                    ).order_by(DetectorResultDB.frame_id.desc()).all()
                    
                    # Convert existing results to dict format for grouping
                    existing_dicts = []
                    for db_result in existing_results:
                        existing_dicts.append({
                            'id': db_result.id,
                            'detector_name': db_result.detector_name,
                            'description': db_result.description,
                            'frame_id': db_result.frame_id,
                            'confidence': db_result.confidence,
                            'bounding_boxes': db_result.bounding_boxes,
                            'error_group_id': db_result.error_group_id,
                            'is_continuous_start': db_result.is_continuous_start,
                            'is_continuous_end': db_result.is_continuous_end
                        })
                    
                    # Add new results to the list
                    new_results_dicts = []
                    for result in take_results:
                        new_results_dicts.append({
                            'detector_name': result['detector_name'],
                            'description': result['description'],
                            'frame_id': result['frame_id'],
                            'confidence': result['confidence'].value if hasattr(result['confidence'], 'value') else result['confidence'],
                            'bounding_boxes': result.get('bounding_boxes', [])
                        })
                    
                    # Combine and group all results
                    all_results = existing_dicts + new_results_dicts
                    grouped_results = DetectorResultGrouping.group_detector_results(all_results, use_spatial=True)
                    
                    # Create database entries for new results with assigned group IDs
                    db_results = []
                    for result in take_results:
                        # Find the grouped version of this result
                        frame_id = result['frame_id']
                        detector_name = result['detector_name']
                        
                        grouped_version = None
                        for grouped in grouped_results:
                            if (grouped['frame_id'] == frame_id and 
                                grouped['detector_name'] == detector_name and
                                'id' not in grouped):  # New result (no ID)
                                grouped_version = grouped
                                break
                        
                        db_result = {
                            'take_id': take_id,
                            'frame_id': frame_id,
                            'detector_name': detector_name,
                            'confidence': result['confidence'].value if hasattr(result['confidence'], 'value') else result['confidence'],
                            'description': result['description'],
                            'bounding_boxes': result.get('bounding_boxes', []),
                            'meta_data': result.get('metadata', {}),
                            'error_group_id': grouped_version['error_group_id'] if grouped_version else None,
                            'is_continuous_start': grouped_version.get('is_continuous_start', False) if grouped_version else False,
                            'is_continuous_end': grouped_version.get('is_continuous_end', False) if grouped_version else False
                        }
                        db_results.append(db_result)
                    
                    # Bulk insert
                    if db_results:
                        bulk_insert_detector_results(db_results)
                    
                    # Update end flags for existing results if needed
                    for grouped in grouped_results:
                        if 'id' in grouped and grouped.get('is_continuous_end', False):
                            # Update existing result
                            db_result = session.query(DetectorResultDB).filter(
                                DetectorResultDB.id == grouped['id']
                            ).first()
                            if db_result:
                                db_result.is_continuous_end = True
                
                session.commit()
                
                # Invalidate cache for all affected takes
                cache = get_error_cache()
                for take_id in results_by_take.keys():
                    cache.invalidate(take_id)
                
                return True
                
            finally:
                session.close()
            
        except Exception as e:
            logger.error(f"Batch detector results insertion failed: {e}")
            return False

    def set_scene_video_config(self, scene_id: int, config: Dict[str, Any]) -> bool:
        """Set video storage configuration for a scene."""
        try:
            # Video configuration is no longer used with direct frame storage
            # Just update scene metadata for backward compatibility
            
            # Update scene metadata with video config
            session = get_session()
            try:
                db_scene = session.query(SceneDB).filter(SceneDB.id == scene_id).first()
                if db_scene:
                    if db_scene.meta_data is None:
                        db_scene.meta_data = {}
                    db_scene.meta_data['video_config'] = config
                    session.commit()
                    return True
                return False
            finally:
                session.close()
        except Exception as e:
            logger.error(f"Failed to set video config for scene {scene_id}: {e}")
            return False
    
    def _save_false_positive_training_data(self, detector_result: 'DetectorResultDB', session):
        """Save false positive data for detector training."""
        try:
            # Get related data
            take = session.query(TakeDB).filter(TakeDB.id == detector_result.take_id).first()
            if not take:
                return
                
            angle = session.query(AngleDB).filter(AngleDB.id == take.angle_id).first()
            if not angle:
                return
                
            scene = session.query(SceneDB).filter(SceneDB.id == angle.scene_id).first()
            if not scene:
                return
            
            # Get project through scene
            project = session.query(ProjectDB).filter(ProjectDB.id == scene.project_id).first()
            if not project:
                return
            
            base_dir = get_config().storage.base_dir
            training_dir = Path(base_dir) / "detectors" / detector_result.detector_name / "training_data" / "false_positives" / str(scene.id)
            training_dir.mkdir(parents=True, exist_ok=True)
            
            # Save metadata
            metadata = {
                'result_id': detector_result.id,
                'frame_id': detector_result.frame_id,
                'detector_name': detector_result.detector_name,
                'description': detector_result.description,
                'confidence': detector_result.confidence,
                'bounding_boxes': detector_result.bounding_boxes,
                'false_positive_reason': detector_result.false_positive_reason,
                'frame_path': f"{project.id}/{scene.id}/{angle.id}/{take.id}/frame_{detector_result.frame_id:08d}.jpg"
            }
            
            metadata_file = training_dir / f"fp_{detector_result.id}.json"
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save false positive training data: {e}")
    
    def get_storage_status(self, take_id: int) -> Dict[str, Any]:
        """Get the current storage status for a take."""
        stats = self.frame_storage.get_storage_stats(take_id)
        frame_count = self.frame_storage.get_frame_count(take_id)
        
        return {
            'mode': 'direct_frames',
            'status': 'active' if frame_count > 0 else 'empty',
            'frame_count': frame_count,
            'storage_type': 'PNG (lossless)',
            'stats': stats
        }
    
    def finalize_take(self, take_id: int):
        """Finalize a take (update frame index)."""
        self.frame_storage.finalize_take(take_id)
    
    # ==================== FRAME PROVIDER INTEGRATION ====================
    
    def set_frame_context(self, project_id: Optional[int] = None, scene_id: Optional[int] = None, 
                         angle_id: Optional[int] = None, take_id: Optional[int] = None):
        """Set the current context for frame requests."""
        with self._context_lock:
            if project_id is not None:
                self._current_project_id = project_id
            if scene_id is not None:
                self._current_scene_id = scene_id
            if angle_id is not None:
                self._current_angle_id = angle_id
            if take_id is not None:
                self._current_take_id = take_id
                
            # Clear cache when context changes
            self._clear_frame_cache()
    
    def get_frame_context(self) -> Dict[str, Optional[int]]:
        """Get the current frame context."""
        with self._context_lock:
            return {
                'project_id': self._current_project_id,
                'scene_id': self._current_scene_id,
                'angle_id': self._current_angle_id,
                'take_id': self._current_take_id
            }
    
    def _get_cached_frame(self, take_id: int, frame_id: int) -> Optional[np.ndarray]:
        """Get frame from cache or storage."""
        cache_key = f"{take_id}_{frame_id}"
        
        # Try cache first
        with self._cache_lock:
            if cache_key in self._frame_cache:
                return self._frame_cache[cache_key]
        
        # Load from storage - get_frame already returns numpy array
        frame_data = self.get_frame(take_id, frame_id)
        if frame_data is not None:
            # Cache it
            with self._cache_lock:
                self._frame_cache[cache_key] = frame_data
                
                # Limit cache size
                if len(self._frame_cache) > self._cache_size:
                    # Remove oldest entries
                    oldest_keys = list(self._frame_cache.keys())[:10]
                    for key in oldest_keys:
                        del self._frame_cache[key]
            
            return frame_data
        
        return None
    
    def _clear_frame_cache(self):
        """Clear the frame cache."""
        with self._cache_lock:
            self._frame_cache.clear()
    
    def get_current_frame(self) -> Optional[np.ndarray]:
        """Get the latest captured frame from current take."""
        if self._current_take_id is None:
            return None
        
        latest_frame_id = self.get_latest_frame_id(self._current_take_id)
        if latest_frame_id is None:
            return None
        
        return self._get_cached_frame(self._current_take_id, latest_frame_id)
    
    def get_current_reference_frame(self) -> Optional[np.ndarray]:
        """Get current frame from reference take of current angle."""
        if self._current_angle_id is None:
            return None
        
        ref_take = self.get_reference_take_for_angle(self._current_angle_id)
        if ref_take is None:
            return None
        
        latest_frame_id = self.get_latest_frame_id(ref_take.id)
        if latest_frame_id is None:
            return None
        
        return self._get_cached_frame(ref_take.id, latest_frame_id)
    
    def get_frame_array_with_context(self, frame_id: int, take_id: Optional[int] = None) -> Optional[np.ndarray]:
        """Get specific frame as numpy array using current take context if take_id not provided."""
        if take_id is None:
            take_id = self._current_take_id
        
        if take_id is None:
            return None
        
        # Call the frame storage method with correct parameter order
        return self.frame_storage.get_frame(take_id, frame_id)
    
    def get_reference_frame_array(self, frame_id: int) -> Optional[np.ndarray]:
        """Get specific frame from reference take as numpy array."""
        if self._current_angle_id is None:
            return None
        
        ref_take = self.get_reference_take_for_angle(self._current_angle_id)
        if ref_take is None:
            return None
        
        return self._get_cached_frame(ref_take.id, frame_id)
    
    def get_frame_from_take(self, take_id: int, frame_id: int) -> Optional[np.ndarray]:
        """Get specific frame from given take as numpy array."""
        return self._get_cached_frame(take_id, frame_id)
    
    def get_frame_range(self, start: int, end: Optional[int] = None, take_id: Optional[int] = None) -> List[np.ndarray]:
        """Get range of frames from take."""
        if take_id is None:
            take_id = self._current_take_id
        
        if take_id is None:
            return []
        
        frames = []
        frame_ids = self.get_frame_ids_in_range(take_id, start, end)
        
        for frame_id in frame_ids:
            frame_data = self._get_cached_frame(take_id, frame_id)
            if frame_data is not None:
                frames.append(frame_data)
        
        return frames
    
    def get_frame_ids_in_range(self, take_id: int, start: int, end: Optional[int] = None) -> List[int]:
        """Get frame IDs in the specified range."""
        with self.session_scope() as session:
            query = session.query(FrameDB.frame_number).filter(
                FrameDB.take_id == take_id,
                FrameDB.frame_number >= start
            )
            
            if end is not None:
                query = query.filter(FrameDB.frame_number <= end)
            
            return [row[0] for row in query.all()]
    
    def preload_frames(self, frame_ids: List[int], take_id: Optional[int] = None) -> int:
        """Preload frames into cache for faster access."""
        if take_id is None:
            take_id = self._current_take_id
        
        if take_id is None:
            return 0
        
        loaded = 0
        for frame_id in frame_ids:
            if self._get_cached_frame(take_id, frame_id) is not None:
                loaded += 1
        
        return loaded
    
    def get_frames_for_take(self, take_id: int) -> List[Any]:
        """Get all frames for a take."""
        with self.session_scope() as session:
            db_frames = session.query(FrameDB).filter(
                FrameDB.take_id == take_id
            ).order_by(FrameDB.frame_number).all()
            
            # Convert to Frame objects with frame_number attribute
            frames = []
            for db_frame in db_frames:
                frame = self._db_frame_to_model(db_frame)
                # Add frame_number attribute (same as frame_id for now)
                frame.frame_number = db_frame.frame_number
                frame.id = db_frame.frame_number
                frame.path = self.frame_storage.get_frame_path(take_id, db_frame.frame_number)
                frames.append(frame)
            
            return frames
    
    def get_frame_cache_stats(self) -> Dict[str, Any]:
        """Get frame cache statistics."""
        with self._cache_lock:
            return {
                'size': len(self._frame_cache),
                'max_size': self._cache_size,
                'hit_rate': 0.0  # Could track this if needed
            }
    
    # Note Management Methods
    
    def create_note(self, take_id: int, text: str, 
                   frame_id: Optional[int] = None, 
                   detector_name: Optional[str] = None, 
                   tags: List[str] = None) -> Dict[str, Any]:
        """
        Create a note for a take.
        
        Args:
            take_id: Take ID
            text: Note text
            frame_id: Optional frame ID reference
            detector_name: Optional detector that generated the note
            tags: Optional list of tags
            
        Returns:
            Note information dictionary
        """
        if tags is None:
            tags = []
            
        # Get take to ensure it exists
        take = self.get_take(take_id)
        if not take:
            raise ValueError(f"Take {take_id} not found")
        
        # If frame_id provided, add frame reference to text
        if frame_id is not None:
            if f"frame #{frame_id}" not in text:
                text = f"{text} (see frame #{frame_id})"
        
        # If detector_name provided, add prefix
        if detector_name:
            text = f"[{detector_name}] {text}"
        
        # Get existing notes
        existing_notes = take.notes or ""
        
        # Add timestamp
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_note_entry = f"\n[{timestamp}] {text}" if existing_notes else f"[{timestamp}] {text}"
        
        # Update take notes
        updated_notes = existing_notes + new_note_entry
        updated_take = self.update_take(take_id=take_id, notes=updated_notes)
        
        if updated_take:
            # Parse the note to extract frame references
            parsed = self.note_parser.parse_note(text)
            
            return {
                "success": True,
                "take_id": take_id,
                "note_text": text,
                "timestamp": timestamp,
                "frame_references": parsed.frame_references,
                "detector_name": detector_name,
                "tags": tags
            }
        else:
            raise ValueError("Failed to create note")
    
    def get_note(self, note_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific note by ID.
        
        Note: Since notes are stored as text in the take, we don't have individual note IDs.
        This method is provided for API compatibility but returns None.
        """
        # Notes are stored as text in takes, not as individual records
        return None
    
    def get_notes_for_take(self, take_id: int) -> Dict[str, Any]:
        """
        Get all notes for a take.
        
        Args:
            take_id: Take ID
            
        Returns:
            Dictionary with parsed notes information
        """
        take = self.get_take(take_id)
        if not take:
            return {
                "take_id": take_id,
                "notes": "",
                "parsed": None,
                "frame_references": []
            }
        
        # Parse notes
        parsed = self.note_parser.parse_note(take.notes or "")
        
        return {
            "take_id": take_id,
            "notes": take.notes or "",
            "parsed": {
                "segments": parsed.segments,
                "frame_references": parsed.frame_references,
                "note_type": parsed.note_type.value
            },
            "frame_references": parsed.frame_references
        }
    
    def update_note(self, note_id: int, **kwargs) -> Dict[str, Any]:
        """
        Update a note.
        
        Note: Since notes are stored as text in the take, we can't update individual notes.
        This method is provided for API compatibility.
        """
        # Notes are stored as text in takes, not as individual records
        # For compatibility, we return a failure message
        return {
            "success": False,
            "error": "Individual note updates not supported. Use update_take to modify notes."
        }
    
    def delete_note(self, note_id: int) -> bool:
        """
        Delete a note.
        
        Note: Since notes are stored as text in the take, we can't delete individual notes.
        This method is provided for API compatibility.
        """
        # Notes are stored as text in takes, not as individual records
        return False
    
    def search_notes(self, query: str, 
                    take_id: Optional[int] = None,
                    detector_name: Optional[str] = None,
                    tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Search notes across takes.
        
        Args:
            query: Search query string
            take_id: Optional take ID to limit search
            detector_name: Optional detector name filter
            tags: Optional tag filter
            
        Returns:
            List of matching notes with context
        """
        results = []
        
        # If take_id specified, search only that take
        if take_id:
            take = self.get_take(take_id)
            if take and take.notes:
                if query.lower() in take.notes.lower():
                    # Check detector filter
                    if detector_name and f"[{detector_name}]" not in take.notes:
                        return results
                    
                    parsed = self.note_parser.parse_note(take.notes)
                    results.append({
                        "take_id": take_id,
                        "take_name": take.name,
                        "notes": take.notes,
                        "frame_references": parsed.frame_references,
                        "note_type": parsed.note_type.value
                    })
        else:
            # Search all takes (limited implementation)
            # In a real implementation, this would be more efficient
            with self.session_scope() as session:
                # Search takes with notes containing the query
                db_takes = session.query(TakeDB).filter(
                    TakeDB.notes.ilike(f"%{query}%")
                ).limit(100).all()  # Limit results for performance
                
                for db_take in db_takes:
                    # Apply filters
                    if detector_name and f"[{detector_name}]" not in (db_take.notes or ""):
                        continue
                    
                    parsed = self.note_parser.parse_note(db_take.notes or "")
                    
                    # Get angle and scene info for context
                    db_angle = session.query(AngleDB).filter_by(id=db_take.angle_id).first()
                    angle_name = db_angle.name if db_angle else None
                    scene_name = None
                    if db_angle:
                        db_scene = session.query(SceneDB).filter_by(id=db_angle.scene_id).first()
                        scene_name = db_scene.name if db_scene else None
                    
                    results.append({
                        "take_id": db_take.id,
                        "take_name": db_take.name,
                        "angle_name": angle_name,
                        "scene_name": scene_name,
                        "notes": db_take.notes,
                        "frame_references": parsed.frame_references,
                        "note_type": parsed.note_type.value
                    })
        
        return results
    
    def parse_take_notes(self, take_id: int) -> Optional[ParsedNote]:
        """
        Parse notes for a take to extract frame references and note type.
        
        Args:
            take_id: Take ID
            
        Returns:
            ParsedNote object or None if take not found
        """
        take = self.get_take(take_id)
        if not take:
            return None
        
        return self.note_parser.parse_note(take.notes or "")
    
    # Alias methods for CRUD endpoint compatibility
    
    def list_projects(self) -> List[Project]:
        """Alias for get_all_projects() to match CRUD endpoints."""
        return self.get_all_projects()
    
    def list_scenes(self, project_id: int) -> List[Scene]:
        """Alias for get_scenes_for_project() to match CRUD endpoints."""
        return self.get_scenes_for_project(project_id)
    
    def list_angles(self, scene_id: int) -> List[Angle]:
        """Alias for get_angles_for_scene() to match CRUD endpoints."""
        return self.get_angles_for_scene(scene_id)
    
    def list_takes(self, angle_id: int) -> List[Take]:
        """Alias for get_takes_for_angle() to match CRUD endpoints."""
        return self.get_takes_for_angle(angle_id)
    
    def clear_detector_cache(self, detector_name: str):
        """Clear any cached data for a specific detector.
        This is called when a detector is uninstalled to ensure clean state.
        """
        # Currently, detector-specific caching is handled by the detector framework
        # This method is a placeholder for future detector-specific storage cleanup
        logger.debug(f"Clearing cache for detector: {detector_name}")
        
        # Clear any detector-specific error records from database
        try:
            with self.session_scope() as session:
                # Clear detector errors for this detector
                from .models import DetectorError
                session.query(DetectorError).filter(
                    DetectorError.detector_name == detector_name
                ).delete()
                session.commit()
                logger.info(f"Cleared detector errors for: {detector_name}")
        except Exception as e:
            logger.warning(f"Failed to clear detector errors: {e}")

# Singleton instance
_storage_service = None

def get_storage_service() -> StorageService:
    """Get the storage service singleton."""
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service
"""
False Positive Management for the Storage Service.
Handles marking, storing, and retrieving false positive detections.
"""
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy import or_, and_

from CAMF.services.storage.database import (
    get_session, DetectorResultDB, TakeDB, AngleDB, SceneDB
)

logger = logging.getLogger(__name__)

class FalsePositiveManager:
    """Manages false positive detections in the storage system."""
    
    def __init__(self):
        """Initialize the false positive manager."""
        self.logger = logger
        
    def mark_as_false_positive(
        self, 
        detector_name: str,
        frame_id: int,
        take_id: int,
        error_id: Optional[str] = None,
        marked_by: str = "user",
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Mark a detection as a false positive.
        
        Args:
            detector_name: Name of the detector
            frame_id: Frame ID where the detection occurred
            take_id: Take ID
            error_id: Optional specific error ID
            marked_by: Who marked it as false positive
            reason: Optional reason for marking
            
        Returns:
            Dict with status and updated count
        """
        with get_session() as session:
            try:
                updated_count = 0
                
                # Query for detector results matching the criteria
                query = session.query(DetectorResultDB).filter(
                    DetectorResultDB.take_id == take_id,
                    DetectorResultDB.frame_id == frame_id,
                    DetectorResultDB.detector_name == detector_name,
                    DetectorResultDB.is_false_positive == False
                )
                
                # If specific error_id provided, filter by it
                if error_id:
                    try:
                        error_id_int = int(error_id)
                        query = query.filter(DetectorResultDB.id == error_id_int)
                    except ValueError:
                        # If error_id is not a valid integer, filter by error_group_id
                        query = query.filter(DetectorResultDB.error_group_id == error_id)
                
                detector_results = query.all()
                
                for result in detector_results:
                    # Update the database fields
                    result.is_false_positive = True
                    result.false_positive_reason = reason
                    
                    # Also update metadata for backward compatibility
                    if not result.metadata:
                        result.metadata = {}
                    result.metadata['false_positive'] = True
                    result.metadata['false_positive_by'] = marked_by
                    result.metadata['false_positive_at'] = datetime.now().isoformat()
                    if reason:
                        result.metadata['false_positive_reason'] = reason
                    
                    updated_count += 1
                        
                session.commit()
                
                self.logger.info(
                    f"Marked {updated_count} detections as false positive "
                    f"for {detector_name} in frame {frame_id}"
                )
                
                return {
                    "success": True,
                    "updated_count": updated_count,
                    "detector_name": detector_name,
                    "frame_id": frame_id
                }
                
            except Exception as e:
                session.rollback()
                self.logger.error(f"Error marking false positive: {e}")
                return {
                    "success": False,
                    "error": str(e)
                }
                
    def unmark_false_positive(
        self,
        detector_name: str,
        frame_id: int,
        take_id: int,
        error_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Remove false positive marking from a detection.
        
        Args:
            detector_name: Name of the detector
            frame_id: Frame ID
            take_id: Take ID
            error_id: Optional specific error ID
            
        Returns:
            Dict with status and updated count
        """
        with get_session() as session:
            try:
                updated_count = 0
                
                # Query for detector results matching the criteria
                query = session.query(DetectorResultDB).filter(
                    DetectorResultDB.take_id == take_id,
                    DetectorResultDB.frame_id == frame_id,
                    DetectorResultDB.detector_name == detector_name,
                    DetectorResultDB.is_false_positive == True
                )
                
                if error_id:
                    try:
                        error_id_int = int(error_id)
                        query = query.filter(DetectorResultDB.id == error_id_int)
                    except ValueError:
                        query = query.filter(DetectorResultDB.error_group_id == error_id)
                
                detector_results = query.all()
                
                for result in detector_results:
                    # Update the database fields
                    result.is_false_positive = False
                    result.false_positive_reason = None
                    
                    # Also update metadata
                    if result.metadata and 'false_positive' in result.metadata:
                        del result.metadata['false_positive']
                        result.metadata.pop('false_positive_by', None)
                        result.metadata.pop('false_positive_at', None)
                        result.metadata.pop('false_positive_reason', None)
                    
                    updated_count += 1
                        
                session.commit()
                
                return {
                    "success": True,
                    "updated_count": updated_count
                }
                
            except Exception as e:
                session.rollback()
                self.logger.error(f"Error unmarking false positive: {e}")
                return {
                    "success": False,
                    "error": str(e)
                }
                
    def get_false_positives(
        self,
        take_id: Optional[int] = None,
        detector_name: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get all false positive detections.
        
        Args:
            take_id: Optional filter by take
            detector_name: Optional filter by detector
            limit: Maximum number of results
            
        Returns:
            List of false positive detections
        """
        with get_session() as session:
            try:
                query = session.query(
                    DetectorResultDB,
                    TakeDB,
                    AngleDB,
                    SceneDB
                ).join(
                    TakeDB, TakeDB.id == DetectorResultDB.take_id
                ).join(
                    AngleDB, AngleDB.id == TakeDB.angle_id
                ).join(
                    SceneDB, SceneDB.id == AngleDB.scene_id
                ).filter(
                    DetectorResultDB.is_false_positive == True
                )
                
                if take_id:
                    query = query.filter(DetectorResultDB.take_id == take_id)
                    
                if detector_name:
                    query = query.filter(DetectorResultDB.detector_name == detector_name)
                    
                results = query.limit(limit).all()
                
                false_positives = []
                for result, take, angle, scene in results:
                    fp_info = {
                        "id": result.id,
                        "frame_id": result.frame_id,
                        "take_id": take.id,
                        "take_name": take.name,
                        "angle_name": angle.name,
                        "scene_name": scene.name,
                        "detector_name": result.detector_name,
                        "description": result.description,
                        "confidence": result.confidence,
                        "false_positive_reason": result.false_positive_reason,
                        "bounding_boxes": result.bounding_boxes,
                        "created_at": result.created_at.isoformat() if result.created_at else None
                    }
                    
                    # Add metadata info if available
                    if result.metadata:
                        fp_info["marked_by"] = result.metadata.get("false_positive_by", "unknown")
                        fp_info["marked_at"] = result.metadata.get("false_positive_at")
                    
                    false_positives.append(fp_info)
                    
                return false_positives
                
            except Exception as e:
                self.logger.error(f"Error getting false positives: {e}")
                return []
                
    def get_false_positive_stats(
        self,
        detector_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get statistics about false positives.
        
        Args:
            detector_name: Optional filter by detector
            
        Returns:
            Statistics dictionary
        """
        with get_session() as session:
            try:
                query = session.query(DetectorResultDB).filter(
                    DetectorResultDB.is_false_positive == True
                )
                
                if detector_name:
                    query = query.filter(DetectorResultDB.detector_name == detector_name)
                    
                total_false_positives = query.count()
                
                # Get per-detector stats
                from sqlalchemy import func
                detector_stats = session.query(
                    DetectorResultDB.detector_name,
                    func.count(DetectorResultDB.id).label('count')
                ).filter(
                    DetectorResultDB.is_false_positive == True
                ).group_by(
                    DetectorResultDB.detector_name
                ).all()
                
                stats = {
                    "total_false_positives": total_false_positives,
                    "by_detector": {
                        detector: count 
                        for detector, count in detector_stats
                    }
                }
                
                return stats
                
            except Exception as e:
                self.logger.error(f"Error getting false positive stats: {e}")
                return {
                    "total_false_positives": 0,
                    "by_detector": {}
                }
                
    def is_false_positive(
        self,
        detector_name: str,
        frame_id: int,
        take_id: int
    ) -> bool:
        """
        Check if a detection is marked as false positive.
        
        Args:
            detector_name: Detector name
            frame_id: Frame ID
            take_id: Take ID
            
        Returns:
            True if marked as false positive
        """
        with get_session() as session:
            try:
                exists = session.query(DetectorResultDB).filter(
                    DetectorResultDB.take_id == take_id,
                    DetectorResultDB.detector_name == detector_name,
                    DetectorResultDB.frame_id == frame_id,
                    DetectorResultDB.is_false_positive == True
                ).first() is not None
                
                return exists
                
            except Exception as e:
                self.logger.error(f"Error checking false positive: {e}")
                return False
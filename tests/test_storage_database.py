"""
Comprehensive tests for storage database operations.
Tests database models, queries, transactions, and performance.
"""

import pytest
import tempfile
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import json
import time
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError, OperationalError

from CAMF.services.storage.database import (
    Base, init_db, get_session, get_engine,
    ProjectDB, SceneDB, AngleDB, TakeDB, FrameDB, DetectorResultDB,
    bulk_insert_frames, bulk_insert_detector_results,
    cleanup_orphaned_records, vacuum_database, reset_database,
    analyze_database
)


class TestDatabaseModels:
    """Test database model definitions and relationships."""
    
    @pytest.fixture
    def test_db(self):
        """Create a test database."""
        # Create temporary database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        # Create engine and tables
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        
        # Create session factory
        Session = sessionmaker(bind=engine)
        
        yield engine, Session, db_path
        
        # Cleanup
        engine.dispose()
        os.unlink(db_path)
    
    def test_project_model(self, test_db):
        """Test Project model."""
        engine, Session, db_path = test_db
        session = Session()
        
        # Create project
        project = ProjectDB(
            name="Test Project",
            created_at=datetime.now()
        )
        session.add(project)
        session.commit()
        
        # Query project
        retrieved = session.query(ProjectDB).first()
        assert retrieved.name == "Test Project"
        assert retrieved.id is not None
        assert isinstance(retrieved.created_at, datetime)
        
        session.close()
    
    def test_scene_model(self, test_db):
        """Test Scene model with relationships."""
        engine, Session, db_path = test_db
        session = Session()
        
        # Create project and scene
        project = ProjectDB(name="Test Project")
        scene = SceneDB(
            name="Scene 1",
            scene_number=1,
            project=project,
            detector_settings={"detector1": {"threshold": 0.8}}
        )
        
        session.add(project)
        session.add(scene)
        session.commit()
        
        # Test relationship
        assert scene.project_id == project.id
        assert project.scenes[0] == scene
        
        session.close()
    
    def test_angle_model(self, test_db):
        """Test Angle model."""
        engine, Session, db_path = test_db
        session = Session()
        
        # Create hierarchy
        project = ProjectDB(name="Test Project")
        scene = SceneDB(name="Scene 1", scene_number=1, project=project)
        angle = AngleDB(
            name="Wide Shot",
            angle_number=1,
            scene=scene,
            camera_settings="Camera A, 24mm"
        )
        
        session.add_all([project, scene, angle])
        session.commit()
        
        # Test relationships
        assert angle.scene_id == scene.id
        assert scene.angles[0] == angle
        
        session.close()
    
    def test_take_model(self, test_db):
        """Test Take model."""
        engine, Session, db_path = test_db
        session = Session()
        
        # Create hierarchy
        project = ProjectDB(name="Test Project")
        scene = SceneDB(name="Scene 1", scene_number=1, project=project)
        angle = AngleDB(name="Wide Shot", angle_number=1, scene=scene)
        take = TakeDB(
            name="Take 1",
            take_number=1,
            angle=angle,
            is_reference=True,
            notes="Good take"
        )
        
        session.add_all([project, scene, angle, take])
        session.commit()
        
        # Test properties
        assert take.angle_id == angle.id
        assert take.is_reference is True
        assert angle.takes[0] == take
        
        session.close()
    
    def test_frame_model(self, test_db):
        """Test Frame model."""
        engine, Session, db_path = test_db
        session = Session()
        
        # Create hierarchy
        project = ProjectDB(name="Test Project")
        scene = SceneDB(name="Scene 1", scene_number=1, project=project)
        angle = AngleDB(name="Wide Shot", angle_number=1, scene=scene)
        take = TakeDB(name="Take 1", take_number=1, angle=angle)
        frame = FrameDB(
            frame_number=42,
            take=take,
            timestamp=datetime.now(),
            filepath="/path/to/frame.jpg"
        )
        
        session.add_all([project, scene, angle, take, frame])
        session.commit()
        
        # Test properties
        assert frame.take_id == take.id
        assert frame.frame_number == 42
        assert take.frames[0] == frame
        
        session.close()
    
    def test_detector_result_model(self, test_db):
        """Test DetectorResult model."""
        engine, Session, db_path = test_db
        session = Session()
        
        # Create full hierarchy
        project = ProjectDB(name="Test Project")
        scene = SceneDB(name="Scene 1", scene_number=1, project=project)
        angle = AngleDB(name="Wide Shot", angle_number=1, scene=scene)
        take = TakeDB(name="Take 1", take_number=1, angle=angle)
        frame = FrameDB(frame_number=1, take=take, timestamp=datetime.now())
        
        result = DetectorResultDB(
            frame=frame,
            detector_name="TestDetector",
            confidence=0.95,
            description="Object detected",
            bounding_boxes=[{"x": 10, "y": 20, "w": 100, "h": 50}],
            metadata={"extra": "data"}
        )
        
        session.add_all([project, scene, angle, take, frame, result])
        session.commit()
        
        # Test properties
        assert result.frame_id == frame.id
        assert result.confidence == 0.95
        assert len(result.bounding_boxes) == 1
        assert frame.detector_results[0] == result
        
        session.close()
    
    def test_cascade_delete(self, test_db):
        """Test cascade delete behavior."""
        engine, Session, db_path = test_db
        session = Session()
        
        # Create hierarchy
        project = ProjectDB(name="Test Project")
        scene = SceneDB(name="Scene 1", scene_number=1, project=project)
        angle = AngleDB(name="Wide Shot", angle_number=1, scene=scene)
        take = TakeDB(name="Take 1", take_number=1, angle=angle)
        frame = FrameDB(frame_number=1, take=take, timestamp=datetime.now())
        
        session.add_all([project, scene, angle, take, frame])
        session.commit()
        
        # Delete project should cascade
        session.delete(project)
        session.commit()
        
        # Check all related objects are deleted
        assert session.query(SceneDB).count() == 0
        assert session.query(AngleDB).count() == 0
        assert session.query(TakeDB).count() == 0
        assert session.query(FrameDB).count() == 0
        
        session.close()
    
    def test_unique_constraints(self, test_db):
        """Test unique constraints."""
        engine, Session, db_path = test_db
        session = Session()
        
        # Create project
        project1 = ProjectDB(name="Unique Project")
        project2 = ProjectDB(name="Unique Project")
        
        session.add(project1)
        session.commit()
        
        # Adding duplicate should fail
        session.add(project2)
        with pytest.raises(IntegrityError):
            session.commit()
        
        session.close()


class TestDatabaseQueries:
    """Test database query operations."""
    
    @pytest.fixture
    def populated_db(self, test_db):
        """Create a populated test database."""
        engine, Session, db_path = test_db
        session = Session()
        
        # Create test data
        project = ProjectDB(name="Test Project")
        
        for i in range(3):
            scene = SceneDB(
                name=f"Scene {i+1}",
                scene_number=i+1,
                project=project
            )
            
            for j in range(2):
                angle = AngleDB(
                    name=f"Angle {j+1}",
                    angle_number=j+1,
                    scene=scene
                )
                
                for k in range(3):
                    take = TakeDB(
                        name=f"Take {k+1}",
                        take_number=k+1,
                        angle=angle,
                        is_reference=(k == 0)
                    )
                    
                    for f in range(10):
                        frame = FrameDB(
                            frame_number=f+1,
                            take=take,
                            timestamp=datetime.now() + timedelta(seconds=f)
                        )
                        session.add(frame)
        
        session.add(project)
        session.commit()
        
        yield session, project
        
        session.close()
    
    def test_query_with_joins(self, populated_db):
        """Test queries with joins."""
        session, project = populated_db
        
        # Query frames with full hierarchy
        frames = (session.query(FrameDB)
                  .join(TakeDB)
                  .join(AngleDB)
                  .join(SceneDB)
                  .filter(SceneDB.project_id == project.id)
                  .all())
        
        assert len(frames) == 180  # 3 scenes * 2 angles * 3 takes * 10 frames
    
    def test_query_with_filters(self, populated_db):
        """Test queries with filters."""
        session, project = populated_db
        
        # Query reference takes only
        ref_takes = (session.query(TakeDB)
                    .filter(TakeDB.is_reference == True)
                    .all())
        
        assert len(ref_takes) == 6  # 3 scenes * 2 angles * 1 reference take
    
    def test_query_with_aggregation(self, populated_db):
        """Test queries with aggregation."""
        session, project = populated_db
        
        from sqlalchemy import func
        
        # Count frames per take
        frame_counts = (session.query(
                            TakeDB.id,
                            func.count(FrameDB.id).label('frame_count')
                        )
                        .join(FrameDB)
                        .group_by(TakeDB.id)
                        .all())
        
        # Each take should have 10 frames
        for take_id, count in frame_counts:
            assert count == 10
    
    def test_query_with_ordering(self, populated_db):
        """Test queries with ordering."""
        session, project = populated_db
        
        # Query scenes ordered by scene number
        scenes = (session.query(SceneDB)
                  .filter(SceneDB.project_id == project.id)
                  .order_by(SceneDB.scene_number.desc())
                  .all())
        
        assert scenes[0].scene_number == 3
        assert scenes[-1].scene_number == 1
    
    def test_query_with_limit_offset(self, populated_db):
        """Test queries with pagination."""
        session, project = populated_db
        
        # Get second page of frames
        page_size = 10
        page = 2
        
        frames = (session.query(FrameDB)
                  .order_by(FrameDB.id)
                  .limit(page_size)
                  .offset((page - 1) * page_size)
                  .all())
        
        assert len(frames) == 10


class TestBulkOperations:
    """Test bulk database operations."""
    
    @pytest.fixture
    def bulk_db(self, test_db):
        """Create database for bulk operations."""
        engine, Session, db_path = test_db
        session = Session()
        
        # Create basic structure
        project = ProjectDB(name="Bulk Test")
        scene = SceneDB(name="Scene 1", scene_number=1, project=project)
        angle = AngleDB(name="Angle 1", angle_number=1, scene=scene)
        take = TakeDB(name="Take 1", take_number=1, angle=angle)
        
        session.add_all([project, scene, angle, take])
        session.commit()
        
        yield session, take
        
        session.close()
    
    def test_bulk_insert_frames(self, bulk_db):
        """Test bulk frame insertion."""
        session, take = bulk_db
        
        # Create frame data
        frames = []
        for i in range(100):
            frames.append({
                'frame_number': i + 1,
                'take_id': take.id,
                'timestamp': datetime.now() + timedelta(seconds=i),
                'filepath': f'/path/to/frame_{i+1}.jpg'
            })
        
        # Bulk insert
        bulk_insert_frames(session, frames)
        
        # Verify
        count = session.query(FrameDB).filter(FrameDB.take_id == take.id).count()
        assert count == 100
    
    def test_bulk_insert_detector_results(self, bulk_db):
        """Test bulk detector result insertion."""
        session, take = bulk_db
        
        # Create a frame first
        frame = FrameDB(
            frame_number=1,
            take=take,
            timestamp=datetime.now()
        )
        session.add(frame)
        session.commit()
        
        # Create detector results
        results = []
        for i in range(50):
            results.append({
                'frame_id': frame.id,
                'detector_name': f'Detector{i % 3}',
                'confidence': 0.5 + (i % 5) * 0.1,
                'description': f'Detection {i}',
                'bounding_boxes': [{"x": i, "y": i, "w": 10, "h": 10}],
                'metadata': {"index": i}
            })
        
        # Bulk insert
        bulk_insert_detector_results(session, results)
        
        # Verify
        count = session.query(DetectorResultDB).filter(
            DetectorResultDB.frame_id == frame.id
        ).count()
        assert count == 50


class TestDatabaseMaintenance:
    """Test database maintenance operations."""
    
    @pytest.fixture
    def maintenance_db(self, test_db):
        """Create database for maintenance tests."""
        engine, Session, db_path = test_db
        return engine, Session, db_path
    
    def test_cleanup_orphaned_records(self, maintenance_db):
        """Test cleanup of orphaned records."""
        engine, Session, db_path = maintenance_db
        session = Session()
        
        # Create orphaned frame (no take)
        frame = FrameDB(
            frame_number=1,
            take_id=999,  # Non-existent take
            timestamp=datetime.now()
        )
        
        # Force insert bypassing foreign key
        session.execute(
            f"INSERT INTO frames (frame_number, take_id, timestamp) "
            f"VALUES (1, 999, '{datetime.now().isoformat()}')"
        )
        session.commit()
        
        # Run cleanup
        cleanup_orphaned_records(session)
        
        # Orphaned record should be gone
        count = session.query(FrameDB).count()
        assert count == 0
        
        session.close()
    
    def test_vacuum_database(self, maintenance_db):
        """Test database vacuum operation."""
        engine, Session, db_path = maintenance_db
        
        # Get initial size
        initial_size = os.path.getsize(db_path)
        
        # Add and delete data to create fragmentation
        session = Session()
        for i in range(100):
            project = ProjectDB(name=f"Project {i}")
            session.add(project)
        session.commit()
        
        # Delete all
        session.query(ProjectDB).delete()
        session.commit()
        session.close()
        
        # Vacuum
        vacuum_database(engine)
        
        # Size should be reduced (though this is not guaranteed in all cases)
        final_size = os.path.getsize(db_path)
        assert final_size <= initial_size + 1000  # Allow small growth
    
    def test_analyze_database(self, maintenance_db):
        """Test database analysis."""
        engine, Session, db_path = maintenance_db
        session = Session()
        
        # Add some data
        for i in range(10):
            project = ProjectDB(name=f"Project {i}")
            session.add(project)
        session.commit()
        
        # Analyze should not raise
        analyze_database(engine)
        
        session.close()
    
    def test_reset_database(self, maintenance_db):
        """Test database reset."""
        engine, Session, db_path = maintenance_db
        session = Session()
        
        # Add data
        project = ProjectDB(name="To be deleted")
        session.add(project)
        session.commit()
        
        # Reset
        reset_database(engine)
        
        # Reconnect and check
        session = Session()
        count = session.query(ProjectDB).count()
        assert count == 0
        
        session.close()


class TestDatabaseTransactions:
    """Test database transaction handling."""
    
    @pytest.fixture
    def transaction_db(self, test_db):
        """Create database for transaction tests."""
        engine, Session, db_path = test_db
        return Session
    
    def test_transaction_commit(self, transaction_db):
        """Test successful transaction commit."""
        Session = transaction_db
        session = Session()
        
        try:
            project = ProjectDB(name="Transaction Test")
            session.add(project)
            session.commit()
            
            # Should be persisted
            count = session.query(ProjectDB).count()
            assert count == 1
        finally:
            session.close()
    
    def test_transaction_rollback(self, transaction_db):
        """Test transaction rollback."""
        Session = transaction_db
        session = Session()
        
        try:
            project = ProjectDB(name="To be rolled back")
            session.add(project)
            
            # Simulate error
            session.rollback()
            
            # Should not be persisted
            count = session.query(ProjectDB).count()
            assert count == 0
        finally:
            session.close()
    
    def test_nested_transaction(self, transaction_db):
        """Test nested transaction handling."""
        Session = transaction_db
        session = Session()
        
        try:
            # Start transaction
            project = ProjectDB(name="Parent")
            session.add(project)
            session.flush()  # Get ID without committing
            
            # Nested operation
            scene = SceneDB(name="Child", scene_number=1, project_id=project.id)
            session.add(scene)
            
            # Commit all
            session.commit()
            
            # Both should be persisted
            assert session.query(ProjectDB).count() == 1
            assert session.query(SceneDB).count() == 1
        finally:
            session.close()


class TestDatabasePerformance:
    """Test database performance characteristics."""
    
    @pytest.fixture
    def perf_db(self, test_db):
        """Create database for performance tests."""
        engine, Session, db_path = test_db
        return Session
    
    def test_insert_performance(self, perf_db):
        """Test insert performance."""
        Session = perf_db
        session = Session()
        
        start_time = time.time()
        
        # Insert many records
        for i in range(1000):
            project = ProjectDB(name=f"Project {i}")
            session.add(project)
        
        session.commit()
        elapsed = time.time() - start_time
        
        # Should complete in reasonable time
        assert elapsed < 5.0  # 5 seconds for 1000 inserts
        
        session.close()
    
    def test_query_performance(self, perf_db):
        """Test query performance."""
        Session = perf_db
        session = Session()
        
        # Add test data
        project = ProjectDB(name="Performance Test")
        session.add(project)
        session.commit()
        
        for i in range(100):
            scene = SceneDB(
                name=f"Scene {i}",
                scene_number=i,
                project_id=project.id
            )
            session.add(scene)
        session.commit()
        
        # Test query performance
        start_time = time.time()
        
        for _ in range(100):
            scenes = session.query(SceneDB).filter(
                SceneDB.project_id == project.id
            ).all()
        
        elapsed = time.time() - start_time
        
        # Should be fast
        assert elapsed < 1.0  # 1 second for 100 queries
        
        session.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
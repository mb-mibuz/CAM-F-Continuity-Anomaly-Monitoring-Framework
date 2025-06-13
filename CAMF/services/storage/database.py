"""
Database schema for CAMF storage.
Clean implementation without legacy suffixes.
"""

from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, ForeignKey, JSON, DateTime, Text, text, Index, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session
from sqlalchemy.pool import QueuePool, StaticPool
import datetime
import logging
import os
from typing import Dict, Any
import time
from CAMF.common.ensure_db_path import ensure_db_directory

logger = logging.getLogger(__name__)

Base = declarative_base()

_engine = None
_SessionLocal = None

# Query result cache with 60s TTL
_query_cache: Dict[str, tuple[Any, float]] = {}
CACHE_TTL = 60.0  # seconds

def get_engine():
    """Get SQLAlchemy engine with optimized connection pooling."""
    global _engine
    if _engine is None:
        ensure_db_directory()
        database_url = "sqlite:///data/camf_metadata.db"
        logger.info(f"Using database at: {database_url}")
        
        if database_url.startswith('sqlite'):
            # SQLite optimizations
            _engine = create_engine(
                database_url,
                poolclass=StaticPool,  # Use StaticPool for SQLite
                connect_args={
                    'check_same_thread': False,
                    'timeout': 30.0  # 30 second timeout
                },
                pool_pre_ping=True
            )
            
            # Enable optimizations including WAL mode
            try:
                with _engine.connect() as conn:
                    # Enable WAL mode for better concurrent read performance
                    conn.execute(text("PRAGMA journal_mode=WAL"))
                    conn.execute(text("PRAGMA synchronous=NORMAL"))
                    conn.execute(text("PRAGMA cache_size=10000"))  # 10MB cache
                    conn.execute(text("PRAGMA temp_store=MEMORY"))
                    conn.commit()
            except Exception as e:
                logger.warning(f"Failed to set SQLite pragmas: {e}")
        else:
            # PostgreSQL/MySQL with connection pooling
            _engine = create_engine(
                database_url,
                poolclass=QueuePool,
                pool_size=5,
                max_overflow=5,
                pool_timeout=30,
                pool_recycle=3600,
                pool_pre_ping=True
            )
    return _engine

def get_session_factory():
    """Get session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal

def get_session() -> Session:
    """Get SQLAlchemy session."""
    SessionLocal = get_session_factory()
    return SessionLocal()

def cached_query(cache_key: str, ttl: float = CACHE_TTL):
    """Decorator for caching query results."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            now = time.time()
            
            # Check cache
            if cache_key in _query_cache:
                result, timestamp = _query_cache[cache_key]
                if now - timestamp < ttl:
                    return result
            
            # Execute query
            result = func(*args, **kwargs)
            
            # Cache result
            _query_cache[cache_key] = (result, now)
            
            # Clean old cache entries
            for key in list(_query_cache.keys()):
                _, ts = _query_cache[key]
                if now - ts > ttl * 2:
                    del _query_cache[key]
            
            return result
        return wrapper
    return decorator

# Core tables
class ProjectDB(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_modified = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    meta_data = Column(JSON, default={})

    scenes = relationship("SceneDB", back_populates="project", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_project_name', 'name'),
        Index('idx_project_last_modified', 'last_modified'),
    )

class SceneDB(Base):
    __tablename__ = "scenes"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    frame_rate = Column(Float, default=24.0)
    resolution = Column(String(20), default="1920x1080")
    detector_settings = Column(JSON, default={})
    meta_data = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    project = relationship("ProjectDB", back_populates="scenes")
    angles = relationship("AngleDB", back_populates="scene", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint('project_id', 'name'),
        Index('idx_scene_project_id', 'project_id'),
        Index('idx_scene_name', 'name'),
        CheckConstraint('frame_rate > 0', name='check_frame_rate_positive'),
    )

class AngleDB(Base):
    __tablename__ = "angles"

    id = Column(Integer, primary_key=True)
    scene_id = Column(Integer, ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    reference_take_id = Column(Integer, ForeignKey("takes.id", use_alter=True))
    meta_data = Column(JSON, default={})

    scene = relationship("SceneDB", back_populates="angles")
    takes = relationship("TakeDB", back_populates="angle", cascade="all, delete-orphan",
                        foreign_keys="TakeDB.angle_id")
    reference_take = relationship("TakeDB", foreign_keys=[reference_take_id], post_update=True)
    
    __table_args__ = (
        UniqueConstraint('scene_id', 'name'),
        Index('idx_angle_scene_id', 'scene_id'),
        Index('idx_angle_name', 'name'),
    )

class TakeDB(Base):
    __tablename__ = "takes"

    id = Column(Integer, primary_key=True)
    angle_id = Column(Integer, ForeignKey("angles.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    is_reference = Column(Boolean, default=False)
    start_time = Column(DateTime, default=datetime.datetime.utcnow)
    end_time = Column(DateTime)
    notes = Column(Text)
    meta_data = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    angle = relationship("AngleDB", back_populates="takes", foreign_keys=[angle_id])
    frames = relationship("FrameDB", back_populates="take", cascade="all, delete-orphan")
    detector_results = relationship("DetectorResultDB", back_populates="take", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint('angle_id', 'name'),
        Index('idx_take_angle_id', 'angle_id'),
        Index('idx_take_created_at', 'created_at'),
        Index('idx_take_is_reference', 'is_reference'),
    )

class FrameDB(Base):
    __tablename__ = "frames"

    id = Column(Integer, primary_key=True)
    take_id = Column(Integer, ForeignKey("takes.id", ondelete="CASCADE"), nullable=False, index=True)
    frame_number = Column(Integer, nullable=False)
    timestamp = Column(Float, nullable=False)
    path = Column(String(512), nullable=False)

    take = relationship("TakeDB", back_populates="frames")
    
    __table_args__ = (
        Index('idx_take_frame', 'take_id', 'frame_number', unique=True),
    )

class DetectorResultDB(Base):
    __tablename__ = "detector_results"

    id = Column(Integer, primary_key=True)
    take_id = Column(Integer, ForeignKey("takes.id", ondelete="CASCADE"), nullable=False, index=True)
    frame_id = Column(Integer, nullable=False, index=True)
    detector_name = Column(String(100), nullable=False, index=True)
    confidence = Column(Float, nullable=False)  # 0.0-1.0 for new system
    description = Column(Text)
    bounding_boxes = Column(JSON)
    
    # Continuity tracking
    error_group_id = Column(String(255), index=True)  # Groups continuous errors
    is_continuous_start = Column(Boolean, default=False)
    is_continuous_end = Column(Boolean, default=False)
    
    # False positive tracking
    is_false_positive = Column(Boolean, default=False, index=True)
    false_positive_reason = Column(Text)
    
    meta_data = Column(JSON)  # Renamed from metadata to avoid SQLAlchemy reserved word
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    take = relationship("TakeDB", back_populates="detector_results")
    
    __table_args__ = (
        Index('idx_take_frame_detector', 'take_id', 'frame_id', 'detector_name'),
        Index('idx_confidence', 'confidence'),
        CheckConstraint('confidence >= -1.0 AND confidence <= 1.0', name='check_confidence_range'),
    )


def init_db():
    """Initialize the database."""
    engine = get_engine()
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    # Test the connection
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        try:
            session.execute(text("SELECT 1"))
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            raise

def drop_all_tables():
    """Drop all tables - use with caution!"""
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    logger.info("All tables dropped")

def reset_database():
    """Reset the database by dropping and recreating all tables."""
    drop_all_tables()
    init_db()
    logger.info("Database reset complete")

# Batch insert functions
def bulk_insert_frames(frames: list) -> bool:
    """Bulk insert frames for better performance."""
    try:
        session = get_session()
        session.bulk_insert_mappings(FrameDB, frames)
        session.commit()
        session.close()
        return True
    except Exception as e:
        logger.error(f"Bulk frame insert failed: {e}")
        return False

def bulk_insert_detector_results(results: list) -> bool:
    """Bulk insert detector results."""
    try:
        session = get_session()
        session.bulk_insert_mappings(DetectorResultDB, results)
        session.commit()
        session.close()
        return True
    except Exception as e:
        logger.error(f"Bulk detector results insert failed: {e}")
        return False

# Maintenance functions
def vacuum_database():
    """Run VACUUM on the database (SQLite only)."""
    engine = get_engine()
    if engine.url.drivername == 'sqlite':
        with engine.connect() as conn:
            conn.execute(text("VACUUM"))
            conn.commit()
        logger.info("Database VACUUM completed")

def analyze_database():
    """Update database statistics."""
    engine = get_engine()
    if engine.url.drivername == 'sqlite':
        with engine.connect() as conn:
            conn.execute(text("ANALYZE"))
            conn.commit()
    elif engine.url.drivername == 'postgresql':
        with engine.connect() as conn:
            conn.execute(text("ANALYZE"))
            conn.commit()
    logger.info("Database ANALYZE completed")

def cleanup_orphaned_records():
    """Clean up orphaned records."""
    session = get_session()
    try:
        # Clean orphaned detector results
        session.execute(text("""
            DELETE FROM detector_results 
            WHERE take_id NOT IN (SELECT id FROM takes)
        """))
        
        # Clean orphaned frames
        session.execute(text("""
            DELETE FROM frames 
            WHERE take_id NOT IN (SELECT id FROM takes)
        """))
        
        session.commit()
        logger.info("Orphaned records cleanup completed")
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        session.rollback()
    finally:
        session.close()
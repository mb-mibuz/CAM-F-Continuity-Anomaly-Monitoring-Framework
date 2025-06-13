"""
Database maintenance scheduler for CAMF storage.
Runs automatic maintenance tasks to keep the database optimized.
"""

import threading
import time
import schedule
import logging
from datetime import datetime
from .database import vacuum_database, analyze_database, cleanup_orphaned_records

logger = logging.getLogger(__name__)

class DatabaseMaintenanceScheduler:
    """Scheduler for automatic database maintenance tasks."""
    
    def __init__(self):
        self.running = False
        self.scheduler_thread = None
        self.last_vacuum = None
        self.last_analyze = None
        self.last_cleanup = None
        
    def start(self):
        """Start the maintenance scheduler."""
        if self.running:
            logger.warning("Maintenance scheduler already running")
            return
            
        self.running = True
        
        # Schedule tasks
        schedule.every(24).hours.do(self._run_vacuum)
        schedule.every(7).days.do(self._run_analyze)
        schedule.every(12).hours.do(self._run_cleanup)
        
        # Run initial maintenance
        self._run_vacuum()
        self._run_analyze()
        self._run_cleanup()
        
        # Start scheduler thread
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        
        logger.info("Database maintenance scheduler started")
        
    def stop(self):
        """Stop the maintenance scheduler."""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        schedule.clear()
        logger.info("Database maintenance scheduler stopped")
        
    def _scheduler_loop(self):
        """Main scheduler loop."""
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Error in maintenance scheduler: {e}")
                
    def _run_vacuum(self):
        """Run VACUUM operation."""
        try:
            logger.info("Starting database VACUUM...")
            start_time = time.time()
            vacuum_database()
            duration = time.time() - start_time
            self.last_vacuum = datetime.now()
            logger.info(f"Database VACUUM completed in {duration:.2f} seconds")
        except Exception as e:
            logger.error(f"VACUUM failed: {e}")
            
    def _run_analyze(self):
        """Run ANALYZE operation."""
        try:
            logger.info("Starting database ANALYZE...")
            start_time = time.time()
            analyze_database()
            duration = time.time() - start_time
            self.last_analyze = datetime.now()
            logger.info(f"Database ANALYZE completed in {duration:.2f} seconds")
        except Exception as e:
            logger.error(f"ANALYZE failed: {e}")
            
    def _run_cleanup(self):
        """Run orphaned records cleanup."""
        try:
            logger.info("Starting orphaned records cleanup...")
            start_time = time.time()
            cleanup_orphaned_records()
            duration = time.time() - start_time
            self.last_cleanup = datetime.now()
            logger.info(f"Orphaned records cleanup completed in {duration:.2f} seconds")
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            
    def get_status(self):
        """Get maintenance status."""
        return {
            "running": self.running,
            "last_vacuum": self.last_vacuum.isoformat() if self.last_vacuum else None,
            "last_analyze": self.last_analyze.isoformat() if self.last_analyze else None,
            "last_cleanup": self.last_cleanup.isoformat() if self.last_cleanup else None,
            "next_vacuum": schedule.next_run() if self.running else None
        }
        
    def trigger_maintenance(self, task: str = "all"):
        """Manually trigger maintenance tasks."""
        if task in ["vacuum", "all"]:
            self._run_vacuum()
        if task in ["analyze", "all"]:
            self._run_analyze()
        if task in ["cleanup", "all"]:
            self._run_cleanup()

# Singleton instance
_maintenance_scheduler = None

def get_maintenance_scheduler() -> DatabaseMaintenanceScheduler:
    """Get the maintenance scheduler singleton."""
    global _maintenance_scheduler
    if _maintenance_scheduler is None:
        _maintenance_scheduler = DatabaseMaintenanceScheduler()
    return _maintenance_scheduler
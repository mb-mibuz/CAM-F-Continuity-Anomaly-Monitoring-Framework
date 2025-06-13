# CAMF/services/api_gateway/error_recovery.py
"""
Error recovery middleware and utilities for API Gateway.
"""

import time
import asyncio
import logging
from typing import Dict, Any, Optional, Callable
from fastapi import Request
from fastapi.responses import JSONResponse
import traceback

logger = logging.getLogger(__name__)

class ServiceHealthTracker:
    """Track service health and manage recovery."""
    
    def __init__(self):
        self.service_status: Dict[str, Dict[str, Any]] = {}
        self.failure_counts: Dict[str, int] = {}
        self.last_check_times: Dict[str, float] = {}
        self.recovery_callbacks: Dict[str, Callable] = {}
        self.max_failures = 3
        from CAMF.common.config import get_config
        self.check_interval = get_config().service.recovery_check_interval
        self.recovery_delay = 5.0  # seconds
        
    def register_service(self, service_name: str, recovery_callback: Optional[Callable] = None):
        """Register a service for health tracking."""
        self.service_status[service_name] = {
            'healthy': True,
            'last_error': None,
            'last_success': time.time()
        }
        self.failure_counts[service_name] = 0
        self.last_check_times[service_name] = time.time()
        
        if recovery_callback:
            self.recovery_callbacks[service_name] = recovery_callback
            
    def record_success(self, service_name: str):
        """Record successful service operation."""
        if service_name in self.service_status:
            self.service_status[service_name]['healthy'] = True
            self.service_status[service_name]['last_success'] = time.time()
            self.failure_counts[service_name] = 0
            
    def record_failure(self, service_name: str, error: Exception):
        """Record service failure and trigger recovery if needed."""
        if service_name not in self.service_status:
            self.register_service(service_name)
            
        self.failure_counts[service_name] += 1
        self.service_status[service_name]['last_error'] = str(error)
        
        logger.error(f"Service {service_name} failed: {error}")
        
        # Check if recovery is needed
        if self.failure_counts[service_name] >= self.max_failures:
            self.service_status[service_name]['healthy'] = False
            asyncio.create_task(self._attempt_recovery(service_name))
            
    async def _attempt_recovery(self, service_name: str):
        """Attempt to recover a failed service."""
        logger.info(f"Attempting recovery for service: {service_name}")
        
        # Wait before attempting recovery
        await asyncio.sleep(self.recovery_delay)
        
        try:
            if service_name in self.recovery_callbacks:
                # Call service-specific recovery
                await self.recovery_callbacks[service_name]()
                logger.info(f"Recovery callback completed for {service_name}")
            else:
                # Generic recovery - just reset status
                logger.info(f"No recovery callback for {service_name}, resetting status")
                
            # Reset failure count
            self.failure_counts[service_name] = 0
            self.service_status[service_name]['healthy'] = True
            logger.info(f"Service {service_name} recovered successfully")
            
        except Exception as e:
            logger.error(f"Recovery failed for {service_name}: {e}")
            # Schedule another recovery attempt
            await asyncio.sleep(self.recovery_delay * 2)
            asyncio.create_task(self._attempt_recovery(service_name))
            
    def is_healthy(self, service_name: str) -> bool:
        """Check if a service is healthy."""
        return self.service_status.get(service_name, {}).get('healthy', False)
        
    def get_status(self) -> Dict[str, Any]:
        """Get status of all tracked services."""
        return {
            name: {
                **status,
                'failure_count': self.failure_counts.get(name, 0)
            }
            for name, status in self.service_status.items()
        }

# Global health tracker
health_tracker = ServiceHealthTracker()

async def error_recovery_middleware(request: Request, call_next):
    """Middleware to handle errors and trigger recovery."""
    try:
        # Extract service name from path
        path_parts = request.url.path.split('/')
        service_name = path_parts[2] if len(path_parts) > 2 else 'unknown'
        
        # Process request
        response = await call_next(request)
        
        # Record success for 2xx responses
        if 200 <= response.status_code < 300:
            health_tracker.record_success(service_name)
            
        return response
        
    except Exception as e:
        # Log the full error
        logger.error(f"Error processing request {request.url.path}: {e}")
        logger.error(traceback.format_exc())
        
        # Record failure
        service_name = 'api_gateway'
        health_tracker.record_failure(service_name, e)
        
        # Return error response with CORS headers
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "message": str(e),
                "service": service_name,
                "healthy": health_tracker.is_healthy(service_name)
            },
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "*",
                "Access-Control-Allow-Headers": "*",
                "Access-Control-Allow-Credentials": "true"
            }
        )

def setup_recovery_callbacks():
    """Setup recovery callbacks for various services."""
    
    async def recover_capture_service():
        """Recover capture service."""
        try:
            from CAMF.services.capture import get_capture_service
            capture_service = get_capture_service()
            
            # Stop any active captures
            if hasattr(capture_service, 'stop_capture'):
                await capture_service.stop_capture()
                
            # Reset state
            if hasattr(capture_service, 'reset_state'):
                capture_service.reset_state()
                
            logger.info("Capture service recovered")
        except Exception as e:
            logger.error(f"Failed to recover capture service: {e}")
            raise
            
    async def recover_detector_service():
        """Recover detector framework."""
        try:
            from CAMF.services.detector_framework import get_detector_framework_service
            detector_framework = get_detector_framework_service()
            
            # Stop all active detectors
            if hasattr(detector_framework, 'disable_all_detectors'):
                detector_framework.disable_all_detectors()
                
            # Clear any stuck processing
            if hasattr(detector_framework, 'clear_processing_queue'):
                detector_framework.clear_processing_queue()
                
            # Refresh detector list
            if hasattr(detector_framework, 'refresh_detectors'):
                detector_framework.refresh_detectors()
                
            logger.info("Detector service recovered")
        except Exception as e:
            logger.error(f"Failed to recover detector service: {e}")
            raise
            
    async def recover_storage_service():
        """Recover storage service."""
        try:
            from CAMF.services.storage import get_storage_service
            storage_service = get_storage_service()
            
            # Reconnect to database if needed
            if hasattr(storage_service, 'reconnect'):
                storage_service.reconnect()
                
            logger.info("Storage service recovered")
        except Exception as e:
            logger.error(f"Failed to recover storage service: {e}")
            raise
            
    # Register services with recovery callbacks
    health_tracker.register_service('capture', recover_capture_service)
    health_tracker.register_service('detectors', recover_detector_service)
    health_tracker.register_service('storage', recover_storage_service)
    health_tracker.register_service('api_gateway', None)  # No specific recovery
    
    logger.info("Recovery callbacks registered")

async def periodic_health_check():
    """Periodically check service health."""
    while True:
        try:
            await asyncio.sleep(30)  # Check every 30 seconds
            
            # Check each service
            for service_name in list(health_tracker.service_status.keys()):
                try:
                    # Skip if recently checked
                    last_check = health_tracker.last_check_times.get(service_name, 0)
                    if time.time() - last_check < health_tracker.check_interval:
                        continue
                        
                    # Perform service-specific health check
                    if service_name == 'capture':
                        from CAMF.services.capture import get_capture_service
                        capture_service = get_capture_service()
                        # Simple check - service exists
                        if capture_service:
                            health_tracker.record_success(service_name)
                            
                    elif service_name == 'detectors':
                        from CAMF.services.detector_framework import get_detector_framework_service
                        detector_framework = get_detector_framework_service()
                        # Check detector list is accessible
                        detector_framework.list_installed_detectors()
                        health_tracker.record_success(service_name)
                        
                    elif service_name == 'storage':
                        from CAMF.services.storage import get_storage_service
                        storage_service = get_storage_service()
                        # Try a simple query
                        storage_service.get_all_projects()
                        health_tracker.record_success(service_name)
                        
                    health_tracker.last_check_times[service_name] = time.time()
                    
                except Exception as e:
                    health_tracker.record_failure(service_name, e)
                    
        except Exception as e:
            logger.error(f"Error in health check loop: {e}")
            await asyncio.sleep(60)  # Wait longer on error

def start_health_monitoring():
    """Start background health monitoring."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(periodic_health_check())
        logger.info("Health monitoring started")
    except RuntimeError:
        logger.warning("No event loop running - health monitoring will start later")
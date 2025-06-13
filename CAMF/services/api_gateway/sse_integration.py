"""
SSE integration for real-time event streaming.

This module provides integration points for Server-Sent Events (SSE)
for all service communications.
"""

import time
import logging
from typing import Dict, Any, List

from .sse_handler import sse_manager, broadcast_system_event, broadcast_to_channel, send_to_take

logger = logging.getLogger(__name__)


def setup_capture_sse(capture_service):
    """Setup SSE callbacks for capture service."""
    
    def sse_callback(message: Dict[str, Any]):
        """Forward capture service messages to SSE clients."""
        message_type = message.get('type', '')
        
        # Handle different message types
        if message_type == 'capture_status':
            # Forward status updates to take-specific channel
            take_id = message.get('data', {}).get('take_id')
            if take_id:
                # Send to take-specific channel
                send_to_take(take_id, message, event_type="capture_status")
                # Also send to general capture events channel
                broadcast_to_channel('capture_events', message, event_type="capture_status")
        
        elif message_type == 'capture_started':
            data = message.get('data', {})
            take_id = data.get('take_id')
            event_data = {
                'type': 'capture_started',
                'take_id': take_id,
                'source_type': data.get('source_type'),
                'timestamp': time.time()
            }
            broadcast_system_event('capture_started', event_data)
            if take_id:
                send_to_take(take_id, event_data, event_type="capture_started")
        
        elif message_type == 'capture_stopped':
            data = message.get('data', {})
            take_id = data.get('take_id')
            event_data = {
                'type': 'capture_stopped',
                'take_id': take_id,
                'frame_count': data.get('frame_count', 0),
                'duration': data.get('duration', 0),
                'timestamp': time.time()
            }
            broadcast_system_event('capture_stopped', event_data)
            if take_id:
                send_to_take(take_id, event_data, event_type="capture_stopped")
        
        elif message_type == 'source_disconnected':
            # Important event - broadcast to all
            broadcast_system_event('connection_lost', message.get('data', {}))
            broadcast_to_channel('capture_events', message, event_type="source_disconnected")
            
        elif message_type == 'capture_error':
            # Error events go to system channel
            broadcast_system_event('capture_error', message.get('data', {}))
            broadcast_to_channel('capture_events', message, event_type="capture_error")
            
        elif message_type == 'frame_captured':
            # Send frame captured events to capture channel with preview
            data = message.get('data', {})
            take_id = data.get('take_id')
            # Frame captured event for take
            if take_id:
                # Send to take-specific channel
                # Include the type in the data for frontend routing
                event_data = {
                    'type': 'frame_captured',
                    'take_id': take_id,
                    **data  # Include all the original data
                }
                send_to_take(take_id, event_data, event_type="frame_captured")
                # Also send to capture channel
                broadcast_to_channel('capture', event_data, event_type="frame_captured")
    
    # Register the SSE callback with capture service
    if hasattr(capture_service, 'add_sse_callback'):
        capture_service.add_sse_callback(sse_callback)
        logger.info("Capture SSE callback registered")
    else:
        logger.warning("Capture service does not support callbacks")


def setup_detector_sse(detector_framework):
    """Setup SSE callbacks for detector framework."""
    
    def detector_result_callback(results: List[Any]):
        """Send detector results via SSE."""
        try:
            for result in results:
                # Handle confidence as a float (not an object with .value)
                confidence_value = result.confidence if isinstance(result.confidence, (int, float)) else 0.0
                
                # Special handling for detector failures (confidence = -1.0)
                if confidence_value == -1.0:
                    event_type = 'detector_failure'
                    is_error = True
                else:
                    # Determine if this is an error or just a result
                    is_error = confidence_value > 0.5
                    event_type = 'detector_error' if is_error else 'detector_result'
                
                event_data = {
                    'detector_name': result.detector_name,
                    'frame_id': result.frame_id,
                    'frame_index': getattr(result, 'frame_index', None),
                    'take_id': getattr(result, 'take_id', None),
                    'confidence': confidence_value,
                    'description': result.description,
                    'bounding_boxes': getattr(result, 'bounding_boxes', []),
                    'severity': 'critical' if confidence_value > 0.8 else ('failure' if confidence_value == -1.0 else 'warning'),
                    'timestamp': time.time(),
                    'metadata': getattr(result, 'metadata', {})
                }
                
                # Send as system event if it's an error
                if is_error:
                    broadcast_system_event(event_type, event_data)
                
                # Always send to detector events channel
                broadcast_to_channel('detector_events', {
                    'type': event_type,
                    'data': event_data
                }, event_type=event_type)
                
                # Send to take-specific channel if available
                if hasattr(result, 'take_id') and result.take_id:
                    send_to_take(result.take_id, {
                        'type': event_type,
                        'data': event_data
                    }, event_type=event_type)
                    
        except Exception as e:
            logger.error(f"Error in detector SSE callback: {e}")
            # Send error notification
            broadcast_system_event('system_error', {
                'message': f'Error processing detector results: {str(e)}',
                'context': 'detector_callback',
                'timestamp': time.time()
            })
    
    # Register result callback
    detector_framework.add_result_callback(detector_result_callback)
    logger.info("Detector SSE callback registered")
    
    # Set up processing lifecycle callbacks
    processing_callbacks = setup_processing_sse()
    logger.info(f"Setting up processing callbacks: {processing_callbacks}")
    detector_framework.set_processing_callbacks(
        processing_started=processing_callbacks['processing_started'],
        processing_complete=processing_callbacks['processing_complete']
    )
    logger.info("Processing lifecycle callbacks registered")


def setup_session_sse():
    """Setup SSE callbacks for session events."""
    # Session management service has been moved to archive
    # This functionality is temporarily disabled
    logger.info("Session SSE callbacks disabled (service archived)")


def setup_performance_sse():
    """
    Setup SSE for performance monitoring.
    
    Note: Performance updates are handled via polling to prevent
    high-frequency events.
    """
    logger.info("Performance monitoring uses polling instead of SSE")


def setup_processing_sse():
    """Setup SSE for processing status updates."""
    
    def processing_started(take_id: int, detector_names: List[str]):
        """Notify when processing starts."""
        event_data = {
            'take_id': take_id,
            'detectors': detector_names,
            'timestamp': time.time()
        }
        broadcast_system_event('processing_started', event_data)
        send_to_take(take_id, {
            'type': 'processing_started',
            'data': event_data
        }, event_type="processing_started")
    
    def processing_complete(take_id: int, results_summary: Dict[str, Any]):
        """Notify when processing completes."""
        event_data = {
            'takeId': take_id,  # Frontend expects camelCase
            'summary': results_summary,
            'timestamp': time.time()
        }
        broadcast_system_event('processing_complete', event_data)
        send_to_take(take_id, {
            'type': 'processing_complete',
            'data': event_data
        }, event_type="processing_complete")
    
    # Return the callbacks for use by processing service
    return {
        'processing_started': processing_started,
        'processing_complete': processing_complete
    }


def setup_sse_integrations():
    """
    Set up all SSE integrations for real-time communication.
    
    This function should be called during API Gateway startup
    to set up all SSE integrations.
    """
    logger.info("Setting up SSE integrations...")
    
    try:
        # Get services
        from CAMF.services.capture import get_capture_service
        from CAMF.services.detector_framework import get_detector_framework_service
        
        # SSE manager is already initialized and doesn't need starting
        logger.info("SSE manager initialized")
        
        # Setup capture SSE
        try:
            capture_service = get_capture_service()
            setup_capture_sse(capture_service)
        except Exception as e:
            logger.error(f"Failed to setup capture SSE: {e}")
        
        # Setup detector SSE
        try:
            detector_framework = get_detector_framework_service()
            setup_detector_sse(detector_framework)
        except Exception as e:
            logger.error(f"Failed to setup detector SSE: {e}")
        
        # Setup session SSE
        try:
            setup_session_sse()
        except Exception as e:
            logger.error(f"Failed to setup session SSE: {e}")
        
        # Performance uses polling, no SSE needed
        setup_performance_sse()
        
        logger.info("SSE integrations setup completed successfully")
        
    except Exception as e:
        logger.error(f"Error during SSE setup: {e}")
        raise


# SSE Manager Adapter
class SSEManagerAdapter:
    """
    Adapter for SSE event broadcasting.
    
    Provides a clean interface for broadcasting events via SSE.
    """
    
    @staticmethod
    def queue_broadcast(message: Dict[str, Any], channel: str):
        """Queue a message for SSE broadcast."""
        # Extract event type if present
        event_type = message.get('type', 'message')
        
        # Route messages to appropriate SSE channels
        if channel == 'general':
            sse_manager.broadcast(message, 'system', event_type)
        elif channel.startswith('take_'):
            # Extract take ID and use dedicated function
            try:
                take_id = int(channel.split('_')[1])
                sse_manager.broadcast(message, f'take_{take_id}', event_type)
            except:
                sse_manager.broadcast(message, channel, event_type)
        else:
            sse_manager.broadcast(message, channel, event_type)
    
    @staticmethod
    def broadcast_system_event(event_type: str, data: Dict[str, Any]):
        """Broadcast a system event via SSE."""
        broadcast_system_event(event_type, data)


# Export the adapter as SSEManager for cleaner imports
SSEManager = SSEManagerAdapter


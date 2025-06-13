"""
Server-Sent Events (SSE) handler for real-time updates.
Fixed version that properly handles asyncio event loops.
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Dict, Optional, Set, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class SSEConnection:
    """Represents an active SSE connection."""
    
    def __init__(self, client_id: str, channels: Set[str]):
        self.client_id = client_id
        self.channels = channels
        self.connected_at = datetime.now()
        self.last_heartbeat = time.time()
        self.event_queue = asyncio.Queue(maxsize=100)  # Limit queue size
        self.active = True


class SSEConnectionManager:
    """Manages SSE connections and event distribution."""
    
    def __init__(self):
        self.connections: Dict[str, SSEConnection] = {}
        self.event_queues: Dict[str, asyncio.Queue] = {}
        self.channel_subscriptions: Dict[str, Set[str]] = defaultdict(set)
        
        # Broadcast queue for all events
        self.broadcast_queue = asyncio.Queue(maxsize=1000)
        
        # Metrics
        self.total_connections = 0
        self.total_events_sent = 0
        self.total_events_dropped = 0
        
        # Background task for event distribution
        self._distributor_task = None
        self._loop = None
        self._started = False
    
    async def start(self):
        """Start the event distributor in the current event loop."""
        if self._started:
            return
            
        try:
            # Get the current running loop
            self._loop = asyncio.get_running_loop()
            
            # Create the distributor task in the current loop
            self._distributor_task = asyncio.create_task(self._distribute_events())
            self._started = True
            logger.info("SSE event distributor started")
        except Exception as e:
            logger.error(f"Failed to start SSE distributor: {e}")
    
    async def _distribute_events(self):
        """Distribute events from broadcast queue to connections."""
        logger.info("SSE event distributor task running")
        
        while True:
            try:
                # Get event from broadcast queue
                event_data = await self.broadcast_queue.get()
                channel = event_data.get('channel', 'default')
                event = event_data.get('event')
                
                # Get subscribers for this channel
                subscribers = self.channel_subscriptions.get(channel, set()).copy()
                
                # Send to each subscriber
                disconnected = []
                for client_id in subscribers:
                    if client_id in self.event_queues:
                        try:
                            # Try to put event in client queue (non-blocking)
                            self.event_queues[client_id].put_nowait(event)
                            self.total_events_sent += 1
                        except asyncio.QueueFull:
                            # Queue is full, drop event
                            self.total_events_dropped += 1
                            logger.warning(f"Dropped event for client {client_id} - queue full")
                        except Exception as e:
                            logger.error(f"Error sending event to client {client_id}: {e}")
                            disconnected.append(client_id)
                
                # Clean up disconnected clients
                for client_id in disconnected:
                    self.disconnect(client_id)
            
            except asyncio.CancelledError:
                logger.info("SSE distributor task cancelled")
                break
            except RuntimeError as e:
                # Ignore event loop errors - they occur when events are sent from different threads
                if "attached to a different loop" not in str(e):
                    logger.error(f"Runtime error in event distributor: {e}")
                await asyncio.sleep(0.01)
            except Exception as e:
                logger.error(f"Error in event distributor: {e}")
                await asyncio.sleep(0.1)
    
    def connect(self, client_id: str, channels: Set[str] = None) -> 'SSEConnection':
        """Register a new SSE connection."""
        if client_id in self.connections:
            # Update channels for existing connection
            connection = self.connections[client_id]
            old_channels = connection.channels
            new_channels = channels or {'default'}
            
            # Update channel subscriptions
            for channel in old_channels - new_channels:
                self.channel_subscriptions[channel].discard(client_id)
            for channel in new_channels - old_channels:
                self.channel_subscriptions[channel].add(client_id)
            
            connection.channels = new_channels
            return connection
        
        # Create new connection
        channels = channels or {'default'}
        connection = SSEConnection(client_id, channels)
        
        self.connections[client_id] = connection
        self.event_queues[client_id] = connection.event_queue
        
        # Subscribe to channels
        for channel in channels:
            self.channel_subscriptions[channel].add(client_id)
        
        self.total_connections += 1
        logger.info(f"Client {client_id} connected to channels: {channels}")
        
        return connection
    
    def disconnect(self, client_id: str):
        """Disconnect a client and clean up resources."""
        if client_id not in self.connections:
            return
        
        connection = self.connections[client_id]
        connection.active = False
        
        # Unsubscribe from all channels
        for channel in connection.channels:
            self.channel_subscriptions[channel].discard(client_id)
        
        # Clean up
        del self.connections[client_id]
        del self.event_queues[client_id]
        
        logger.info(f"Client {client_id} disconnected")
    
    async def broadcast(self, event: str, data: Any = None, channel: str = 'default'):
        """Broadcast an event to all subscribers of a channel."""
        if not self._started:
            # Try to start if not already started
            await self.start()
            
        event_data = {
            'channel': channel,
            'event': {
                'event': event,
                'data': data,
                'timestamp': datetime.now().isoformat()
            }
        }
        
        try:
            # Put event in broadcast queue (non-blocking)
            self.broadcast_queue.put_nowait(event_data)
        except asyncio.QueueFull:
            logger.warning(f"Broadcast queue full, dropping event: {event}")
            self.total_events_dropped += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics."""
        return {
            'active_connections': len(self.connections),
            'total_connections': self.total_connections,
            'total_events_sent': self.total_events_sent,
            'total_events_dropped': self.total_events_dropped,
            'channels': {
                channel: len(subscribers) 
                for channel, subscribers in self.channel_subscriptions.items()
            }
        }
    
    async def cleanup(self):
        """Clean up resources."""
        if self._distributor_task:
            self._distributor_task.cancel()
            try:
                await self._distributor_task
            except asyncio.CancelledError:
                pass
        
        # Disconnect all clients
        for client_id in list(self.connections.keys()):
            self.disconnect(client_id)


# Global SSE manager instance
sse_manager = SSEConnectionManager()


# Synchronous wrappers for compatibility with non-async code
def broadcast_system_event(event_type: str, data: Dict[str, Any]):
    """Synchronous wrapper for broadcasting system events."""
    try:
        # Try to get the running loop
        loop = asyncio.get_running_loop()
        # Schedule the coroutine in the existing loop
        asyncio.run_coroutine_threadsafe(
            sse_manager.broadcast(event_type, data, channel='system'), 
            loop
        )
    except RuntimeError:
        # No running loop - this happens in sync contexts
        # Just queue the event directly if manager is started
        if sse_manager._started and sse_manager.broadcast_queue:
            event_data = {
                'channel': 'system',
                'event': {
                    'event': event_type,
                    'data': data,
                    'timestamp': datetime.now().isoformat()
                }
            }
            try:
                sse_manager.broadcast_queue.put_nowait(event_data)
            except:
                logger.warning(f"Failed to queue SSE event: {event_type}")


def broadcast_to_channel(channel: str, data: Dict[str, Any], event_type: str = 'message'):
    """Synchronous wrapper for broadcasting to a channel."""
    try:
        loop = asyncio.get_running_loop()
        asyncio.run_coroutine_threadsafe(
            sse_manager.broadcast(event_type, data, channel=channel), 
            loop
        )
    except RuntimeError:
        if sse_manager._started and sse_manager.broadcast_queue:
            event_data = {
                'channel': channel,
                'event': {
                    'event': event_type,
                    'data': data,
                    'timestamp': datetime.now().isoformat()
                }
            }
            try:
                sse_manager.broadcast_queue.put_nowait(event_data)
            except:
                logger.warning(f"Failed to queue SSE event to channel {channel}")


def send_to_take(take_id: int, data: Dict[str, Any], event_type: str = 'message'):
    """Synchronous wrapper for sending to a take."""
    channel = f'take_{take_id}'
    try:
        loop = asyncio.get_running_loop()
        asyncio.run_coroutine_threadsafe(
            sse_manager.broadcast(event_type, data, channel=channel), 
            loop
        )
    except RuntimeError:
        if sse_manager._started and sse_manager.broadcast_queue:
            event_data = {
                'channel': channel,
                'event': {
                    'event': event_type,
                    'data': data,
                    'timestamp': datetime.now().isoformat()
                }
            }
            try:
                sse_manager.broadcast_queue.put_nowait(event_data)
            except:
                logger.warning(f"Failed to queue SSE event to take {take_id}")


async def sse_endpoint(request, client_id: Optional[str] = None, channels: Optional[str] = None):
    """SSE endpoint handler for FastAPI."""
    from fastapi.responses import StreamingResponse
    
    # Generate client ID if not provided
    if not client_id:
        client_id = str(uuid.uuid4())
    
    # Parse channels
    channel_set = set()
    if channels:
        channel_set = set(channels.split(','))
    
    # Connect client
    connection = sse_manager.connect(client_id, channel_set)
    
    async def event_generator():
        """Generate SSE events for the client."""
        try:
            # Send initial connection event
            yield f"event: connected\ndata: {json.dumps({'client_id': client_id})}\n\n"
            
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
                    yield f"event: heartbeat\ndata: {json.dumps({'timestamp': time.time()})}\n\n"
                    connection.last_heartbeat = time.time()
                
        except asyncio.CancelledError:
            logger.info(f"SSE connection cancelled for client {client_id}")
        except Exception as e:
            logger.error(f"Error in SSE connection for client {client_id}: {e}")
        finally:
            # Disconnect client
            sse_manager.disconnect(client_id)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',  # Disable Nginx buffering
        }
    )
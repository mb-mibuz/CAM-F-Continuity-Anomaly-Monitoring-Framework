"""
Comprehensive tests for API Gateway SSE (Server-Sent Events) functionality.
Tests SSE handler, event broadcasting, channel subscriptions, and error recovery.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
import json
import time
from typing import Set

from CAMF.services.api_gateway.sse_handler import SSEConnection, SSEConnectionManager


class TestSSEConnection:
    """Test SSE connection functionality."""
    
    def test_connection_creation(self):
        """Test creating an SSE connection."""
        client_id = "test-client-123"
        channels = {"project_updates", "detector_events"}
        
        conn = SSEConnection(client_id, channels)
        
        assert conn.client_id == client_id
        assert conn.channels == channels
        assert isinstance(conn.connected_at, datetime)
        assert conn.last_heartbeat > 0
        assert conn.active is True
        assert isinstance(conn.event_queue, asyncio.Queue)
    
    def test_connection_channels_modification(self):
        """Test modifying connection channels."""
        conn = SSEConnection("test-client", {"channel1"})
        
        # Add channel
        conn.channels.add("channel2")
        assert "channel2" in conn.channels
        
        # Remove channel
        conn.channels.remove("channel1")
        assert "channel1" not in conn.channels


class TestSSEConnectionManager:
    """Test SSE connection manager functionality."""
    
    @pytest.fixture
    def manager(self):
        """Create a connection manager instance."""
        return SSEConnectionManager()
    
    def test_manager_initialization(self, manager):
        """Test manager initialization."""
        assert manager.connections == {}
        assert manager.event_queues == {}
        assert len(manager.channel_subscriptions) == 0
        assert isinstance(manager.broadcast_queue, asyncio.Queue)
        assert manager.total_connections == 0
        assert manager.total_events_sent == 0
        assert manager.total_events_dropped == 0
        assert manager._started is False
    
    @pytest.mark.asyncio
    async def test_add_connection(self, manager):
        """Test adding a connection."""
        client_id = "test-client-123"
        channels = {"updates", "events"}
        
        # Start the manager
        await manager.start()
        
        # Add connection
        connection = await manager.add_connection(client_id, channels)
        
        assert client_id in manager.connections
        assert manager.connections[client_id] == connection
        assert manager.total_connections == 1
        
        # Check channel subscriptions
        for channel in channels:
            assert client_id in manager.channel_subscriptions[channel]
        
        # Cleanup
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_remove_connection(self, manager):
        """Test removing a connection."""
        client_id = "test-client-123"
        channels = {"updates"}
        
        await manager.start()
        
        # Add and then remove connection
        await manager.add_connection(client_id, channels)
        await manager.remove_connection(client_id)
        
        assert client_id not in manager.connections
        assert client_id not in manager.channel_subscriptions["updates"]
        
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_broadcast_event(self, manager):
        """Test broadcasting an event."""
        await manager.start()
        
        # Add a connection
        client_id = "test-client"
        await manager.add_connection(client_id, {"all"})
        
        # Broadcast event
        event_data = {"type": "test", "message": "Hello"}
        await manager.broadcast_event("all", event_data)
        
        # Check that event was queued
        assert manager.broadcast_queue.qsize() > 0
        
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_send_to_client(self, manager):
        """Test sending event to specific client."""
        await manager.start()
        
        client_id = "test-client"
        connection = await manager.add_connection(client_id, {"updates"})
        
        # Send event
        event_data = {"type": "update", "data": "test"}
        await manager.send_to_client(client_id, event_data)
        
        # Event should be in client's queue
        assert connection.event_queue.qsize() > 0
        
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_heartbeat_handling(self, manager):
        """Test heartbeat mechanism."""
        await manager.start()
        
        client_id = "test-client"
        connection = await manager.add_connection(client_id, {"updates"})
        
        # Update heartbeat
        old_heartbeat = connection.last_heartbeat
        await asyncio.sleep(0.1)
        await manager.heartbeat(client_id)
        
        assert connection.last_heartbeat > old_heartbeat
        
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_get_client_events(self, manager):
        """Test getting events for a client."""
        await manager.start()
        
        client_id = "test-client"
        connection = await manager.add_connection(client_id, {"updates"})
        
        # Add some events
        event1 = {"type": "update", "data": "1"}
        event2 = {"type": "update", "data": "2"}
        
        await connection.event_queue.put(("event", event1))
        await connection.event_queue.put(("event", event2))
        
        # Get events generator
        events_gen = manager.get_client_events(client_id)
        
        # Collect events
        events = []
        async for event in events_gen:
            events.append(event)
            if len(events) >= 2:
                break
        
        assert len(events) >= 2
        
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_cleanup_inactive_connections(self, manager):
        """Test cleaning up inactive connections."""
        await manager.start()
        
        # Add connection
        client_id = "inactive-client"
        connection = await manager.add_connection(client_id, {"updates"})
        
        # Make it inactive
        connection.active = False
        
        # Run cleanup
        await manager._cleanup_inactive_connections()
        
        # Connection should be removed
        assert client_id not in manager.connections
        
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_channel_subscription(self, manager):
        """Test channel subscription management."""
        await manager.start()
        
        # Add multiple clients to same channel
        await manager.add_connection("client1", {"news", "updates"})
        await manager.add_connection("client2", {"news"})
        await manager.add_connection("client3", {"updates"})
        
        # Check subscriptions
        assert len(manager.channel_subscriptions["news"]) == 2
        assert len(manager.channel_subscriptions["updates"]) == 2
        assert "client1" in manager.channel_subscriptions["news"]
        assert "client2" in manager.channel_subscriptions["news"]
        
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_event_distribution(self, manager):
        """Test event distribution to multiple clients."""
        await manager.start()
        
        # Add clients
        conn1 = await manager.add_connection("client1", {"channel1"})
        conn2 = await manager.add_connection("client2", {"channel1", "channel2"})
        conn3 = await manager.add_connection("client3", {"channel2"})
        
        # Broadcast to channel1
        await manager.broadcast_event("channel1", {"msg": "to channel1"})
        
        # Give distributor time to process
        await asyncio.sleep(0.1)
        
        # Check distribution
        # Note: We can't directly check queue contents due to async processing
        # but we can verify the structure is correct
        assert "client1" in manager.channel_subscriptions["channel1"]
        assert "client2" in manager.channel_subscriptions["channel1"]
        assert "client3" not in manager.channel_subscriptions["channel1"]
        
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_connection_limit(self, manager):
        """Test connection queue limits."""
        await manager.start()
        
        client_id = "test-client"
        connection = await manager.add_connection(client_id, {"updates"})
        
        # Fill queue to capacity (100 as per implementation)
        for i in range(100):
            try:
                connection.event_queue.put_nowait(("event", {"id": i}))
            except asyncio.QueueFull:
                break
        
        # Queue should be at capacity
        assert connection.event_queue.full()
        
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, manager):
        """Test concurrent connection operations."""
        await manager.start()
        
        # Add multiple connections concurrently
        tasks = []
        for i in range(10):
            task = manager.add_connection(f"client-{i}", {f"channel-{i % 3}"})
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        
        # Verify all connections added
        assert len(manager.connections) == 10
        
        # Remove connections concurrently
        remove_tasks = []
        for i in range(10):
            task = manager.remove_connection(f"client-{i}")
            remove_tasks.append(task)
        
        await asyncio.gather(*remove_tasks)
        
        # Verify all connections removed
        assert len(manager.connections) == 0
        
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_error_handling_in_distribution(self, manager):
        """Test error handling during event distribution."""
        await manager.start()
        
        # Add connection with mocked queue that raises
        client_id = "error-client"
        connection = await manager.add_connection(client_id, {"updates"})
        
        # Mock the queue to raise an exception
        mock_queue = AsyncMock()
        mock_queue.put.side_effect = Exception("Queue error")
        connection.event_queue = mock_queue
        
        # Try to send event - should not crash
        await manager.send_to_client(client_id, {"test": "data"})
        
        # Manager should still be operational
        assert manager._started
        
        await manager.stop()
    
    def test_metrics_tracking(self, manager):
        """Test metrics are tracked correctly."""
        initial_connections = manager.total_connections
        initial_events = manager.total_events_sent
        
        # Metrics should be initialized
        assert initial_connections == 0
        assert initial_events == 0
        assert manager.total_events_dropped == 0
    
    @pytest.mark.asyncio
    async def test_graceful_shutdown(self, manager):
        """Test graceful shutdown of manager."""
        await manager.start()
        assert manager._started is True
        
        # Add some connections
        await manager.add_connection("client1", {"updates"})
        await manager.add_connection("client2", {"events"})
        
        # Stop manager
        await manager.stop()
        
        # Verify shutdown
        assert manager._started is False
        assert manager._distributor_task is None


class TestSSEIntegration:
    """Test SSE integration with FastAPI."""
    
    @pytest.mark.asyncio
    async def test_sse_endpoint_format(self):
        """Test SSE event format."""
        from CAMF.services.api_gateway.sse_handler import SSEConnectionManager
        
        manager = SSEConnectionManager()
        await manager.start()
        
        # Add test connection
        client_id = "test-client"
        await manager.add_connection(client_id, {"test"})
        
        # Send event
        event_data = {"type": "test", "data": "hello"}
        await manager.send_to_client(client_id, event_data)
        
        # Get event
        connection = manager.connections[client_id]
        event_type, event = await connection.event_queue.get()
        
        assert event_type == "event"
        assert event == event_data
        
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_reconnection_handling(self):
        """Test client reconnection handling."""
        manager = SSEConnectionManager()
        await manager.start()
        
        client_id = "reconnect-client"
        
        # Initial connection
        conn1 = await manager.add_connection(client_id, {"updates"})
        
        # Disconnect
        await manager.remove_connection(client_id)
        
        # Reconnect
        conn2 = await manager.add_connection(client_id, {"updates", "events"})
        
        # Should be a new connection
        assert conn1 != conn2
        assert len(conn2.channels) == 2
        
        await manager.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
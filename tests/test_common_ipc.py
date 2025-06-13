"""
Comprehensive tests for common IPC (Inter-Process Communication) modules.
Tests transport layer, patterns, registry, and communication protocols.
"""

import pytest
import asyncio
import json
import time
import multiprocessing
import threading
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import queue
import pickle
import tempfile
import os

from CAMF.common.ipc.base import IPCMessage, IPCChannel, IPCError
from CAMF.common.ipc.transport import (
    Transport, QueueTransport, PipeTransport, 
    SharedMemoryTransport, SocketTransport
)
from CAMF.common.ipc.patterns import (
    RequestResponse, PublishSubscribe, Pipeline,
    MessageRouter, LoadBalancer
)
from CAMF.common.ipc.registry import ServiceRegistry, ServiceDiscovery


class TestIPCBase:
    """Test base IPC functionality."""
    
    def test_ipc_message_creation(self):
        """Test creating IPC messages."""
        message = IPCMessage(
            id="msg_123",
            type="request",
            source="service_a",
            destination="service_b",
            payload={"data": "test"},
            timestamp=time.time()
        )
        
        assert message.id == "msg_123"
        assert message.type == "request"
        assert message.payload["data"] == "test"
        assert message.timestamp > 0
    
    def test_ipc_message_serialization(self):
        """Test message serialization/deserialization."""
        original = IPCMessage(
            id="msg_123",
            type="request",
            payload={"complex": {"nested": ["data", 123, True]}}
        )
        
        # Serialize
        serialized = original.serialize()
        assert isinstance(serialized, bytes)
        
        # Deserialize
        deserialized = IPCMessage.deserialize(serialized)
        assert deserialized.id == original.id
        assert deserialized.payload == original.payload
    
    def test_ipc_channel_operations(self):
        """Test IPC channel operations."""
        channel = IPCChannel(name="test_channel")
        
        # Send message
        message = IPCMessage(id="1", payload={"test": True})
        channel.send(message)
        
        # Receive message
        received = channel.receive(timeout=1.0)
        assert received is not None
        assert received.id == "1"
        assert received.payload["test"] is True
        
        # Non-blocking receive
        assert channel.receive_nowait() is None
    
    def test_ipc_error_handling(self):
        """Test IPC error types and handling."""
        # Connection error
        conn_error = IPCError.connection_error("Failed to connect")
        assert conn_error.error_type == "connection"
        assert "Failed to connect" in str(conn_error)
        
        # Timeout error
        timeout_error = IPCError.timeout_error("Operation timed out", timeout=5.0)
        assert timeout_error.error_type == "timeout"
        assert timeout_error.details["timeout"] == 5.0
        
        # Serialization error
        ser_error = IPCError.serialization_error("Invalid data")
        assert ser_error.error_type == "serialization"


class TestTransportLayer:
    """Test different transport implementations."""
    
    def test_queue_transport(self):
        """Test queue-based transport."""
        transport = QueueTransport()
        
        # Send message
        message = IPCMessage(id="1", payload={"data": "test"})
        transport.send(message)
        
        # Receive message
        received = transport.receive(timeout=1.0)
        assert received.id == "1"
        assert received.payload["data"] == "test"
        
        # Test queue size
        for i in range(5):
            transport.send(IPCMessage(id=str(i)))
        assert transport.size() == 5
    
    def test_pipe_transport(self):
        """Test pipe-based transport."""
        # Create parent-child pipe transport
        parent_transport, child_transport = PipeTransport.create_pair()
        
        def child_process(transport):
            # Receive in child
            msg = transport.receive()
            # Send response
            response = IPCMessage(
                id=f"{msg.id}_response",
                payload={"received": msg.payload}
            )
            transport.send(response)
        
        # Start child process
        p = multiprocessing.Process(target=child_process, args=(child_transport,))
        p.start()
        
        # Send from parent
        parent_transport.send(IPCMessage(id="1", payload={"test": True}))
        
        # Receive response
        response = parent_transport.receive(timeout=2.0)
        assert response.id == "1_response"
        assert response.payload["received"]["test"] is True
        
        p.join()
    
    def test_shared_memory_transport(self):
        """Test shared memory transport."""
        # Create shared memory transports
        transport1 = SharedMemoryTransport(name="test_shm", size=1024*1024)
        transport2 = SharedMemoryTransport(name="test_shm", create=False)
        
        # Send large data
        large_data = {"array": list(range(10000))}
        message = IPCMessage(id="1", payload=large_data)
        
        transport1.send(message)
        received = transport2.receive()
        
        assert received.id == "1"
        assert len(received.payload["array"]) == 10000
        
        # Cleanup
        transport1.cleanup()
    
    def test_socket_transport(self):
        """Test socket-based transport."""
        # Server transport
        server = SocketTransport.create_server("localhost", 0)  # Random port
        port = server.get_port()
        
        # Client transport
        client = SocketTransport.create_client("localhost", port)
        
        # Exchange messages
        client.send(IPCMessage(id="1", payload={"from": "client"}))
        
        # Server receives
        server_msg = server.receive(timeout=1.0)
        assert server_msg.payload["from"] == "client"
        
        # Server responds
        server.send(IPCMessage(id="2", payload={"from": "server"}))
        
        # Client receives
        client_msg = client.receive(timeout=1.0)
        assert client_msg.payload["from"] == "server"
        
        # Cleanup
        client.close()
        server.close()
    
    def test_transport_reliability(self):
        """Test transport reliability features."""
        transport = QueueTransport(reliable=True)
        
        # Send with acknowledgment
        msg_id = transport.send_reliable(
            IPCMessage(id="1", payload={"important": True})
        )
        
        # Simulate acknowledgment
        transport.acknowledge(msg_id)
        
        # Check delivery status
        assert transport.is_delivered(msg_id) is True
        
        # Test retransmission for unacknowledged
        msg_id2 = transport.send_reliable(
            IPCMessage(id="2", payload={"data": "test"}),
            max_retries=3,
            retry_delay=0.1
        )
        
        # Should retry automatically
        time.sleep(0.5)
        assert transport.get_retry_count(msg_id2) > 0


class TestCommunicationPatterns:
    """Test communication patterns."""
    
    @pytest.mark.asyncio
    async def test_request_response_pattern(self):
        """Test request-response pattern."""
        # Create pattern
        pattern = RequestResponse()
        
        # Server handler
        async def handler(request):
            return IPCMessage(
                id=f"{request.id}_response",
                payload={"result": request.payload["value"] * 2}
            )
        
        pattern.set_handler(handler)
        
        # Client request
        request = IPCMessage(id="1", payload={"value": 21})
        response = await pattern.request(request, timeout=1.0)
        
        assert response.payload["result"] == 42
    
    def test_publish_subscribe_pattern(self):
        """Test publish-subscribe pattern."""
        pubsub = PublishSubscribe()
        
        # Subscribers
        received1 = []
        received2 = []
        
        def subscriber1(msg):
            received1.append(msg)
        
        def subscriber2(msg):
            if msg.payload.get("important"):
                received2.append(msg)
        
        # Subscribe
        pubsub.subscribe("topic1", subscriber1)
        pubsub.subscribe("topic1", subscriber2)
        
        # Publish messages
        pubsub.publish("topic1", IPCMessage(id="1", payload={"data": "test"}))
        pubsub.publish("topic1", IPCMessage(id="2", payload={"important": True}))
        
        assert len(received1) == 2
        assert len(received2) == 1
        assert received2[0].payload["important"] is True
    
    def test_pipeline_pattern(self):
        """Test pipeline pattern."""
        pipeline = Pipeline()
        
        # Add stages
        def stage1(msg):
            msg.payload["stage1"] = True
            return msg
        
        def stage2(msg):
            msg.payload["stage2"] = True
            msg.payload["value"] = msg.payload.get("value", 0) * 2
            return msg
        
        def stage3(msg):
            msg.payload["stage3"] = True
            msg.payload["value"] = msg.payload.get("value", 0) + 10
            return msg
        
        pipeline.add_stage(stage1)
        pipeline.add_stage(stage2)
        pipeline.add_stage(stage3)
        
        # Process message
        input_msg = IPCMessage(id="1", payload={"value": 5})
        output_msg = pipeline.process(input_msg)
        
        assert output_msg.payload["stage1"] is True
        assert output_msg.payload["stage2"] is True
        assert output_msg.payload["stage3"] is True
        assert output_msg.payload["value"] == 20  # (5 * 2) + 10
    
    def test_message_router(self):
        """Test message routing."""
        router = MessageRouter()
        
        # Define routes
        router.add_route(
            lambda msg: msg.type == "typeA",
            "serviceA"
        )
        router.add_route(
            lambda msg: msg.payload.get("priority") == "high",
            "priorityService"
        )
        router.add_route(
            lambda msg: True,  # Default route
            "defaultService"
        )
        
        # Route messages
        msg1 = IPCMessage(id="1", type="typeA", payload={})
        assert router.route(msg1) == "serviceA"
        
        msg2 = IPCMessage(id="2", type="typeB", payload={"priority": "high"})
        assert router.route(msg2) == "priorityService"
        
        msg3 = IPCMessage(id="3", type="typeC", payload={})
        assert router.route(msg3) == "defaultService"
    
    def test_load_balancer(self):
        """Test load balancing."""
        balancer = LoadBalancer(strategy="round_robin")
        
        # Add services
        services = ["service1", "service2", "service3"]
        for service in services:
            balancer.add_service(service)
        
        # Test round-robin
        destinations = []
        for i in range(6):
            msg = IPCMessage(id=str(i), payload={})
            dest = balancer.get_destination(msg)
            destinations.append(dest)
        
        # Should cycle through services
        assert destinations == ["service1", "service2", "service3"] * 2
        
        # Test weighted load balancing
        weighted_balancer = LoadBalancer(strategy="weighted")
        weighted_balancer.add_service("service1", weight=3)
        weighted_balancer.add_service("service2", weight=1)
        
        # Should favor service1
        destinations = []
        for i in range(8):
            msg = IPCMessage(id=str(i), payload={})
            dest = weighted_balancer.get_destination(msg)
            destinations.append(dest)
        
        service1_count = destinations.count("service1")
        assert service1_count >= 5  # Should get most requests


class TestServiceRegistry:
    """Test service registry and discovery."""
    
    @pytest.fixture
    def service_registry(self):
        """Create service registry."""
        return ServiceRegistry()
    
    def test_service_registration(self, service_registry):
        """Test registering services."""
        # Register service
        service_info = {
            "name": "StorageService",
            "version": "1.0.0",
            "endpoint": "ipc://storage",
            "capabilities": ["store", "retrieve", "query"],
            "metadata": {"max_connections": 100}
        }
        
        service_registry.register("storage", service_info)
        
        # Lookup service
        found = service_registry.lookup("storage")
        assert found is not None
        assert found["name"] == "StorageService"
        assert "store" in found["capabilities"]
    
    def test_service_discovery(self, service_registry):
        """Test service discovery by capabilities."""
        # Register multiple services
        services = [
            {
                "id": "storage1",
                "info": {
                    "name": "StorageService1",
                    "capabilities": ["store", "retrieve"]
                }
            },
            {
                "id": "storage2",
                "info": {
                    "name": "StorageService2",
                    "capabilities": ["store", "query"]
                }
            },
            {
                "id": "detector1",
                "info": {
                    "name": "DetectorService",
                    "capabilities": ["detect", "analyze"]
                }
            }
        ]
        
        for service in services:
            service_registry.register(service["id"], service["info"])
        
        # Discover by capability
        storage_services = service_registry.discover_by_capability("store")
        assert len(storage_services) == 2
        
        query_services = service_registry.discover_by_capability("query")
        assert len(query_services) == 1
        assert query_services[0]["name"] == "StorageService2"
    
    def test_service_health_monitoring(self, service_registry):
        """Test service health monitoring."""
        # Register service with health endpoint
        service_registry.register("api", {
            "name": "APIGateway",
            "health_endpoint": "ipc://api/health"
        })
        
        # Update health status
        service_registry.update_health("api", {
            "status": "healthy",
            "uptime": 3600,
            "load": 0.7
        })
        
        # Check health
        health = service_registry.get_health("api")
        assert health["status"] == "healthy"
        
        # Mark unhealthy
        service_registry.mark_unhealthy("api", reason="High error rate")
        health = service_registry.get_health("api")
        assert health["status"] == "unhealthy"
    
    def test_service_versioning(self, service_registry):
        """Test service version management."""
        # Register multiple versions
        service_registry.register("detector_v1", {
            "name": "Detector",
            "version": "1.0.0",
            "deprecated": False
        })
        
        service_registry.register("detector_v2", {
            "name": "Detector",
            "version": "2.0.0",
            "deprecated": False
        })
        
        service_registry.register("detector_v0", {
            "name": "Detector",
            "version": "0.9.0",
            "deprecated": True
        })
        
        # Find latest version
        latest = service_registry.find_latest_version("Detector")
        assert latest["version"] == "2.0.0"
        
        # Find compatible versions
        compatible = service_registry.find_compatible_versions(
            "Detector",
            min_version="1.0.0"
        )
        assert len(compatible) == 2
        assert all(v["version"] >= "1.0.0" for v in compatible)
    
    def test_distributed_registry(self):
        """Test distributed service registry."""
        # Create registry with replication
        primary = ServiceRegistry(role="primary")
        replica1 = ServiceRegistry(role="replica")
        replica2 = ServiceRegistry(role="replica")
        
        # Connect replicas
        primary.add_replica(replica1)
        primary.add_replica(replica2)
        
        # Register on primary
        primary.register("service1", {"name": "Service1"})
        
        # Should replicate to replicas
        time.sleep(0.1)  # Allow replication
        
        assert replica1.lookup("service1") is not None
        assert replica2.lookup("service1") is not None


class TestIPCReliability:
    """Test IPC reliability features."""
    
    def test_message_acknowledgment(self):
        """Test message acknowledgment system."""
        transport = QueueTransport()
        
        # Send with ack required
        msg = IPCMessage(id="1", payload={"data": "important"}, require_ack=True)
        transport.send(msg)
        
        # Receiver gets message
        received = transport.receive()
        assert received.require_ack is True
        
        # Send acknowledgment
        ack = IPCMessage(
            id=f"{received.id}_ack",
            type="ack",
            correlation_id=received.id
        )
        transport.send(ack)
        
        # Sender receives ack
        ack_received = transport.receive()
        assert ack_received.type == "ack"
        assert ack_received.correlation_id == "1"
    
    def test_message_ordering(self):
        """Test message ordering guarantees."""
        transport = QueueTransport(ordered=True)
        
        # Send messages with sequence numbers
        messages = []
        for i in range(10):
            msg = IPCMessage(
                id=str(i),
                payload={"seq": i},
                sequence_number=i
            )
            messages.append(msg)
            transport.send(msg)
        
        # Receive should maintain order
        received = []
        for _ in range(10):
            msg = transport.receive()
            received.append(msg.payload["seq"])
        
        assert received == list(range(10))
    
    def test_duplicate_detection(self):
        """Test duplicate message detection."""
        transport = QueueTransport(deduplicate=True)
        
        # Send same message multiple times
        msg = IPCMessage(id="1", payload={"data": "test"})
        
        for _ in range(5):
            transport.send(msg)
        
        # Should only receive once
        received_count = 0
        while True:
            try:
                transport.receive(timeout=0.1)
                received_count += 1
            except:
                break
        
        assert received_count == 1
    
    def test_circuit_breaker_transport(self):
        """Test circuit breaker for unreliable transports."""
        # Create transport with circuit breaker
        transport = SocketTransport(
            host="localhost",
            port=9999,  # Non-existent
            circuit_breaker=True,
            failure_threshold=3,
            reset_timeout=1.0
        )
        
        # Should fail and open circuit
        failures = 0
        for _ in range(5):
            try:
                transport.send(IPCMessage(id="1", payload={}))
            except:
                failures += 1
        
        assert failures >= 3
        assert transport.is_circuit_open() is True
        
        # Should fail fast while circuit is open
        start = time.time()
        try:
            transport.send(IPCMessage(id="2", payload={}))
        except IPCError as e:
            assert e.error_type == "circuit_open"
        duration = time.time() - start
        assert duration < 0.1  # Failed fast
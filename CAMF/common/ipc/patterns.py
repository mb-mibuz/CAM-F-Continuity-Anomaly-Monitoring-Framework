"""
Common ZeroMQ patterns for IPC communication.

Provides high-level abstractions for common communication patterns.
"""

import zmq
import time
import threading
import logging
from typing import Dict, List, Callable, Optional, Any
from collections import defaultdict

from .base import IPCMessage, IPCServer, IPCClient, SerializationType
from .transport import get_transport_url, get_optimal_transport
from .registry import get_registry

logger = logging.getLogger(__name__)


class PubSubBroker:
    """
    High-performance publish-subscribe broker.
    
    Optimized for distributing frames and detector results.
    """
    
    def __init__(self, service_name: str, context: Optional[zmq.Context] = None):
        self.service_name = service_name
        self.context = context or zmq.Context.instance()
        self.transport = get_optimal_transport()
        
        # Publisher side
        self.pub_socket = None
        self.pub_url = None
        
        # Subscriber management
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self.sub_sockets: Dict[str, zmq.Socket] = {}
        self._running = False
        self._threads: List[threading.Thread] = []
    
    def start_publisher(self, endpoint: str = "pub") -> str:
        """Start publisher and return URL."""
        self.pub_url = get_transport_url(self.service_name, endpoint, self.transport)
        
        self.pub_socket = self.context.socket(zmq.PUB)
        self.pub_socket.bind(self.pub_url)
        
        # Register with service registry
        registry = get_registry()
        registry.register_endpoint(
            self.service_name, endpoint, self.pub_url, 
            self.transport, "PUB"
        )
        
        logger.info(f"{self.service_name} publisher started at {self.pub_url}")
        return self.pub_url
    
    def publish(self, topic: str, data: Any, msg_type: str = "data"):
        """Publish data to a topic."""
        if not self.pub_socket:
            raise RuntimeError("Publisher not started")
        
        message = IPCMessage(msg_type=msg_type, data=data)
        
        # Send with topic prefix
        topic_bytes = topic.encode('utf-8') + b' '
        data_bytes = message.serialize(SerializationType.MSGPACK)
        
        try:
            self.pub_socket.send(topic_bytes + data_bytes, zmq.DONTWAIT)
        except zmq.Again:
            logger.warning(f"Publisher queue full for topic {topic}")
    
    def subscribe(self, service: str, endpoint: str, topics: List[str], 
                  handler: Callable):
        """Subscribe to topics from a service."""
        # Discover service endpoint
        registry = get_registry()
        endpoint_info = registry.get_endpoint(service, endpoint)
        
        if not endpoint_info:
            raise ValueError(f"Service endpoint not found: {service}:{endpoint}")
        
        # Create or reuse subscriber socket
        if endpoint_info.url not in self.sub_sockets:
            sub_socket = self.context.socket(zmq.SUB)
            sub_socket.connect(endpoint_info.url)
            
            # Subscribe to topics
            for topic in topics:
                sub_socket.setsockopt_string(zmq.SUBSCRIBE, topic)
            
            self.sub_sockets[endpoint_info.url] = sub_socket
            
            # Start receiver thread
            self._start_receiver(endpoint_info.url)
        
        # Register handler
        for topic in topics:
            self.subscribers[topic].append(handler)
    
    def _start_receiver(self, url: str):
        """Start receiver thread for a subscription."""
        def receive_loop():
            socket = self.sub_sockets[url]
            self._running = True
            
            while self._running:
                try:
                    if socket.poll(timeout=100):
                        data = socket.recv()
                        
                        # Extract topic
                        space_idx = data.find(b' ')
                        if space_idx > 0:
                            topic = data[:space_idx].decode('utf-8')
                            msg_data = data[space_idx + 1:]
                            
                            # Deserialize message
                            message = IPCMessage.deserialize(msg_data, SerializationType.MSGPACK)
                            
                            # Call handlers
                            for handler in self.subscribers.get(topic, []):
                                try:
                                    handler(topic, message)
                                except Exception as e:
                                    logger.error(f"Error in subscription handler: {e}")
                
                except Exception as e:
                    logger.error(f"Error in receiver loop: {e}")
        
        thread = threading.Thread(target=receive_loop, daemon=True)
        thread.start()
        self._threads.append(thread)
    
    def close(self):
        """Close all sockets."""
        self._running = False
        
        # Wait for threads
        for thread in self._threads:
            thread.join(timeout=1.0)
        
        # Close sockets
        if self.pub_socket:
            self.pub_socket.close()
        
        for socket in self.sub_sockets.values():
            socket.close()


class RequestReplyBroker:
    """
    Request-Reply broker for command handling.
    
    Provides RPC-like semantics with high performance.
    """
    
    def __init__(self, service_name: str, context: Optional[zmq.Context] = None):
        self.service_name = service_name
        self.context = context or zmq.Context.instance()
        self.transport = get_optimal_transport()
        
        # Server components
        self.server: Optional[IPCServer] = None
        self.handlers: Dict[str, Callable] = {}
        
        # Client components  
        self.clients: Dict[str, IPCClient] = {}
    
    def start_server(self, endpoint: str = "rpc") -> str:
        """Start RPC server."""
        url = get_transport_url(self.service_name, endpoint, self.transport)
        
        self.server = IPCServer(self.service_name, self.context)
        self.server.bind_reply(url, self._handle_request)
        
        # Register with service registry
        registry = get_registry()
        registry.register_endpoint(
            self.service_name, endpoint, url,
            self.transport, "REP"
        )
        
        logger.info(f"{self.service_name} RPC server started at {url}")
        return url
    
    def register_handler(self, method: str, handler: Callable):
        """Register a method handler."""
        self.handlers[method] = handler
    
    def _handle_request(self, message: IPCMessage) -> IPCMessage:
        """Handle incoming RPC request."""
        method = message.msg_type
        
        if method not in self.handlers:
            return IPCMessage(
                msg_type="error",
                data={"error": f"Unknown method: {method}"}
            )
        
        try:
            # Call handler
            result = self.handlers[method](message.data)
            
            return IPCMessage(
                msg_type="result",
                data=result
            )
        
        except Exception as e:
            logger.error(f"Error handling RPC {method}: {e}")
            return IPCMessage(
                msg_type="error", 
                data={"error": str(e)}
            )
    
    def call(self, service: str, method: str, data: Any = None,
             timeout: int = 5000) -> Any:
        """Call remote method."""
        # Get or create client
        if service not in self.clients:
            # Discover service
            registry = get_registry()
            endpoint = registry.get_endpoint(service, "rpc")
            
            if not endpoint:
                raise ValueError(f"Service not found: {service}")
            
            client = IPCClient(f"{self.service_name}_client", self.context)
            client.connect_req(endpoint.url)
            self.clients[service] = client
        
        # Make request
        request = IPCMessage(msg_type=method, data=data)
        response = self.clients[service].request(
            self.clients[service].sockets[f"req_{endpoint.url}"],
            request,
            timeout
        )
        
        if response.msg_type == "error":
            raise RuntimeError(f"RPC error: {response.data}")
        
        return response.data
    
    def close(self):
        """Close broker."""
        if self.server:
            self.server.close()
        
        for client in self.clients.values():
            client.close()


class PushPullBroker:
    """
    Push-Pull broker for work distribution.
    
    Used for distributing frames to multiple detectors.
    """
    
    def __init__(self, service_name: str, context: Optional[zmq.Context] = None):
        self.service_name = service_name
        self.context = context or zmq.Context.instance()
        self.transport = get_optimal_transport()
        
        # Ventilator (PUSH) side
        self.push_socket = None
        self.push_url = None
        
        # Worker (PULL) side
        self.pull_socket = None
        self.worker_handler = None
        self._worker_thread = None
        self._running = False
    
    def start_ventilator(self, endpoint: str = "tasks") -> str:
        """Start task ventilator (PUSH socket)."""
        self.push_url = get_transport_url(self.service_name, endpoint, self.transport)
        
        self.push_socket = self.context.socket(zmq.PUSH)
        self.push_socket.bind(self.push_url)
        
        # Register with service registry
        registry = get_registry()
        registry.register_endpoint(
            self.service_name, endpoint, self.push_url,
            self.transport, "PUSH"
        )
        
        logger.info(f"{self.service_name} ventilator started at {self.push_url}")
        return self.push_url
    
    def push_task(self, task_data: Any, task_type: str = "task"):
        """Push a task to workers."""
        if not self.push_socket:
            raise RuntimeError("Ventilator not started")
        
        message = IPCMessage(msg_type=task_type, data=task_data)
        
        try:
            self.push_socket.send(message.serialize(SerializationType.MSGPACK), zmq.DONTWAIT)
        except zmq.Again:
            logger.warning("Task queue full")
            # Could implement backpressure here
    
    def start_worker(self, service: str, endpoint: str, handler: Callable):
        """Start worker to process tasks."""
        # Discover service
        registry = get_registry()
        endpoint_info = registry.get_endpoint(service, endpoint)
        
        if not endpoint_info:
            raise ValueError(f"Service endpoint not found: {service}:{endpoint}")
        
        self.pull_socket = self.context.socket(zmq.PULL)
        self.pull_socket.connect(endpoint_info.url)
        self.worker_handler = handler
        
        # Start worker thread
        self._start_worker_thread()
    
    def _start_worker_thread(self):
        """Start thread to process tasks."""
        def worker_loop():
            self._running = True
            
            while self._running:
                try:
                    if self.pull_socket.poll(timeout=100):
                        data = self.pull_socket.recv()
                        message = IPCMessage.deserialize(data, SerializationType.MSGPACK)
                        
                        # Process task
                        try:
                            self.worker_handler(message)
                        except Exception as e:
                            logger.error(f"Error processing task: {e}")
                
                except Exception as e:
                    logger.error(f"Error in worker loop: {e}")
        
        self._worker_thread = threading.Thread(target=worker_loop, daemon=True)
        self._worker_thread.start()
    
    def close(self):
        """Close broker."""
        self._running = False
        
        if self._worker_thread:
            self._worker_thread.join(timeout=1.0)
        
        if self.push_socket:
            self.push_socket.close()
        
        if self.pull_socket:
            self.pull_socket.close()


# High-level pattern for frame distribution
class FrameDistributor:
    """
    Optimized frame distribution using ZeroMQ.
    
    Replaces HTTP-based frame distribution with zero-copy IPC.
    """
    
    def __init__(self, service_name: str = "frame_provider"):
        self.broker = PubSubBroker(service_name)
        self.started = False
    
    def start(self) -> str:
        """Start frame distributor."""
        url = self.broker.start_publisher("frames")
        self.started = True
        return url
    
    def distribute_frame(self, take_id: int, frame_index: int, 
                        frame_data: bytes, metadata: Dict[str, Any]):
        """Distribute frame to subscribers."""
        if not self.started:
            raise RuntimeError("Distributor not started")
        
        # Use take_id as topic for filtering
        topic = f"take_{take_id}"
        
        # Package frame data
        frame_package = {
            "take_id": take_id,
            "frame_index": frame_index,
            "frame_data": frame_data,  # Already bytes
            "metadata": metadata,
            "timestamp": time.time()
        }
        
        self.broker.publish(topic, frame_package, "frame")
    
    def subscribe_to_frames(self, take_id: int, handler: Callable):
        """Subscribe to frames for a specific take."""
        topic = f"take_{take_id}"
        self.broker.subscribe("frame_provider", "frames", [topic], handler)
    
    def close(self):
        """Close distributor."""
        self.broker.close()
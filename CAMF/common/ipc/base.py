"""
Base classes for ZeroMQ IPC communication.

Provides high-performance inter-process communication with zero network overhead.
"""

import zmq
import json
import pickle
import time
import logging
from typing import Any, Dict, Optional, Union, Callable, List
from dataclasses import dataclass, field
from enum import Enum
import msgpack
import threading
from abc import ABC

logger = logging.getLogger(__name__)


class SerializationType(Enum):
    """Serialization methods for IPC messages."""
    JSON = "json"
    PICKLE = "pickle"
    MSGPACK = "msgpack"
    RAW = "raw"


@dataclass
class IPCMessage:
    """Standard message format for IPC communication."""
    msg_type: str
    data: Any
    timestamp: float = field(default_factory=time.time)
    headers: Dict[str, Any] = field(default_factory=dict)
    
    def serialize(self, serialization: SerializationType = SerializationType.MSGPACK) -> bytes:
        """Serialize message to bytes."""
        msg_dict = {
            "msg_type": self.msg_type,
            "data": self.data,
            "timestamp": self.timestamp,
            "headers": self.headers
        }
        
        if serialization == SerializationType.JSON:
            return json.dumps(msg_dict).encode('utf-8')
        elif serialization == SerializationType.PICKLE:
            return pickle.dumps(msg_dict)
        elif serialization == SerializationType.MSGPACK:
            return msgpack.packb(msg_dict, use_bin_type=True)
        elif serialization == SerializationType.RAW:
            if isinstance(self.data, bytes):
                return self.data
            else:
                raise ValueError("RAW serialization requires bytes data")
        else:
            raise ValueError(f"Unknown serialization type: {serialization}")
    
    @classmethod
    def deserialize(cls, data: bytes, serialization: SerializationType = SerializationType.MSGPACK) -> 'IPCMessage':
        """Deserialize message from bytes."""
        if serialization == SerializationType.JSON:
            msg_dict = json.loads(data.decode('utf-8'))
        elif serialization == SerializationType.PICKLE:
            msg_dict = pickle.loads(data)
        elif serialization == SerializationType.MSGPACK:
            msg_dict = msgpack.unpackb(data, raw=False)
        elif serialization == SerializationType.RAW:
            return cls(msg_type="raw", data=data)
        else:
            raise ValueError(f"Unknown serialization type: {serialization}")
        
        return cls(**msg_dict)


class IPCBase(ABC):
    """Base class for IPC communication."""
    
    def __init__(self, context: Optional[zmq.Context] = None, 
                 serialization: SerializationType = SerializationType.MSGPACK):
        self.context = context or zmq.Context.instance()
        self.serialization = serialization
        self.sockets: Dict[str, zmq.Socket] = {}
        self._running = False
        self._threads: List[threading.Thread] = []
    
    def close(self):
        """Close all sockets and cleanup."""
        self._running = False
        
        # Wait for threads to finish
        for thread in self._threads:
            from CAMF.common.config import get_config
            config = get_config()
            thread.join(timeout=config.service.thread_join_timeout)
        
        # Close all sockets
        for socket in self.sockets.values():
            socket.close()
        self.sockets.clear()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class IPCServer(IPCBase):
    """High-performance IPC server using ZeroMQ."""
    
    def __init__(self, service_name: str, context: Optional[zmq.Context] = None,
                 serialization: SerializationType = SerializationType.MSGPACK):
        super().__init__(context, serialization)
        self.service_name = service_name
        self.handlers: Dict[str, Callable] = {}
    
    def bind_reply(self, address: str, handler: Optional[Callable] = None) -> zmq.Socket:
        """Bind a REP socket for request-reply pattern."""
        socket = self.context.socket(zmq.REP)
        socket.bind(address)
        self.sockets[f"rep_{address}"] = socket
        
        if handler:
            self._start_reply_handler(socket, handler)
        
        logger.info(f"{self.service_name} bound REP socket to {address}")
        return socket
    
    def bind_pub(self, address: str) -> zmq.Socket:
        """Bind a PUB socket for publish-subscribe pattern."""
        socket = self.context.socket(zmq.PUB)
        socket.bind(address)
        self.sockets[f"pub_{address}"] = socket
        
        logger.info(f"{self.service_name} bound PUB socket to {address}")
        return socket
    
    def bind_pull(self, address: str, handler: Optional[Callable] = None) -> zmq.Socket:
        """Bind a PULL socket for push-pull pattern."""
        socket = self.context.socket(zmq.PULL)
        socket.bind(address)
        self.sockets[f"pull_{address}"] = socket
        
        if handler:
            self._start_pull_handler(socket, handler)
        
        logger.info(f"{self.service_name} bound PULL socket to {address}")
        return socket
    
    def publish(self, socket: Union[str, zmq.Socket], message: IPCMessage, topic: str = ""):
        """Publish a message on PUB socket."""
        if isinstance(socket, str):
            socket = self.sockets.get(f"pub_{socket}")
            if not socket:
                raise ValueError(f"No PUB socket bound to {socket}")
        
        # Add topic as prefix for filtering
        if topic:
            topic_bytes = topic.encode('utf-8') + b' '
        else:
            topic_bytes = b''
        
        data = topic_bytes + message.serialize(self.serialization)
        socket.send(data, zmq.DONTWAIT)
    
    def register_handler(self, msg_type: str, handler: Callable):
        """Register a message handler."""
        self.handlers[msg_type] = handler
    
    def _start_reply_handler(self, socket: zmq.Socket, handler: Callable):
        """Start a thread to handle REP socket requests."""
        def reply_loop():
            self._running = True
            while self._running:
                try:
                    # Use polling to allow graceful shutdown
                    from CAMF.common.config import get_config
                    config = get_config()
                    if socket.poll(timeout=config.service.ipc_poll_timeout_ms):
                        data = socket.recv()
                        message = IPCMessage.deserialize(data, self.serialization)
                        
                        # Call handler
                        response = handler(message)
                        
                        # Send response
                        if isinstance(response, IPCMessage):
                            socket.send(response.serialize(self.serialization))
                        else:
                            # Auto-wrap response
                            resp_msg = IPCMessage(
                                msg_type="response",
                                data=response
                            )
                            socket.send(resp_msg.serialize(self.serialization))
                
                except zmq.ZMQError as e:
                    if e.errno != zmq.EAGAIN:
                        logger.error(f"ZMQ error in reply handler: {e}")
                except Exception as e:
                    logger.error(f"Error in reply handler: {e}")
                    # Send error response
                    error_msg = IPCMessage(
                        msg_type="error",
                        data={"error": str(e)}
                    )
                    try:
                        socket.send(error_msg.serialize(self.serialization))
                    except:
                        pass
        
        thread = threading.Thread(target=reply_loop, daemon=True)
        thread.start()
        self._threads.append(thread)
    
    def _start_pull_handler(self, socket: zmq.Socket, handler: Callable):
        """Start a thread to handle PULL socket messages."""
        def pull_loop():
            self._running = True
            while self._running:
                try:
                    from CAMF.common.config import get_config
                    config = get_config()
                    if socket.poll(timeout=config.service.ipc_poll_timeout_ms):
                        data = socket.recv()
                        message = IPCMessage.deserialize(data, self.serialization)
                        
                        # Call handler (no response needed)
                        handler(message)
                
                except zmq.ZMQError as e:
                    if e.errno != zmq.EAGAIN:
                        logger.error(f"ZMQ error in pull handler: {e}")
                except Exception as e:
                    logger.error(f"Error in pull handler: {e}")
        
        thread = threading.Thread(target=pull_loop, daemon=True)
        thread.start()
        self._threads.append(thread)


class IPCClient(IPCBase):
    """High-performance IPC client using ZeroMQ."""
    
    def __init__(self, client_name: str, context: Optional[zmq.Context] = None,
                 serialization: SerializationType = SerializationType.MSGPACK):
        super().__init__(context, serialization)
        self.client_name = client_name
    
    def connect_req(self, address: str) -> zmq.Socket:
        """Connect a REQ socket for request-reply pattern."""
        socket = self.context.socket(zmq.REQ)
        socket.connect(address)
        self.sockets[f"req_{address}"] = socket
        
        logger.info(f"{self.client_name} connected REQ socket to {address}")
        return socket
    
    def connect_sub(self, address: str, topics: List[str] = None) -> zmq.Socket:
        """Connect a SUB socket for publish-subscribe pattern."""
        socket = self.context.socket(zmq.SUB)
        socket.connect(address)
        
        # Subscribe to topics
        if topics:
            for topic in topics:
                socket.setsockopt_string(zmq.SUBSCRIBE, topic)
        else:
            # Subscribe to all messages
            socket.setsockopt(zmq.SUBSCRIBE, b'')
        
        self.sockets[f"sub_{address}"] = socket
        
        logger.info(f"{self.client_name} connected SUB socket to {address}")
        return socket
    
    def connect_push(self, address: str) -> zmq.Socket:
        """Connect a PUSH socket for push-pull pattern."""
        socket = self.context.socket(zmq.PUSH)
        socket.connect(address)
        self.sockets[f"push_{address}"] = socket
        
        logger.info(f"{self.client_name} connected PUSH socket to {address}")
        return socket
    
    def request(self, socket: Union[str, zmq.Socket], message: IPCMessage, 
                timeout: int = 5000) -> IPCMessage:
        """Send request and wait for reply."""
        if isinstance(socket, str):
            socket = self.sockets.get(f"req_{socket}")
            if not socket:
                raise ValueError(f"No REQ socket connected to {socket}")
        
        # Send request
        socket.send(message.serialize(self.serialization))
        
        # Wait for reply with timeout
        if socket.poll(timeout=timeout):
            data = socket.recv()
            return IPCMessage.deserialize(data, self.serialization)
        else:
            raise TimeoutError(f"Request timed out after {timeout}ms")
    
    def push(self, socket: Union[str, zmq.Socket], message: IPCMessage):
        """Push a message on PUSH socket."""
        if isinstance(socket, str):
            socket = self.sockets.get(f"push_{socket}")
            if not socket:
                raise ValueError(f"No PUSH socket connected to {socket}")
        
        socket.send(message.serialize(self.serialization), zmq.DONTWAIT)
    
    def receive(self, socket: Union[str, zmq.Socket], timeout: Optional[int] = None) -> Optional[IPCMessage]:
        """Receive message from SUB or PULL socket."""
        if isinstance(socket, str):
            # Try SUB first, then PULL
            sock = self.sockets.get(f"sub_{socket}") or self.sockets.get(f"pull_{socket}")
            if not sock:
                raise ValueError(f"No SUB or PULL socket for {socket}")
            socket = sock
        
        if timeout is None:
            data = socket.recv()
        else:
            if socket.poll(timeout=timeout):
                data = socket.recv()
            else:
                return None
        
        # Handle topic prefix for SUB sockets
        if socket.socket_type == zmq.SUB:
            # Extract topic if present
            space_idx = data.find(b' ')
            if space_idx > 0:
                topic = data[:space_idx].decode('utf-8')
                data = data[space_idx + 1:]
                message = IPCMessage.deserialize(data, self.serialization)
                message.headers['topic'] = topic
                return message
        
        return IPCMessage.deserialize(data, self.serialization)
    
    def start_subscription_handler(self, socket: Union[str, zmq.Socket], 
                                  handler: Callable, run_in_thread: bool = True):
        """Start handling subscription messages."""
        if isinstance(socket, str):
            socket = self.sockets.get(f"sub_{socket}")
            if not socket:
                raise ValueError(f"No SUB socket connected to {socket}")
        
        def sub_loop():
            self._running = True
            while self._running:
                try:
                    from CAMF.common.config import get_config
                    config = get_config()
                    message = self.receive(socket, timeout=config.service.ipc_timeout_ms)
                    if message:
                        handler(message)
                except Exception as e:
                    logger.error(f"Error in subscription handler: {e}")
        
        if run_in_thread:
            thread = threading.Thread(target=sub_loop, daemon=True)
            thread.start()
            self._threads.append(thread)
        else:
            sub_loop()


# High-level convenience functions
def create_ipc_pair(service_name: str, client_name: str, 
                    pattern: str = "req-rep") -> tuple[IPCServer, IPCClient]:
    """Create a matched IPC server-client pair."""
    context = zmq.Context()
    server = IPCServer(service_name, context)
    client = IPCClient(client_name, context)
    return server, client
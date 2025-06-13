"""
High-performance IPC communication using ZeroMQ.

This module provides zero-overhead local communication between services
using ZeroMQ's various socket patterns.
"""

from .base import IPCClient, IPCServer, IPCMessage
from .registry import IPCServiceRegistry
from .patterns import PubSubBroker, RequestReplyBroker, PushPullBroker
from .transport import get_transport_url, TransportType

__all__ = [
    'IPCClient',
    'IPCServer', 
    'IPCMessage',
    'IPCServiceRegistry',
    'PubSubBroker',
    'RequestReplyBroker',
    'PushPullBroker',
    'get_transport_url',
    'TransportType'
]
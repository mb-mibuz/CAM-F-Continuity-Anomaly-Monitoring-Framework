import { useState, useEffect, useCallback, useRef } from 'react';
import { SSEService } from '../services';
import { useAppStore } from '../stores';
import { api } from '../utils/api';

/**
 * Hook for SSE (Server-Sent Events) connection management
 * @param {Object} options - SSE options
 * @returns {Object} SSE state and controls
 */
export function useSSE(options = {}) {
  const {
    autoConnect = true,
    reconnectOnError = true,
    onConnect,
    onDisconnect,
    onError,
    onMessage
  } = options;
  
  // State
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [lastError, setLastError] = useState(null);
  const [lastMessage, setLastMessage] = useState(null);
  
  // Refs
  const sseService = useRef(null);
  const subscriptions = useRef(new Map());
  const isMountedRef = useRef(true);
  
  const { addNotification } = useAppStore();
  
  useEffect(() => {
    sseService.current = SSEService;
    
    return () => {
      isMountedRef.current = false;
    };
  }, []);
  
  // Connection status monitoring
  useEffect(() => {
    if (!sseService.current) return;
    
    const checkConnection = setInterval(() => {
      if (isMountedRef.current) {
        const connected = sseService.current.isConnected;
        setIsConnected(connected);
      }
    }, 1000);
    
    return () => clearInterval(checkConnection);
  }, []);
  
  // Auto-connect on mount
  useEffect(() => {
    if (autoConnect && sseService.current) {
      connect();
    }
  }, [autoConnect]);
  
  // Connect to SSE
  const connect = useCallback(async () => {
    if (!sseService.current || isConnecting) {
      return false;
    }
    
    setIsConnecting(true);
    setLastError(null);
    
    try {
      await sseService.current.connect();
      
      if (isMountedRef.current) {
        setIsConnected(true);
        onConnect?.();
        
        // Resubscribe to all channels
        for (const [channel, handler] of subscriptions.current) {
          sseService.current.subscribe(channel, handler);
        }
      }
      
      return true;
    } catch (error) {
      console.error('SSE connection failed:', error);
      
      if (isMountedRef.current) {
        setLastError(error);
        onError?.(error);
        
        if (reconnectOnError) {
          addNotification({ type: 'warning', message: 'Connection lost. Attempting to reconnect...' });
        } else {
          addNotification({ type: 'error', message: 'Failed to connect to server' });
        }
      }
      
      return false;
    } finally {
      if (isMountedRef.current) {
        setIsConnecting(false);
      }
    }
  }, [isConnecting, onConnect, onError, reconnectOnError, addNotification]);
  
  // Disconnect from SSE
  const disconnect = useCallback(() => {
    if (!sseService.current) {
      return;
    }
    
    // Unsubscribe all handlers
    for (const [channel, handler] of subscriptions.current) {
      sseService.current.unsubscribe(channel, handler);
    }
    subscriptions.current.clear();
    
    // Disconnect
    sseService.current.disconnect();
    
    if (isMountedRef.current) {
      setIsConnected(false);
      onDisconnect?.();
    }
  }, [onDisconnect]);
  
  // Subscribe to a channel
  const subscribe = useCallback((channel, handler) => {
    if (!sseService.current) {
      console.warn('SSE service not initialized');
      return () => {};
    }
    
    // Wrap handler to update last message
    const wrappedHandler = (message) => {
      if (isMountedRef.current) {
        setLastMessage({ channel, data: message, timestamp: Date.now() });
        onMessage?.(channel, message);
      }
      handler(message);
    };
    
    // Store subscription
    subscriptions.current.set(channel, wrappedHandler);
    
    // Subscribe through service
    sseService.current.subscribe(channel, wrappedHandler);
    
    // Return unsubscribe function
    return () => {
      subscriptions.current.delete(channel);
      sseService.current.unsubscribe(channel, wrappedHandler);
    };
  }, [onMessage]);
  
  // Send a message (SSE is receive-only, so we use HTTP POST)
  const send = useCallback(async (message) => {
    if (!isConnected) {
      console.warn('SSE not connected');
      return false;
    }
    
    try {
      // SSE is receive-only, so we need to use HTTP API for sending messages
      // This is a placeholder - replace with appropriate API endpoint
      console.warn('SSE is receive-only. Use appropriate HTTP API endpoints for sending data.');
      return false;
    } catch (error) {
      console.error('Failed to send message:', error);
      setLastError(error);
      return false;
    }
  }, [isConnected]);
  
  // Get connection state
  const getReadyState = useCallback(() => {
    if (!sseService.current) {
      return 3; // CLOSED
    }
    return sseService.current.readyState;
  }, []);
  
  return {
    // State
    isConnected,
    isConnecting,
    lastError,
    lastMessage,
    
    // Actions
    connect,
    disconnect,
    subscribe,
    send,
    
    // Utilities
    getReadyState,
    readyState: getReadyState(),
    
    // Constants (SSE mapped to WebSocket states)
    CONNECTING: 0,
    OPEN: 1,
    CLOSING: 2,
    CLOSED: 3
  };
}

/**
 * Hook for subscribing to a specific SSE channel
 * @param {string} channel - Channel to subscribe to
 * @param {Function} handler - Message handler
 * @param {Object} options - Subscription options
 */
export function useSSEChannel(channel, handler, options = {}) {
  const { enabled = true } = options;
  const { subscribe, isConnected } = useSSE();
  
  useEffect(() => {
    if (!enabled || !channel || !handler) {
      return;
    }
    
    // Subscribe when connected
    if (isConnected) {
      return subscribe(channel, handler);
    }
  }, [channel, handler, enabled, isConnected, subscribe]);
  
  return { isConnected };
}

/**
 * Hook for SSE event subscriptions
 * @param {Object} eventHandlers - Map of event types to handlers
 * @param {Object} options - Subscription options
 */
export function useSSEEvents(eventHandlers, options = {}) {
  const { enabled = true } = options;
  const { subscribe, isConnected } = useSSE();
  
  useEffect(() => {
    if (!enabled || !eventHandlers || !isConnected) {
      return;
    }
    
    const unsubscribes = [];
    
    // Subscribe to each event type
    for (const [eventType, handler] of Object.entries(eventHandlers)) {
      if (handler && typeof handler === 'function') {
        const unsubscribe = subscribe(eventType, handler);
        unsubscribes.push(unsubscribe);
      }
    }
    
    // Cleanup
    return () => {
      unsubscribes.forEach(unsubscribe => unsubscribe());
    };
  }, [enabled, eventHandlers, isConnected, subscribe]);
  
  return { isConnected };
}
import { useAppStore } from '../stores';
import config from '../config';

class SSEService {
  static instance = null;
  
  constructor() {
    this.eventSource = null;
    this.subscriptions = new Map();
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = Infinity; // Keep trying forever
    this.reconnectDelay = 1000;
    this.isConnecting = false;
    this.clientId = `sse-client-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    this.connectionPromise = null;
    this.lastEventTime = Date.now();
    
    // Message and connection handlers for event bridge compatibility
    this.messageHandlers = new Set();
    this.connectionHandlers = new Set();
    
    // Track subscribed channels
    this.subscribedChannels = new Set();
  }
  
  static getInstance() {
    if (!this.instance) {
      this.instance = new SSEService();
    }
    return this.instance;
  }
  
  async connect() {
    // Return existing connection promise if connecting
    if (this.connectionPromise) {
      return this.connectionPromise;
    }
    
    // Already connected
    if (this.eventSource?.readyState === EventSource.OPEN) {
      return Promise.resolve();
    }
    
    this.isConnecting = true;
    
    this.connectionPromise = new Promise((resolve, reject) => {
      try {
        console.log('Connecting to SSE...');
        
        // Build URL with channels
        const channels = Array.from(this.subscribedChannels).join(',');
        const url = new URL(config.sse.url);
        url.searchParams.append('client_id', this.clientId);
        if (channels) {
          url.searchParams.append('channels', channels);
        }
        
        this.eventSource = new EventSource(url.toString());
        
        this.eventSource.onopen = () => {
          console.log('SSE connected');
          this.isConnecting = false;
          const wasReconnecting = this.reconnectAttempts > 0;
          this.reconnectAttempts = 0;
          this.connectionPromise = null;
          
          // Show success notification if reconnecting
          if (wasReconnecting) {
            const appStore = useAppStore.getState();
            appStore.notify.success('Connection restored');
          }
          
          // Notify connection handlers
          this.notifyConnectionHandlers(true);
          
          resolve();
        };
        
        // Handle named events
        this.eventSource.addEventListener('message', (event) => {
          try {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
          } catch (error) {
            console.error('Error parsing SSE message:', error);
          }
        });
        
        // Handle specific event types
        this.eventSource.addEventListener('connection', (event) => {
          console.log('SSE connection event:', event.data);
          this.lastEventTime = Date.now();
        });
        
        this.eventSource.addEventListener('heartbeat', (event) => {
          this.lastEventTime = Date.now();
          // Don't log heartbeats to reduce console noise
        });
        
        // Handle system events
        this.eventSource.addEventListener('system', (event) => {
          try {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
          } catch (error) {
            console.error('Error parsing system event:', error);
          }
        });
        
        // Handle detector events
        this.eventSource.addEventListener('detector_result', (event) => {
          try {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
          } catch (error) {
            console.error('Error parsing detector event:', error);
          }
        });
        
        this.eventSource.addEventListener('detector_error', (event) => {
          try {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
          } catch (error) {
            console.error('Error parsing detector error:', error);
          }
        });
        
        this.eventSource.addEventListener('detector_failure', (event) => {
          try {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
          } catch (error) {
            console.error('Error parsing detector failure:', error);
          }
        });
        
        // Handle capture events
        this.eventSource.addEventListener('capture_status', (event) => {
          try {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
          } catch (error) {
            console.error('Error parsing capture status:', error);
          }
        });
        
        this.eventSource.addEventListener('capture_started', (event) => {
          try {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
          } catch (error) {
            console.error('Error parsing capture started:', error);
          }
        });
        
        this.eventSource.addEventListener('capture_stopped', (event) => {
          try {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
          } catch (error) {
            console.error('Error parsing capture stopped:', error);
          }
        });
        
        // Handle frame events
        this.eventSource.addEventListener('frame_captured', (event) => {
          try {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
          } catch (error) {
            console.error('Error parsing frame captured:', error);
          }
        });
        
        this.eventSource.addEventListener('frame_processed', (event) => {
          try {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
          } catch (error) {
            console.error('Error parsing frame processed:', error);
          }
        });
        
        // Handle processing events
        this.eventSource.addEventListener('processing_started', (event) => {
          try {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
          } catch (error) {
            console.error('Error parsing processing started:', error);
          }
        });
        
        this.eventSource.addEventListener('processing_complete', (event) => {
          try {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
          } catch (error) {
            console.error('Error parsing processing complete:', error);
          }
        });
        
        this.eventSource.addEventListener('detector_results_cleared', (event) => {
          try {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
          } catch (error) {
            console.error('Error parsing detector results cleared:', error);
          }
        });
        
        this.eventSource.addEventListener('processing_restarted', (event) => {
          try {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
          } catch (error) {
            console.error('Error parsing processing restarted:', error);
          }
        });
        
        this.eventSource.addEventListener('source_disconnected', (event) => {
          try {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
          } catch (error) {
            console.error('Error parsing source disconnected:', error);
          }
        });
        
        // Handle video upload events
        this.eventSource.addEventListener('upload_started', (event) => {
          try {
            const data = JSON.parse(event.data);
            console.log('[SSEService] Received upload_started event:', data);
            this.handleMessage({
              ...data,
              event_type: 'upload_started'
            });
          } catch (error) {
            console.error('Error parsing upload started:', error);
          }
        });
        
        this.eventSource.addEventListener('upload_completed', (event) => {
          try {
            const data = JSON.parse(event.data);
            console.log('[SSEService] Received upload_completed event:', data);
            this.handleMessage({
              ...data,
              event_type: 'upload_completed'
            });
          } catch (error) {
            console.error('Error parsing upload completed:', error);
          }
        });
        
        this.eventSource.addEventListener('upload_error', (event) => {
          try {
            const data = JSON.parse(event.data);
            console.log('[SSEService] Received upload_error event:', data);
            this.handleMessage({
              ...data,
              event_type: 'upload_error'
            });
          } catch (error) {
            console.error('Error parsing upload error:', error);
          }
        });
        
        this.eventSource.onerror = (error) => {
          console.error('SSE error:', error);
          this.isConnecting = false;
          this.connectionPromise = null;
          
          // EventSource will auto-reconnect, but we need to handle our state
          if (this.eventSource.readyState === EventSource.CLOSED) {
            // Notify connection handlers
            this.notifyConnectionHandlers(false);
            
            // Handle reconnection
            this.handleReconnect();
          }
        };
        
        // Set connection timeout
        setTimeout(() => {
          if (this.isConnecting) {
            this.eventSource?.close();
            reject(new Error('Connection timeout'));
          }
        }, 10000);
        
      } catch (error) {
        this.isConnecting = false;
        this.connectionPromise = null;
        reject(error);
      }
    });
    
    return this.connectionPromise;
  }
  
  disconnect() {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    
    this.subscriptions.clear();
    this.subscribedChannels.clear();
    this.reconnectAttempts = 0;
    this.connectionPromise = null;
  }
  
  subscribe(channel, handler) {
    if (!this.subscriptions.has(channel)) {
      this.subscriptions.set(channel, new Set());
    }
    
    this.subscriptions.get(channel).add(handler);
    this.subscribedChannels.add(channel);
    
    // If already connected, we need to reconnect with new channels
    if (this.eventSource?.readyState === EventSource.OPEN) {
      // Close current connection and reconnect with updated channels
      this.eventSource.close();
      this.eventSource = null;
      this.connect();
    }
    
    console.log(`Subscribed to channel: ${channel}`);
    
    // Return unsubscribe function
    return () => this.unsubscribe(channel, handler);
  }
  
  unsubscribe(channel, handler) {
    const handlers = this.subscriptions.get(channel);
    
    if (handlers) {
      if (handler) {
        handlers.delete(handler);
        
        if (handlers.size === 0) {
          this.subscriptions.delete(channel);
          this.subscribedChannels.delete(channel);
        }
      } else {
        // Unsubscribe all handlers
        this.subscriptions.delete(channel);
        this.subscribedChannels.delete(channel);
      }
    }
    
    console.log(`Unsubscribed from channel: ${channel}`);
  }
  
  // WebSocket compatibility method - SSE is receive-only
  send(message) {
    console.warn('SSE is receive-only. Use HTTP APIs for sending data.');
    // For compatibility, we could queue these and send via HTTP
  }
  
  handleMessage(data) {
    // Only log non-frequent messages
    if (!['frame_update', 'capture_progress', 'heartbeat'].includes(data.type)) {
      console.log('SSE message received:', data.type, data.channel);
    }
    
    // Special logging for frame events
    if (data.type === 'frame_captured' || data.channel?.includes('take_')) {
      console.log('[SSE] Frame event:', data);
    }
    
    // Debug: Log all data for frame_captured events
    if (data.type === 'frame_captured') {
      console.log('[SSE Debug] Full frame_captured data:', JSON.stringify(data, null, 2));
    }
    
    // Special handling for upload events - extract channel from data if needed
    if (data.event_type && ['upload_started', 'upload_completed', 'upload_error'].includes(data.event_type)) {
      console.log('[SSE] Upload event:', data);
      // If no channel but has take_id, set channel
      if (!data.channel && data.take_id) {
        data.channel = `take_${data.take_id}`;
      }
    }
    
    // First, notify all message handlers (for event bridge)
    this.messageHandlers.forEach(handler => {
      try {
        handler(data);
      } catch (error) {
        console.error('Error in message handler:', error);
      }
    });
    
    // Check for channel-specific handlers
    if (data.channel) {
      const handlers = this.subscriptions.get(data.channel);
      if (handlers && handlers.size > 0) {
        handlers.forEach(handler => {
          try {
            handler(data);
          } catch (error) {
            console.error('Error in channel handler:', error, { channel: data.channel });
          }
        });
      }
    }
    
    // Also check for type-based channels (for backward compatibility)
    const typeChannel = `${data.type}_events`;
    const typeHandlers = this.subscriptions.get(typeChannel);
    if (typeHandlers && typeHandlers.size > 0) {
      typeHandlers.forEach(handler => {
        try {
          handler(data);
        } catch (error) {
          console.error('Error in type handler:', error, { type: data.type });
        }
      });
    }
  }
  
  handleReconnect() {
    this.reconnectAttempts++;
    const delay = Math.min(
      this.reconnectDelay * Math.pow(2, Math.min(this.reconnectAttempts - 1, 6)), 
      30000 // Max 30 second delay
    );
    
    console.log(`Attempting reconnection #${this.reconnectAttempts} in ${delay}ms`);
    
    // Show reconnecting notification only on first attempt
    if (this.reconnectAttempts === 1) {
      const appStore = useAppStore.getState();
      appStore.notify.info('Connection lost. Reconnecting...');
    }
    
    // Show periodic updates
    if (this.reconnectAttempts % 5 === 0) {
      const appStore = useAppStore.getState();
      appStore.notify.info(`Still trying to reconnect... (attempt ${this.reconnectAttempts})`);
    }
    
    setTimeout(() => {
      this.connect().catch(error => {
        console.error('Reconnection failed:', error);
        // Keep trying
        this.handleReconnect();
      });
    }, delay);
  }
  
  get isConnected() {
    return this.eventSource?.readyState === EventSource.OPEN;
  }
  
  get readyState() {
    // Map EventSource states to WebSocket states for compatibility
    if (!this.eventSource) return 3; // CLOSED
    switch (this.eventSource.readyState) {
      case EventSource.CONNECTING: return 0; // CONNECTING
      case EventSource.OPEN: return 1; // OPEN
      case EventSource.CLOSED: return 3; // CLOSED
      default: return 3;
    }
  }
  
  // Event Bridge Support Methods
  addMessageHandler(handler) {
    this.messageHandlers.add(handler);
    return () => this.removeMessageHandler(handler);
  }
  
  removeMessageHandler(handler) {
    this.messageHandlers.delete(handler);
  }
  
  addConnectionHandler(handler) {
    this.connectionHandlers.add(handler);
    return () => this.removeConnectionHandler(handler);
  }
  
  removeConnectionHandler(handler) {
    this.connectionHandlers.delete(handler);
  }
  
  notifyConnectionHandlers(isConnected) {
    this.connectionHandlers.forEach(handler => {
      try {
        handler(isConnected);
      } catch (error) {
        console.error('Error in connection handler:', error);
      }
    });
  }
}

// Export both the class and singleton instance
export { SSEService };
export default SSEService.getInstance();
/**
 * SSE Event Bridge
 * 
 * This service bridges SSE (Server-Sent Events) to store updates,
 * handling the system_event wrapper from the backend and
 * ensuring proper state synchronization across stores.
 */

import { 
  useAppStore,
  useDataStore,
  useProcessingStore
} from '../stores';
import SSEService from './SSEService';

class SSEEventBridge {
  constructor() {
    this.sseService = SSEService;
    this.eventHandlers = new Map();
    this.initialized = false;
    this.setupEventHandlers();
  }

  setupEventHandlers() {
    // Capture events
    this.registerHandler('capture_started', this.handleCaptureStarted.bind(this));
    this.registerHandler('capture_stopped', this.handleCaptureStopped.bind(this));
    this.registerHandler('capture_error', this.handleCaptureError.bind(this));
    this.registerHandler('frame_captured', this.handleFrameCaptured.bind(this));
    this.registerHandler('capture_status', this.handleCaptureStatus.bind(this));
    this.registerHandler('capture_source_disconnected', this.handleSourceDisconnected.bind(this));
    
    // Processing events
    this.registerHandler('processing_started', this.handleProcessingStarted.bind(this));
    this.registerHandler('processing_complete', this.handleProcessingComplete.bind(this));
    this.registerHandler('processing_progress', this.handleProcessingProgress.bind(this));
    this.registerHandler('detector_results_cleared', this.handleDetectorResultsCleared.bind(this));
    this.registerHandler('processing_restarted', this.handleProcessingRestarted.bind(this));
    this.registerHandler('detector_error', this.handleDetectorError.bind(this));
    this.registerHandler('detector_failure', this.handleDetectorFailure.bind(this));
    this.registerHandler('detector_result', this.handleDetectorResult.bind(this));
    
    // Frame events
    this.registerHandler('frame_processed', this.handleFrameProcessed.bind(this));
    this.registerHandler('frame_deleted', this.handleFrameDeleted.bind(this));
    this.registerHandler('frame_pair_processed', this.handleFramePairProcessed.bind(this));
    
    // Connection events
    this.registerHandler('connection_established', this.handleConnectionEstablished.bind(this));
    this.registerHandler('connection_lost', this.handleConnectionLost.bind(this));
    
    // System events
    this.registerHandler('system_error', this.handleSystemError.bind(this));
    this.registerHandler('resource_warning', this.handleResourceWarning.bind(this));
  }

  registerHandler(eventType, handler) {
    this.eventHandlers.set(eventType, handler);
  }

  initialize() {
    if (this.initialized) return;
    
    // Subscribe to raw SSE messages
    this.sseService.addMessageHandler(this.handleSSEMessage.bind(this));
    
    // Subscribe to connection state changes
    this.sseService.addConnectionHandler(this.handleConnectionChange.bind(this));
    
    this.initialized = true;
    // SSE Event Bridge initialized
  }

  handleSSEMessage(message) {
    try {
      // Handle system_event wrapper from backend
      if (message.type === 'system_event' && message.event_type) {
        const handler = this.eventHandlers.get(message.event_type);
        if (handler) {
          handler(message.data || {}, message);
        } else {
          console.warn(`[SSEEventBridge] No handler for event type: ${message.event_type}`);
        }
      } 
      // Handle direct event types for backward compatibility
      else if (message.type && this.eventHandlers.has(message.type)) {
        const handler = this.eventHandlers.get(message.type);
        handler(message.data || message, message);
      }
      // Handle detector results
      else if (message.detector_id && message.results) {
        this.handleDetectorResult(message);
      }
    } catch (error) {
      console.error('[SSEEventBridge] Error handling message:', error, message);
    }
  }

  handleConnectionChange(isConnected) {
    const appStore = useAppStore.getState();
    
    if (isConnected) {
      appStore.addNotification({ type: 'success', message: 'Connected to server' });
      appStore.updateConnectionStatus('sse', 'connected');
      
      // Re-subscribe to active channels
      this.resubscribeToActiveChannels();
    } else {
      appStore.addNotification({ type: 'warning', message: 'Connection lost. Attempting to reconnect...' });
      appStore.updateConnectionStatus('sse', 'disconnected');
    }
  }

  resubscribeToActiveChannels() {
    // Note: SSEEventBridge handles all messages through handleSSEMessage
    // which is registered as a message handler. We don't need to subscribe to 
    // specific channels here as the bridge processes all incoming messages.
    
    // This method is kept for backward compatibility but doesn't need to do anything.
    // The SSE service will automatically resubscribe to channels that have
    // actual handlers registered through proper subscribe(channel, handler) calls.
  }

  // Capture Event Handlers
  handleCaptureStarted(data) {
    const dataStore = useDataStore.getState();
    dataStore.startCapture(data.source || {});
    
    if (data.takeId) {
      dataStore.updateTakeStatus(data.takeId, 'capturing');
    }
  }

  handleCaptureStopped(data) {
    const dataStore = useDataStore.getState();
    
    // Batch all updates in a single store update to prevent multiple re-renders
    dataStore.setState((state) => {
      // Stop capture
      state.isCapturing = false;
      state.captureProgress.isComplete = true;
      
      // Update frame count
      if (data.frameCount !== undefined) {
        state.frameCount = data.frameCount;
        if (!state.isNavigatingManually) {
          state.latestFrameIndex = Math.max(0, data.frameCount - 1);
          state.currentFrameIndex = Math.max(0, data.frameCount - 1);
        }
      }
      
      // Update take status
      if (data.takeId) {
        // Update take status in all angles
        for (const [angleId, takes] of state.takes.entries()) {
          const takeIndex = takes.findIndex(t => t.id === data.takeId);
          if (takeIndex !== -1) {
            takes[takeIndex].status = 'captured';
            takes[takeIndex].frame_count = data.frameCount || 0;
          }
        }
        
        // Update current take if it matches
        if (state.currentTake?.id === data.takeId) {
          state.currentTake.status = 'captured';
          state.currentTake.frame_count = data.frameCount || 0;
        }
      }
      
      // Remove from active processes
      if (state.captureSession?.takeId) {
        useProcessingStore.getState().removeActiveProcess(`capture-${state.captureSession.takeId}`);
      }
    });
  }

  handleCaptureError(data) {
    const dataStore = useDataStore.getState();
    const appStore = useAppStore.getState();
    
    dataStore.setCaptureError(data.error || 'Unknown capture error');
    appStore.addNotification({ 
      type: 'error', 
      message: `Capture error: ${data.error || 'Unknown error'}` 
    });
  }

  handleFrameCaptured(data) {
    const dataStore = useDataStore.getState();
    
    // Frame captured event received
    
    // Update frame count - check both frame_count and frameIndex
    const frameCount = data.frame_count !== undefined ? data.frame_count : (data.frameIndex + 1);
    
    if (frameCount !== undefined) {
      // Update navigation frame count
      dataStore.updateFrameCount(frameCount);
      
      // IMPORTANT: Also update capture progress to show correct count during capture
      dataStore.updateCaptureProgress({
        capturedFrames: frameCount
      });
    }
    
    // Don't update preview during capture - frames are handled differently
  }

  handleCaptureStatus(data) {
    const dataStore = useDataStore.getState();
    
    // Update frame count and latest frame index
    if (data.data) {
      const statusData = data.data;
      
      if (statusData.frame_count !== undefined) {
        dataStore.updateFrameCount(statusData.frame_count);
        
        // IMPORTANT: Also update capture progress to show correct count during capture
        dataStore.updateCaptureProgress({
          capturedFrames: statusData.frame_count
        });
      }
      
      if (statusData.frame_index !== undefined) {
        dataStore.setLatestFrameIndex(statusData.frame_index);
      }
      
      // Update capture progress
      if (statusData.is_capturing !== undefined) {
        if (!statusData.is_capturing && dataStore.isCapturing) {
          // Capture just stopped
          dataStore.stopCapture();
        }
      }
    }
  }

  handleSourceDisconnected(data) {
    const dataStore = useDataStore.getState();
    const appStore = useAppStore.getState();
    
    dataStore.setSourceDisconnected(true);
    appStore.openModal('sourceDisconnected', { 
      source: data.source,
      reason: data.reason 
    });
  }

  // Processing Event Handlers
  handleProcessingStarted(data) {
    const processingStore = useProcessingStore.getState();
    const dataStore = useDataStore.getState();
    
    processingStore.startProcessing(data.takeId, data.detectors || []);
    
    // CRITICAL: Also update dataStore processing flags since UI reads from there
    dataStore.startRedoDetection();
    
    if (data.takeId) {
      dataStore.updateTakeStatus(data.takeId, 'processing');
    }
  }

  handleProcessingComplete(data) {
    // Processing complete event received
    
    const processingStore = useProcessingStore.getState();
    const dataStore = useDataStore.getState();
    const appStore = useAppStore.getState();
    
    // Check current processing session
    // Check current dataStore state
    // Call completeProcessing
    
    // Handle both takeId and take_id formats
    const takeId = data.takeId || data.take_id;
    
    processingStore.completeProcessing(takeId);
    
    // CRITICAL: Also update dataStore processing flags since UI reads from there
    dataStore.completeRedoDetection();
    
    // Ensure all active processes are cleared
    const remainingProcesses = processingStore.activeProcesses.filter(p => p.takeId === takeId);
    if (remainingProcesses.length > 0) {
      // Clear remaining active processes
      remainingProcesses.forEach(p => processingStore.removeActiveProcess(p.id));
    }
    
    // Log the state after calling completeProcessing
    const newState = useProcessingStore.getState();
    const newDataState = useDataStore.getState();
    // Processing state updated
    // Data store processing state updated
    // Data store redo detection state updated
    
    if (takeId) {
      dataStore.updateTakeStatus(takeId, 'completed');
      dataStore.updateTakeProcessingResults(takeId, data.results || {});
    }
    
    appStore.addNotification({ type: 'success', message: 'Processing completed successfully' });
  }
  
  handleDetectorResultsCleared(data) {
    const processingStore = useProcessingStore.getState();
    const dataStore = useDataStore.getState();
    const appStore = useAppStore.getState();
    
    // Detector results cleared
    
    // Clear detector errors in processing store
    processingStore.clearDetectorErrors();
    
    // Clear detector errors in data store
    if (dataStore.clearDetectorErrors) {
      dataStore.clearDetectorErrors();
    }
    
    // IMPORTANT: Force update detector errors to empty array
    // This ensures the UI immediately reflects the cleared state
    dataStore.updateDetectorErrors([]);
    
    // Also clear the detectorErrors state directly
    dataStore.setState((state) => {
      state.detectorErrors = [];
    });
    
    // Notify user
    const message = data.cleared_count 
      ? `Cleared ${data.cleared_count} previous detector results` 
      : 'Previous detector results cleared';
    appStore.addNotification({ type: 'info', message });
  }
  
  handleProcessingRestarted(data) {
    const processingStore = useProcessingStore.getState();
    const dataStore = useDataStore.getState();
    
    // Processing restarted
    
    // Start redo detection state
    processingStore.startProcessing(data.take_id, []);
    
    // CRITICAL: Also update dataStore processing flags since UI reads from there
    dataStore.startRedoDetection();
    
    if (data.take_id) {
      dataStore.updateTakeStatus(data.take_id, 'processing');
    }
  }

  handleProcessingProgress(data) {
    const processingStore = useProcessingStore.getState();
    const dataStore = useDataStore.getState();
    
    // Update overall progress
    if (data.processed_frames !== undefined || data.total_frames !== undefined) {
      processingStore.updateProcessingProgress({
        processedFrames: data.processed_frames || 0,
        totalFrames: data.total_frames || 0,
        currentFrame: data.current_frame || 0
      });
      
      // Also update capture progress if capturing
      if (dataStore.isCapturing) {
        dataStore.updateCaptureProgress({
          processedFrames: data.processed_frames || 0
        });
      }
    }
    
    // Update detector-specific progress
    if (data.detector && data.progress !== undefined) {
      processingStore.updateDetectorProgress(data.detector, data.progress);
    }
  }

  handleDetectorError(data) {
    const processingStore = useProcessingStore.getState();
    const appStore = useAppStore.getState();
    const dataStore = useDataStore.getState();
    
    // Create error object for detector error list
    const error = {
      id: `${Date.now()}-${Math.random()}`,
      detector_name: data.detector_name || data.detector,
      description: data.description || data.error || 'Detector error',
      frame_id: data.frame_id,
      frame_index: data.frame_index,
      take_id: data.take_id,
      confidence: data.confidence !== undefined ? data.confidence : 0.8,
      severity: data.severity || 'warning',
      timestamp: data.timestamp || Date.now(),
      metadata: data.metadata || {},
      bounding_boxes: data.bounding_boxes || []
    };
    
    // Update detector errors in data store
    const currentErrors = dataStore.detectorErrors || [];
    const updatedErrors = [...currentErrors, error];
    
    dataStore.updateDetectorErrors(updatedErrors);
    
    processingStore.addDetectorError(data.detector_name || data.detector, data.error || data.description);
    
    // Only show notification for critical errors or detector failures
    if (data.severity === 'critical' || data.severity === 'failure' || data.isCritical || data.confidence === -1.0) {
      appStore.addNotification({
        type: 'error',
        message: `Detector error (${data.detector_name || data.detector}): ${data.description || data.error}`
      });
    }
  }

  handleDetectorFailure(data) {
    const processingStore = useProcessingStore.getState();
    const appStore = useAppStore.getState();
    const dataStore = useDataStore.getState();
    
    // Create error object for detector failure
    const error = {
      id: `${Date.now()}-${Math.random()}`,
      detector_name: data.detector_name || data.detector,
      description: data.description || `Detector failed: ${data.error || 'Unknown error'}`,
      frame_id: data.frame_id,
      frame_index: data.frame_index,
      take_id: data.take_id,
      confidence: -1.0, // Special value for detector failures
      severity: 'failure',
      timestamp: data.timestamp || Date.now(),
      metadata: data.metadata || {}
    };
    
    // Update detector errors in data store
    const currentErrors = dataStore.detectorErrors || [];
    dataStore.updateDetectorErrors([...currentErrors, error]);
    
    processingStore.addDetectorError(data.detector_name || data.detector, data.error || data.description);
    
    // Always show notification for detector failures
    appStore.addNotification({
      type: 'error',
      message: `Detector failed (${data.detector_name || data.detector}): ${data.description || data.error || 'Unknown error'}`
    });
  }

  handleDetectorResult(data) {
    const processingStore = useProcessingStore.getState();
    const dataStore = useDataStore.getState();
    
    // Update processing results
    if (data.detector_id && data.results) {
      processingStore.updateDetectorResults(data.detector_id, data.results);
      
      // Update frame-specific results if frame info is provided
      if (data.frame_index !== undefined && data.take_id) {
        dataStore.updateFrameResults(data.take_id, data.frame_index, {
          [data.detector_id]: data.results
        });
      }
    }
  }

  // Frame Event Handlers
  handleFrameProcessed(data) {
    const dataStore = useDataStore.getState();
    
    if (data.takeId && data.frameIndex !== undefined) {
      dataStore.markFrameProcessed(data.takeId, data.frameIndex);
    }
  }
  
  handleFramePairProcessed(data) {
    const processingStore = useProcessingStore.getState();
    const dataStore = useDataStore.getState();
    
    // Update processing progress
    if (data.take_id && data.frame_index !== undefined) {
      const currentProgress = processingStore.processingProgress;
      processingStore.updateProcessingProgress({
        processedFrames: currentProgress.processedFrames + 1,
        currentFrame: data.frame_index
      });
      
      // Update capture progress if capturing
      if (dataStore.isCapturing) {
        dataStore.updateCaptureProgress({
          processedFrames: dataStore.captureProgress.processedFrames + 1
        });
      }
    }
  }

  handleFrameDeleted(data) {
    const dataStore = useDataStore.getState();
    
    if (data.takeId && data.frameIndex !== undefined) {
      dataStore.removeFrameFromCache(data.takeId, data.frameIndex);
    }
  }

  // Connection Event Handlers
  handleConnectionEstablished(data) {
    const appStore = useAppStore.getState();
    appStore.updateConnectionStatus('sse', 'connected');
    appStore.updateServerInfo(data.server || {});
  }

  handleConnectionLost() {
    const appStore = useAppStore.getState();
    const dataStore = useDataStore.getState();
    
    appStore.updateConnectionStatus('sse', 'disconnected');
    
    // Pause any active capture
    if (dataStore.isCapturing) {
      dataStore.pauseCapture();
    }
  }

  // System Event Handlers
  handleSystemError(data) {
    const appStore = useAppStore.getState();
    appStore.addNotification({
      type: 'error',
      message: `System error: ${data.message || 'Unknown error'}`
    });
  }

  handleResourceWarning(data) {
    const appStore = useAppStore.getState();
    
    // appStore.setResourceWarning(data); // TODO: Add this method to appStore if needed
    
    if (data.severity === 'high') {
      appStore.addNotification({
        type: 'warning',
        message: `High resource usage: ${data.message}`
      });
    }
  }

  // Utility methods for external use
  subscribeToTake(takeId) {
    if (takeId) {
      this.sseService.subscribe(`take_${takeId}`);
    }
  }

  unsubscribeFromTake(takeId) {
    if (takeId) {
      this.sseService.unsubscribe(`take_${takeId}`);
    }
  }

  destroy() {
    this.sseService.removeMessageHandler(this.handleSSEMessage.bind(this));
    this.sseService.removeConnectionHandler(this.handleConnectionChange.bind(this));
    this.initialized = false;
  }
}

// Create singleton instance
const sseEventBridge = new SSEEventBridge();

export default sseEventBridge;
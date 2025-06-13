import { api } from '../utils/api';
import { useDataStore, useAppStore } from '../stores';
import SSEService from './SSEService';
import FrameService from './FrameService';
import { buildApiUrl } from '../config';

class CaptureService {
  static instance = null;
  
  constructor() {
    this.sseService = SSEService;
    this.frameService = FrameService.getInstance();
    this.captureSession = null;
    this.previewInterval = null;
    this.previewSourceKey = null; // Track which source the preview is for
    this.progressPolling = null;
    this.sourceCheckInterval = null;
    this.framePreloadInterval = null;
    
    // Bind methods
    this.handleCaptureEvent = this.handleCaptureEvent.bind(this);
    this.handleTakeEvent = this.handleTakeEvent.bind(this);
  }
  
  static getInstance() {
    if (!this.instance) {
      this.instance = new CaptureService();
    }
    return this.instance;
  }
  
  async initialize(takeId) {
    try {
      // Connect SSE
      await this.sseService.connect();
      
      // Subscribe to capture events
      this.sseService.subscribe('capture_events', this.handleCaptureEvent);
      this.sseService.subscribe(`take_${takeId}`, this.handleTakeEvent);
      
      // Initialize frame service for this take
      this.frameService.clearTakeFrames(takeId);
      
      return true;
    } catch (error) {
      console.error('Failed to initialize capture service:', error);
      throw error;
    }
  }
  
  async setSource(sourceType, sourceId, sourceName) {
    console.log('[CaptureService.setSource] Called with:', { sourceType, sourceId, sourceName });
    try {
      let response;
      
      switch (sourceType) {
        case 'camera':
          console.log('[CaptureService.setSource] Setting camera source:', sourceId);
          response = await api.setCameraSource(sourceId);
          break;
        case 'monitor':
        case 'screen':
          console.log('[CaptureService.setSource] Setting screen source:', sourceId);
          response = await api.setScreenSource(sourceId);
          break;
        case 'window':
          console.log('[CaptureService.setSource] Setting window source:', sourceId);
          response = await api.setWindowSource(sourceId);
          break;
        default:
          throw new Error(`Unknown source type: ${sourceType}`);
      }
      
      console.log('[CaptureService.setSource] Backend response:', response);
      
      // Update store with the source info
      const sourceObj = {
        type: sourceType,
        id: sourceId,
        name: sourceName
      };
      useDataStore.getState().setSource(sourceObj);
      
      console.log('[CaptureService.setSource] Source set in store:', sourceObj);
      
      return response;
    } catch (error) {
      console.error('[CaptureService.setSource] Failed to set source:', error);
      throw error;
    }
  }
  
  validateCapture() {
    const store = useDataStore.getState();
    
    if (!store.source) {
      throw new Error('No capture source selected');
    }
    
    if (store.isCapturing) {
      throw new Error('Capture already in progress');
    }
    
    // Clean up any stale session
    if (this.captureSession) {
      console.warn('Previous capture session found, cleaning up');
      this.captureSession = null;
    }
    
    return true;
  }
  
  async startCapture(takeId, options = {}) {
    const store = useDataStore.getState();
    const uiStore = useAppStore.getState();
    
    try {
      // Validate
      this.validateCapture();
      
      // Stop preview before starting capture
      this.stopPreview();
      
      // Initialize session
      this.captureSession = {
        takeId,
        startTime: Date.now(),
        frameRate: options.frameRate || 24,
        referenceFrameCount: options.frame_count_limit,
        skipDetectors: options.skip_detectors || false
      };
      
      // Update store (don't call store.startCapture as it would call this method again)
      store.startCapture(takeId, options);
      
      // Subscribe to SSE events for this take
      console.log('[CaptureService] Subscribing to take events for:', takeId);
      await this.sseService.subscribe(`take_${takeId}`, this.handleTakeEvent);
      
      // Also subscribe to general frame events
      await this.sseService.subscribe('frame_events', this.handleTakeEvent);
      
      // Use monitoring mode from options if provided, otherwise determine from page
      const currentPage = uiStore.currentPage;
      const isMonitoringMode = options.is_monitoring_mode !== undefined 
        ? options.is_monitoring_mode 
        : currentPage === 'take-monitoring';
      
      // Use reference take from options if provided, otherwise get it
      let referenceTakeId = options.reference_take_id;
      if (referenceTakeId === undefined && isMonitoringMode) {
        const currentAngle = store.currentAngle;
        if (currentAngle) {
          const referenceTake = store.getReferenceTakeForAngle(currentAngle.id);
          referenceTakeId = referenceTake?.id;
        }
      }
      
      // Start capture via API
      const response = await api.startCapture({
        take_id: takeId,
        frame_count_limit: options.frame_count_limit,
        skip_detectors: options.skip_detectors,
        is_monitoring_mode: isMonitoringMode,
        reference_take_id: referenceTakeId
      });
      
      // Start progress polling
      this.startProgressPolling(takeId);
      
      // Start source availability checking
      this.startSourceCheck();
      
      // Start frame preloading after a delay
      setTimeout(() => {
        this.startFramePreloading(takeId);
      }, 2000);
      
      return response;
      
    } catch (error) {
      // Cleanup on error
      this.captureSession = null;
      store.stopCapture();
      
      // User-friendly error messages
      const errorMessage = this.getErrorMessage(error);
      uiStore.addNotification({ type: 'error', message: errorMessage });
      
      throw error;
    }
  }
  
  async stopCapture() {
    const store = useDataStore.getState();
    const uiStore = useAppStore.getState();
    
    if (!this.captureSession) {
      console.warn('No active capture session');
      return;
    }
    
    try {
      // Stop all intervals first
      this.stopProgressPolling();
      this.stopSourceCheck();
      this.stopFramePreloading();
      
      // Stop capture via API
      await api.stopCapture();
      
      // Unsubscribe from events
      if (this.captureSession.takeId) {
        this.sseService.unsubscribe(`take_${this.captureSession.takeId}`);
        this.sseService.unsubscribe('frame_events');
      }
      
      // Update store
      store.stopCapture();
      
      // Clear preview since we were capturing
      this.stopPreview();
      
      // Log capture stats
      this.logCaptureStats();
      
      // Show completion notification
      const frames = store.captureProgress.capturedFrames;
      uiStore.addNotification({ type: 'success', message: `Capture completed: ${frames} frames` });
      
    } catch (error) {
      console.error('Error stopping capture:', error);
      uiStore.addNotification({ type: 'error', message: 'Failed to stop capture properly' });
      
    } finally {
      // Always cleanup
      this.captureSession = null;
    }
  }
  
  startProgressPolling(takeId) {
    let pollInterval = 250; // Start with 250ms
    const maxInterval = 2000; // Max 2 seconds
    
    const poll = async () => {
      if (!this.captureSession || this.captureSession.takeId !== takeId) {
        return;
      }
      
      try {
        const progress = await api.getCaptureProgress(takeId);
        console.log('[CaptureService] Progress poll result:', progress);
        const store = useDataStore.getState();
        
        store.updateCaptureProgress({
          capturedFrames: progress.frame_count,
          isComplete: !progress.is_capturing
        });
        
        // Also update the frame count for UI display
        store.updateFrameCount(progress.frame_count);
        console.log('[CaptureService] Updated frame count to:', progress.frame_count);
        
        // Stop polling if capture is complete
        if (!progress.is_capturing) {
          this.handleCaptureComplete();
          return;
        }
        
        // Continue polling with backoff
        pollInterval = Math.min(pollInterval * 1.5, maxInterval);
        this.progressPolling = setTimeout(poll, pollInterval);
        
      } catch (error) {
        console.error('Error polling progress:', error);
        // Retry with backoff
        this.progressPolling = setTimeout(poll, pollInterval);
      }
    };
    
    poll();
  }
  
  stopProgressPolling() {
    if (this.progressPolling) {
      clearTimeout(this.progressPolling);
      this.progressPolling = null;
    }
  }
  
  startSourceCheck() {
    const store = useDataStore.getState();
    const source = store.source;
    
    if (!source) return;
    
    let consecutiveFailures = 0;
    const maxFailures = 3;
    
    const check = async () => {
      if (!this.captureSession) {
        return;
      }
      
      try {
        let sourceStillExists = false;
        
        // Only check source availability for critical source types
        // Camera and window sources can disappear, monitors are more stable
        if (source.type === 'camera' || source.type === 'window') {
          switch (source.type) {
            case 'camera':
              const camerasResponse = await api.getCameras();
              const cameras = camerasResponse.cameras || [];
              sourceStillExists = cameras.some(c => c.id === source.id);
              break;
              
            case 'window':
              const windowsResponse = await api.getWindows();
              const windows = windowsResponse.windows || [];
              sourceStillExists = windows.some(w => w.handle === source.id);
              break;
          }
          
          if (!sourceStillExists) {
            consecutiveFailures++;
            if (consecutiveFailures >= maxFailures) {
              this.handleSourceDisconnected();
              return;
            }
          } else {
            consecutiveFailures = 0;
          }
        } else {
          // For monitor sources, just reset the failure count
          consecutiveFailures = 0;
        }
        
        // Continue checking with longer interval
        this.sourceCheckInterval = setTimeout(check, 5000);
        
      } catch (error) {
        console.error('Error checking source availability:', error);
        consecutiveFailures++;
        
        if (consecutiveFailures >= maxFailures) {
          this.handleSourceDisconnected();
        } else {
          this.sourceCheckInterval = setTimeout(check, 5000);
        }
      }
    };
    
    // Start checking after a delay
    this.sourceCheckInterval = setTimeout(check, 3000);
  }
  
  stopSourceCheck() {
    if (this.sourceCheckInterval) {
      clearTimeout(this.sourceCheckInterval);
      this.sourceCheckInterval = null;
    }
  }
  
  startFramePreloading(takeId) {
    if (!this.captureSession || this.captureSession.skipDetectors) {
      return;
    }
    
    const preloadNext = async () => {
      if (!this.captureSession || this.captureSession.takeId !== takeId) {
        return;
      }
      
      const store = useDataStore.getState();
      const currentFrame = store.captureProgress.capturedFrames;
      
      if (currentFrame > 0 && store.isCapturing) {
        // Preload last 3 frames
        const startFrame = Math.max(0, currentFrame - 3);
        this.frameService.loadFrames(takeId, startFrame, currentFrame - 1, {
          withBoundingBoxes: false
        }).catch(console.error);
      }
      
      if (store.isCapturing) {
        this.framePreloadInterval = setTimeout(preloadNext, 5000);
      }
    };
    
    preloadNext();
  }
  
  stopFramePreloading() {
    if (this.framePreloadInterval) {
      clearTimeout(this.framePreloadInterval);
      this.framePreloadInterval = null;
    }
  }
  
  async startPreview() {
    const store = useDataStore.getState();
    const source = store.source;
    
    console.log('CaptureService.startPreview called', { source, isCapturing: store.isCapturing });
    
    if (!source || store.isCapturing) {
      return;
    }
    
    // Create a unique key for this source
    const sourceKey = `${source.type}_${source.id}`;
    
    // If preview is already running for this exact source, don't restart
    if (this.previewInterval && this.previewSourceKey === sourceKey && store.isPreviewActive) {
      console.log('Preview already running for this source');
      return;
    }
    
    // CRITICAL: Stop any existing preview completely before starting a new one
    this.stopPreview();
    
    // Wait a bit to ensure cleanup
    await new Promise(resolve => setTimeout(resolve, 100));
    
    // Re-check conditions after cleanup
    const currentStore = useDataStore.getState();
    if (!currentStore.source || currentStore.isCapturing) {
      console.log('Preview cancelled: no source or capturing');
      return;
    }
    
    // Store the source key
    this.previewSourceKey = sourceKey;
    
    // Mark preview as active BEFORE starting the fetch loop
    console.log('[CaptureService.startPreview] Setting preview active for source:', sourceKey);
    useDataStore.getState().setPreviewActive(true);
    
    const fetchPreview = async () => {
      // Get fresh store state
      const currentStore = useDataStore.getState();
      if (!currentStore.source || currentStore.isCapturing || !currentStore.isPreviewActive) {
        console.log('Preview fetch skipped:', { 
          hasSource: !!currentStore.source, 
          isCapturing: currentStore.isCapturing, 
          isPreviewActive: currentStore.isPreviewActive 
        });
        this.stopPreview();
        return;
      }
      
      try {
        let url;
        
        // Use the current source from the store, NOT the closure
        const currentSource = currentStore.source;
        if (!currentSource) {
          console.log('No source in current store');
          return;
        }
        
        // Use consistent endpoint for all sources
        if (currentStore.source === currentSource) {
          // Use the /api/capture/preview endpoint that works with the current source
          url = buildApiUrl(`api/capture/preview?quality=80&t=${Date.now()}`);
        } else {
          console.log('Source changed during preview fetch');
          return;
        }
        
        console.log('Fetching preview from:', url);
        
        const response = await fetch(url, {
          headers: {
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
          }
        });
        
        if (response.ok) {
          const data = await response.json();
          if (data?.frame) {
            // Check if frame already includes data:image prefix
            const frameData = data.frame.startsWith('data:') 
              ? data.frame 
              : `data:image/jpeg;base64,${data.frame}`;
            
            // Only update if we're still active
            const currentState = useDataStore.getState();
            // Always update preview frame when not capturing
            if (!currentState.isCapturing) {
              console.log('Updating preview frame in store', {
                frameDataLength: frameData.length,
                frameDataPrefix: frameData.substring(0, 50)
              });
              currentState.updatePreviewFrame(frameData);
              currentState.setPreviewError(null);
            } else {
              console.log('Preview frame received but not updating (capturing):', {
                isPreviewActive: currentState.isPreviewActive,
                isCapturing: currentState.isCapturing
              });
            }
          } else {
            console.error('CaptureService - No frame in response:', data);
          }
        } else {
          throw new Error(`Preview unavailable (${response.status})`);
        }
      } catch (error) {
        console.error('Preview fetch error:', error);
        const currentStore = useDataStore.getState();
        if (currentStore.isPreviewActive && !currentStore.isCapturing) {
          currentStore.setPreviewError(error.message);
        }
      }
    };
    
    // Initial fetch with a small delay to ensure backend is ready
    setTimeout(async () => {
      await fetchPreview();
      
      // Set up interval only if still active
      const currentStore = useDataStore.getState();
      if (currentStore.isPreviewActive && !currentStore.isCapturing) {
        const fps = source.type === 'camera' ? 5 : 10;
        const intervalMs = Math.round(1000 / fps);
        
        this.previewInterval = setInterval(fetchPreview, intervalMs);
      }
    }, 100);
  }
  
  stopPreview() {
    console.log('[CaptureService.stopPreview] Stopping preview for source:', this.previewSourceKey);
    
    if (this.previewInterval) {
      clearInterval(this.previewInterval);
      this.previewInterval = null;
    }
    
    // Clear the source key
    this.previewSourceKey = null;
    
    // Update store state atomically
    const store = useDataStore.getState();
    store.setPreviewActive(false);
    // Don't clear preview frame here - let it be cleared explicitly when needed
    store.setPreviewError(null);
  }
  
  handleCaptureComplete() {
    const store = useDataStore.getState();
    const uiStore = useAppStore.getState();
    
    console.log('Capture completed');
    
    // Stop all intervals
    this.stopProgressPolling();
    this.stopSourceCheck();
    this.stopFramePreloading();
    
    // Log stats
    this.logCaptureStats();
    
    // Update store
    store.stopCapture();
    
    // Clear session
    const completedSession = this.captureSession;
    this.captureSession = null;
    
    // Notify UI with stats
    if (completedSession) {
      const duration = (Date.now() - completedSession.startTime) / 1000;
      const frames = store.captureProgress.capturedFrames;
      const fps = frames / duration;
      
      uiStore.addNotification({ 
        type: 'success', 
        message: `Capture completed: ${frames} frames in ${duration.toFixed(1)}s (${fps.toFixed(1)} fps)`
      });
    }
  }
  
  handleSourceDisconnected() {
    const store = useDataStore.getState();
    const uiStore = useAppStore.getState();
    
    console.log('Source disconnected');
    
    // Stop capture if active
    if (this.captureSession) {
      this.stopCapture().then(() => {
        // Show disconnection modal
        uiStore.openModal('sourceDisconnected', {
          sourceName: store.source?.name || 'Capture source',
          wasCapturing: true
        });
      });
    } else {
      // Just notify
      uiStore.addNotification({ type: 'warning', message: 'Capture source disconnected' });
      // Clear source
      store.clearSource();
    }
  }
  
  handleCaptureEvent(event) {
    const store = useDataStore.getState();
    const uiStore = useAppStore.getState();
    
    switch (event.type) {
      case 'source_disconnected':
        console.log('Source disconnected event received:', event.data);
        this.handleSourceDisconnected();
        break;
        
      case 'capture_started':
        console.log('Capture started event:', event.data);
        break;
        
      case 'capture_stopped':
        if (event.data?.take_id === this.captureSession?.takeId) {
          this.handleCaptureComplete();
        }
        break;
        
      case 'capture_error':
        console.error('Capture error:', event.data);
        const errorMsg = event.data?.error || 'Unknown capture error';
        uiStore.addNotification({ type: 'error', message: `Capture error: ${errorMsg}` });
        
        // Stop capture on error
        this.stopCapture();
        break;
        
      case 'source_disconnected':
        this.handleSourceDisconnected();
        break;
        
      case 'frame_dropped':
        console.warn('Frame dropped:', event.data);
        if (event.data?.count > 5) {
          uiStore.addNotification({ type: 'warning', message: 'Multiple frames dropped - performance issue detected' });
        }
        break;
    }
  }
  
  handleTakeEvent(event) {
    const store = useDataStore.getState();
    
    console.log('[CaptureService] Take event received:', event.type, event.data);
    console.log('[CaptureService] Full event object:', JSON.stringify(event, null, 2));
    
    // Handle both direct events and wrapped data
    const eventData = event.data || event;
    
    switch (event.type) {
      case 'frame_captured':
        // Update progress and frame count
        const frameCount = eventData.frame_count || (eventData.frame_index !== undefined ? eventData.frame_index + 1 : 0);
        console.log('[CaptureService] Frame captured - updating count to:', frameCount);
        console.log('[CaptureService] Event data details:', {
          frame_count: eventData.frame_count,
          frameIndex: eventData.frameIndex,
          frame_index: eventData.frame_index,
          take_id: eventData.take_id
        });
        store.updateCaptureProgress({
          capturedFrames: frameCount
        });
        
        // Update frame count in capture store
        store.updateFrameCount(frameCount);
        break;
        
      case 'frame_processed':
        // Update processed count
        store.updateCaptureProgress({
          processedFrames: event.data.processed_count
        });
        break;
        
      case 'detector_complete':
        // Update detector progress
        if (event.data?.detector_name) {
          console.log(`Detector ${event.data.detector_name} completed`);
        }
        break;
        
      case 'capture_complete':
        // Handle capture completion
        if (event.data?.take_id === this.captureSession?.takeId) {
          this.handleCaptureComplete();
        }
        break;
    }
  }
  
  logCaptureStats() {
    if (!this.captureSession) return;
    
    const store = useDataStore.getState();
    const duration = (Date.now() - this.captureSession.startTime) / 1000;
    const frames = store.captureProgress.capturedFrames;
    const targetFps = this.captureSession.frameRate;
    const actualFps = frames / duration;
    
    console.log('Capture Statistics:', {
      takeId: this.captureSession.takeId,
      duration: `${duration.toFixed(2)}s`,
      frames,
      targetFps,
      actualFps: actualFps.toFixed(2),
      efficiency: `${((actualFps / targetFps) * 100).toFixed(1)}%`
    });
  }
  
  getErrorMessage(error) {
    if (error.message.includes('No capture source')) {
      return 'Please select a capture source first';
    }
    if (error.message.includes('already in progress')) {
      return 'A capture is already in progress';
    }
    if (error.message.includes('Camera disconnected')) {
      return 'Camera disconnected. Please reconnect and try again.';
    }
    if (error.message.includes('Permission denied')) {
      return 'Camera/screen access permission denied';
    }
    if (error.message.includes('Network')) {
      return 'Network error - please check your connection';
    }
    
    return `Capture failed: ${error.message}`;
  }
  
  cleanup() {
    this.stopPreview();
    this.stopProgressPolling();
    this.stopSourceCheck();
    this.stopFramePreloading();
    
    if (this.captureSession) {
      this.sseService.unsubscribe(`take_${this.captureSession.takeId}`);
    }
    
    this.sseService.unsubscribe('capture_events', this.handleCaptureEvent);
    this.captureSession = null;
  }
  
  getCaptureStats() {
    if (!this.captureSession) return null;
    
    const store = useDataStore.getState();
    const duration = (Date.now() - this.captureSession.startTime) / 1000;
    
    return {
      takeId: this.captureSession.takeId,
      duration,
      frames: store.captureProgress.capturedFrames,
      fps: store.captureProgress.capturedFrames / duration,
      isActive: store.isCapturing
    };
  }
}

export default CaptureService;
import { api } from '../utils/api';
import { useDataStore, useAppStore } from '../stores';
import SSEService from './SSEService';
import asyncOperationManager from '../utils/AsyncOperationManager';
import { buildApiUrl } from '../config';

class DetectorService {
  static instance = null;
  
  constructor() {
    this.sseService = SSEService;
    this.detectorSchemas = new Map();
    this.processingSession = null;
    
    // Create managed operations
    this.createManagedOperations();
  }
  
  static getInstance() {
    if (!this.instance) {
      this.instance = new DetectorService();
    }
    return this.instance;
  }
  
  createManagedOperations() {
    // Wrap API calls with async operation manager
    this.managedOps = {
      getDetectors: asyncOperationManager.createOperation(
        'getDetectors',
        async () => {
          const response = await api.getDetectors();
          // Handle response format
          let detectors = [];
          if (Array.isArray(response)) {
            detectors = response;
          } else if (response?.detectors) {
            detectors = response.detectors;
          }
          return detectors;
        },
        {
          timeout: 30000,
          retries: 2,
          showNotifications: false
        }
      ),
      
      getDetectorSchema: asyncOperationManager.createOperation(
        'getDetectorSchema',
        async (detectorName) => {
          // Check cache first
          if (this.detectorSchemas.has(detectorName)) {
            return this.detectorSchemas.get(detectorName);
          }
          
          const schema = await api.getDetectorSchema(detectorName);
          console.log(`DetectorService - Schema received for ${detectorName}:`, schema);
          
          // Cache the schema
          this.detectorSchemas.set(detectorName, schema);
          
          return schema;
        },
        {
          timeout: 15000,
          retries: 1,
          onError: (error) => {
            console.error(`Failed to load schema for detector:`, error);
          }
        }
      ),
      
      startProcessing: asyncOperationManager.createOperation(
        'startProcessing',
        async (takeId, referenceTakeId, options = {}) => {
          const store = useDataStore.getState();
          
          if (this.processingSession) {
            throw new Error('Processing already in progress');
          }
          
          // Initialize session
          this.processingSession = {
            takeId,
            referenceTakeId,
            startTime: Date.now(),
            detectors: options.detectors || []
          };
          
          // Update store
          store.startProcessing();
          
          // Subscribe to processing events
          await this.sseService.subscribe('detector_events', this.handleDetectorEvent);
          await this.sseService.subscribe(`processing_${takeId}`, this.handleProcessingEvent);
          
          // Start processing via API
          const response = await api.startProcessing(takeId, referenceTakeId);
          
          // Start monitoring
          this.startProcessingMonitor(takeId);
          
          return response;
        },
        {
          timeout: 30000,
          retries: 0,
          successMessage: 'Processing started successfully',
          onError: (error) => {
            // Cleanup on error
            this.processingSession = null;
            useDataStore.getState().stopProcessing();
          }
        }
      ),
      
      stopProcessing: asyncOperationManager.createOperation(
        'stopProcessing',
        async () => {
          if (!this.processingSession) {
            console.warn('No active processing session');
            return;
          }
          
          // Stop monitoring
          this.stopProcessingMonitor();
          
          // Stop processing via API
          await api.stopProcessing();
          
          // Unsubscribe from events
          if (this.processingSession.takeId) {
            await this.sseService.unsubscribe(`processing_${this.processingSession.takeId}`);
          }
          
          // Update store
          useDataStore.getState().stopProcessing();
          
          // Clear session
          this.processingSession = null;
        },
        {
          timeout: 10000,
          successMessage: 'Processing stopped'
        }
      ),
      
      installDetector: asyncOperationManager.createOperation(
        'installDetector',
        async (file, options = {}) => {
          const formData = new FormData();
          formData.append('file', file);
          
          // Use XMLHttpRequest for progress tracking
          return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            
            // Track upload progress
            xhr.upload.addEventListener('progress', (e) => {
              if (e.lengthComputable && options.onProgress) {
                const percentComplete = Math.round((e.loaded / e.total) * 90); // 0-90% for upload
                options.onProgress(percentComplete);
              }
            });
            
            xhr.addEventListener('load', () => {
              if (xhr.status === 200) {
                try {
                  const result = JSON.parse(xhr.responseText);
                  
                  // Clear schema cache for new detector
                  this.detectorSchemas.clear();
                  
                  // Show 100% complete
                  if (options.onProgress) {
                    options.onProgress(100);
                  }
                  
                  resolve(result);
                } catch (error) {
                  reject(new Error('Failed to parse response'));
                }
              } else {
                reject(new Error(xhr.responseText || `HTTP ${xhr.status}`));
              }
            });
            
            xhr.addEventListener('error', () => {
              reject(new Error('Network error'));
            });
            
            xhr.open('POST', buildApiUrl('api/detectors/install?force_reinstall=true'));
            xhr.send(formData);
          });
        },
        {
          timeout: 60000,
          retries: 0,
          successMessage: 'Detector installed successfully',
          onSuccess: () => {
            // Refresh detector list
            this.managedOps.getDetectors();
          }
        }
      )
    };
  }
  
  // Public methods now use managed operations
  async getDetectors() {
    return this.managedOps.getDetectors();
  }
  
  async getDetectorSchema(detectorName) {
    return this.managedOps.getDetectorSchema(detectorName);
  }
  
  async startProcessing(takeId, referenceTakeId, options) {
    return this.managedOps.startProcessing(takeId, referenceTakeId, options);
  }
  
  async stopProcessing() {
    return this.managedOps.stopProcessing();
  }
  
  async installDetector(file) {
    return this.managedOps.installDetector(file);
  }
  
  /**
   * Get detector location
   */
  async getDetectorLocation(detectorName) {
    try {
      const response = await fetch(buildApiUrl(`api/detectors/${encodeURIComponent(detectorName)}/location`));
      
      if (!response.ok) {
        const error = await response.text();
        throw new Error(error || 'Failed to get detector location');
      }
      
      return await response.json();
    } catch (error) {
      console.error('Error getting detector location:', error);
      throw error;
    }
  }
  
  /**
   * Uninstall detector
   */
  async uninstallDetector(detectorName) {
    try {
      const response = await fetch(buildApiUrl(`api/detectors/uninstall/${encodeURIComponent(detectorName)}`), {
        method: 'DELETE'
      });
      
      if (!response.ok) {
        let errorMessage = 'Failed to uninstall detector';
        try {
          const errorData = await response.json();
          errorMessage = errorData.detail || errorMessage;
        } catch (e) {
          // If parsing fails, try text
          try {
            errorMessage = await response.text() || errorMessage;
          } catch (e2) {
            // Use default message
          }
        }
        throw new Error(errorMessage);
      }
      
      const result = await response.json();
      const appStore = useAppStore.getState();
      appStore.addNotification({
        type: 'success',
        message: result.message || `${detectorName} uninstalled successfully`
      });
      
      // Refresh detector list
      await this.managedOps.getDetectors();
      
      return result;
    } catch (error) {
      console.error('Error uninstalling detector:', error);
      const appStore = useAppStore.getState();
      appStore.addNotification({
        type: 'error',
        message: error.message || 'Failed to uninstall detector'
      });
      throw error;
    }
  }
  
  /**
   * Cleanup service
   */
  // Event handlers
  handleDetectorEvent = (event) => {
    console.log('Detector event:', event);
    // Handle detector-specific events
    const store = useDataStore.getState();
    
    if (event.type === 'detector_result' && event.data) {
      store.updateDetectorResults(event.data);
    } else if (event.type === 'detector_error' && event.data) {
      store.addDetectorError(event.data);
    }
  };
  
  handleProcessingEvent = (event) => {
    console.log('Processing event:', event);
    // Handle processing-specific events
    const store = useDataStore.getState();
    
    if (event.type === 'processing_progress' && event.data) {
      store.updateProcessingProgress(event.data);
    } else if (event.type === 'processing_complete') {
      this.stopProcessingMonitor();
      store.completeProcessing();
    }
  };
  
  // Processing monitor
  startProcessingMonitor(takeId) {
    // Implementation for monitoring processing progress
    console.log(`Starting processing monitor for take ${takeId}`);
  }
  
  stopProcessingMonitor() {
    // Implementation for stopping processing monitor
    console.log('Stopping processing monitor');
  }
  
  /**
   * Restart processing for a take
   */
  async restartProcessing(takeId, referenceTakeId = null) {
    try {
      console.log(`[DetectorService] Restarting processing for take ${takeId} with reference ${referenceTakeId}`);
      
      // Update store to show processing state
      const store = useDataStore.getState();
      store.startRedoDetection();
      
      // Subscribe to processing events before starting
      await this.sseService.subscribe('detector_events', this.handleDetectorEvent);
      await this.sseService.subscribe(`processing_${takeId}`, this.handleProcessingEvent);
      
      // Call API to restart processing
      const response = await api.restartProcessing(takeId, referenceTakeId);
      
      console.log('[DetectorService] Processing restart response:', response);
      
      // Don't clear the state here - wait for processing_complete event from SSE
      // The backend will send the appropriate events when processing actually completes
      
      return response;
    } catch (error) {
      console.error('[DetectorService] Failed to restart processing:', error);
      
      // Update store on error
      const store = useDataStore.getState();
      store.stopProcessing();
      
      // Unsubscribe on error
      await this.sseService.unsubscribe(`processing_${takeId}`);
      
      throw error;
    }
  }

  /**
   * Cleanup service
   */
  cleanup() {
    this.stopProcessingMonitor();
    
    if (this.processingSession) {
      this.sseService.unsubscribe(`processing_${this.processingSession.takeId}`);
    }
    
    this.sseService.unsubscribe('detector_events');
    this.processingSession = null;
  }
}

export default DetectorService;
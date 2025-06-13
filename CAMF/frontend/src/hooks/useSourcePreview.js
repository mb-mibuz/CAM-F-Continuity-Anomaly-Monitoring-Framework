import { useState, useEffect, useCallback, useRef } from 'react';
import { useDataStore } from '../stores';
import { useCaptureSources } from '../queries/hooks';
import { api } from '../utils/api';
import config, { buildApiUrl } from '../config';

/**
 * Hook for managing capture source selection and preview
 * @param {Object} options - Preview options
 * @returns {Object} Source preview state and controls
 */
export function useSourcePreview(options = {}) {
  const {
    autoStartPreview = true,
    previewQuality = 50,
    previewFps = null, // null = auto based on source type
    onSourceChange,
    onPreviewError
  } = options;
  
  // Store state
  const source = useDataStore(state => state.source);
  const isCapturing = useDataStore(state => state.isCapturing);
  const hasFrames = useDataStore(state => state.frameCount > 0);
  const setSource = useDataStore(state => state.setSource);
  const storePreviewFrame = useDataStore(state => state.previewFrame);
  const storeIsPreviewActive = useDataStore(state => state.isPreviewActive);
  const storePreviewError = useDataStore(state => state.previewError);
  
  // Local state
  const [previewFrame, setPreviewFrame] = useState(null);
  const [isPreviewActive, setIsPreviewActive] = useState(false);
  const [previewError, setPreviewError] = useState(null);
  const [sourceAvailability, setSourceAvailability] = useState({});
  
  // Refs
  const previewInterval = useRef(null);
  const availabilityInterval = useRef(null);
  const isMountedRef = useRef(true);
  
  // Query for available sources
  const { data: availableSources, refetch: refetchSources } = useCaptureSources();
  
  useEffect(() => {
    return () => {
      isMountedRef.current = false;
      stopPreview();
      stopAvailabilityCheck();
    };
  }, []);
  
  // Auto-start preview when conditions are met
  useEffect(() => {
    if (autoStartPreview && source && !isCapturing && !hasFrames) {
      startPreview();
    } else {
      stopPreview();
    }
  }, [source, isCapturing, hasFrames, autoStartPreview]);
  
  // Check source availability
  useEffect(() => {
    if (source && !hasFrames) {
      startAvailabilityCheck();
    } else {
      stopAvailabilityCheck();
    }
  }, [source, hasFrames]);
  
  // Select a source
  const selectSource = useCallback(async (sourceType, sourceId, sourceName) => {
    try {
      // Stop current preview only if changing source
      const currentSource = source;
      if (currentSource && (currentSource.type !== sourceType || currentSource.id !== sourceId)) {
        stopPreview();
        const dataStore = useDataStore.getState();
        dataStore.updatePreviewFrame(null);
        dataStore.setPreviewError(null);
      }
      
      // Set source via API
      switch (sourceType) {
        case 'camera':
          await api.setCameraSource(sourceId);
          break;
        case 'monitor':
        case 'screen':
          await api.setScreenSource(sourceId);
          break;
        case 'window':
          await api.setWindowSource(sourceId);
          break;
        default:
          throw new Error(`Unknown source type: ${sourceType}`);
      }
      
      // Update store
      setSource({ type: sourceType, id: sourceId, name: sourceName });
      
      // Call callback
      onSourceChange?.({ type: sourceType, id: sourceId, name: sourceName });
      
      return true;
    } catch (error) {
      console.error('Failed to set source:', error);
      const dataStore = useDataStore.getState();
      dataStore.setPreviewError(error.message);
      onPreviewError?.(error);
      return false;
    }
  }, [setSource, onSourceChange, onPreviewError]);
  
  // Clear source
  const clearSource = useCallback(() => {
    stopPreview();
    setSource(null);
    const dataStore = useDataStore.getState();
    dataStore.updatePreviewFrame(null);
    dataStore.setPreviewError(null);
  }, [setSource]);
  
  // Start preview
  const startPreview = useCallback(async () => {
    if (!source || storeIsPreviewActive) return;
    
    console.log('Starting preview for source:', source);
    const dataStore = useDataStore.getState();
    dataStore.setPreviewActive(true);
    dataStore.setPreviewError(null);
    
    // For camera sources, ensure it's set as capture source
    if (source.type === 'camera') {
      try {
        const status = await api.getCaptureStatus();
        if (status.source_type !== 'camera' || status.source_id !== source.id) {
          await api.setCameraSource(source.id);
          await new Promise(resolve => setTimeout(resolve, 500));
        }
      } catch (error) {
        console.error('Failed to set camera for preview:', error);
        const dataStore = useDataStore.getState();
        dataStore.setPreviewError('Failed to initialize camera');
        onPreviewError?.(error);
        return;
      }
    }
    
    const fetchPreview = async () => {
      if (!isMountedRef.current || !source) return;
      
      try {
        let url;
        
        if (source.type === 'camera') {
          url = buildApiUrl(`api/capture/preview/current?quality=${previewQuality}&t=${Date.now()}`);
        } else {
          const apiSourceType = source.type === 'monitor' ? 'screen' : source.type;
          url = buildApiUrl(`api/capture/preview/${apiSourceType}/${source.id}?quality=${previewQuality}&t=${Date.now()}`);
        }
        
        const response = await fetch(url, {
          headers: {
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
          }
        });
        
        if (response.ok) {
          const data = await response.json();
          if (data?.frame && isMountedRef.current) {
            const frameData = `data:image/jpeg;base64,${data.frame}`;
            
            // Update the store so other components can use the preview
            const dataStore = useDataStore.getState();
            dataStore.updatePreviewFrame(frameData);
            dataStore.setPreviewError(null);
          }
        } else {
          throw new Error(`Preview unavailable (${response.status})`);
        }
      } catch (error) {
        console.error('Preview fetch error:', error);
        if (isMountedRef.current) {
          const dataStore = useDataStore.getState();
          dataStore.setPreviewError(error.message);
          onPreviewError?.(error);
        }
      }
    };
    
    // Initial fetch
    await fetchPreview();
    
    // Set up interval
    const fps = previewFps || (source.type === 'camera' ? 5 : 10);
    const intervalMs = Math.round(1000 / fps);
    
    previewInterval.current = setInterval(fetchPreview, intervalMs);
  }, [source, storeIsPreviewActive, previewQuality, previewFps, onPreviewError]);
  
  // Stop preview
  const stopPreview = useCallback(() => {
    console.log('Stopping preview');
    const dataStore = useDataStore.getState();
    dataStore.setPreviewActive(false);
    
    if (previewInterval.current) {
      clearInterval(previewInterval.current);
      previewInterval.current = null;
    }
    
    // Don't clear preview frame when stopping - let it persist
    // It will be replaced by actual frames during capture
  }, []);
  
  // Check source availability
  const startAvailabilityCheck = useCallback(() => {
    const checkAvailability = async () => {
      if (!source || !isMountedRef.current) return;
      
      const sources = await refetchSources();
      if (!sources || !isMountedRef.current) return;
      
      let isAvailable = false;
      
      switch (source.type) {
        case 'camera':
          isAvailable = sources.data?.cameras?.some(c => c.id === source.id) || false;
          break;
        case 'monitor':
          isAvailable = sources.data?.monitors?.some(m => m.id === source.id) || false;
          break;
        case 'window':
          isAvailable = sources.data?.windows?.some(w => w.handle === source.id) || false;
          break;
      }
      
      setSourceAvailability(prev => ({
        ...prev,
        [source.id]: isAvailable
      }));
      
      if (!isAvailable) {
        console.log('Source disconnected:', source.name);
        const dataStore = useDataStore.getState();
        dataStore.setPreviewError('Source disconnected');
        onPreviewError?.(new Error('Source disconnected'));
      }
    };
    
    // Initial check
    checkAvailability();
    
    // Set up interval
    availabilityInterval.current = setInterval(checkAvailability, 2000);
  }, [source, refetchSources, onPreviewError]);
  
  // Stop availability check
  const stopAvailabilityCheck = useCallback(() => {
    if (availabilityInterval.current) {
      clearInterval(availabilityInterval.current);
      availabilityInterval.current = null;
    }
  }, []);
  
  // Get grouped sources
  const getGroupedSources = useCallback(() => {
    if (!availableSources) {
      return { cameras: [], monitors: [], windows: [] };
    }
    
    return {
      cameras: availableSources.cameras || [],
      monitors: availableSources.monitors || [],
      windows: availableSources.windows || []
    };
  }, [availableSources]);
  
  // Check if a source is available
  const isSourceAvailable = useCallback((sourceId) => {
    return sourceAvailability[sourceId] !== false;
  }, [sourceAvailability]);
  
  return {
    // State
    source,
    previewFrame: storePreviewFrame,
    isPreviewActive: storeIsPreviewActive,
    previewError: storePreviewError,
    availableSources: getGroupedSources(),
    
    // Actions
    selectSource,
    clearSource,
    startPreview,
    stopPreview,
    refetchSources,
    
    // Computed
    hasSource: !!source,
    canPreview: !!source && !isCapturing,
    isSourceAvailable,
    
    // Utilities
    getSourceType: () => source?.type || null,
    getSourceName: () => source?.name || 'No source selected'
  };
}
// src/hooks/useCapture.js
import { useCallback, useEffect, useRef } from 'react';
import { useDataStore, useAppStore } from '../../stores';
import { CaptureService } from '../../services';
import { shallow } from '../../stores/utils/shallow';
import { useProcessingStore } from '../../stores';

/**
 * Hook for managing capture operations
 * @param {string} takeId - Current take ID
 * @param {Object} options - Hook options
 * @returns {Object} Capture state and controls
 */
export function useCapture(takeId, options = {}) {
  const {
    onCaptureStart,
    onCaptureComplete,
    onCaptureError,
    referenceFrameCount,
    skipDetectors = false
  } = options;
  
  // Get state from store
  const {
    source,
    isCapturing,
    captureProgress,
    frameCount,
    setSource,
    startCapture: storeStartCapture,
    stopCapture: storeStopCapture,
    updateCaptureProgress
  } = useDataStore(
    state => ({
      source: state.source,
      isCapturing: state.isCapturing,
      captureProgress: state.captureProgress,
      frameCount: state.frameCount,
      setSource: state.setSource,
      startCapture: state.startCapture,
      stopCapture: state.stopCapture,
      updateCaptureProgress: state.updateCaptureProgress
    }),
    shallow
  );
  
  const addNotification = useAppStore(state => state.addNotification);
  
  // Service instance
  const captureService = useRef(null);
  const isMountedRef = useRef(true);
  
  useEffect(() => {
    captureService.current = CaptureService.getInstance();
    
    return () => {
      isMountedRef.current = false;
    };
  }, []);
  
  // Initialize capture service for the take
  useEffect(() => {
    if (takeId && captureService.current) {
      captureService.current.initialize(takeId).catch(error => {
        console.error('Failed to initialize capture service:', error);
      });
    }
  }, [takeId]);
  
  // Set capture source
  const setSourceWithService = useCallback(async (sourceType, sourceId, sourceName) => {
    try {
      await captureService.current.setSource(sourceType, sourceId, sourceName);
      return true;
    } catch (error) {
      addNotification({ type: 'error', message: `Failed to set capture source: ${error.message}` });
      return false;
    }
  }, [addNotification]);
  
  // Start capture
  const startCapture = useCallback(async () => {
    if (!source) {
      addNotification({ type: 'warning', message: 'Please select a capture source first' });
      return false;
    }
    
    if (!takeId) {
      addNotification({ type: 'error', message: 'No take selected' });
      return false;
    }
    
    try {
      // Call lifecycle hook
      onCaptureStart?.();
      
      // Start capture through service
      await captureService.current.startCapture(takeId, {
        frame_count_limit: referenceFrameCount,
        skip_detectors: skipDetectors
      });
      
      return true;
    } catch (error) {
      console.error('Failed to start capture:', error);
      addNotification({ type: 'error', message: `Failed to start capture: ${error.message}` });
      onCaptureError?.(error);
      return false;
    }
  }, [source, takeId, referenceFrameCount, skipDetectors, addNotification, onCaptureStart, onCaptureError]);
  
  // Stop capture
  const stopCapture = useCallback(async () => {
    try {
      await captureService.current.stopCapture();
      
      // Call lifecycle hook
      onCaptureComplete?.();
      
      return true;
    } catch (error) {
      console.error('Failed to stop capture:', error);
      addNotification({ type: 'error', message: `Failed to stop capture: ${error.message}` });
      return false;
    }
  }, [addNotification, onCaptureComplete]);
  
  // Check if ready to capture
  const canStartCapture = source && !isCapturing && frameCount === 0;
  const canStopCapture = isCapturing;
  
  // Get capture duration
  const getCaptureDuration = useCallback(() => {
    if (!isCapturing || !captureProgress.startTime) {
      return '00:00';
    }
    
    const elapsed = Date.now() - captureProgress.startTime;
    const seconds = Math.floor(elapsed / 1000);
    const minutes = Math.floor(seconds / 60);
    const displaySeconds = seconds % 60;
    
    return `${minutes.toString().padStart(2, '0')}:${displaySeconds.toString().padStart(2, '0')}`;
  }, [isCapturing, captureProgress.startTime]);
  
  // Get capture progress percentage
  const getCaptureProgress = useCallback(() => {
    if (!referenceFrameCount || referenceFrameCount === 0) {
      return 0;
    }
    
    return Math.min((captureProgress.capturedFrames / referenceFrameCount) * 100, 100);
  }, [captureProgress.capturedFrames, referenceFrameCount]);
  
  return {
    // State
    source,
    isCapturing,
    captureProgress,
    frameCount,
    
    // Actions
    setSource: setSourceWithService,
    startCapture,
    stopCapture,
    
    // Computed
    canStartCapture,
    canStopCapture,
    captureDuration: getCaptureDuration(),
    captureProgressPercent: getCaptureProgress(),
    
    // Utilities
    isSourceConnected: !!source,
    hasFrames: frameCount > 0
  };
}
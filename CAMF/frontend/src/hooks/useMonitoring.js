import { useState, useEffect, useCallback, useRef } from 'react';
import { useDataStore, useAppStore } from '../stores';
import { useCapture } from '../queries/hooks/useCapture';
import { useFrameNavigation } from './useFrameNavigation';
import { useSSEEvents } from './useSSE';
import { useProcessGuard } from './useProcessGuard';
import { api } from '../utils/api';

/**
 * High-level hook for take monitoring page
 * Combines multiple hooks for comprehensive monitoring functionality
 * @param {Object} params - Monitoring parameters
 * @returns {Object} Complete monitoring state and controls
 */
export function useMonitoring({
  takeId,
  angleId,
  sceneId,
  referenceFrameCount,
  referenceTakeId
}) {
  // Local state
  const [sceneData, setSceneData] = useState(null);
  const [detectorErrors, setDetectorErrors] = useState([]);
  const [availableTakes, setAvailableTakes] = useState([]);
  const [notes, setNotes] = useState('');
  const [isInitialized, setIsInitialized] = useState(false);
  
  // Store states
  const notify = useAppStore(state => state.notify);
  const hasProcessedFrames = useDataStore(state => state.hasProcessedFrames);
  const setHasProcessedFrames = useDataStore(state => state.setHasProcessedFrames);
  
  // Compose hooks
  const capture = useCapture(takeId, {
    referenceFrameCount,
    skipDetectors: false,
    onCaptureComplete: () => {
      loadDetectorErrors();
    }
  });
  
  const navigation = useFrameNavigation(takeId, {
    withBoundingBoxes: hasProcessedFrames,
    preloadRadius: 3,
    onFrameChange: (frameIndex) => {
      // Update frame-specific errors if needed
    }
  });
  
  const processGuard = useProcessGuard({
    processName: 'Take Monitoring',
    allowForceStop: true
  });
  
  // SSE event handlers
  const sseEventHandlers = {
    capture_events: (event) => {
      if (event.type === 'capture_stopped' && event.data?.take_id === takeId) {
        capture.onCaptureComplete?.();
      }
    },
    detector_events: (event) => {
      if (event.type === 'detector_error' && event.data?.take_id === takeId) {
        loadDetectorErrors();
      }
    },
    [`take_${takeId}`]: (event) => {
      // Handle take-specific events
      console.log('Take event:', event);
    }
  };
  
  useSSEEvents(sseEventHandlers, { enabled: isInitialized });
  
  // Initialize monitoring
  useEffect(() => {
    if (!takeId || !angleId || !sceneId) return;
    
    initializeMonitoring();
  }, [takeId, angleId, sceneId]);
  
  const initializeMonitoring = async () => {
    try {
      // Load scene data
      const scene = await api.getScene(sceneId);
      setSceneData(scene);
      
      // Load take data
      const take = await api.getTake(takeId);
      setNotes(take.notes || '');
      
      // Load available takes for reference
      await loadAvailableTakes();
      
      // Check for existing frames
      const frameCount = await api.getFrameCount(takeId);
      if (frameCount > 0) {
        // Check if we have processed frames
        const errors = await api.getTakeErrors(takeId);
        setHasProcessedFrames(errors && errors.length > 0);
      }
      
      // Load detector errors
      await loadDetectorErrors();
      
      setIsInitialized(true);
    } catch (error) {
      console.error('Error initializing monitoring:', error);
      notify.error('Failed to initialize monitoring');
    }
  };
  
  const loadAvailableTakes = async () => {
    try {
      const angles = await api.getAngles(sceneId);
      const allTakes = [];
      
      for (const angle of angles) {
        const takes = await api.getTakes(angle.id);
        takes.forEach(take => {
          allTakes.push({
            ...take,
            angleName: angle.name,
            angleId: angle.id,
            isCurrentTake: take.id === takeId
          });
        });
      }
      
      setAvailableTakes(allTakes);
    } catch (error) {
      console.error('Error loading available takes:', error);
    }
  };
  
  const loadDetectorErrors = async () => {
    try {
      const errors = await api.getTakeErrors(takeId);
      
      // Group continuous errors
      const groupedErrors = groupDetectorErrors(errors);
      setDetectorErrors(groupedErrors);
    } catch (error) {
      console.error('Error loading detector errors:', error);
    }
  };
  
  const groupDetectorErrors = (errors) => {
    if (!Array.isArray(errors)) return [];
    
    const errorGroups = new Map();
    
    errors.forEach(error => {
      const key = `${error.detector_name || error.detector}-${error.description}`;
      
      if (!errorGroups.has(key)) {
        errorGroups.set(key, {
          ...error,
          id: error.id || `${Date.now()}-${Math.random()}`,
          detector_name: error.detector_name || error.detector,
          instances: []
        });
      }
      
      errorGroups.get(key).instances.push(error);
    });
    
    return Array.from(errorGroups.values());
  };
  
  // Save notes
  const saveNotes = useCallback(async (newNotes) => {
    try {
      await api.updateTake(takeId, { notes: newNotes });
      setNotes(newNotes);
    } catch (error) {
      console.error('Error saving notes:', error);
      notify.error('Failed to save notes');
    }
  }, [takeId, notify]);
  
  // Export notes
  const exportNotes = useCallback(async (filePath) => {
    try {
      await api.exportTake(takeId, filePath);
      notify.success('Notes exported successfully');
    } catch (error) {
      console.error('Error exporting notes:', error);
      notify.error('Failed to export notes');
    }
  }, [takeId, notify]);
  
  // Clear take data
  const clearTakeData = useCallback(async () => {
    try {
      await api.clearTakeData(takeId);
      
      // Reset local state
      capture.stopCapture();
      navigation.clearCache();
      setDetectorErrors([]);
      setNotes('');
      
      notify.success('Take data cleared');
      
      // Reinitialize
      await initializeMonitoring();
    } catch (error) {
      console.error('Error clearing take data:', error);
      notify.error('Failed to clear take data');
    }
  }, [takeId, capture, navigation, notify]);
  
  // Redo detection
  const redoDetection = useCallback(async () => {
    if (navigation.frameCount === 0) {
      notify.warning('No frames to process');
      return;
    }
    
    try {
      // Clear existing errors
      setDetectorErrors([]);
      
      // Reset to first frame
      navigation.navigateToFirst();
      
      // Start redo detection
      const captureStore = useDataStore.getState();
      captureStore.startRedoDetection();
      
      // Use restart processing API
      await api.restartProcessing(takeId, referenceTakeId);
      
      notify.info('Re-processing detection...');
    } catch (error) {
      console.error('Error restarting processing:', error);
      notify.error('Failed to restart processing');
    }
  }, [takeId, referenceTakeId, navigation, notify]);
  
  return {
    // State
    isInitialized,
    sceneData,
    detectorErrors,
    availableTakes,
    notes,
    
    // Capture
    ...capture,
    
    // Navigation
    ...navigation,
    
    // Process guard
    ...processGuard,
    
    // Actions
    saveNotes,
    exportNotes,
    clearTakeData,
    redoDetection,
    loadDetectorErrors,
    
    // Utilities
    hasReferenceTake: !!referenceTakeId,
    canStartCapture: capture.canStartCapture && isInitialized,
    canRedoDetection: navigation.hasFrames && !capture.isCapturing && !processGuard.isProcessing
  };
}
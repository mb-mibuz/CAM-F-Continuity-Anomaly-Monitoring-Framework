import { useState, useEffect, useCallback, useRef } from 'react';
import { useDataStore } from '../../../stores';
import { DetectorService } from '../../../services';
import { api } from '../../../utils/api';
import { shallow } from '../../../stores/utils/shallow';

export function useDetectorSync(takeId) {
  const [detectorErrors, setDetectorErrors] = useState([]);
  const [isLoadingErrors, setIsLoadingErrors] = useState(false);
  
  const detectorService = useRef(DetectorService.getInstance());
  const pollingIntervalRef = useRef(null);
  
  // Get processing state from capture store
  const {
    isProcessing,
    isRedoingDetection,
    processedFrameCount,
    captureProgress,
    detectorErrors: storeErrors
  } = useDataStore(
    state => ({
      isProcessing: state.isProcessing,
      isRedoingDetection: state.isRedoingDetection,
      processedFrameCount: state.captureProgress.processedFrames,
      captureProgress: state.captureProgress,
      detectorErrors: state.detectorErrors
    }),
    shallow
  );

  // Sync with store errors - this is critical for SSE updates
  useEffect(() => {
    // Always sync with store errors, even if empty
    // This ensures SSE updates are reflected immediately
    // Store errors updated
    
    // During processing, group the errors as they come in
    if ((isProcessing || isRedoingDetection) && storeErrors && storeErrors.length > 0) {
      // Group the raw errors from SSE
      const processedErrors = processDetectorErrors(storeErrors);
      setDetectorErrors(processedErrors);
    } else {
      // When not processing, just use the store errors as-is
      setDetectorErrors(storeErrors || []);
    }
  }, [storeErrors, isProcessing, isRedoingDetection]);

  // Load detector errors
  const loadDetectorErrors = useCallback(async () => {
    if (!takeId) return;
    
    // During processing, skip loading if we have SSE updates coming in
    if ((isProcessing || isRedoingDetection) && storeErrors && storeErrors.length > 0) {
      // Trust the store errors during processing as they come from SSE
      return;
    }
    
    setIsLoadingErrors(true);
    try {
      // Use the grouped endpoint to get pre-grouped errors
      const response = await api.getGroupedErrors(takeId);
      const groupedErrors = response.errors || [];
      
      // Transform grouped errors to the expected format
      const processedErrors = groupedErrors.map(group => ({
        id: group.error_group_id || `${Date.now()}-${Math.random()}`,
        detector_name: group.detector_name,
        description: group.description,
        frame_id: group.first_frame_id || group.frame_id,
        confidence: group.average_confidence !== undefined ? group.average_confidence : group.confidence,
        bounding_boxes: group.instances?.[0]?.bounding_boxes || group.bounding_boxes,
        metadata: group.instances?.[0]?.metadata || group.metadata,
        is_false_positive: group.is_false_positive || false,
        // Store all instances in the error group
        instances: group.instances || [{
          frame_id: group.frame_id,
          confidence: group.confidence,
          bounding_boxes: group.bounding_boxes,
          is_false_positive: group.is_false_positive || false
        }]
      }));
      
      setDetectorErrors(processedErrors);
      
      // Update store only if not processing (to avoid overwriting SSE updates)
      if (!isProcessing && !isRedoingDetection) {
        useDataStore.getState().updateDetectorErrors(processedErrors);
      }
    } catch (error) {
      console.error('Error loading detector errors:', error);
      // Fallback to ungrouped endpoint if grouped fails
      try {
        const errors = await api.getTakeErrors(takeId);
        const processedErrors = processDetectorErrors(errors);
        setDetectorErrors(processedErrors);
        if (!isProcessing && !isRedoingDetection) {
          useDataStore.getState().updateDetectorErrors(processedErrors);
        }
      } catch (fallbackError) {
        console.error('Fallback error loading failed:', fallbackError);
        setDetectorErrors([]);
      }
    } finally {
      setIsLoadingErrors(false);
    }
  }, [takeId, isProcessing, isRedoingDetection, storeErrors]);

  // Process and group detector errors (fallback for ungrouped API)
  const processDetectorErrors = (errors) => {
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
      
      const group = errorGroups.get(key);
      // Add this error as an instance
      group.instances.push({
        frame_id: error.frame_id,
        confidence: error.confidence,
        bounding_boxes: error.bounding_boxes || [],
        is_false_positive: error.is_false_positive || false,
        metadata: error.metadata || {}
      });
      
      // Update group confidence (use max confidence)
      if (error.confidence > (group.confidence || 0)) {
        group.confidence = error.confidence;
      }
    });
    
    // Sort groups by first occurrence
    const sortedGroups = Array.from(errorGroups.values()).sort((a, b) => {
      const aFrame = a.instances[0]?.frame_id || 0;
      const bFrame = b.instances[0]?.frame_id || 0;
      return aFrame - bFrame;
    });
    
    return sortedGroups;
  };

  // Initial load
  useEffect(() => {
    loadDetectorErrors();
  }, [loadDetectorErrors]);

  // Poll for errors during processing
  useEffect(() => {
    if (isProcessing || isRedoingDetection) {
      // Clear existing errors if redoing
      if (isRedoingDetection) {
        setDetectorErrors([]);
      }
      
      // During processing, rely primarily on SSE updates
      // Only poll occasionally as a fallback to catch any missed updates
      pollingIntervalRef.current = setInterval(() => {
        loadDetectorErrors();
      }, 10000); // Poll every 10 seconds as a fallback
      
      return () => {
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current);
          pollingIntervalRef.current = null;
        }
      };
    }
  }, [isProcessing, isRedoingDetection, loadDetectorErrors]);

  // Load final errors when processing completes
  useEffect(() => {
    if (!isProcessing && !isRedoingDetection && processedFrameCount > 0) {
      // Load one final time after processing
      const timer = setTimeout(() => {
        loadDetectorErrors();
        
        // Ensure processing state is cleared
        const dataStore = useDataStore.getState();
        if (dataStore.isProcessing || dataStore.isRedoingDetection) {
          // Force processing state to complete if needed
          dataStore.completeRedoDetection();
        }
      }, 1000);
      
      return () => clearTimeout(timer);
    }
  }, [isProcessing, isRedoingDetection, processedFrameCount, loadDetectorErrors]);

  // Refresh function
  const refreshErrors = useCallback(async () => {
    await loadDetectorErrors();
  }, [loadDetectorErrors]);

  return {
    detectorErrors,
    isLoadingErrors,
    isProcessing: isProcessing || isRedoingDetection,
    processedFrameCount,
    refreshErrors
  };
}
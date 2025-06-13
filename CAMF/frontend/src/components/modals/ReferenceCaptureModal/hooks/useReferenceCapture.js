import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useDataStore, useAppStore } from '../../../../stores';
import { CaptureService, FrameService, SSEService } from '../../../../services';
import { api } from '../../../../utils/api';
import { useVideoUpload } from './useVideoUpload';
import { debugFrames, checkFrameConsistency } from '../../../../utils/debugFrames';

export function useReferenceCapture({ takeName, angleId, sceneId, onComplete }) {
  const [tempTakeId, setTempTakeId] = useState(null);
  const [isCreating, setIsCreating] = useState(false);
  const [isCleaningUp, setIsCleaningUp] = useState(false);
  const [takeWasCreated, setTakeWasCreated] = useState(false);
  const [captureTimer, setCaptureTimer] = useState('00:00');
  
  // Services
  const captureService = useRef(CaptureService.getInstance());
  const frameService = useRef(FrameService.getInstance());
  const wsService = useRef(SSEService);
  
  // Intervals
  const timerInterval = useRef(null);
  const isMountedRef = useRef(true);
  const captureCleanupRef = useRef(null);
  
  // Frame state - Define this first
  const [frameState, setFrameState] = useState({
    currentFrame: null,
    frameCount: 0,
    currentFrameIndex: 0,
    setCurrentFrameIndex: (index) => {
      setFrameState(prev => {
        const clampedIndex = Math.max(0, Math.min(index, prev.frameCount - 1));
        if (clampedIndex !== prev.currentFrameIndex) {
          return { ...prev, currentFrameIndex: clampedIndex };
        }
        return prev;
      });
    },
    navigateFrame: (direction) => {
      setFrameState(prev => {
        let newIndex = prev.currentFrameIndex;
        if (direction === 'prev' && prev.currentFrameIndex > 0) {
          newIndex = prev.currentFrameIndex - 1;
        } else if (direction === 'next' && prev.currentFrameIndex < prev.frameCount - 1) {
          newIndex = prev.currentFrameIndex + 1;
        } else if (direction === 'first') {
          newIndex = 0;
        } else if (direction === 'last') {
          newIndex = Math.max(0, prev.frameCount - 1);
        }
        console.log('[navigateFrame]', { direction, oldIndex: prev.currentFrameIndex, newIndex, frameCount: prev.frameCount });
        return { ...prev, currentFrameIndex: newIndex };
      });
    },
    resetFrames: () => setFrameState(prev => ({
      ...prev,
      currentFrame: null,
      frameCount: 0,
      currentFrameIndex: 0
    }))
  });
  
  // Store states - separate data and actions for proper reactivity
  const source = useDataStore(state => state.source);
  const isCapturing = useDataStore(state => state.isCapturing);
  const captureProgress = useDataStore(state => state.captureProgress);
  const previewFrame = useDataStore(state => state.previewFrame);
  const previewError = useDataStore(state => state.previewError);
  const isPreviewActive = useDataStore(state => state.isPreviewActive);
  
  // Store actions
  const setSource = useDataStore(state => state.setSource);
  const updatePreviewFrame = useDataStore(state => state.updatePreviewFrame);
  const setPreviewActive = useDataStore(state => state.setPreviewActive);
  
  const addNotification = useAppStore(state => state.addNotification);
  
  // Track if preview is being managed
  const previewActiveRef = useRef(false);
  
  // Source setter with preview
  const handleSetSource = useCallback(async (newSource) => {
    console.log('handleSetSource called:', { newSource, currentSource: source });
    
    // Stop any existing preview first if changing sources
    if (source && (!newSource || source.id !== newSource?.id)) {
      await captureService.current.stopPreview();
      previewActiveRef.current = false;
    }
    
    // Update the store first
    setSource(newSource);
    
    // Set source on backend and start preview
    if (newSource && !isCapturing && frameState.frameCount === 0) {
      try {
        // Set source on backend
        await captureService.current.setSource(newSource.type, newSource.id, newSource.name);
        
        // Small delay to ensure backend is ready
        await new Promise(resolve => setTimeout(resolve, 200));
        
        // Start preview - CaptureService will check if already active
        previewActiveRef.current = true;
        await captureService.current.startPreview();
      } catch (error) {
        console.error('Failed to set source:', error);
        addNotification({ type: 'error', message: 'Failed to set capture source' });
        previewActiveRef.current = false;
      }
    } else if (!newSource) {
      // Clear preview if no source
      await captureService.current.stopPreview();
      previewActiveRef.current = false;
    }
  }, [isCapturing, addNotification, frameState.frameCount, source, setSource]);
  
  // Capture state object for component - use useMemo to ensure it updates when dependencies change
  const captureState = useMemo(() => {
    console.log('[useReferenceCapture] Creating captureState:', {
      hasSource: !!source,
      isCapturing,
      hasPreviewFrame: !!previewFrame,
      previewFrameLength: previewFrame ? previewFrame.length : 0,
      isPreviewActive,
      captureTimer
    });
    return {
      source,
      isCapturing,
      captureProgress,
      previewFrame,
      previewError,
      isPreviewActive,
      captureTimer,
      setSource: handleSetSource
    };
  }, [source, isCapturing, captureProgress, previewFrame, previewError, isPreviewActive, captureTimer, handleSetSource]);

  // Initialize capture
  const initializeCapture = useCallback(async () => {
    try {
      // Check and stop any existing capture
      const status = await api.getCaptureStatus();
      if (status.is_capturing) {
        await api.stopCapture();
      }
      
      // Don't reset capture state here - it clears the preview
      // Just ensure we're not in a capturing state
      const store = useDataStore.getState();
      if (store.isCapturing) {
        store.stopCapture();
      }
      
      // Start preview if we have a source
      if (source && !store.isCapturing && frameState.frameCount === 0 && !previewActiveRef.current) {
        try {
          // Set source on backend
          await captureService.current.setSource(
            source.type, 
            source.id, 
            source.name
          );
          
          // Add a small delay to ensure backend is ready
          await new Promise(resolve => setTimeout(resolve, 200));
          
          // Start preview
          previewActiveRef.current = true;
          await captureService.current.startPreview();
        } catch (error) {
          console.error('Failed to initialize source:', error);
          previewActiveRef.current = false;
        }
      }
      
    } catch (error) {
      console.error('Error initializing capture:', error);
    }
  }, [source, frameState.frameCount]);

  // Start capture
  const handleStartCapture = useCallback(async () => {
    if (!captureState.source) {
      addNotification({ type: 'warning', message: 'Please select a capture source first' });
      return;
    }
    
    let newTakeId = tempTakeId;
    
    try {
      // Create temporary take if not exists
      if (!newTakeId) {
        const response = await api.createTake({
          angleId: angleId,
          name: `${takeName}_temp_${Date.now()}`
        });
        newTakeId = response.id;
        setTempTakeId(newTakeId);
      }
      
      // Stop preview before starting capture
      await captureService.current.stopPreview();
      previewActiveRef.current = false;
      
      // Don't clear preview frame - let it stay visible until first capture frame
      
      // Initialize capture service
      await captureService.current.initialize(newTakeId);
      
      // Ensure source is set on backend
      if (captureState.source) {
        await captureService.current.setSource(
          captureState.source.type, 
          captureState.source.id, 
          captureState.source.name
        );
      }
      
      // Start capture timer
      const startTime = Date.now();
      timerInterval.current = setInterval(() => {
        const elapsed = Date.now() - startTime;
        const seconds = Math.floor(elapsed / 1000);
        const minutes = Math.floor(seconds / 60);
        const displaySeconds = seconds % 60;
        setCaptureTimer(`${minutes.toString().padStart(2, '0')}:${displaySeconds.toString().padStart(2, '0')}`);
      }, 1000);
      
      // Track last frame loaded via SSE to avoid duplicates
      let lastSSEFrame = -1;
      
      // Subscribe to frame updates from SSE
      const frameHandler = async (event) => {
        if (event.type === 'frame_captured' && event.data) {
          const { frameIndex, frame_index, preview } = event.data;
          const actualFrameIndex = frameIndex !== undefined ? frameIndex : frame_index;
          
          // Update frame count and load the actual frame
          if (isMountedRef.current && actualFrameIndex !== undefined) {
            console.log('[useReferenceCapture] Frame captured event:', { actualFrameIndex, hasPreview: !!preview });
            
            // Update frame count and index
            setFrameState(prev => ({
              ...prev,
              frameCount: actualFrameIndex + 1,
              currentFrameIndex: actualFrameIndex
            }));
            
            // Load frame for every frame to show live updates
            // Only skip if we've already loaded this frame
            if (actualFrameIndex > lastSSEFrame) {
              lastSSEFrame = actualFrameIndex;
              
              // Small delay to ensure frame is saved on backend
              setTimeout(async () => {
                try {
                  const frameData = await frameService.current.loadFrame(newTakeId, actualFrameIndex);
                  if (frameData && isMountedRef.current) {
                    setFrameState(prev => ({
                      ...prev,
                      currentFrame: frameData
                    }));
                  }
                } catch (error) {
                  console.error('[useReferenceCapture] Error loading frame during capture:', error);
                }
              }, 100);
            }
          }
        }
      };
      
      // Subscribe to SSE channels for frame updates
      wsService.current.subscribe('capture', frameHandler);
      wsService.current.subscribe(`take_${newTakeId}`, frameHandler);
      wsService.current.subscribe('frame_events', frameHandler);
      
      // Start capture
      await captureService.current.startCapture(newTakeId, {
        skip_detectors: true // Don't run detectors for reference
      });
      
      // Track last loaded frame to avoid duplicate loads
      let lastLoadedFrame = -1;
      
      // Update frame state on progress and load frames
      const unsubscribe = useDataStore.subscribe(
        state => state.captureProgress,
        async (progress) => {
          if (isMountedRef.current && progress.capturedFrames > 0) {
            const newFrameIndex = progress.capturedFrames - 1;
            
            // Update frame count and index
            setFrameState(prev => ({
              ...prev,
              frameCount: progress.capturedFrames,
              currentFrameIndex: newFrameIndex
            }));
            
            // Load frame only if it's a new frame
            // For reference capture at low FPS (1 FPS), we can afford to load every frame
            if (newFrameIndex > lastLoadedFrame) {
              lastLoadedFrame = newFrameIndex;
              
              try {
                const frameData = await frameService.current.loadFrame(newTakeId, newFrameIndex);
                if (frameData && isMountedRef.current) {
                  setFrameState(prev => ({
                    ...prev,
                    currentFrame: frameData
                  }));
                }
              } catch (error) {
                console.error('[useReferenceCapture] Error loading frame from progress update:', error);
              }
            }
          }
        }
      );
      
      // Store cleanup functions
      captureCleanupRef.current = () => {
        unsubscribe();
        wsService.current.unsubscribe('capture', frameHandler);
        wsService.current.unsubscribe(`take_${newTakeId}`, frameHandler);
        wsService.current.unsubscribe('frame_events', frameHandler);
      };
      
    } catch (error) {
      console.error('Error starting capture:', error);
      addNotification({ type: 'error', message: 'Failed to start capture' });
      
      // Cleanup on error
      if (timerInterval.current) {
        clearInterval(timerInterval.current);
      }
      
      if (newTakeId && !tempTakeId) {
        await api.deleteTake(newTakeId);
      }
    }
  }, [tempTakeId, takeName, angleId, captureState.source]);

  // Stop capture
  const handleStopCapture = useCallback(async () => {
    try {
      await captureService.current.stopCapture();
      
      if (timerInterval.current) {
        clearInterval(timerInterval.current);
        timerInterval.current = null;
      }
      
      // Cleanup capture subscriptions
      if (captureCleanupRef.current) {
        captureCleanupRef.current();
        captureCleanupRef.current = null;
      }
      
      // Debug frame consistency
      if (tempTakeId && frameState.frameCount > 0) {
        console.log('[useReferenceCapture] Checking frame consistency after capture stop');
        try {
          await checkFrameConsistency(tempTakeId, frameState.frameCount);
        } catch (error) {
          console.error('[useReferenceCapture] Error checking frame consistency:', error);
        }
      }
      
      // Load first frame for review
      if (tempTakeId && frameState.frameCount > 0) {
        console.log('[useReferenceCapture] Loading first frame for review, frameCount:', frameState.frameCount);
        try {
          const frameData = await frameService.current.loadFrame(tempTakeId, 0);
          setFrameState(prev => ({
            ...prev,
            currentFrame: frameData,
            currentFrameIndex: 0
          }));
        } catch (error) {
          console.error('[useReferenceCapture] Error loading first frame:', error);
          addNotification({ type: 'error', message: 'Failed to load first frame for review' });
        }
      }
      
      // Restart preview after stopping capture if no frames captured
      if (captureState.source && frameState.frameCount === 0 && !previewActiveRef.current) {
        setTimeout(async () => {
          if (!previewActiveRef.current) {
            previewActiveRef.current = true;
            await captureService.current.startPreview();
          }
        }, 500);
      }
      
    } catch (error) {
      console.error('Error stopping capture:', error);
      addNotification({ type: 'error', message: 'Failed to stop capture' });
    }
  }, [tempTakeId, frameState.frameCount, captureState.source, addNotification]);

  // Create final take
  const handleCreateTake = useCallback(async () => {
    if (frameState.frameCount === 0 || !tempTakeId) {
      addNotification({ type: 'warning', message: 'Please capture some footage first' });
      return;
    }
    
    setIsCreating(true);
    try {
      // Rename the take to remove the temporary suffix
      await api.updateTake(tempTakeId, { name: takeName });
      
      // Set this take as the reference take since it's from the reference capture modal
      // Only set as reference after renaming (no longer temporal)
      console.log('[useReferenceCapture] Setting take as reference:', tempTakeId);
      await api.setReferenceTake(tempTakeId);
      
      // Small delay to ensure backend has processed the reference take update
      await new Promise(resolve => setTimeout(resolve, 500));
      
      // Verify it was set
      try {
        const refTake = await api.getReferenceTake(angleId);
        console.log('[useReferenceCapture] Verified reference take:', refTake);
      } catch (error) {
        console.error('[useReferenceCapture] Failed to verify reference take:', error);
      }
      
      setTakeWasCreated(true);
      onComplete(takeName, angleId, tempTakeId);
    } catch (error) {
      console.error('Error creating take:', error);
      addNotification({ type: 'error', message: 'Failed to create take' });
      setIsCreating(false);
    }
  }, [frameState.frameCount, tempTakeId, takeName, angleId, onComplete, addNotification]);

  // Handle video upload completion
  const handleVideoUploadComplete = useCallback(async ({ takeId, frameCount, firstFrame }) => {
    console.log('[handleVideoUploadComplete] Called with:', { takeId, frameCount, hasFirstFrame: !!firstFrame });
    setTempTakeId(takeId);
    
    // Update frame state
    setFrameState(prev => {
      console.log('[handleVideoUploadComplete] Previous frameState:', prev);
      const newState = {
        ...prev,
        frameCount,
        currentFrameIndex: 0,
        currentFrame: firstFrame
      };
      console.log('[handleVideoUploadComplete] New frameState:', newState);
      return newState;
    });
    
    // Force load the first frame to ensure it's available
    if (takeId && frameCount > 0) {
      try {
        const frameData = await frameService.current.loadFrame(takeId, 0);
        if (frameData) {
          setFrameState(prev => ({
            ...prev,
            currentFrame: frameData
          }));
        }
      } catch (error) {
        console.error('[handleVideoUploadComplete] Error loading first frame:', error);
      }
    }
    
    // Automatically create the take after video upload
    if (frameCount > 0 && takeId) {
      setIsCreating(true);
      try {
        // Rename the take to remove the temporary suffix
        await api.updateTake(takeId, { name: takeName });
        
        // Set this take as the reference take
        console.log('[handleVideoUploadComplete] Setting take as reference:', takeId);
        await api.setReferenceTake(takeId);
        
        // Small delay to ensure backend has processed the reference take update
        await new Promise(resolve => setTimeout(resolve, 500));
        
        // Verify it was set
        try {
          const refTake = await api.getReferenceTake(angleId);
          console.log('[handleVideoUploadComplete] Verified reference take:', refTake);
        } catch (error) {
          console.error('[handleVideoUploadComplete] Failed to verify reference take:', error);
        }
        
        setTakeWasCreated(true);
        addNotification({
          type: 'success',
          message: 'Reference take created successfully'
        });
        
        // Call the completion callback to navigate to the take
        onComplete(takeName, angleId, takeId);
      } catch (error) {
        console.error('Error creating take from video:', error);
        addNotification({ type: 'error', message: 'Failed to create take' });
        setIsCreating(false);
      }
    }
  }, [takeName, angleId, onComplete, addNotification]);

  // Video upload hook
  const { uploadVideo, isUploading, uploadProgress } = useVideoUpload({
    angleId,
    takeName,
    onUploadComplete: handleVideoUploadComplete
  });

  // Handle video upload
  const handleVideoUpload = useCallback(async (file) => {
    try {
      const result = await uploadVideo(file);
      return result;
    } catch (error) {
      console.error('Error processing video:', error);
      throw error;
    }
  }, [uploadVideo]);

  // Cleanup
  const cleanup = useCallback(async (force = false) => {
    if ((tempTakeId && !takeWasCreated) || force) {
      setIsCleaningUp(true);
      
      try {
        // Stop capture if active
        if (isCapturing) {
          await captureService.current.stopCapture();
        }
        
        // Only stop preview if force cleaning (modal closing)
        if (force) {
          await captureService.current.stopPreview();
          previewActiveRef.current = false;
        }
        
        // Clear intervals
        if (timerInterval.current) {
          clearInterval(timerInterval.current);
        }
        
        // Delete temporary take
        if (tempTakeId && !takeWasCreated) {
          try {
            await api.deleteTake(tempTakeId);
          } catch (error) {
            console.error('[useReferenceCapture] Error deleting temporal take:', error);
            // If deletion fails due to reference take restriction, try to clear reference first
            if (error.status === 400 && error.message?.includes('reference take')) {
              try {
                // Get the angle's current reference
                const refTake = await api.getReferenceTake(angleId);
                if (refTake?.reference_take?.id === tempTakeId) {
                  // Clear reference by updating angle
                  const angle = await api.getAngles(angleId);
                  if (angle) {
                    await api.updateAngle(angleId, { reference_take_id: null });
                  }
                }
                // Try deleting again
                await api.deleteTake(tempTakeId);
              } catch (retryError) {
                console.error('[useReferenceCapture] Failed to delete temporal take after clearing reference:', retryError);
              }
            }
          }
        }
        
        // Clear frame cache - this will revoke blob URLs
        if (tempTakeId) {
          frameService.current.clearTakeFrames(tempTakeId);
        }
        
        // Reset frame state
        frameState.resetFrames();
        
        // Reset store only if force cleaning
        if (force) {
          useDataStore.getState().resetCaptureState();
        }
        
      } catch (error) {
        console.error('Error during cleanup:', error);
      } finally {
        setIsCleaningUp(false);
      }
    }
  }, [tempTakeId, takeWasCreated, isCapturing, frameState]);

  // Load frame when navigating (including during capture)
  useEffect(() => {
    // During capture, frames are loaded by the SSE handler
    // This effect only handles review mode navigation
    if (tempTakeId && !isCapturing && frameState.frameCount > 0) {
      console.log('[useReferenceCapture] Frame loading effect triggered:', {
        takeId: tempTakeId,
        currentFrameIndex: frameState.currentFrameIndex,
        frameCount: frameState.frameCount,
        isCapturing,
        hasCurrentFrame: !!frameState.currentFrame
      });
      
      // Add a debounce to prevent rapid frame loading
      const loadTimeout = setTimeout(async () => {
        try {
          console.log('[useReferenceCapture] Loading frame:', {
            takeId: tempTakeId,
            frameIndex: frameState.currentFrameIndex,
            frameCount: frameState.frameCount
          });
          
          // Ensure frame index is within bounds
          const frameIndex = Math.min(frameState.currentFrameIndex, frameState.frameCount - 1);
          
          const frameData = await frameService.current.loadFrame(
            tempTakeId, 
            frameIndex
          );
          
          console.log('[useReferenceCapture] Frame loaded:', {
            frameIndex,
            hasFrameData: !!frameData,
            frameDataLength: frameData ? frameData.length : 0
          });
          
          if (frameData && isMountedRef.current) {
            setFrameState(prev => ({ 
              ...prev, 
              currentFrame: frameData,
              currentFrameIndex: frameIndex // Update to corrected index if needed
            }));
          } else if (!frameData) {
            console.error('[useReferenceCapture] No frame data returned for index:', frameIndex);
          }
        } catch (error) {
          console.error('[useReferenceCapture] Error loading frame:', error);
          if (isMountedRef.current) {
            addNotification({ type: 'error', message: `Failed to load frame ${frameState.currentFrameIndex}` });
          }
        }
      }, 100); // 100ms debounce
      
      return () => clearTimeout(loadTimeout);
    } else {
      console.log('[useReferenceCapture] Frame loading effect skipped:', {
        hasTempTakeId: !!tempTakeId,
        isCapturing,
        frameCount: frameState.frameCount
      });
    }
  }, [tempTakeId, frameState.currentFrameIndex, frameState.frameCount, isCapturing, addNotification]);

  // Debug preview frame updates
  useEffect(() => {
    console.log('[useReferenceCapture] State updated:', {
      hasPreviewFrame: !!previewFrame,
      previewFrameLength: previewFrame ? previewFrame.length : 0,
      isPreviewActive,
      source: source?.name
    });
  }, [previewFrame, isPreviewActive, source]);

  // Direct subscription to debug store updates
  useEffect(() => {
    const unsubscribe = useDataStore.subscribe(
      state => state.previewFrame,
      (newPreviewFrame) => {
        console.log('[useReferenceCapture] Store previewFrame changed:', {
          hasFrame: !!newPreviewFrame,
          length: newPreviewFrame ? newPreviewFrame.length : 0
        });
      }
    );
    
    return unsubscribe;
  }, []);

  // Initialize on mount
  useEffect(() => {
    isMountedRef.current = true;
    
    // Ensure clean state when modal opens
    const store = useDataStore.getState();
    console.log('[useReferenceCapture] Initial store state:', {
      source: store.source,
      previewFrame: !!store.previewFrame,
      isPreviewActive: store.isPreviewActive,
      isCapturing: store.isCapturing
    });
    
    // Initialize capture after a small delay to ensure modal is fully rendered
    setTimeout(() => {
      initializeCapture();
    }, 100);
    
    return () => {
      isMountedRef.current = false;
      // Clear preview ref
      previewActiveRef.current = false;
      // Only force cleanup on unmount
      cleanup(true);
    };
  }, []);

  return {
    tempTakeId,
    captureState,
    frameState,
    isCreating,
    isCleaningUp,
    isUploading,
    uploadProgress,
    initializeCapture,
    handleStartCapture,
    handleStopCapture,
    handleCreateTake,
    handleVideoUpload,
    cleanup
  };
}
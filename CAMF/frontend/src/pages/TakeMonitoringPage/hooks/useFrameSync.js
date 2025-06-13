import { useState, useEffect, useCallback, useRef } from 'react';
import { useDataStore } from '../../../stores';
import { FrameService } from '../../../services';
import { shallow } from '../../../stores/utils/shallow';

export function useFrameSync(takeId, referenceTakeId) {
  const [currentFrame, setCurrentFrame] = useState(null);
  const [referenceFrame, setReferenceFrame] = useState(null);
  const [isLoadingFrame, setIsLoadingFrame] = useState(false);
  
  const frameService = useRef(FrameService.getInstance());
  const wasCapturing = useRef(false);
  
  // Get frame-related state from capture store
  const {
    frameCount,
    currentFrameIndex,
    hasProcessedFrames,
    isCapturing,
    latestFrameIndex,
    currentFrame: storeCurrentFrame,
    referenceFrame: storeReferenceFrame
  } = useDataStore(
    state => ({
      frameCount: state.frameCount,
      currentFrameIndex: state.currentFrameIndex,
      hasProcessedFrames: state.hasProcessedFrames,
      isCapturing: state.isCapturing,
      latestFrameIndex: state.latestFrameIndex,
      currentFrame: state.currentFrame,
      referenceFrame: state.referenceFrame
    }),
    shallow
  );

  // Sync with store frames
  useEffect(() => {
    setCurrentFrame(storeCurrentFrame);
    setReferenceFrame(storeReferenceFrame);
  }, [storeCurrentFrame, storeReferenceFrame]);
  
  // Track capture state transitions and force reload when capture stops
  useEffect(() => {
    if (isCapturing) {
      wasCapturing.current = true;
    } else if (wasCapturing.current) {
      // Capture just stopped - force reload current frame
      console.log('[useFrameSync] Capture stopped, will force reload current frame');
      // The frame loading effect will handle the actual reload
    }
  }, [isCapturing]);

  // Load current frame when index changes
  useEffect(() => {
    if (!takeId || frameCount === 0) {
      console.log('[useFrameSync] Skipping frame load:', { takeId, frameCount });
      return;
    }
    
    let cancelled = false;
    let timeoutId = null;
    
    const loadFrame = async () => {
      console.log('[useFrameSync] Loading frame:', { takeId, currentFrameIndex, frameCount, isCapturing });
      
      // Force reload when transitioning from capturing to viewing
      const forceReload = !isCapturing && wasCapturing.current;
      
      // Only show loading state if we don't have a frame to display
      // This prevents UI flicker during transitions
      if (!storeCurrentFrame || forceReload) {
        setIsLoadingFrame(true);
      }
      
      try {
        // Only add delay if we don't have a current frame displayed
        // This prevents the "blink" when we already have a valid frame
        if (forceReload && !storeCurrentFrame) {
          console.log('[useFrameSync] No current frame, waiting for server...');
          await new Promise(resolve => setTimeout(resolve, 300));
        }
        
        if (cancelled) return;
        
        if (forceReload) {
          wasCapturing.current = false;
        }
        
        await frameService.current.updateCurrentFrame(
          takeId,
          currentFrameIndex,
          { 
            withBoundingBoxes: hasProcessedFrames,
            forceReload: forceReload
          }
        );
      } catch (error) {
        console.error('[useFrameSync] Error loading frame:', error);
      } finally {
        if (!cancelled) {
          setIsLoadingFrame(false);
        }
      }
    };

    // Debounce frame loading to prevent multiple loads
    timeoutId = setTimeout(loadFrame, 50);
    
    return () => {
      cancelled = true;
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [takeId, currentFrameIndex, frameCount, hasProcessedFrames, isCapturing]);

  // Load reference frame when it changes or frame index changes
  useEffect(() => {
    if (!referenceTakeId) return;
    
    const loadReferenceFrame = async () => {
      try {
        // Get reference frame count from store
        const state = useDataStore.getState();
        const referenceFrameCount = state.referenceFrameCount || 0;
        
        // Don't try to load frames if reference take has no frames
        if (referenceFrameCount === 0) {
          console.log('[useFrameSync] Skipping reference frame load - reference take has no frames');
          frameService.current.clearReferenceFrame();
          return;
        }
        
        // Don't try to load frames beyond reference take's frame count
        if (currentFrameIndex >= referenceFrameCount) {
          console.log('[useFrameSync] Skipping reference frame load - index exceeds reference frame count:', 
            { currentFrameIndex, referenceFrameCount });
          // Clear reference frame in the service
          frameService.current.clearReferenceFrame();
          return;
        }
        
        console.log('[useFrameSync] Loading reference frame:', { referenceTakeId, currentFrameIndex, referenceFrameCount });
        await frameService.current.updateReferenceFrame(
          referenceTakeId,
          currentFrameIndex,
          { withBoundingBoxes: hasProcessedFrames }
        );
      } catch (error) {
        console.error('Error loading reference frame:', error);
        // Clear reference frame on error to prevent repeated failed attempts
        frameService.current.clearReferenceFrame();
      }
    };

    loadReferenceFrame();
  }, [referenceTakeId, currentFrameIndex, hasProcessedFrames]);

  // Auto-advance to latest frame during capture
  useEffect(() => {
    if (isCapturing && !useDataStore.getState().isNavigatingManually) {
      const interval = setInterval(() => {
        const state = useDataStore.getState();
        if (state.latestFrameIndex > state.currentFrameIndex) {
          state.setCurrentFrameIndex(state.latestFrameIndex);
        }
      }, 100);

      return () => clearInterval(interval);
    }
  }, [isCapturing]);

  // Preload nearby frames
  const preloadNearbyFrames = useCallback(() => {
    if (!takeId || frameCount === 0) return;
    
    frameService.current.preloadAroundIndex(
      takeId,
      currentFrameIndex,
      3, // Preload 3 frames in each direction
      { withBoundingBoxes: hasProcessedFrames }
    );
  }, [takeId, currentFrameIndex, frameCount, hasProcessedFrames]);

  // Preload on index change
  useEffect(() => {
    const timer = setTimeout(preloadNearbyFrames, 200);
    return () => clearTimeout(timer);
  }, [preloadNearbyFrames]);

  return {
    currentFrame,
    referenceFrame,
    frameCount,
    currentFrameIndex,
    latestFrameIndex,
    isLoadingFrame,
    isCapturing,
    hasProcessedFrames
  };
}
import { useState, useCallback, useEffect, useRef } from 'react';
import { useDataStore } from '../stores';
import { FrameService } from '../services';
import { shallow } from '../stores/utils/shallow';

/**
 * Hook for frame navigation and loading
 * @param {string} takeId - Current take ID
 * @param {Object} options - Navigation options
 * @returns {Object} Frame navigation state and controls
 */
export function useFrameNavigation(takeId, options = {}) {
  const {
    autoLoad = true,
    preloadRadius = 3,
    withBoundingBoxes = false,
    onFrameChange,
    onLoadError
  } = options;
  
  // Get state from store
  const {
    currentFrameIndex,
    frameCount,
    isCapturing,
    hasProcessedFrames,
    setCurrentFrameIndex,
    updateCurrentFrame
  } = useDataStore(
    state => ({
      currentFrameIndex: state.currentFrameIndex,
      frameCount: state.frameCount,
      isCapturing: state.isCapturing,
      hasProcessedFrames: state.hasProcessedFrames,
      setCurrentFrameIndex: state.setCurrentFrameIndex,
      updateCurrentFrame: state.updateCurrentFrame
    }),
    shallow
  );
  
  // Local state
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  
  // Service instance
  const frameService = useRef(null);
  const loadingRef = useRef(false);
  
  useEffect(() => {
    frameService.current = FrameService.getInstance();
  }, []);
  
  // Load frame when index changes
  useEffect(() => {
    if (!takeId || !autoLoad || frameCount === 0) {
      return;
    }
    
    loadFrame(currentFrameIndex);
  }, [takeId, currentFrameIndex, frameCount, autoLoad, withBoundingBoxes]);
  
  // Load a specific frame
  const loadFrame = useCallback(async (frameIndex, forceReload = false) => {
    if (!takeId || frameIndex < 0 || frameIndex >= frameCount) {
      return;
    }
    
    // Prevent concurrent loads
    if (loadingRef.current && !forceReload) {
      return;
    }
    
    loadingRef.current = true;
    setIsLoading(true);
    setError(null);
    
    try {
      const frameData = await frameService.current.updateCurrentFrame(
        takeId,
        frameIndex,
        {
          withBoundingBoxes: withBoundingBoxes || hasProcessedFrames,
          forceReload
        }
      );
      
      // Preload nearby frames
      if (preloadRadius > 0) {
        frameService.current.preloadAroundIndex(
          takeId,
          frameIndex,
          preloadRadius,
          { withBoundingBoxes: withBoundingBoxes || hasProcessedFrames }
        );
      }
      
      // Call callback
      onFrameChange?.(frameIndex, frameData);
      
    } catch (err) {
      console.error('Error loading frame:', err);
      setError(err);
      onLoadError?.(err);
    } finally {
      loadingRef.current = false;
      setIsLoading(false);
    }
  }, [takeId, frameCount, withBoundingBoxes, hasProcessedFrames, preloadRadius, onFrameChange, onLoadError]);
  
  // Navigate to previous frame
  const navigatePrev = useCallback(() => {
    if (currentFrameIndex > 0 && !isCapturing) {
      const newIndex = currentFrameIndex - 1;
      setCurrentFrameIndex(newIndex);
      return newIndex;
    }
    return currentFrameIndex;
  }, [currentFrameIndex, isCapturing, setCurrentFrameIndex]);
  
  // Navigate to next frame
  const navigateNext = useCallback(() => {
    if (currentFrameIndex < frameCount - 1 && !isCapturing) {
      const newIndex = currentFrameIndex + 1;
      setCurrentFrameIndex(newIndex);
      return newIndex;
    }
    return currentFrameIndex;
  }, [currentFrameIndex, frameCount, isCapturing, setCurrentFrameIndex]);
  
  // Navigate to specific frame
  const navigateToFrame = useCallback((frameIndex) => {
    if (frameIndex >= 0 && frameIndex < frameCount && !isCapturing) {
      setCurrentFrameIndex(frameIndex);
      return frameIndex;
    }
    return currentFrameIndex;
  }, [frameCount, isCapturing, currentFrameIndex, setCurrentFrameIndex]);
  
  // Navigate to first frame
  const navigateToFirst = useCallback(() => {
    return navigateToFrame(0);
  }, [navigateToFrame]);
  
  // Navigate to last frame
  const navigateToLast = useCallback(() => {
    return navigateToFrame(frameCount - 1);
  }, [frameCount, navigateToFrame]);
  
  // Keyboard navigation
  useEffect(() => {
    if (isCapturing) return;
    
    const handleKeyPress = (e) => {
      // Don't handle if user is typing in an input
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
        return;
      }
      
      switch (e.key) {
        case 'ArrowLeft':
          e.preventDefault();
          navigatePrev();
          break;
        case 'ArrowRight':
          e.preventDefault();
          navigateNext();
          break;
        case 'Home':
          e.preventDefault();
          navigateToFirst();
          break;
        case 'End':
          e.preventDefault();
          navigateToLast();
          break;
      }
    };
    
    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [isCapturing, navigatePrev, navigateNext, navigateToFirst, navigateToLast]);
  
  // Get frame cache stats
  const getCacheStats = useCallback(() => {
    return frameService.current?.getCacheStats() || { size: 0, maxSize: 100, usage: 0 };
  }, []);
  
  // Clear frame cache for current take
  const clearCache = useCallback(() => {
    if (takeId && frameService.current) {
      frameService.current.clearTakeFrames(takeId);
    }
  }, [takeId]);
  
  return {
    // State
    currentFrameIndex,
    frameCount,
    isLoading,
    error,
    
    // Navigation
    navigatePrev,
    navigateNext,
    navigateToFrame,
    navigateToFirst,
    navigateToLast,
    
    // Frame control
    loadFrame,
    reloadCurrentFrame: () => loadFrame(currentFrameIndex, true),
    clearCache,
    
    // Computed
    canNavigatePrev: currentFrameIndex > 0 && !isCapturing,
    canNavigateNext: currentFrameIndex < frameCount - 1 && !isCapturing,
    hasFrames: frameCount > 0,
    isFirstFrame: currentFrameIndex === 0,
    isLastFrame: currentFrameIndex === frameCount - 1,
    
    // Utilities
    getCacheStats
  };
}
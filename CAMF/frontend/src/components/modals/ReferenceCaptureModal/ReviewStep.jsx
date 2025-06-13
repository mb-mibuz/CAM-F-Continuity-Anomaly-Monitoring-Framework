import React, { useEffect, useCallback } from 'react';
import FrameDisplay from '../../monitoring/FrameDisplay';
import FrameNavigator from '../../monitoring/FrameNavigator';
import { FrameService } from '../../../services';

export default function ReviewStep({ takeId, frameState, onRetake }) {
  const { 
    currentFrame, 
    frameCount, 
    currentFrameIndex,
    setCurrentFrameIndex,
    navigateFrame
  } = frameState;
  
  console.log('[ReviewStep] Rendered with:', {
    takeId,
    frameCount,
    currentFrameIndex,
    hasCurrentFrame: !!currentFrame,
    frameState
  });
  
  // Preload adjacent frames for smoother navigation
  useEffect(() => {
    if (!takeId || frameCount === 0) return;
    
    const frameService = FrameService.getInstance();
    
    // Only preload adjacent frames to current
    const preloadAdjacentFrames = async () => {
      const preloadRange = 2; // Load 2 frames before and after
      const startFrame = Math.max(0, currentFrameIndex - preloadRange);
      const endFrame = Math.min(frameCount - 1, currentFrameIndex + preloadRange);
      
      // Preload frames one by one to avoid overwhelming the system
      for (let i = startFrame; i <= endFrame; i++) {
        if (i !== currentFrameIndex) { // Skip current frame as it's already loaded
          frameService.loadFrame(takeId, i, { withBoundingBoxes: false })
            .catch(err => console.warn(`Failed to preload frame ${i}:`, err));
        }
      }
    };
    
    // Debounce preloading
    const timeout = setTimeout(preloadAdjacentFrames, 200);
    
    return () => clearTimeout(timeout);
  }, [takeId, frameCount, currentFrameIndex]);

  return (
    <>
      {/* Frame display */}
      <div className="mb-4">
        <FrameDisplay
          key={`review-frame-${currentFrameIndex}`}
          frame={currentFrame}
          frameIndex={currentFrameIndex}
          totalFrames={frameCount}
          isLoading={false}
          showPlaceholder={!currentFrame}
          placeholderText="Loading frame..."
        />
      </div>

      {/* Navigation controls */}
      <div className="mb-6">
        <FrameNavigator
          currentIndex={currentFrameIndex}
          totalFrames={frameCount}
          isCapturing={false}
          onNavigate={navigateFrame}
          onIndexChange={setCurrentFrameIndex}
        />
      </div>

      {/* Retake option if no frames */}
      {frameCount === 0 && (
        <div className="text-center">
          <p className="text-14 text-gray-600 mb-4">
            No frames were captured. Please try again.
          </p>
          <button
            onClick={onRetake}
            className="px-4 py-2 text-14 font-medium bg-white border border-gray-300 rounded hover:bg-gray-50"
          >
            Try Again
          </button>
        </div>
      )}
    </>
  );
}
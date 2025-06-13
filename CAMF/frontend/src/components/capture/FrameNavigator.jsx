import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useDataStore } from '../../stores';
import { shallow } from '../../stores/utils/shallow';

/**
 * Frame navigation controls using store state
 */
export default function FrameNavigator() {
  const { 
    currentFrameIndex, 
    frameCount, 
    isCapturing,
    navigateFrame,
    setCurrentFrameIndex 
  } = useDataStore(
    state => ({
      currentFrameIndex: state.currentFrameIndex,
      frameCount: state.frameCount,
      isCapturing: state.isCapturing,
      navigateFrame: state.navigateFrame,
      setCurrentFrameIndex: state.setCurrentFrameIndex
    }),
    shallow
  );
  
  const canNavigate = !isCapturing && frameCount > 0;
  const canGoPrev = currentFrameIndex > 0;
  const canGoNext = currentFrameIndex < frameCount - 1;
  
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <button
          onClick={() => navigateFrame('prev')}
          disabled={!canNavigate || !canGoPrev}
          className={`w-8 h-8 flex items-center justify-center hover:scale-110 transition-all duration-150 ${
            !canNavigate || !canGoPrev
              ? 'text-gray-300 cursor-not-allowed hover:scale-100'
              : 'text-gray-800 hover:text-black'
          }`}
        >
          <ChevronLeft size={20} strokeWidth={1.5} />
        </button>
        
        <button
          onClick={() => navigateFrame('next')}
          disabled={!canNavigate || !canGoNext}
          className={`w-8 h-8 flex items-center justify-center hover:scale-110 transition-all duration-150 ${
            !canNavigate || !canGoNext
              ? 'text-gray-300 cursor-not-allowed hover:scale-100'
              : 'text-gray-800 hover:text-black'
          }`}
        >
          <ChevronRight size={20} strokeWidth={1.5} />
        </button>
      </div>
      
      <div className="flex-1 mx-4">
        <div className="relative flex items-center h-5">
          <div 
            className="absolute inset-x-0 h-0.5 rounded-full"
            style={{
              background: `linear-gradient(to right, #515151 0%, #515151 ${
                frameCount > 1 ? (currentFrameIndex / (frameCount - 1)) * 100 : 0
              }%, #D1D5DB ${
                frameCount > 1 ? (currentFrameIndex / (frameCount - 1)) * 100 : 0
              }%, #D1D5DB 100%)`
            }}
          />
          <input
            type="range"
            min="0"
            max={Math.max(0, frameCount - 1)}
            value={currentFrameIndex}
            onChange={(e) => setCurrentFrameIndex(parseInt(e.target.value))}
            disabled={!canNavigate}
            className={`relative w-full appearance-none bg-transparent z-10 ${
              !canNavigate ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
            }`}
          />
        </div>
      </div>
      
      <div className="text-14 text-gray-600">
        {frameCount > 0 ? `${currentFrameIndex + 1}/${frameCount}` : '0/0'} frames
      </div>
    </div>
  );
}
// src/components/monitoring/FrameNavigator.jsx
import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

export default function FrameNavigator({
  currentIndex,
  totalFrames,
  isCapturing,
  onNavigate,
  onIndexChange,
  showProgress = false,
  maxFrames = null
}) {
  const canNavigate = !isCapturing && totalFrames > 0;
  const canGoPrev = currentIndex > 0;
  const canGoNext = currentIndex < totalFrames - 1;
  
  const displayTotal = totalFrames;
  const progress = totalFrames > 0 ? (currentIndex / (totalFrames - 1)) * 100 : 0;

  const handleSliderChange = (e) => {
    if (canNavigate && onIndexChange) {
      onIndexChange(parseInt(e.target.value));
    }
  };

  return (
    <div className="flex items-center gap-2 w-full">
      {/* Navigation buttons */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => onNavigate('prev')}
          disabled={!canNavigate || !canGoPrev}
          className={`
            w-8 h-8 flex items-center justify-center rounded
            transition-all duration-150
            ${!canNavigate || !canGoPrev
              ? 'text-gray-300 cursor-not-allowed'
              : 'text-gray-800 hover:text-black hover:bg-gray-100'
            }
          `}
          title="Previous frame"
        >
          <ChevronLeft size={20} strokeWidth={1.5} />
        </button>
        
        <button
          onClick={() => onNavigate('next')}
          disabled={!canNavigate || !canGoNext}
          className={`
            w-8 h-8 flex items-center justify-center rounded
            transition-all duration-150
            ${!canNavigate || !canGoNext
              ? 'text-gray-300 cursor-not-allowed'
              : 'text-gray-800 hover:text-black hover:bg-gray-100'
            }
          `}
          title="Next frame"
        >
          <ChevronRight size={20} strokeWidth={1.5} />
        </button>
      </div>
      
      {/* Slider */}
      <div className="flex-1 px-2">
        <div className="relative flex items-center h-5">
          <div 
            className="absolute inset-x-0 h-0.5 rounded-full"
            style={{
              background: `linear-gradient(to right, #515151 0%, #515151 ${progress}%, #D1D5DB ${progress}%, #D1D5DB 100%)`
            }}
          />
          <input
            type="range"
            min="0"
            max={Math.max(0, totalFrames - 1)}
            value={currentIndex}
            onChange={handleSliderChange}
            disabled={!canNavigate}
            className={`
              relative w-full appearance-none bg-transparent cursor-pointer z-10
              ${!canNavigate ? 'opacity-50 cursor-not-allowed' : ''}
            `}
          />
          
          {/* Progress markers for reference frames - disabled for now */}
        </div>
      </div>
      
      {/* Frame counter */}
      <div className="text-14 text-gray-600 whitespace-nowrap">
        {totalFrames > 0 ? (
          <>
            <span className="font-medium">{currentIndex + 1}</span>
            <span className="mx-1">/</span>
            <span>{totalFrames}</span>
            <span className="ml-1 text-gray-500">frames</span>
          </>
        ) : (
          <span>0 frames</span>
        )}
      </div>
    </div>
  );
}
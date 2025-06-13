// src/components/monitoring/FrameDisplaySection.jsx
import React, { useState, useEffect, useRef } from 'react';
import { ChevronDown, ChevronLeft, ChevronRight, RotateCw, SlidersHorizontal, Airplay, Play } from 'lucide-react';
import SourceSelectionModal from '../modals/SourceSelectionModal';
import { usePredictiveFrames } from '../../hooks/usePredictiveFrames';

export default function FrameDisplaySection({
  currentFrame,
  referenceFrame,
  frameCount,
  currentFrameIndex,
  latestFrameIndex,
  isCapturing,
  isNavigatingManually,
  captureSource,
  onSliderChange,
  availableSources,
  referenceTakeId,
  availableTakes,
  isStopRequested = false,
  hasFrames,
  referenceFrameCount,
  previewFrame,
  onSourceSelect,
  onStartCapture,
  onStopCapture,
  onRedoDetection,
  onFrameNavigation,
  onReferenceChange,
  onSceneSettings,
  onReturnToLatest,
  angleId,
  currentTakeId,
  // NEW: Add these props for processed vs captured tracking
  processedFrameCount,
  capturedFrameCount,
  isProcessingComplete,
  lastPreviewFrame
}) {
  const [showSourceModal, setShowSourceModal] = useState(false);
  const [showReferenceDropdown, setShowReferenceDropdown] = useState(false);
  const [selectedReferenceId, setSelectedReferenceId] = useState(null);
  const [showRecordingTooltip, setShowRecordingTooltip] = useState(false);

  const recordButtonRef = useRef(null);

  useEffect(() => {
    if (referenceTakeId) {
      if (referenceTakeId === currentTakeId) {
        const sameAngleTakes = availableTakes.filter(t => 
          t.angleId === angleId && t.id !== currentTakeId
        );
        
        if (sameAngleTakes.length > 0) {
          setSelectedReferenceId(sameAngleTakes[0].id);
          onReferenceChange(sameAngleTakes[0].id);
        } else {
          const otherTakes = availableTakes.filter(t => t.id !== currentTakeId);
          if (otherTakes.length > 0) {
            setSelectedReferenceId(otherTakes[0].id);
            onReferenceChange(otherTakes[0].id);
          }
        }
      } else {
        setSelectedReferenceId(referenceTakeId);
      }
    } else {
      const refTake = findReferenceTakeForCurrentAngle();
      if (refTake && refTake.id !== currentTakeId) {
        setSelectedReferenceId(refTake.id);
        onReferenceChange(refTake.id);
      }
    }
  }, [referenceTakeId, availableTakes, currentTakeId]);

  const handleSourceSelect = (sourceType, sourceId, sourceName) => {
    if (isCapturing || hasFrames) {
      console.log('Source selection blocked - recording in progress or completed');
      return;
    }
    
    onSourceSelect(sourceType, sourceId, sourceName);
    setShowSourceModal(false);
    
    if (window.pendingCaptureAfterSourceSelect) {
      window.pendingCaptureAfterSourceSelect = false;
      setTimeout(() => {
        onStartCapture();
      }, 100);
    }
  };

  const handleRecordClick = () => {
    console.log('Record button clicked. isCapturing:', isCapturing, 'hasFrames:', hasFrames, 'captureSource:', captureSource);
    
    if (!hasFrames && !isCapturing) {
      if (!captureSource) {
        console.log('No capture source, opening source selection modal');
        setShowSourceModal(true);
        window.pendingCaptureAfterSourceSelect = true;
      } else {
        console.log('Starting capture with existing source');
        onStartCapture();
      }
    }
  };

  const handleReferenceSelect = (takeId) => {
    setSelectedReferenceId(takeId);
    onReferenceChange(takeId);
    setShowReferenceDropdown(false);
  };

  const findReferenceTakeForCurrentAngle = () => {
    const currentAngleTakes = availableTakes.filter(t => t.angleId === angleId);
    const refTake = currentAngleTakes.find(t => t.is_reference);
    
    if (!refTake && referenceTakeId) {
      return availableTakes.find(t => t.id === referenceTakeId);
    }
    
    return refTake;
  };

  const groupTakesByAngle = () => {
    const grouped = {};
    availableTakes.forEach(take => {
      if (!grouped[take.angleName]) {
        grouped[take.angleName] = [];
      }
      grouped[take.angleName].push(take);
    });
    return grouped;
  };

  const referenceTake = findReferenceTakeForCurrentAngle();
  const selectedTake = availableTakes.find(t => t.id === selectedReferenceId);
  const groupedTakes = groupTakesByAngle();
  const isViewingReferenceTake = currentTakeId === referenceTake?.id;

  const getDropdownLabel = () => {
    if (!referenceTake && !selectedReferenceId) {
      return 'Reference Take (None)';
    }
    
    if (selectedReferenceId === referenceTake?.id) {
      return `Reference Take (${referenceTake.name})`;
    }
    
    if (selectedTake) {
      return `${selectedTake.name} (${selectedTake.angleName})`;
    }
    
    return 'Reference Take (None)';
  };

  // Determine which frame to show
  const displayFrame = (() => {
    // If we have a current frame (processed), always show it
    if (currentFrame) {
      return currentFrame;
    }
    
    // During capture, keep showing the last processed frame (which is currentFrame)
    // Don't show preview or lastPreviewFrame during capture
    if (isCapturing) {
      return null; // Will show "Waiting for processed frames..."
    }
    
    // If we have a preview and source is selected but not capturing and no frames yet
    if (previewFrame && captureSource && !isCapturing && !hasFrames) {
      return previewFrame;
    }
    
    // Otherwise nothing
    return null;
  })();

  // Recording button component - FIXED to use handleRecordClick
  const RecordButton = () => {
    const handleClick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      
      // Only allow starting capture, no manual stop
      if (!isCapturing && !hasFrames) {
        handleRecordClick();
      }
    };
    
    return (
      <button
        ref={recordButtonRef}
        onClick={handleClick}
        onMouseDown={(e) => e.preventDefault()}
        disabled={isCapturing || hasFrames} // Disable during capture and after recording
        className={`relative w-[36px] h-[36px] flex items-center justify-center transition-transform duration-150 ${
          isCapturing || hasFrames 
            ? 'opacity-50 cursor-not-allowed' 
            : 'hover:scale-110'
        }`}
        title={isCapturing ? "Recording in progress..." : hasFrames ? "Recording complete" : "Start Recording"}
        style={{ 
          touchAction: 'none',
          zIndex: 10
        }}
      >
        <div className="absolute inset-0 rounded-full border-[2.5px] border-red-600"></div>
        <div className={`
          bg-red-600 transition-all duration-200 ease-in-out pointer-events-none
          ${isCapturing 
            ? 'w-[14px] h-[14px] rounded-[3px] animate-pulse' 
            : 'w-[28px] h-[28px] rounded-full'
          }
        `}></div>
      </button>
    );
  };

  // Recording indicator component with predictive UI
  const RecordingIndicator = () => {
    const { displayFrames, confidence } = usePredictiveFrames();
    
    if (!isCapturing && !isProcessingComplete) return null;

    const actualFrames = capturedFrameCount || frameCount;
    const framesForDisplay = isCapturing ? displayFrames : actualFrames;
    const progress = referenceFrameCount > 0 
      ? Math.min(framesForDisplay / referenceFrameCount * 100, 100)
      : 0;

    return (
      <div 
        className="absolute top-2 right-2 z-10"
        onMouseEnter={() => setShowRecordingTooltip(true)}
        onMouseLeave={() => setShowRecordingTooltip(false)}
      >
        <div className={`w-4 h-4 rounded-full ${isCapturing ? 'bg-red-500' : 'bg-green-500'} animate-pulse`} />
        
        {showRecordingTooltip && (
          <div className="absolute top-full right-0 mt-1 bg-black bg-opacity-90 text-white text-12 px-3 py-2 rounded whitespace-nowrap">
            {isCapturing ? (
              <>
                Recording in progress<br />
                <span className={confidence > 0.8 ? '' : 'opacity-70'}>
                  Frame {framesForDisplay} of {referenceFrameCount} captured
                </span><br />
                {referenceFrameCount > 0 && (
                  <div className="mt-1">
                    <div className="w-32 h-2 bg-gray-700 rounded-full overflow-hidden">
                      <div 
                        className="h-full bg-gradient-to-r from-red-500 to-red-400 transition-all duration-500 ease-out"
                        style={{ width: `${progress}%` }}
                      />
                    </div>
                    <div className="text-10 mt-1">{Math.round(progress)}% complete</div>
                  </div>
                )}
              </>
            ) : (
              <>
                Recording complete<br />
                {referenceFrameCount} frames captured
              </>
            )}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="grid grid-cols-2 gap-4 h-full">
      {/* Current take frame */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-14 font-medium">Current Take</h3>
          {isNavigatingManually && isCapturing && (
            <button
              onClick={onReturnToLatest}
              className="flex items-center gap-1 px-2 py-1 text-12 bg-yellow-100 text-yellow-800 rounded hover:bg-yellow-200"
              title="Return to latest frame"
            >
              <Play size={12} />
              Return to Live
            </button>
          )}
        </div>
        
        <div className="relative bg-gray-200" style={{ paddingBottom: '56.25%' }}>
          {displayFrame ? (
            <img 
              src={displayFrame} 
              alt="Current frame"
              className="absolute inset-0 w-full h-full object-contain"
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center text-gray-500">
              {isCapturing ? 'Waiting for processed frames...' : 'No frames captured'}
            </div>
          )}
          
          {/* Recording indicator */}
          <RecordingIndicator />
          
          {/* Frame counter - show processed frame count with predictive UI */}
          <FrameCounter 
            currentFrameIndex={currentFrameIndex}
            processedFrameCount={processedFrameCount}
            frameCount={frameCount}
            referenceFrameCount={referenceFrameCount}
            isCapturing={isCapturing}
          />
        </div>
        
        {/* Controls under current take */}
        <div className="mt-4 relative flex items-center justify-between">
          {/* Left section - source selection */}
          <div className="w-[140px] min-w-0">
            <button
              onClick={() => setShowSourceModal(true)}
              disabled={isCapturing || hasFrames}
              className={`flex items-center gap-2 hover:scale-105 transition-all duration-150 w-full ${
                isCapturing || hasFrames
                  ? 'text-gray-400 cursor-not-allowed hover:scale-100'
                  : 'text-gray-800 hover:text-black'
              }`}
              title={captureSource ? `Source: ${captureSource.name}` : "Select Capture Source"}
            >
              <Airplay size={20} strokeWidth={1.5} className="flex-shrink-0" />
              <span className="text-14 truncate">
                {captureSource 
                  ? (hasFrames ? `${captureSource.name} (Locked)` : captureSource.name)
                  : 'Select Source'}
              </span>
            </button>
          </div>
          
          {/* Center section - absolutely positioned to center of parent */}
          <div className="absolute left-1/2 transform -translate-x-1/2">
            {!hasFrames ? (
              <RecordButton />
            ) : (
              <button
                onClick={onRedoDetection}
                disabled={isCapturing}
                className={`p-2 hover:scale-110 transition-all duration-150 ${
                  isCapturing
                    ? 'text-gray-400 cursor-not-allowed hover:scale-100'
                    : 'text-gray-800 hover:text-black'
                }`}
                title="Re-run detection"
              >
                <RotateCw size={20} strokeWidth={1.5} />
              </button>
            )}
          </div>
          
          {/* Right section - settings */}
          <button
            onClick={onSceneSettings}
            disabled={isCapturing}
            className={`p-1 hover:scale-110 transition-all duration-150 ${
              isCapturing
                ? 'text-gray-400 cursor-not-allowed hover:scale-100'
                : 'text-gray-800 hover:text-black'
            }`}
            title="Scene Configuration"
          >
            <SlidersHorizontal size={20} strokeWidth={1.5} />
          </button>
        </div>
      </div>
      
      {/* Reference take frame */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <div className="relative">
            <button
              onClick={() => setShowReferenceDropdown(!showReferenceDropdown)}
              disabled={isCapturing}
              className={`flex items-center gap-1 text-14 font-medium ${
                isCapturing
                  ? 'text-gray-400 cursor-not-allowed'
                  : 'hover:opacity-80'
              }`}
            >
              {getDropdownLabel()}
              <ChevronDown size={14} />
            </button>
            
            {showReferenceDropdown && !isCapturing && (
              <div className="absolute top-full mt-1 bg-white border border-gray-200 rounded shadow-lg z-10 w-64 max-h-64 overflow-y-auto">
                <div className="p-2">
                  {referenceTake ? (
                    <>
                      <div className="text-12 font-medium text-gray-600 mb-2">
                        Reference Take
                      </div>
                      <button
                        onClick={() => !isViewingReferenceTake && handleReferenceSelect(referenceTake.id)}
                        disabled={isViewingReferenceTake}
                        className={`block w-full text-left px-2 py-1 text-14 rounded mb-2 ${
                          isViewingReferenceTake
                            ? 'text-gray-400 cursor-not-allowed'
                            : selectedReferenceId === referenceTake.id 
                              ? 'bg-gray-100' 
                              : 'hover:bg-gray-100'
                        }`}
                      >
                        Reference Take ({referenceTake.name})
                      </button>
                    </>
                  ) : (
                    <>
                      <div className="text-12 font-medium text-gray-600 mb-2">
                        Reference Take (None)
                      </div>
                    </>
                  )}
                  
                  {Object.keys(groupedTakes).length > 0 && (
                    <div className="my-2 border-t border-gray-200"></div>
                  )}
                  
                  {Object.entries(groupedTakes).map(([angleName, takes]) => (
                    <div key={angleName} className="mb-3">
                      <div className="text-12 font-medium text-gray-600 mb-1">{angleName}</div>
                      {takes.map((take) => (
                        <button
                          key={take.id}
                          onClick={() => !take.isCurrentTake && handleReferenceSelect(take.id)}
                          disabled={take.isCurrentTake}
                          className={`block w-full text-left px-2 py-1 text-14 rounded ${
                            take.isCurrentTake 
                              ? 'text-gray-400 cursor-not-allowed' 
                              : take.id === selectedReferenceId 
                                ? 'bg-gray-100' 
                                : 'hover:bg-gray-100'
                          }`}
                        >
                          {take.name} {take.isCurrentTake && '(Current)'}
                        </button>
                      ))}
                    </div>
                  ))}
                  
                  {Object.keys(groupedTakes).length === 0 && !referenceTake && (
                    <p className="text-14 text-gray-500">No other takes available</p>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
        
        <div className="relative bg-gray-200" style={{ paddingBottom: '56.25%' }}>
          {referenceFrame ? (
            <img 
              src={referenceFrame} 
              alt="Reference frame"
              className="absolute inset-0 w-full h-full object-contain"
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center text-gray-500">
              {selectedReferenceId && (processedFrameCount > 0 || frameCount > 0) ? 'No matching frame' : 'No reference selected'}
            </div>
          )}
          
          {/* Reference frame counter overlay */}
          {referenceFrame && (processedFrameCount > 0 || frameCount > 0) && (
            <div className="absolute bottom-2 right-2 bg-black bg-opacity-70 text-white text-12 px-2 py-1 rounded">
              Frame {currentFrameIndex + 1}
            </div>
          )}
        </div>
        
        {/* Frame navigation under reference */}
        <div className="mt-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              onClick={() => onFrameNavigation('prev')}
              disabled={currentFrameIndex === 0 || (processedFrameCount === 0 && frameCount === 0) || isCapturing}
              className={`w-8 h-8 flex items-center justify-center hover:scale-110 transition-all duration-150 ${
                currentFrameIndex === 0 || (processedFrameCount === 0 && frameCount === 0) || isCapturing
                  ? 'text-gray-300 cursor-not-allowed hover:scale-100'
                  : 'text-gray-800 hover:text-black'
              }`}
            >
              <ChevronLeft size={20} strokeWidth={1.5} />
            </button>
            
            <button
              onClick={() => onFrameNavigation('next')}
              disabled={currentFrameIndex >= (processedFrameCount > 0 ? processedFrameCount : frameCount) - 1 || (processedFrameCount === 0 && frameCount === 0) || isCapturing}
              className={`w-8 h-8 flex items-center justify-center hover:scale-110 transition-all duration-150 ${
                currentFrameIndex >= (processedFrameCount > 0 ? processedFrameCount : frameCount) - 1 || (processedFrameCount === 0 && frameCount === 0) || isCapturing
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
                    (currentFrameIndex / Math.max((processedFrameCount || frameCount) - 1, 1)) * 100
                  }%, #D1D5DB ${
                    (currentFrameIndex / Math.max((processedFrameCount || frameCount) - 1, 1)) * 100
                  }%, #D1D5DB 100%)`
                }}
              />
              <input
                type="range"
                min="0"
                max={Math.max(0, (isCapturing && processedFrameCount > 0 ? processedFrameCount : frameCount) - 1)}
                value={currentFrameIndex}
                onChange={onSliderChange}
                disabled={isCapturing || (processedFrameCount === 0 && frameCount === 0)}
                className={`relative w-full appearance-none bg-transparent z-10 ${
                  isCapturing || (processedFrameCount === 0 && frameCount === 0)
                    ? 'opacity-50 cursor-not-allowed'
                    : 'cursor-pointer'
                }`}
              />
            </div>
          </div>
          
          <div className="text-14 text-gray-600">
            {(processedFrameCount > 0 || frameCount > 0) ? `${currentFrameIndex + 1}/${referenceFrameCount || processedFrameCount || frameCount}` : '0/0'} frames
          </div>
        </div>
      </div>

      {/* Source selection modal */}
      {showSourceModal && !isCapturing && !hasFrames && (
        <SourceSelectionModal
          availableSources={availableSources}
          currentSource={captureSource}
          onClose={() => {
            setShowSourceModal(false);
            window.pendingCaptureAfterSourceSelect = false;
          }}
          onSelectSource={handleSourceSelect}
        />
      )}
    </div>
  );
}

// Frame counter component with predictive UI
function FrameCounter({ currentFrameIndex, processedFrameCount, frameCount, referenceFrameCount, isCapturing }) {
  const { displayFrames } = usePredictiveFrames();
  
  if (!isCapturing && processedFrameCount === 0 && frameCount === 0) return null;
  
  const totalFrames = referenceFrameCount || frameCount;
  const displayTotal = isCapturing && displayFrames > processedFrameCount ? displayFrames : totalFrames;
  
  return (
    <div className="absolute bottom-2 right-2 bg-black bg-opacity-70 text-white text-12 px-2 py-1 rounded">
      Frame {currentFrameIndex + 1} of {displayTotal}
    </div>
  );
}
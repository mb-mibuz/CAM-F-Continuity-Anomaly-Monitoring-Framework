import React, { useState, useCallback } from 'react';
import { ChevronDown } from 'lucide-react';
import { useDataStore } from '../../../stores';
import { useSelectiveSubscription, useRenderMonitor } from '../../../hooks/useSelectiveSubscription';
import FrameDisplay from '../../../components/monitoring/FrameDisplay';
import FrameNavigator from '../../../components/monitoring/FrameNavigator';

export default function FrameViewer({
  takeId,
  currentFrame,
  referenceFrame,
  frameCount,
  currentFrameIndex,
  isLoadingFrame,
  availableTakes,
  angleId,
  referenceTakeId,
  referenceFrameCount,
  isCapturing,
  hasDetectorErrors,
  detectorErrors = []
}) {
  const [showReferenceDropdown, setShowReferenceDropdown] = useState(false);
  const [selectedReferenceId, setSelectedReferenceId] = useState(referenceTakeId);
  
  // Sync selectedReferenceId with prop changes
  React.useEffect(() => {
    setSelectedReferenceId(referenceTakeId);
  }, [referenceTakeId]);
  
  // Debug logging
  console.log('[FrameViewer] Overlay conditions:', {
    selectedReferenceId,
    referenceFrameCount,
    currentFrameIndex,
    shouldShowOverlay: selectedReferenceId && referenceFrameCount > 0 && currentFrameIndex >= referenceFrameCount
  });
  
  // Use render monitor in development
  useRenderMonitor('FrameViewer');
  
  // Selective subscriptions for frame navigation
  const navigationActions = useSelectiveSubscription(
    useDataStore,
    state => ({
      setCurrentFrameIndex: state.setCurrentFrameIndex,
      navigateFrame: state.navigateFrame,
      returnToLatest: state.returnToLatest
    })
  );
  
  const isNavigatingManually = useSelectiveSubscription(
    useDataStore,
    state => state.isNavigatingManually
  );
  
  // Get preview frame when no frames exist
  const previewFrame = useSelectiveSubscription(
    useDataStore,
    state => state.previewFrame
  );
  
  const { setCurrentFrameIndex, navigateFrame, returnToLatest } = navigationActions;
  
  // Check if viewing reference take
  const currentTake = availableTakes.find(t => t.id === takeId);
  const isViewingReferenceTake = currentTake?.isReferenceTake;
  
  // Group takes by angle
  const groupedTakes = availableTakes.reduce((acc, take) => {
    if (!acc[take.angleName]) {
      acc[take.angleName] = [];
    }
    acc[take.angleName].push(take);
    return acc;
  }, {});

  // Handle reference selection
  const handleReferenceSelect = useCallback((newReferenceId) => {
    setSelectedReferenceId(newReferenceId);
    setShowReferenceDropdown(false);
    
    // Update reference frame in store
    const captureStore = useDataStore.getState();
    captureStore.setReferenceTake(newReferenceId, referenceFrameCount);
  }, [referenceFrameCount]);

  // Get dropdown label
  const getDropdownLabel = () => {
    if (!selectedReferenceId) {
      return 'No Reference';
    }
    
    const selectedTake = availableTakes.find(t => t.id === selectedReferenceId);
    if (selectedTake) {
      if (selectedTake.isReferenceTake) {
        return `Reference Take (${selectedTake.name})`;
      }
      return `${selectedTake.name} (${selectedTake.angleName})`;
    }
    
    return 'Reference Take';
  };
  
  // Extract bounding boxes for current frame
  const currentFrameBoundingBoxes = React.useMemo(() => {
    const boxes = [];
    
    // Find all errors for the current frame
    detectorErrors.forEach(error => {
      if (error.instances) {
        // Check instances for current frame
        error.instances.forEach(instance => {
          if (instance.frame_id === currentFrameIndex && instance.bounding_boxes) {
            boxes.push(...instance.bounding_boxes);
          }
        });
      } else if (error.frame_id === currentFrameIndex && error.bounding_boxes) {
        // Single error with bounding boxes
        boxes.push(...error.bounding_boxes);
      }
    });
    
    return boxes;
  }, [detectorErrors, currentFrameIndex]);

  return (
    <div className="h-full grid grid-cols-2 gap-4">
      {/* Current take frame with recording controls below */}
      <div className="flex flex-col min-h-0">
        <div className="flex items-center justify-between mb-2 flex-shrink-0">
          <h3 className="text-14 font-medium">Current Take</h3>
          {isCapturing && isNavigatingManually && (
            <button
              onClick={returnToLatest}
              className="px-2 py-1 text-12 bg-yellow-100 text-yellow-800 rounded hover:bg-yellow-200"
            >
              Return to Live
            </button>
          )}
        </div>
        
        <div className="flex-1 min-h-0 mb-4">
          <FrameDisplay
            frame={frameCount > 0 ? currentFrame : previewFrame}
            frameIndex={currentFrameIndex}
            totalFrames={frameCount}
            isLoading={isLoadingFrame}
            isCapturing={isCapturing}
            hasErrors={hasDetectorErrors}
            showBoundingBoxes={hasDetectorErrors}
            boundingBoxes={currentFrameBoundingBoxes}
            showPlaceholder={frameCount === 0 && !previewFrame}
            placeholderText={frameCount === 0 ? "Select a source to preview" : undefined}
          />
        </div>
      </div>
      
      {/* Reference frame with frame navigation below */}
      <div className="flex flex-col min-h-0">
        <div className="flex items-center justify-between mb-2 flex-shrink-0">
          <div className="relative">
            <button
              onClick={() => setShowReferenceDropdown(!showReferenceDropdown)}
              disabled={isCapturing}
              className={`
                flex items-center gap-1 text-14 font-medium
                ${isCapturing ? 'text-gray-400 cursor-not-allowed' : 'hover:opacity-80'}
              `}
            >
              {getDropdownLabel()}
              <ChevronDown size={14} />
            </button>
            
            {/* Reference dropdown */}
            {showReferenceDropdown && !isCapturing && (
              <div className="absolute top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-10 w-64 max-h-64 overflow-y-auto">
                <div className="p-2">
                  {/* Reference take option */}
                  {referenceTakeId && (
                    <div className="mb-2">
                      <div className="text-12 font-medium text-gray-600 mb-1">Reference Take</div>
                      <button
                        onClick={() => handleReferenceSelect(referenceTakeId)}
                        disabled={isViewingReferenceTake}
                        className={`
                          block w-full text-left px-2 py-1 text-14 rounded
                          ${isViewingReferenceTake
                            ? 'text-gray-400 cursor-not-allowed'
                            : selectedReferenceId === referenceTakeId
                              ? 'bg-gray-100'
                              : 'hover:bg-gray-100'
                          }
                        `}
                      >
                        {availableTakes.find(t => t.id === referenceTakeId)?.name || 'Reference Take'}
                      </button>
                    </div>
                  )}
                  
                  {/* Separator */}
                  {referenceTakeId && Object.keys(groupedTakes).length > 0 && (
                    <div className="my-2 border-t border-gray-200" />
                  )}
                  
                  {/* Grouped takes */}
                  {Object.entries(groupedTakes).map(([angleName, takes]) => (
                    <div key={angleName} className="mb-3">
                      <div className="text-12 font-medium text-gray-600 mb-1">{angleName}</div>
                      {takes.map(take => (
                        <button
                          key={take.id}
                          onClick={() => !take.isCurrentTake && handleReferenceSelect(take.id)}
                          disabled={take.isCurrentTake}
                          className={`
                            block w-full text-left px-2 py-1 text-14 rounded
                            ${take.isCurrentTake
                              ? 'text-gray-400 cursor-not-allowed'
                              : take.id === selectedReferenceId
                                ? 'bg-gray-100'
                                : 'hover:bg-gray-100'
                            }
                          `}
                        >
                          {take.name} {take.isCurrentTake && '(Current)'}
                        </button>
                      ))}
                    </div>
                  ))}
                  
                  {/* No takes available */}
                  {Object.keys(groupedTakes).length === 0 && !referenceTakeId && (
                    <p className="text-14 text-gray-500 px-2 py-2">No other takes available</p>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
        
        <div className="flex-1 min-h-0 mb-4 relative overflow-hidden">
          {/* Always render FrameDisplay */}
          <FrameDisplay
            frame={referenceFrame}
            frameIndex={currentFrameIndex}
            totalFrames={referenceFrameCount}
            isReference={true}
            showPlaceholder={!selectedReferenceId}
            placeholderText="No reference selected"
          />
          
          {/* Overlay for when we exceed reference frames */}
          {selectedReferenceId && referenceFrameCount > 0 && currentFrameIndex >= referenceFrameCount && (
            <div className="absolute inset-0 bg-gray-900 bg-opacity-75 rounded-lg flex items-center justify-center z-50 pointer-events-none">
              <div className="text-center bg-gray-800 bg-opacity-95 p-6 rounded-lg shadow-2xl">
                <p className="text-18 text-white font-semibold mb-2">No More Matching Frames</p>
                <p className="text-16 text-gray-200">
                  Reference take has only {referenceFrameCount} frame{referenceFrameCount !== 1 ? 's' : ''}
                </p>
                <p className="text-14 text-gray-400 mt-3">
                  Current frame: {currentFrameIndex + 1}
                </p>
              </div>
            </div>
          )}
        </div>
        
        {/* Frame navigation controls under reference */}
        <div className="h-20 flex items-center">
          <FrameNavigator
            currentIndex={currentFrameIndex}
            totalFrames={frameCount || 0}
            isCapturing={isCapturing}
            onNavigate={navigateFrame}
            onIndexChange={setCurrentFrameIndex}
            showProgress={referenceFrameCount > 0}
            maxFrames={referenceFrameCount}
          />
        </div>
      </div>
    </div>
  );
}
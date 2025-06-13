import React, { useState, useCallback, useRef } from 'react';
import { ChevronDown, Maximize2, Activity, Upload } from 'lucide-react';
import { useDataStore, useAppStore } from '../../../stores';
import { useSelectiveSubscription } from '../../../hooks/useSelectiveSubscription';
import FrameDisplay from '../../../components/monitoring/FrameDisplay';
import FrameNavigator from '../../../components/monitoring/FrameNavigator';
import CaptureControls from './CaptureControls';
import FullscreenFrameModal from '../../../components/modals/FullscreenFrameModal';
import VideoUploadModal from '../../../components/modals/VideoUploadModal';
import { api } from '../../../utils/api';
import { SSEService } from '../../../services';

export default function FrameViewerWithControls({
  takeId,
  sceneId,
  sceneName,
  sceneData,
  currentFrame,
  referenceFrame,
  frameCount,
  currentFrameIndex,
  isLoadingFrame,
  availableTakes,
  angleId,
  referenceTakeId,
  referenceFrameCount: propReferenceFrameCount,
  captureState,
  hasDetectorErrors,
  detectorErrors = []
}) {
  const [showReferenceDropdown, setShowReferenceDropdown] = useState(false);
  const [showFullscreenModal, setShowFullscreenModal] = useState(false);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  
  // Get reference take data from store
  const storeReferenceTakeId = useDataStore(state => state.referenceTakeId);
  const storeReferenceFrameCount = useDataStore(state => state.referenceFrameCount);
  
  // Use store values if available, otherwise fall back to props
  const selectedReferenceId = storeReferenceTakeId || referenceTakeId;
  const referenceFrameCount = storeReferenceFrameCount ?? propReferenceFrameCount;
  
  // Auto-select reference take on mount and when referenceTakeId changes
  React.useEffect(() => {
    console.log('[FrameViewerWithControls] Reference take update:', { 
      referenceTakeId, 
      referenceFrameCount,
      availableTakes: availableTakes.length,
      selectedReferenceId,
      storeReferenceTakeId
    });
    
    // Only set initial reference if nothing is selected in store
    if (!storeReferenceTakeId && availableTakes.length > 0) {
      // Check if any take is marked as reference
      const referenceTake = availableTakes.find(t => t.isReferenceTake);
      if (referenceTake) {
        console.log('[FrameViewerWithControls] Found reference take in available takes:', referenceTake);
        const captureStore = useDataStore.getState();
        captureStore.setReferenceTake(referenceTake.id, referenceTake.frame_count || 0);
      } else if (referenceTakeId) {
        // Use the prop value if no reference take found
        const captureStore = useDataStore.getState();
        captureStore.setReferenceTake(referenceTakeId, referenceFrameCount);
      }
    }
  }, [referenceTakeId, referenceFrameCount, availableTakes, storeReferenceTakeId]);
  
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
  
  // Debug: Get the full store state to see what's happening
  React.useEffect(() => {
    const state = useDataStore.getState();
    console.log('[FrameViewerWithControls] Store state:', {
      previewFrame: state.previewFrame ? 'has data' : 'no data',
      previewFrameLength: state.previewFrame?.length,
      isCapturing: state.isCapturing,
      frameCount: state.frameCount
    });
  }, []);
  
  // Track preview frame changes
  React.useEffect(() => {
    console.log('[FrameViewerWithControls] Preview frame changed:', previewFrame ? 'has data' : 'no data');
  }, [previewFrame]);
  
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
  
  // Get all detector results for current frame (for fullscreen modal)
  const currentFrameDetectorResults = React.useMemo(() => {
    const results = [];
    
    detectorErrors.forEach(error => {
      if (error.instances) {
        // Check instances for current frame
        error.instances.forEach(instance => {
          if (instance.frame_id === currentFrameIndex) {
            results.push({
              ...error,
              frame_id: instance.frame_id,
              confidence: instance.confidence,
              bounding_boxes: instance.bounding_boxes || error.bounding_boxes || [],
              is_false_positive: instance.is_false_positive || error.is_false_positive || false
            });
          }
        });
      } else if (error.frame_id === currentFrameIndex) {
        // Single error for this frame
        results.push(error);
      }
    });
    
    return results;
  }, [detectorErrors, currentFrameIndex]);
  
  console.log('[FrameViewerWithControls] Render state:', {
    previewFrame: previewFrame ? 'has data' : 'no data',
    frameCount,
    hasFrames: captureState.hasFrames,
    isCapturing: captureState.isCapturing,
    currentFrame: currentFrame ? 'has data' : 'no data',
    frameToDisplay: captureState.hasFrames ? 'currentFrame' : 'previewFrame',
    currentFrameIndex,
    referenceTakeId,
    referenceFrameCount,
    selectedReferenceId,
    shouldShowOverlay: selectedReferenceId && referenceFrameCount > 0 && frameCount > 0 && currentFrameIndex >= referenceFrameCount
  });
  
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
    setShowReferenceDropdown(false);
    
    // Get the frame count for the newly selected take
    const selectedTake = availableTakes.find(t => t.id === newReferenceId);
    const newReferenceFrameCount = selectedTake?.frame_count || 0;
    
    // Update reference frame in store with the correct frame count
    const captureStore = useDataStore.getState();
    captureStore.setReferenceTake(newReferenceId, newReferenceFrameCount);
  }, [availableTakes]);

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

  const addNotification = useAppStore(state => state.addNotification);
  const uploadCompleteRef = useRef(false);
  const isUploadingRef = useRef(false);

  // Handle video upload
  const handleVideoUpload = useCallback(async (file) => {
    setShowUploadModal(false);
    setIsUploading(true);
    isUploadingRef.current = true;
    setUploadProgress(0);
    uploadCompleteRef.current = false;

    try {
      // Upload video file to existing take
      const uploadResponse = await api.uploadVideoFile(takeId, file);
      console.log('Video upload started for take:', takeId, uploadResponse);

      // Subscribe to SSE events for upload progress
      const handleUploadEvent = (event) => {
        console.log('[FrameViewerWithControls] Upload SSE event:', event);
        
        const eventType = event.event_type || event.type || event.event;
        const eventData = event.data || event;
        
        if (eventData.take_id !== takeId) return;

        switch (eventType) {
          case 'frame_captured':
          case 'upload_progress':
            if (eventData.frame_count !== undefined || eventData.frames_extracted !== undefined) {
              const frameCount = eventData.frame_count || eventData.frames_extracted || 0;
              const totalFrames = eventData.total_frames || 30; // Estimate if not provided
              const progress = Math.min((frameCount / totalFrames) * 100, 95);
              console.log(`[Upload] Progress: ${frameCount}/${totalFrames} = ${progress}%`);
              setUploadProgress(progress);
            }
            break;
          case 'upload_completed':
            if (!uploadCompleteRef.current) {
              uploadCompleteRef.current = true;
              console.log('Upload completed, frame count:', eventData.frame_count);
              setUploadProgress(100);
              
              setTimeout(() => {
                setIsUploading(false);
                isUploadingRef.current = false;
                setUploadProgress(0);
                addNotification({
                  type: 'success',
                  message: 'Video uploaded successfully'
                });
                
                // Refresh frame count
                if (window.refreshTakeData) {
                  window.refreshTakeData();
                }
              }, 500);
            }
            break;
          case 'upload_error':
            console.error('Upload error:', eventData);
            setIsUploading(false);
            isUploadingRef.current = false;
            setUploadProgress(0);
            addNotification({
              type: 'error',
              message: 'Failed to upload video'
            });
            break;
        }
      };

      // Subscribe to multiple SSE channels for better coverage
      const unsubscribe1 = SSEService.subscribe(`take_${takeId}`, handleUploadEvent);
      const unsubscribe2 = SSEService.subscribe('capture', handleUploadEvent);
      const unsubscribe3 = SSEService.subscribe('frame_events', handleUploadEvent);
      
      // Also poll for progress as a backup
      const pollInterval = setInterval(async () => {
        if (uploadCompleteRef.current || !isUploadingRef.current) {
          clearInterval(pollInterval);
          return;
        }
        
        try {
          const progress = await api.getCaptureProgress(takeId);
          if (progress) {
            // Calculate progress based on actual processing
            let calculatedProgress = 0;
            if (progress.frame_count > 0) {
              // Use frame count for progress (assuming average video has ~100-300 frames)
              calculatedProgress = Math.min((progress.frame_count / 100) * 90, 90);
            } else if (progress.processed_frames > 0 && progress.total_frames > 0) {
              // Use processed/total if available
              calculatedProgress = (progress.processed_frames / progress.total_frames) * 90;
            }
            
            console.log(`[Polling] Upload progress:`, progress);
            console.log(`[Polling] Calculated progress: ${calculatedProgress}%`);
            setUploadProgress(calculatedProgress);
            
            // Check if upload is complete
            if (!progress.is_capturing && progress.frame_count > 0) {
              uploadCompleteRef.current = true;
              clearInterval(pollInterval);
              setUploadProgress(100);
              
              setTimeout(() => {
                setIsUploading(false);
                isUploadingRef.current = false;
                setUploadProgress(0);
                addNotification({
                  type: 'success',
                  message: 'Video uploaded successfully'
                });
                
                if (window.refreshTakeData) {
                  window.refreshTakeData();
                }
              }, 500);
            }
          }
        } catch (error) {
          console.error('Error polling upload status:', error);
        }
      }, 1000); // Poll every second

      // Set timeout to clean up after 5 minutes
      setTimeout(() => {
        unsubscribe1();
        unsubscribe2();
        unsubscribe3();
        clearInterval(pollInterval);
        if (isUploadingRef.current && !uploadCompleteRef.current) {
          setIsUploading(false);
          isUploadingRef.current = false;
          setUploadProgress(0);
          addNotification({
            type: 'error',
            message: 'Video upload timed out'
          });
        }
      }, 5 * 60 * 1000);

    } catch (error) {
      console.error('Error uploading video:', error);
      setIsUploading(false);
      isUploadingRef.current = false;
      setUploadProgress(0);
      addNotification({
        type: 'error',
        message: 'Failed to upload video'
      });
    }
  }, [takeId, addNotification]);

  return (
    <div className="flex gap-4">
      {/* Current take frame with recording controls below */}
      <div className="flex-1 flex flex-col justify-between">
        <div className="flex items-center justify-between mb-1 flex-shrink-0">
          <div className="flex items-center gap-2">
            <h3 className="text-14 font-medium">Current Take</h3>
            <button
              onClick={() => setShowUploadModal(true)}
              disabled={captureState.isCapturing || isUploading || captureState.hasFrames}
              className={`p-1 rounded transition-colors ${
                captureState.isCapturing || isUploading || captureState.hasFrames
                  ? 'text-gray-400 cursor-not-allowed'
                  : 'text-gray-600 hover:text-gray-800 hover:bg-gray-100'
              }`}
              title={captureState.hasFrames ? "Cannot upload - take already has frames" : "Upload video file"}
            >
              <Upload size={16} />
            </button>
          </div>
          {captureState.isCapturing && isNavigatingManually && (
            <button
              onClick={returnToLatest}
              className="px-2 py-1 text-12 bg-yellow-100 text-yellow-800 rounded hover:bg-yellow-200"
            >
              Return to Live
            </button>
          )}
        </div>
        
        <div>
          <FrameDisplay
            frame={captureState.hasFrames ? currentFrame : previewFrame}
            frameIndex={currentFrameIndex}
            totalFrames={frameCount}
            isLoading={isLoadingFrame}
            isCapturing={captureState.isCapturing}
            hasErrors={hasDetectorErrors}
            showBoundingBoxes={hasDetectorErrors}
            boundingBoxes={currentFrameBoundingBoxes}
            showPlaceholder={!captureState.hasFrames && !previewFrame}
            placeholderText={!captureState.hasFrames ? "Select a source to preview" : undefined}
            showFrameCounterDuringCapture={true}
            showRecordingOverlay={true}
          />
        </div>
        
        {/* Capture controls under current take */}
        <div className="h-12 flex-shrink-0 mt-4 mb-4">
          <CaptureControls
            takeId={takeId}
            sceneId={sceneId}
            sceneName={sceneName}
            sceneData={sceneData}
            referenceFrameCount={referenceFrameCount}
            hasFrames={captureState.hasFrames}
            isCapturing={captureState.isCapturing}
            source={captureState.source}
            onFullscreen={() => setShowFullscreenModal(true)}
          />
        </div>
      </div>
      
      {/* Reference frame with frame navigation below */}
      <div className="flex-1 flex flex-col justify-between">
        <div className="flex items-center justify-between mb-1 flex-shrink-0">
          <div className="relative">
            <button
              onClick={() => setShowReferenceDropdown(!showReferenceDropdown)}
              disabled={captureState.isCapturing}
              className={`
                flex items-center gap-1 text-14 font-medium
                ${captureState.isCapturing ? 'text-gray-400 cursor-not-allowed' : 'hover:opacity-80'}
              `}
            >
              {getDropdownLabel()}
              <ChevronDown size={14} />
            </button>
            
            {/* Reference dropdown */}
            {showReferenceDropdown && !captureState.isCapturing && (
              <div className="absolute top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-[60] w-64 max-h-64 overflow-y-auto">
                <div className="p-2">
                  {/* Reference take option - always show at top */}
                  <div className="mb-2">
                    <div className="text-12 font-medium text-gray-600 mb-1">Reference Take</div>
                    {(() => {
                      // Find any take marked as reference in available takes
                      const refTake = availableTakes.find(t => t.isReferenceTake);
                      const refId = referenceTakeId || refTake?.id;
                      
                      if (refId) {
                        const takeName = availableTakes.find(t => t.id === refId)?.name || 'Reference Take';
                        return (
                          <button
                            onClick={() => handleReferenceSelect(refId)}
                            disabled={isViewingReferenceTake}
                            className={`
                              block w-full text-left px-2 py-1 text-14 rounded
                              ${isViewingReferenceTake
                                ? 'text-gray-400 cursor-not-allowed'
                                : selectedReferenceId === refId
                                  ? 'bg-gray-100'
                                  : 'hover:bg-gray-100'
                              }
                            `}
                          >
                            {takeName}
                          </button>
                        );
                      }
                      
                      return <div className="px-2 py-1 text-14 text-gray-400 italic">No reference take set</div>;
                    })()}
                  </div>
                  
                  {/* Separator */}
                  {(referenceTakeId || availableTakes.some(t => t.isReferenceTake)) && Object.keys(groupedTakes).length > 0 && (
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
          
          {/* Processing progress indicator */}
          {(captureState.isCapturing || captureState.processedFrames > 0) && (
            <div className="flex items-center gap-2 text-12">
              <Activity size={14} className="text-blue-500 animate-pulse" />
              <span className="text-gray-600">
                Processing: {captureState.processedFrames}/{Math.min(frameCount, referenceFrameCount || frameCount)} frames
              </span>
            </div>
          )}
        </div>
        
        <div className="relative">
          <FrameDisplay
            frame={referenceFrame}
            frameIndex={currentFrameIndex}
            totalFrames={referenceFrameCount}
            isReference={true}
            showPlaceholder={!selectedReferenceId}
            placeholderText={selectedReferenceId ? "No matching frame" : "No reference selected"}
          />
          
          {/* Overlay for when we exceed reference frames */}
          {selectedReferenceId && referenceFrameCount > 0 && frameCount > 0 && currentFrameIndex >= referenceFrameCount && (
            <div className="absolute inset-0 bg-gray-900 bg-opacity-75 rounded-lg flex items-center justify-center z-40 pointer-events-none">
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
        <div className="h-12 flex-shrink-0 mt-4 mb-4 flex items-center">
          <FrameNavigator
            currentIndex={currentFrameIndex}
            totalFrames={frameCount || 0}
            isCapturing={captureState.isCapturing}
            onNavigate={navigateFrame}
            onIndexChange={setCurrentFrameIndex}
            showProgress={referenceFrameCount > 0}
            maxFrames={referenceFrameCount}
          />
        </div>
      </div>
      
      {/* Fullscreen Modal */}
      <FullscreenFrameModal
        isOpen={showFullscreenModal}
        onClose={() => setShowFullscreenModal(false)}
        frameData={captureState.hasFrames ? currentFrame : previewFrame}
        frameNumber={currentFrameIndex + 1}
        totalFrames={frameCount || 0}
        onFrameChange={(newIndex) => {
          console.log('[FrameViewerWithControls] Fullscreen modal frame change:', newIndex);
          setCurrentFrameIndex(newIndex);
        }}
        onNavigate={(direction) => {
          console.log('[FrameViewerWithControls] Fullscreen modal navigate:', direction);
          navigateFrame(direction);
        }}
        frameRate={sceneData?.frame_rate || 24}
        currentTime={currentFrameIndex / (sceneData?.frame_rate || 24)}
        detectorResults={currentFrameDetectorResults}
        isCapturing={captureState.isCapturing}
        getCurrentFrame={() => {
          // Always get the latest frame data from the parent component
          return captureState.hasFrames ? currentFrame : previewFrame;
        }}
      />

      {/* Video upload modal */}
      {showUploadModal && !isUploading && (
        <VideoUploadModal
          onClose={() => setShowUploadModal(false)}
          onUpload={handleVideoUpload}
        />
      )}

      {/* Upload progress overlay */}
      {isUploading && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-sm w-full">
            <h3 className="text-16 font-semibold mb-4">Processing Video</h3>
            <div className="mb-4">
              <div className="flex justify-between text-14 mb-2">
                <span>Progress</span>
                <span>{Math.round(uploadProgress)}%</span>
              </div>
              <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary transition-all duration-300"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
            </div>
            <p className="text-12 text-gray-600">
              Extracting frames from video...
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
import React from 'react';
import { Upload } from 'lucide-react';
import SourceSelector from '../../monitoring/SourceSelector';
import CaptureButton from '../../monitoring/CaptureButton';
import FrameDisplay from '../../monitoring/FrameDisplay';

export default function CaptureStep({
  captureState,
  frameState,
  onStartCapture,
  onStopCapture,
  onUploadClick,
  isCleaningUp,
  isUploadDisabled
}) {
  // Debug raw captureState
  console.log('[CaptureStep] Raw captureState:', captureState);
  
  const { 
    source, 
    isCapturing, 
    captureTimer, 
    captureProgress,
    previewFrame,
    previewError,
    isPreviewActive 
  } = captureState;
  
  const { frameCount, currentFrameIndex, currentFrame } = frameState;
  
  // Show currentFrame if we have captured frames, otherwise show preview
  const displayFrame = frameCount > 0 ? currentFrame : previewFrame;
  
  // Debug logging
  console.log('CaptureStep render:', {
    displayFrame: displayFrame ? 'has frame' : 'no frame',
    displayFrameType: displayFrame ? typeof displayFrame : 'null',
    displayFramePrefix: displayFrame ? displayFrame.substring(0, 50) : 'null',
    previewFrame: previewFrame ? 'has preview' : 'no preview',
    currentFrame: currentFrame ? 'has current' : 'no current',
    frameCount,
    isCapturing,
    isPreviewActive,
    source,
    previewFrameLength: previewFrame ? previewFrame.length : 0,
    previewFrameType: previewFrame ? typeof previewFrame : 'null',
    previewFramePrefix: previewFrame ? previewFrame.substring(0, 50) : 'null',
    shouldShowPlaceholder: !displayFrame,
    captureState: captureState
  });

  return (
    <>
      {/* Upload button */}
      <div className="flex justify-end mb-4">
        <button
          onClick={onUploadClick}
          disabled={isCapturing || isUploadDisabled}
          className={`flex items-center gap-2 px-3 py-1.5 text-14 ${
            isCapturing || isUploadDisabled ? 'text-gray-400 cursor-not-allowed' : 'text-primary hover:opacity-80'
          }`}
        >
          <Upload size={18} />
          Upload Footage
        </button>
      </div>

      {/* Frame display */}
      <div className="mb-4 relative">
        <FrameDisplay
          key={`frame-${currentFrameIndex}-${frameCount}`}
          frame={displayFrame}
          frameIndex={currentFrameIndex}
          totalFrames={frameCount}
          isLoading={false}
          isCapturing={isCapturing}
          showRecordingOverlay={true}  // Show recording indicator
          showPlaceholder={!displayFrame}  // Show placeholder when no frame
          placeholderText={
            isCapturing ? 'Capturing frames...' : 
            previewError ? previewError :
            isPreviewActive && !displayFrame ? 'Connecting to source...' :
            source ? 'Initializing preview...' :
            'No footage yet'
          }
        />
        
        {/* Capture timer overlay */}
        {isCapturing && (
          <div className="absolute bottom-2 right-2 bg-black bg-opacity-70 text-white text-12 px-2 py-1 rounded z-10">
            <span className="mr-2">{captureTimer}</span>
            <span>Frame {frameCount}</span>
          </div>
        )}
      </div>

      {/* Capture controls */}
      <div className="flex items-center justify-center gap-8">
        <SourceSelector
          source={source}
          disabled={isCapturing || isCleaningUp}
          onSelectSource={captureState.setSource}
          className="w-[200px]"
        />
        
        <CaptureButton
          isCapturing={isCapturing}
          onStart={onStartCapture}
          onStop={onStopCapture}
          disabled={isCleaningUp}
          size="large"
        />
        
        <div className="w-[200px]" />
      </div>
    </>
  );
}
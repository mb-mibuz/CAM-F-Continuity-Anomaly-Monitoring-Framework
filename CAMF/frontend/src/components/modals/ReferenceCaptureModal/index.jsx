import React, { useState, useEffect } from 'react';
import ModalBase from '../ModalBase';
import ConfirmModal from '../ConfirmModal';
import VideoUploadModal from '../VideoUploadModal';
import CaptureStep from './CaptureStep';
import ReviewStep from './ReviewStep';
import { useReferenceCapture } from './hooks/useReferenceCapture';
import { useProcessGuard } from '../../../hooks/useProcessGuard';
import { useAppStore } from '../../../stores';

export default function ReferenceCaptureModal({ 
  takeName, 
  angleId, 
  angleName,
  sceneId,
  frameRate,
  onBack, 
  onCreate, 
  onClose 
}) {
  console.log('[ReferenceCaptureModal] Props:', { takeName, angleId, angleName, sceneId });
  const [mode, setMode] = useState('capture');
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showCloseConfirm, setShowCloseConfirm] = useState(false);
  
  const { addNotification } = useAppStore();
  
  // Main capture logic
  const {
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
  } = useReferenceCapture({
    takeName,
    angleId,
    sceneId,
    onComplete: (name, angleId, takeId) => {
      onClose();
      onCreate(name, angleId, takeId);
    }
  });

  // Process guard for navigation protection
  useProcessGuard({
    processName: 'Reference Capture',
    allowForceStop: true,
    onBeforeStop: cleanup
  });

  // Initialize on mount
  useEffect(() => {
    initializeCapture();
  }, []);

  // Switch to review mode when capture completes (but not for uploads)
  useEffect(() => {
    console.log('[ReferenceCaptureModal] Mode switch check:', {
      isCapturing: captureState.isCapturing,
      frameCount: frameState.frameCount,
      currentMode: mode,
      isUploading,
      hasTemporalTakeId: !!tempTakeId
    });
    // Only switch to review mode if we're not uploading and have actually captured frames
    // (not just uploaded a video)
    if (!captureState.isCapturing && !isUploading && frameState.frameCount > 0 && mode === 'capture' && tempTakeId && !String(tempTakeId).includes('_video_')) {
      console.log('[ReferenceCaptureModal] Switching to review mode');
      setMode('review');
    }
  }, [captureState.isCapturing, frameState.frameCount, mode, isUploading, tempTakeId]);

  // Handle close attempt
  const handleCloseAttempt = () => {
    if (captureState.isCapturing) {
      setShowCloseConfirm(true);
    } else if (isUploading) {
      addNotification({
        type: 'warning',
        message: 'Please wait for video processing to complete'
      });
    } else if (!isCleaningUp) {
      handleCancel();
    }
  };

  const handleConfirmClose = async () => {
    setShowCloseConfirm(false);
    await cleanup(true);
    onClose();
  };

  const handleCancel = async () => {
    if (!isCleaningUp) {
      await cleanup();
      onClose();
    }
  };

  const handleBackButton = async () => {
    if (!isCleaningUp) {
      await cleanup();
      onBack();
    }
  };

  // Handle video upload
  const handleVideoUploadComplete = async (file) => {
    setShowUploadModal(false);
    
    try {
      await handleVideoUpload(file);
      addNotification({
        type: 'success',
        message: 'Video processed successfully'
      });
      // Don't switch to review mode here - wait for upload completion
      // setMode('review');
    } catch (error) {
      addNotification({
        type: 'error',
        message: 'Failed to process video'
      });
    }
  };

  return (
    <>
      <ModalBase 
        onClose={handleCloseAttempt} 
        preventClose={captureState.isCapturing || isCleaningUp || isUploading}
        size="medium"
      >
        <div className="p-8">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-18 font-semibold">Capture Reference Take</h2>
            {(captureState.isCapturing || isCleaningUp || isUploading) && (
              <span className="text-12 text-gray-500">
                {isCleaningUp ? 'Cleaning up...' : 
                 isUploading ? 'Processing video...' : 
                 'Recording in progress...'}
              </span>
            )}
          </div>

          {mode === 'capture' ? (
            <CaptureStep
              captureState={captureState}
              frameState={frameState}
              onStartCapture={handleStartCapture}
              onStopCapture={handleStopCapture}
              onUploadClick={() => setShowUploadModal(true)}
              isCleaningUp={isCleaningUp}
              isUploadDisabled={isUploading}
            />
          ) : (
            <ReviewStep
              takeId={tempTakeId}
              frameState={frameState}
              onRetake={() => {
                setMode('capture');
                // Reset frame state
                frameState.resetFrames();
              }}
            />
          )}

          {/* Footer buttons */}
          <div className="flex justify-between mt-6">
            <button 
              onClick={handleBackButton}
              disabled={isCleaningUp || isUploading}
              className={`px-4 py-2 text-14 font-medium rounded ${
                isCleaningUp || isUploading
                  ? 'bg-gray-200 text-gray-400 cursor-not-allowed' 
                  : 'bg-white border border-gray-300 hover:bg-gray-50'
              }`}
            >
              Back
            </button>
            
            <div className="flex gap-3">
              {mode === 'review' && frameState.frameCount === 0 && (
                <button 
                  onClick={() => setMode('capture')}
                  disabled={isCleaningUp || isUploading}
                  className={`px-4 py-2 text-14 font-medium rounded ${
                    isCleaningUp || isUploading
                      ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                      : 'bg-white border border-gray-300 hover:bg-gray-50'
                  }`}
                >
                  Capture Again
                </button>
              )}
              
              <button 
                onClick={handleCreateTake}
                disabled={frameState.frameCount === 0 || isCreating || captureState.isCapturing || isCleaningUp || isUploading}
                className={`px-4 py-2 text-14 font-medium text-white rounded ${
                  frameState.frameCount > 0 && !isCreating && !captureState.isCapturing && !isCleaningUp && !isUploading
                    ? 'bg-primary hover:opacity-80' 
                    : 'bg-gray-300 cursor-not-allowed'
                }`}
              >
                {isCreating ? 'Creating...' : 'Create Take'}
              </button>
            </div>
          </div>
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
                  {uploadProgress < 100 
                    ? 'Extracting frames from video...' 
                    : 'Creating reference take...'}
                </p>
              </div>
            </div>
          )}
        </div>
      </ModalBase>

      {/* Video upload modal */}
      {showUploadModal && !isUploading && (
        <VideoUploadModal
          onClose={() => setShowUploadModal(false)}
          onUpload={handleVideoUploadComplete}
        />
      )}

      {/* Close confirmation modal */}
      {showCloseConfirm && (
        <ConfirmModal
          title="Stop Recording?"
          message="Recording is in progress. Do you want to stop recording and discard the captured frames?"
          confirmText="Stop & Discard"
          cancelText="Continue Recording"
          onConfirm={handleConfirmClose}
          onCancel={() => setShowCloseConfirm(false)}
        />
      )}
    </>
  );
}
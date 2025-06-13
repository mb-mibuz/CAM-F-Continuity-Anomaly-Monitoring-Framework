import React, { useEffect, useState } from 'react';
import { Airplay, Play, RotateCw, SlidersHorizontal } from 'lucide-react';
import { useDataStore, useAppStore } from '../../stores';
import { useCaptureSources, useStartCapture, useStopCapture } from '../../queries/hooks';
import { useStoreActions } from '../../hooks/useStoreActions';
import { usePolling } from '../../hooks/usePolling';
import SourceSelectionModal from '../modals/SourceSelectionModal';
import config, { buildApiUrl } from '../../config';

export default function CaptureControls({ 
  takeId, 
  referenceFrameCount,
  onSceneSettings,
  onRedoDetection 
}) {
  const source = useDataStore(state => state.source);
  const isCapturing = useDataStore(state => state.isCapturing);
  const hasFrames = useDataStore(state => state.frameCount > 0);
  const captureProgress = useDataStore(state => state.captureProgress);
  
  const captureActions = useStoreActions(useDataStore, [
    'setSource',
    'updateAvailableSources',
    'updateCaptureProgress'
  ]);
  
  const { openModal, closeModal, modals } = useAppStore();
  
  const { data: availableSources } = useCaptureSources();
  const startCaptureMutation = useStartCapture();
  const stopCaptureMutation = useStopCapture();
  
  const [showRecordingTooltip, setShowRecordingTooltip] = useState(false);
  
  useEffect(() => {
    if (availableSources) {
      captureActions.updateAvailableSources(availableSources);
    }
  }, [availableSources, captureActions]);
  
  usePolling(
    async () => {
      if (!isCapturing || !takeId) return;
      
      try {
        const response = await fetch(buildApiUrl(`api/capture/progress/${takeId}`));
        if (response.ok) {
          const progress = await response.json();
          captureActions.updateCaptureProgress({
            capturedFrames: progress.frame_count,
            duration: formatDuration(Date.now() - captureProgress.startTime)
          });
        }
      } catch (error) {
        console.error('Error polling capture progress:', error);
      }
    },
    500, // Poll every 500ms
    isCapturing,
    [takeId, isCapturing]
  );
  
  const handleSourceSelect = (sourceType, sourceId, sourceName) => {
    captureActions.setSource({ type: sourceType, id: sourceId, name: sourceName });
    closeModal('sourceSelection');
  };
  
  const handleStartCapture = async () => {
    if (!source) {
      openModal('sourceSelection');
      return;
    }
    
    try {
      await startCaptureMutation.mutateAsync({
        take_id: takeId,
        frame_count_limit: referenceFrameCount
      });
    } catch (error) {
      console.error('Failed to start capture:', error);
    }
  };
  
  const handleStopCapture = async () => {
    try {
      await stopCaptureMutation.mutateAsync();
    } catch (error) {
      console.error('Failed to stop capture:', error);
    }
  };
  
  const formatDuration = (ms) => {
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const displaySeconds = seconds % 60;
    return `${minutes.toString().padStart(2, '0')}:${displaySeconds.toString().padStart(2, '0')}`;
  };
  
  const progress = referenceFrameCount > 0 
    ? Math.min(captureProgress.capturedFrames / referenceFrameCount * 100, 100)
    : 0;
  
  return (
    <div className="relative flex items-center justify-between">
      {/* Source selection */}
      <div className="w-[140px] min-w-0">
        <button
          onClick={() => openModal('sourceSelection')}
          disabled={isCapturing || hasFrames}
          className={`flex items-center gap-2 hover:scale-105 transition-all duration-150 w-full ${
            isCapturing || hasFrames
              ? 'text-gray-400 cursor-not-allowed hover:scale-100'
              : 'text-gray-800 hover:text-black'
          }`}
          title={source ? `Source: ${source.name}` : "Select Capture Source"}
        >
          <Airplay size={20} strokeWidth={1.5} className="flex-shrink-0" />
          <span className="text-14 truncate">
            {source 
              ? (hasFrames ? `${source.name} (Locked)` : source.name)
              : 'Select Source'}
          </span>
        </button>
      </div>
      
      {/* Center - Record/Redo button */}
      <div className="absolute left-1/2 transform -translate-x-1/2">
        {!hasFrames ? (
          <RecordButton
            isCapturing={isCapturing}
            onStart={handleStartCapture}
            onStop={handleStopCapture}
          />
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
      
      {/* Right - Settings */}
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
      
      {/* Recording indicator */}
      {isCapturing && (
        <div 
          className="absolute top-0 right-0 transform translate-x-full ml-4"
          onMouseEnter={() => setShowRecordingTooltip(true)}
          onMouseLeave={() => setShowRecordingTooltip(false)}
        >
          <div className="w-4 h-4 rounded-full bg-red-500 animate-pulse" />
          
          {showRecordingTooltip && (
            <div className="absolute top-full right-0 mt-1 bg-black bg-opacity-90 text-white text-12 px-3 py-2 rounded whitespace-nowrap">
              Recording in progress<br />
              Frame {captureProgress.capturedFrames} of {referenceFrameCount} captured<br />
              {referenceFrameCount > 0 && (
                <div className="mt-1">
                  <div className="w-32 h-2 bg-gray-700 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-red-500 transition-all duration-300"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                  <div className="text-10 mt-1">{Math.round(progress)}% complete</div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
      
      {/* Source selection modal */}
      {modals.sourceSelection && (
        <SourceSelectionModal
          availableSources={availableSources}
          currentSource={source}
          onClose={() => closeModal('sourceSelection')}
          onSelectSource={handleSourceSelect}
        />
      )}
    </div>
  );
}

/**
 * Isolated record button component
 */
function RecordButton({ isCapturing, onStart, onStop }) {
  const handleClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (isCapturing) {
      onStop();
    } else {
      onStart();
    }
  };
  
  return (
    <button
      onClick={handleClick}
      onMouseDown={(e) => e.preventDefault()}
      className="relative w-[36px] h-[36px] flex items-center justify-center transition-transform duration-150 hover:scale-110"
      title={isCapturing ? "Stop Recording" : "Start Recording"}
      style={{ touchAction: 'none', zIndex: 10 }}
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
}
import React, { useCallback } from 'react';
import { Airplay, Play, RotateCw, SlidersHorizontal, Maximize2 } from 'lucide-react';
import { useDataStore, useAppStore } from '../../../stores';
import { CaptureService, DetectorService } from '../../../services';
import { api } from '../../../utils/api';
import SourceSelector from '../../../components/monitoring/SourceSelector';
import CaptureButton from '../../../components/monitoring/CaptureButton';

export default function CaptureControls({
  takeId,
  sceneId,
  sceneName,
  sceneData,
  referenceFrameCount,
  hasFrames,
  isCapturing,
  source,
  onFullscreen
}) {
  const { openModal, addNotification } = useAppStore();
  const captureService = CaptureService.getInstance();
  const detectorService = DetectorService.getInstance();
  
  // Actions from capture store
  const {
    setSource,
    startCapture: storeStartCapture,
    stopCapture: storeStopCapture,
    startRedoDetection,
    isProcessing,
    isRedoingDetection
  } = useDataStore();

  // Handle source selection
  const handleSourceSelect = useCallback(async (sourceObj) => {
    try {
      // Handle both object and individual parameters
      const type = sourceObj.type || sourceObj;
      const id = sourceObj.id || arguments[1];
      const name = sourceObj.name || arguments[2];
      
      // Check if this source is already set to avoid duplicate API calls
      const currentSource = useDataStore.getState().source;
      if (currentSource && 
          currentSource.type === type && 
          currentSource.id === id) {
        console.log('[CaptureControls] Source already set, skipping duplicate call');
        return;
      }
      
      await captureService.setSource(type, id, name);
      
      // Start preview if not capturing and no frames
      if (!isCapturing && !hasFrames) {
        await captureService.startPreview();
      }
      
      addNotification({ type: 'success', message: `Selected ${name}` });
    } catch (error) {
      console.error('Failed to set source:', error);
      addNotification({ type: 'error', message: 'Failed to set capture source' });
    }
  }, [captureService, addNotification, isCapturing, hasFrames]);

  // Handle start capture
  const handleStartCapture = useCallback(async () => {
    if (!source) {
      openModal('sourceSelection');
      return;
    }

    try {
      // Get reference take for real-time processing
      const dataStore = useDataStore.getState();
      const referenceTake = dataStore.getReferenceTakeForAngle(
        dataStore.currentAngle?.id
      );
      
      // Always allow unlimited capture - no auto-stop
      console.log('[CaptureControls] Starting capture with real-time processing');
      await captureService.startCapture(takeId, {
        frame_count_limit: null, // Always unlimited
        skip_detectors: false,
        is_monitoring_mode: true, // Enable real-time processing
        reference_take_id: referenceTake?.id // Pass reference take for comparison
      });
      
      // Start showing processing status immediately
      if (referenceTake?.id) {
        startRedoDetection();
      }
    } catch (error) {
      console.error('Failed to start capture:', error);
      addNotification({ type: 'error', message: 'Failed to start capture' });
    }
  }, [source, takeId, captureService, openModal, addNotification, startRedoDetection]);

  // Handle stop capture
  const handleStopCapture = useCallback(async () => {
    try {
      await captureService.stopCapture();
      
      // If we were processing in real-time, complete the processing
      const dataStore = useDataStore.getState();
      if (dataStore.isProcessing || dataStore.isRedoingDetection) {
        // Processing was happening in real-time, just mark it as complete
        dataStore.completeRedoDetection();
      }
    } catch (error) {
      console.error('Failed to stop capture:', error);
      addNotification({ type: 'error', message: 'Failed to stop capture' });
    }
  }, [captureService, addNotification]);

  // Handle redo detection
  const handleRedoDetection = useCallback(async () => {
    if (!hasFrames) {
      addNotification({ type: 'warning', message: 'No frames to process' });
      return;
    }

    try {
      console.log('[CaptureControls] Starting redo detection for take:', takeId);
      startRedoDetection();
      
      // Get reference take ID if available
      const dataStore = useDataStore.getState();
      const referenceTake = dataStore.getReferenceTakeForAngle(
        dataStore.currentAngle?.id
      );
      
      console.log('[CaptureControls] Reference take for redo:', referenceTake);
      
      const response = await detectorService.restartProcessing(
        takeId,
        referenceTake?.id
      );
      
      console.log('[CaptureControls] Redo detection response:', response);
      
      // Don't clear the state here - let SSE events handle it
      // The backend will send processing_complete when done
    } catch (error) {
      console.error('[CaptureControls] Failed to restart processing:', error);
      // Make sure to clear the processing state on error
      const dataStore = useDataStore.getState();
      dataStore.stopProcessing();
      addNotification({ type: 'error', message: error.message || 'Failed to restart processing' });
    }
  }, [hasFrames, takeId, startRedoDetection, detectorService, addNotification]);

  // Handle scene settings
  const handleSceneSettings = useCallback(async () => {
    // Fetch fresh scene data before opening modal
    try {
      const freshSceneData = await api.getScene(sceneId);
      console.log('[CaptureControls] Fresh scene data:', freshSceneData);
      
      openModal('sceneConfig', { 
        sceneId,
        sceneName: sceneName || freshSceneData?.name || '',
        editMode: true,
        initialFps: freshSceneData?.frame_rate || 1.0,
        initialQuality: freshSceneData?.image_quality || 90,
        initialResolution: freshSceneData?.resolution || '1080p'
      });
    } catch (error) {
      console.error('[CaptureControls] Failed to fetch scene data:', error);
      // Fall back to cached data
      openModal('sceneConfig', { 
        sceneId,
        sceneName: sceneName || sceneData?.name || '',
        editMode: true,
        initialFps: sceneData?.frame_rate || 1.0,
        initialQuality: sceneData?.image_quality || 90,
        initialResolution: sceneData?.resolution || '1080p'
      });
    }
  }, [sceneId, sceneName, sceneData, openModal]);

  return (
    <div className="flex items-center justify-between h-full relative">
      {/* Left section - Source selector */}
      <SourceSelector
        source={source}
        disabled={isCapturing || hasFrames}
        onSelectSource={handleSourceSelect}
        className="w-40"
      />
      
      {/* Center section - Main action */}
      <div className="absolute left-1/2 transform -translate-x-1/2">
        {(!hasFrames || isCapturing) ? (
          <CaptureButton
            isCapturing={isCapturing}
            onStart={handleStartCapture}
            onStop={handleStopCapture}
            disabled={false} // Allow stopping during capture
            size="medium"
          />
        ) : (
          <button
            onClick={handleRedoDetection}
            disabled={isCapturing || isProcessing || isRedoingDetection}
            className={`
              flex items-center justify-center p-2
              transition-all duration-150
              ${isCapturing || isProcessing || isRedoingDetection
                ? 'text-gray-300 cursor-not-allowed'
                : 'text-gray-600 hover:text-gray-800'
              }
            `}
            title={isProcessing || isRedoingDetection ? "Processing in progress..." : "Redo Detection"}
          >
            <RotateCw size={28} className={isProcessing || isRedoingDetection ? 'animate-spin' : ''} />
          </button>
        )}
      </div>
      
      {/* Right section - Settings */}
      <div className="flex items-center gap-2">
        <button
          onClick={onFullscreen}
          className="p-2 rounded hover:bg-gray-200 transition-all duration-150 text-gray-700 hover:text-black"
          title="Fullscreen view"
        >
          <Maximize2 size={20} />
        </button>
        <button
          onClick={handleSceneSettings}
          disabled={isCapturing}
          className={`
            p-2 rounded hover:bg-gray-200 transition-all duration-150
            ${isCapturing
              ? 'text-gray-400 cursor-not-allowed hover:bg-transparent'
              : 'text-gray-700 hover:text-black'
            }
          `}
          title="Scene Configuration"
        >
          <SlidersHorizontal size={20} />
        </button>
      </div>
      
    </div>
  );
}

// Separate component for capture progress with predictive UI
function CaptureProgressIndicator({ referenceFrameCount }) {
  const { displayFrames, confidence } = usePredictiveFrames();
  const { displayProgress, estimatedTime } = usePredictiveProgress();
  
  const percentage = Math.min(100, Math.round((displayFrames / referenceFrameCount) * 100));
  
  return (
    <div className="absolute top-full left-1/2 transform -translate-x-1/2 mt-2 z-50">
      <div className="bg-black bg-opacity-90 text-white text-12 px-4 py-3 rounded-lg shadow-lg">
        <div className="flex items-center gap-3 mb-2">
          <span className="font-medium">Capturing</span>
          <span className="text-14 font-mono">{displayFrames}/{referenceFrameCount}</span>
          <span className="text-primary font-bold">{percentage}%</span>
        </div>
        
        <div className="w-48 h-2 bg-gray-700 rounded-full overflow-hidden mb-2">
          <div 
            className="h-full bg-gradient-to-r from-red-500 to-red-400 transition-all duration-500 ease-out"
            style={{ 
              width: `${percentage}%`,
              opacity: confidence > 0.8 ? 1 : 0.8
            }}
          />
        </div>
        
        {estimatedTime && (
          <div className="text-10 text-gray-300 text-center">
            {estimatedTime}
          </div>
        )}
      </div>
    </div>
  );
}
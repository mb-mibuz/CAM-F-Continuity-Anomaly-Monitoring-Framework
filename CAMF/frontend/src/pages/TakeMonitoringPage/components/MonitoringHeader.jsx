import React, { useState, useEffect } from 'react';
import { ChevronRight, AlertCircle, Info } from 'lucide-react';
import { api } from '../../../utils/api';
import { useDataStore, useProcessingStore } from '../../../stores';

export default function MonitoringHeader({
  projectName,
  projectId,
  sceneName,
  sceneId,
  angleName,
  angleId,
  takeName,
  isReference,
  onNavigateBack,
  onNavigateToProject,
  onNavigateToScene,
  frameCount,
  captureProgress,
  isCapturing,
  isProcessing,
  processedFrameCount
}) {
  const [processingStatus, setProcessingStatus] = useState(null);
  const [showTooltip, setShowTooltip] = useState(false);

  // Poll for processing status when processing
  useEffect(() => {
    if (!isProcessing) {
      setProcessingStatus(null);
      return;
    }

    const fetchStatus = async () => {
      try {
        const status = await api.getProcessingStatus();
        setProcessingStatus(status);
        
        // Check if processing is actually complete
        if (status && status.processed_frames === status.total_frames && status.total_frames > 0) {
          console.log('[MonitoringHeader] Processing appears complete:', status);
          
          // Give a moment for final results to arrive, then clear processing state
          setTimeout(() => {
            const dataStore = useDataStore.getState();
            const processingStore = useProcessingStore.getState();
            
            if (dataStore.isProcessing || dataStore.isRedoingDetection) {
              console.log('[MonitoringHeader] Clearing stuck processing state in dataStore');
              dataStore.completeRedoDetection();
            }
            
            // Also clear processing store state
            if (processingStore.isProcessing || processingStore.activeProcesses.length > 0) {
              console.log('[MonitoringHeader] Clearing stuck processing state in processingStore');
              // Find take ID from active processes or use the one from props
              const activeProcess = processingStore.activeProcesses.find(p => p.type === 'processing');
              if (activeProcess) {
                processingStore.completeProcessing(activeProcess.takeId);
              } else {
                // Clear all active processes if we can't find a specific one
                processingStore.clearActiveProcesses();
                processingStore.stopProcessing();
              }
            }
          }, 1500);
        }
      } catch (error) {
        console.error('[MonitoringHeader] Error fetching processing status:', error);
      }
    };

    // Initial fetch
    fetchStatus();

    // Poll every second
    const interval = setInterval(fetchStatus, 1000);

    return () => clearInterval(interval);
  }, [isProcessing]);
  const formatDuration = (startTime) => {
    if (!startTime) return '00:00';
    
    const elapsed = Date.now() - startTime;
    const seconds = Math.floor(elapsed / 1000);
    const minutes = Math.floor(seconds / 60);
    const displaySeconds = seconds % 60;
    
    return `${minutes.toString().padStart(2, '0')}:${displaySeconds.toString().padStart(2, '0')}`;
  };

  return (
    <div className="px-9 py-6">
      {/* Take info and status */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-18 font-semibold truncate max-w-[400px] block" title={takeName.replace(/^temp#\d+_/, '')}>{takeName.replace(/^temp#\d+_/, '')}</h1>
          
          {isReference && (
            <span className="px-2 py-1 bg-blue-100 text-blue-700 text-12 rounded">
              Reference Take
            </span>
          )}
          
          {frameCount > 0 && (
            <span className="text-14 text-gray-600">
              {frameCount} frames
            </span>
          )}
        </div>
        
        {/* Capture or Processing status */}
        {(isCapturing || isProcessing) && (
          <div className="flex items-center gap-3 text-14">
            <div className="flex items-center gap-2">
              <div className={`w-3 h-3 rounded-full animate-pulse ${isProcessing ? 'bg-blue-500' : 'bg-red-500'}`} />
              <span className="font-medium">{isProcessing ? 'Processing' : 'Recording'}</span>
            </div>
            {isCapturing && (
              <>
                <span className="text-gray-600">
                  {formatDuration(captureProgress.startTime)}
                </span>
                <span className="text-gray-600">
                  {captureProgress.capturedFrames} frames
                </span>
              </>
            )}
            {isProcessing && (
              <div className="relative">
                <span 
                  className="text-gray-600 cursor-help flex items-center gap-1"
                  onMouseEnter={() => setShowTooltip(true)}
                  onMouseLeave={() => setShowTooltip(false)}
                >
                  {processingStatus?.processed_frames || processedFrameCount || 0} / {processingStatus?.total_frames || frameCount} frames
                  <Info size={14} className="text-gray-400" />
                </span>
                
                {/* Tooltip */}
                {showTooltip && processingStatus?.detector_progress && (
                  <div className="absolute top-full right-0 mt-2 z-50">
                    <div className="bg-gray-900 text-white text-12 rounded-lg px-3 py-2 shadow-lg min-w-[200px]">
                      <div className="font-medium mb-2">Detector Progress</div>
                      {Object.entries(processingStatus.detector_progress).map(([detector, progress]) => (
                        <div key={detector} className="flex justify-between items-center py-1">
                          <span className="text-gray-300">{detector}:</span>
                          <span className="ml-3">
                            {progress.processed}/{progress.total} 
                            <span className="text-gray-400 text-10 ml-1">({progress.status})</span>
                          </span>
                        </div>
                      ))}
                      {Object.keys(processingStatus.detector_progress).length === 0 && (
                        <div className="text-gray-400 text-center py-2">No detectors active</div>
                      )}
                    </div>
                    {/* Arrow pointing up */}
                    <div className="absolute bottom-full right-4 w-0 h-0 border-l-[6px] border-l-transparent border-r-[6px] border-r-transparent border-b-[6px] border-b-gray-900"></div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
      
      {/* Warning for reference take */}
      {isReference && frameCount === 0 && (
        <div className="mt-3 flex items-center gap-2 text-14 text-yellow-700 bg-yellow-50 px-3 py-2 rounded">
          <AlertCircle size={16} />
          <span>This is a reference take. The frame count will set the limit for all takes in this angle.</span>
        </div>
      )}
    </div>
  );
}
import React, { useEffect, useState } from 'react';
import { shallow } from 'zustand/shallow';
import { useDataStore, useAppStore, useProcessingStore } from '../../stores';
import { useMonitoringState } from './hooks/useMonitoringState';
import { useFrameSync } from './hooks/useFrameSync';
import { useDetectorSync } from './hooks/useDetectorSync';
import SSEService from '../../services/SSEService';
import { api } from '../../utils/api';

// Components
import MonitoringHeader from './components/MonitoringHeader';
import CaptureControls from './components/CaptureControls';
import FrameViewer from './components/FrameViewer';
import FrameViewerWithControls from './components/FrameViewerWithControls';
import DetectorPanel from './components/DetectorPanel';
import NotesEditor from './components/NotesEditor';

// Common components
import LoadingState from '../../components/common/LoadingState';
import ErrorBoundary from '../../components/common/ErrorBoundary';
import ProcessGuard from '../../components/common/ProcessGuard';

// Modals
import FalsePositiveModal from '../../components/modals/FalsePositiveModal';

// Hooks

export default function TakeMonitoringPage({ 
  projectId, 
  projectName, 
  sceneId, 
  sceneName,
  angleId,
  angleName,
  takeId, 
  takeName,
  isReference,
  onSetRefresh
}) {
  // Navigation and context
  const navigate = useAppStore(state => state.navigate);
  const setCurrentContext = useDataStore(state => state.setCurrentContext);
  
  // False positive modal state
  const [falsePositiveModalOpen, setFalsePositiveModalOpen] = useState(false);
  const [selectedError, setSelectedError] = useState(null);
  
  // Track current reference status
  const [currentIsReference, setCurrentIsReference] = useState(isReference);
  
  useEffect(() => {
    setCurrentContext({
      project: { id: projectId, name: projectName },
      scene: { id: sceneId, name: sceneName },
      angle: { id: angleId, name: angleName },
      take: { id: takeId, name: takeName, is_reference: isReference }
    });
  }, [projectId, sceneId, angleId, takeId]);
  
  // Initialize detectors when opening the take monitoring page
  useEffect(() => {
    if (!sceneId || !takeId) return;
    
    const initializeDetectors = async () => {
      try {
        console.log('[TakeMonitoringPage] Initializing detectors for scene:', sceneId);
        const response = await api.startDetectorsForScene(sceneId, { angle_id: angleId, take_id: takeId });
        console.log('[TakeMonitoringPage] Detector initialization response:', response);
        
        if (response.started && response.started.length > 0) {
          console.log(`[TakeMonitoringPage] Successfully started ${response.started.length} detectors`);
        }
        if (response.failed && response.failed.length > 0) {
          console.error('[TakeMonitoringPage] Failed to start some detectors:', response.failed);
        }
      } catch (error) {
        console.error('[TakeMonitoringPage] Error initializing detectors:', error);
      }
    };
    
    initializeDetectors();
  }, [sceneId, takeId, angleId]);
  
  // Initialize capture service for SSE subscriptions
  useEffect(() => {
    if (!takeId) return;
    
    const initializeCaptureService = async () => {
      try {
        const CaptureService = (await import('../../services/CaptureService')).default;
        const captureService = CaptureService.getInstance();
        await captureService.initialize(takeId);
        console.log('[TakeMonitoringPage] Capture service initialized for take:', takeId);
      } catch (error) {
        console.error('[TakeMonitoringPage] Failed to initialize capture service:', error);
      }
    };
    
    initializeCaptureService();
    
    // Also subscribe to detector events for real-time error updates
    const handleDetectorEvent = (event) => {
      console.log('[TakeMonitoringPage] Detector event received:', event);
      // The SSEEventBridge handles updating the store, we just need to be subscribed
      // Force a refresh of errors if needed
      if (event.type === 'detector_error' || event.type === 'detector_result') {
        // The store should be updated by SSEEventBridge, but we can force a refresh
        const currentErrors = useDataStore.getState().detectorErrors || [];
        console.log('[TakeMonitoringPage] Current detector errors after event:', currentErrors.length);
      }
    };
    
    SSEService.subscribe('detector_events', handleDetectorEvent);
    SSEService.subscribe(`processing_${takeId}`, handleDetectorEvent);
    SSEService.subscribe(`take_${takeId}`, handleDetectorEvent);
    
    // Subscribe to angle updates to catch reference take changes
    const handleAngleUpdate = (event) => {
      console.log('[TakeMonitoringPage] Angle update event received:', event);
      if (event.data && event.data.angle_id === angleId) {
        // Refresh data to get updated reference status
        refreshData();
      }
    };
    SSEService.subscribe(`angle_${angleId}`, handleAngleUpdate);
    
    // Cleanup on unmount
    return () => {
      // Unsubscribe from all events when leaving the page
      try {
        SSEService.unsubscribe(`take_${takeId}`);
        SSEService.unsubscribe('capture_events');
        SSEService.unsubscribe('detector_events');
        SSEService.unsubscribe(`processing_${takeId}`);
        SSEService.unsubscribe(`angle_${angleId}`);
      } catch (error) {
        console.error('[TakeMonitoringPage] Error during cleanup:', error);
      }
    };
  }, [takeId]);
  
  // Stop all detectors and clear processing state when leaving the page
  useEffect(() => {
    return () => {
      // Stop all detectors when unmounting
      const stopDetectors = async () => {
        try {
          console.log('[TakeMonitoringPage] Stopping all detectors on page leave');
          await api.stopAllDetectors();
        } catch (error) {
          console.error('[TakeMonitoringPage] Error stopping detectors:', error);
        }
      };
      
      // Clear processing state
      const dataStore = useDataStore.getState();
      if (dataStore.isProcessing || dataStore.isRedoingDetection) {
        console.log('[TakeMonitoringPage] Clearing processing state on page leave');
        dataStore.completeRedoDetection();
      }
      
      stopDetectors();
    };
  }, []);

  // Main monitoring state
  const {
    sceneData,
    takeData,
    availableTakes,
    loading,
    error,
    refreshData
  } = useMonitoringState(takeId, sceneId, angleId);

  // Get reference take ID from store (can be different from scene default)
  const referenceTakeId = useDataStore(state => state.referenceTakeId);
  
  // Frame synchronization
  const {
    currentFrame,
    referenceFrame,
    frameCount,
    currentFrameIndex,
    isLoadingFrame
  } = useFrameSync(takeId, referenceTakeId || sceneData?.reference_take_id);

  // Detector synchronization
  const {
    detectorErrors,
    isProcessing,
    processedFrameCount,
    refreshErrors
  } = useDetectorSync(takeId);
  
  // Get preview frame from store (managed by CaptureService)
  const previewFrame = useDataStore(state => state.previewFrame);
  const isPreviewActive = useDataStore(state => state.isPreviewActive);
  
  // Monitor processing status and clear when complete
  useEffect(() => {
    if (!isProcessing) return;
    
    const checkProcessingStatus = async () => {
      try {
        const status = await api.getProcessingStatus();
        const dataStore = useDataStore.getState();
        
        // Check if all frames are processed
        if (status && status.processed_frames === status.total_frames && status.total_frames > 0) {
          console.log('[TakeMonitoringPage] Processing complete:', status);
          
          // Wait a bit for final results to come in
          setTimeout(() => {
            const processingStore = useProcessingStore.getState();
            if (dataStore.isProcessing || dataStore.isRedoingDetection) {
              console.log('[TakeMonitoringPage] Clearing processing state after completion');
              dataStore.completeRedoDetection();
            }
            // Also clear processing store
            if (processingStore.isProcessing || processingStore.activeProcesses.length > 0) {
              console.log('[TakeMonitoringPage] Clearing processing store state');
              processingStore.completeProcessing(takeId);
            }
          }, 2000);
        }
      } catch (error) {
        console.error('[TakeMonitoringPage] Error checking processing status:', error);
      }
    };
    
    // Check immediately and then every 2 seconds
    checkProcessingStatus();
    const interval = setInterval(checkProcessingStatus, 2000);
    
    return () => clearInterval(interval);
  }, [isProcessing]);
  
  // Debug reference take info
  useEffect(() => {
    console.log('[TakeMonitoringPage] Scene data updated:', {
      reference_take_id: sceneData?.reference_take_id,
      reference_frame_count: sceneData?.reference_frame_count,
      sceneId: sceneId,
      takeId: takeId,
      angleId: angleId
    });
  }, [sceneData, sceneId, takeId, angleId]);
  
  // Update reference status based on take data
  useEffect(() => {
    if (takeData && takeData.is_reference !== undefined) {
      if (takeData.is_reference !== currentIsReference) {
        console.log('[TakeMonitoringPage] Reference status changed:', {
          takeId,
          is_reference: takeData.is_reference,
          wasReference: currentIsReference
        });
        setCurrentIsReference(takeData.is_reference);
      }
    }
  }, [takeData]); // Re-check when take data changes

  // Capture state
  const captureState = useDataStore(
    state => ({
      isCapturing: state.isCapturing,
      captureProgress: state.captureProgress,
      source: state.source,
      hasFrames: state.frameCount > 0,
      previewFrame: state.previewFrame,
      processedFrames: state.captureProgress.processedFrames || 0
    }),
    shallow
  );

  // Set frame count from take data when it loads
  useEffect(() => {
    if (takeData?.frame_count !== undefined) {
      console.log('[TakeMonitoringPage] Setting frame count from take data:', takeData.frame_count);
      const dataStore = useDataStore.getState();
      dataStore.setTotalFrames(takeData.frame_count);
      dataStore.updateFrameCount(takeData.frame_count);
    }
  }, [takeData?.frame_count]);
  
  // Initialize reference take in store when scene data loads
  useEffect(() => {
    if (sceneData?.reference_take_id && sceneData?.reference_frame_count !== undefined) {
      console.log('[TakeMonitoringPage] Initializing reference take in store:', {
        id: sceneData.reference_take_id,
        frameCount: sceneData.reference_frame_count
      });
      const dataStore = useDataStore.getState();
      dataStore.setReferenceTake(sceneData.reference_take_id, sceneData.reference_frame_count);
    }
  }, [sceneData?.reference_take_id, sceneData?.reference_frame_count]);
  
  // Debug preview state
  useEffect(() => {
    console.log('[TakeMonitoringPage] Preview state:', {
      hasPreviewFrame: !!previewFrame,
      isPreviewActive,
      hasSource: !!captureState.source,
      isCapturing: captureState.isCapturing,
      hasFrames: captureState.hasFrames
    });
  }, [previewFrame, isPreviewActive, captureState.source, captureState.isCapturing, captureState.hasFrames]);

  // Don't refresh data when capture completes - the frame count is already updated via SSE
  // This prevents the "blink" that occurs from reloading all data
  // useEffect(() => {
  //   if (!captureState.isCapturing && captureState.captureProgress.isComplete) {
  //     // Small delay to ensure backend has finished processing
  //     const timer = setTimeout(() => {
  //       refreshData();
  //     }, 1000);
  //     return () => clearTimeout(timer);
  //   }
  // }, [captureState.isCapturing, captureState.captureProgress.isComplete, refreshData]);

  // Register refresh function
  useEffect(() => {
    // Make refresh function globally available for video upload
    window.refreshTakeData = refreshData;
    
    if (onSetRefresh) {
      const unregister = onSetRefresh(async () => {
        await Promise.all([
          refreshData(),
          refreshErrors()
        ]);
      });
      return () => {
        delete window.refreshTakeData;
        if (typeof unregister === 'function') {
          unregister();
        }
      };
    }
    
    return () => {
      delete window.refreshTakeData;
    };
  }, [onSetRefresh, refreshData]); // Don't include refreshErrors to avoid loops

  // Handle navigation
  const handleNavigateBack = () => {
    navigate('takes', { 
      projectId, 
      projectName, 
      sceneId, 
      sceneName,
      angleId,
      angleName
    });
  };
  
  const handleNavigateToProject = () => {
    navigate('scenes', {
      projectId,
      projectName
    });
  };
  
  const handleNavigateToScene = () => {
    navigate('takes', {
      projectId,
      projectName,
      sceneId,
      sceneName
    });
  };
  
  // Handle mark false positive
  const handleMarkFalsePositive = (error) => {
    setSelectedError(error);
    setFalsePositiveModalOpen(true);
  };
  
  const handleConfirmFalsePositive = async (error, reason) => {
    try {
      await api.markErrorAsFalsePositive(takeId, error, reason);
      
      // Refresh errors to update the display
      await refreshErrors();
      
      // Show success notification (could use a toast library)
      console.log('Successfully marked as false positive');
    } catch (error) {
      console.error('Failed to mark as false positive:', error);
      // Could show error notification
    }
  };

  // Loading state
  if (loading) {
    return <LoadingState message="Loading take data..." />;
  }

  // Error state
  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <p className="text-red-600 mb-4">Error: {error.message}</p>
          <button 
            onClick={handleNavigateBack}
            className="px-4 py-2 bg-primary text-white rounded hover:opacity-80"
          >
            Back to Takes
          </button>
        </div>
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <ProcessGuard 
        processName="Take Monitoring"
        allowForceStop={true}
      >
        <div className="flex flex-col h-full bg-white relative">
          {/* Main content - horizontal layout */}
          <div className="flex-1 flex overflow-hidden">
            {/* Left side - Frames and controls */}
            <div className="flex-1 flex flex-col overflow-hidden">
              {/* Header */}
              <MonitoringHeader
                projectName={projectName}
                projectId={projectId}
                sceneName={sceneName}
                sceneId={sceneId}
                angleName={angleName}
                angleId={angleId}
                takeName={takeName}
                isReference={currentIsReference}
                onNavigateBack={handleNavigateBack}
                onNavigateToProject={handleNavigateToProject}
                onNavigateToScene={handleNavigateToScene}
                frameCount={frameCount}
                captureProgress={captureState.captureProgress}
                isCapturing={captureState.isCapturing}
                isProcessing={isProcessing}
                processedFrameCount={processedFrameCount}
              />
              
              {/* Main content with integrated controls */}
              <div className="px-9">
                <FrameViewerWithControls
                  takeId={takeId}
                  sceneId={sceneId}
                  sceneName={sceneName}
                  sceneData={sceneData}
                  currentFrame={currentFrame}
                  referenceFrame={referenceFrame}
                  frameCount={frameCount}
                  currentFrameIndex={currentFrameIndex}
                  isLoadingFrame={isLoadingFrame}
                  availableTakes={availableTakes}
                  angleId={angleId}
                  referenceTakeId={sceneData?.reference_take_id}
                  referenceFrameCount={sceneData?.reference_frame_count}
                  captureState={captureState}
                  hasDetectorErrors={detectorErrors.length > 0}
                  detectorErrors={detectorErrors}
                />
              </div>
              
              {/* Detector panel */}
              <div className="flex-1 min-h-0 px-9 pb-4" style={{ marginBottom: '38px' }}>
                <DetectorPanel
                  takeId={takeId}
                  sceneId={sceneId}
                  sceneName={sceneName}
                  errors={detectorErrors}
                  frameCount={frameCount}
                  isDisabled={captureState.isCapturing || isProcessing}
                  onErrorClick={(error) => {
                    // Navigate to error frame
                    const frameIndex = error.frame_id || error.instances?.[0]?.frame_id;
                    if (frameIndex !== undefined) {
                      useDataStore.getState().setCurrentFrameIndex(frameIndex);
                    }
                  }}
                  onMarkFalsePositive={handleMarkFalsePositive}
                />
              </div>
            </div>

            {/* Notes sidebar */}
            <div className="w-96 h-full border-l border-gray-200 bg-gray-50 flex-shrink-0">
              <NotesEditor
                takeId={takeId}
                takeName={takeName}
                sceneName={sceneName}
                initialNotes={takeData?.notes || ''}
                frameCount={frameCount}
                currentFrameIndex={currentFrameIndex}
                isDisabled={captureState.isCapturing}
              />
            </div>
          </div>
        </div>
        
        {/* False positive modal */}
        <FalsePositiveModal
          isOpen={falsePositiveModalOpen}
          onClose={() => {
            setFalsePositiveModalOpen(false);
            setSelectedError(null);
          }}
          error={selectedError}
          onConfirm={handleConfirmFalsePositive}
        />
      </ProcessGuard>
    </ErrorBoundary>
  );
}
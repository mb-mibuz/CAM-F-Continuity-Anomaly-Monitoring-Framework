import { useEffect, useRef, useCallback } from 'react';
import { useDataStore, useAppStore } from '../stores';
import { CaptureService, DetectorService } from '../services';

/**
 * Hook to prevent navigation during active processes
 * @param {Object} options - Guard options
 * @returns {Object} Guard state and controls
 */
export function useProcessGuard(options = {}) {
  const {
    processName = 'Process',
    allowForceStop = true,
    onBeforeStop,
    onAfterStop,
    customMessage
  } = options;
  
  // Store states
  const registerGuard = useAppStore(state => state.registerGuard);
  const { isCapturing, isProcessing, isRedoingDetection, stopCapture } = useDataStore();
  const { openModal, closeModal } = useAppStore();
  
  // Services
  const captureService = useRef(null);
  const detectorService = useRef(null);
  
  useEffect(() => {
    captureService.current = CaptureService.getInstance();
    detectorService.current = DetectorService.getInstance();
  }, []);
  
  // Check if any process is active
  const hasActiveProcess = isCapturing || isProcessing || isRedoingDetection;
  
  // Get active process name
  const getActiveProcessName = useCallback(() => {
    if (isCapturing) return 'Recording';
    if (isRedoingDetection) return 'Detection Processing';
    if (isProcessing) return 'Processing';
    return processName;
  }, [isCapturing, isRedoingDetection, isProcessing, processName]);
  
  // Get appropriate message
  const getMessage = useCallback(() => {
    if (customMessage) return customMessage;
    
    const activeProcess = getActiveProcessName();
    
    if (isCapturing) {
      return `${activeProcess} is in progress. Do you want to continue recording or stop and ${
        allowForceStop ? 'discard the recording' : 'save the captured frames'
      }?`;
    }
    
    if (isRedoingDetection) {
      return `${activeProcess} is in progress. Leaving now will cancel the processing. Continue?`;
    }
    
    if (isProcessing) {
      return `${activeProcess} is in progress. Leaving now will cancel the processing. Continue?`;
    }
    
    return `${activeProcess} is currently running. Are you sure you want to leave?`;
  }, [customMessage, getActiveProcessName, isCapturing, isRedoingDetection, isProcessing, allowForceStop]);
  
  // Create stable reference for callbacks
  const callbacksRef = useRef({ onBeforeStop, onAfterStop });
  useEffect(() => {
    callbacksRef.current = { onBeforeStop, onAfterStop };
  }, [onBeforeStop, onAfterStop]);
  
  // Stop all active processes
  const stopActiveProcesses = useCallback(async () => {
    try {
      // Get current state
      const state = useDataStore.getState();
      
      // Call before stop hook
      await callbacksRef.current.onBeforeStop?.();
      
      // Stop capture if active
      if (state.isCapturing && captureService.current) {
        await captureService.current.stopCapture();
      }
      
      // Stop processing if active
      if ((state.isProcessing || state.isRedoingDetection) && detectorService.current) {
        try {
          await detectorService.current.stopProcessing();
        } catch (error) {
          console.error('Error stopping detector processing:', error);
        }
        // Also update the store state directly
        useDataStore.getState().completeRedoDetection();
      }
      
      // Call after stop hook
      await callbacksRef.current.onAfterStop?.();
      
      return true;
    } catch (error) {
      console.error('Error stopping processes:', error);
      return false;
    }
  }, []); // No dependencies - uses refs and getState
  
  // Store guard ID and unregister function in refs
  const guardIdRef = useRef(null);
  const unregisterRef = useRef(null);
  
  // Generate guard ID only once
  if (!guardIdRef.current) {
    guardIdRef.current = `process-guard-${processName}-${Math.random()}`;
  }
  
  // Register navigation guard
  useEffect(() => {
    if (!registerGuard) return;
    
    // Clean up previous registration if exists
    if (unregisterRef.current) {
      unregisterRef.current();
      unregisterRef.current = null;
    }
    
    const guardId = guardIdRef.current;
    const unregister = registerGuard(guardId, async (navigation) => {
      // Get fresh state values at guard execution time
      const state = useDataStore.getState();
      const appState = useAppStore.getState();
      const currentlyCapturing = state.isCapturing;
      const currentlyProcessing = state.isProcessing;
      const currentlyRedoing = state.isRedoingDetection;
      const hasActive = currentlyCapturing || currentlyProcessing || currentlyRedoing;
      
      if (!hasActive) {
        return true;
      }
      
      // Determine active process name
      let activeProcess = processName;
      if (currentlyCapturing) activeProcess = 'Recording';
      else if (currentlyRedoing) activeProcess = 'Detection Processing';
      else if (currentlyProcessing) activeProcess = 'Processing';
      
      // Determine message
      let message = customMessage;
      if (!message) {
        if (currentlyCapturing) {
          message = `${activeProcess} is in progress. Do you want to continue recording or stop and ${
            allowForceStop ? 'discard the recording' : 'save the captured frames'
          }?`;
        } else if (currentlyRedoing || currentlyProcessing) {
          message = `${activeProcess} is in progress. Leaving now will cancel the processing. Continue?`;
        } else {
          message = `${activeProcess} is currently running. Are you sure you want to leave?`;
        }
      }
      
      return new Promise((resolve) => {
        appState.openModal('processGuard', {
          title: `${activeProcess} in Progress`,
          message: message,
          confirmText: currentlyCapturing ? 'Continue Recording' : 'Continue Processing',
          cancelText: allowForceStop ? 'Stop & Leave' : 'Cancel',
          onConfirm: () => {
            appState.closeModal('processGuard');
            resolve(false); // Don't navigate
          },
          onCancel: async () => {
            if (allowForceStop) {
              const stopped = await stopActiveProcesses();
              appState.closeModal('processGuard');
              // Add small delay to ensure state updates propagate
              setTimeout(() => {
                resolve(stopped); // Navigate if successfully stopped
              }, 100);
            } else {
              appState.closeModal('processGuard');
              resolve(false); // Don't navigate
            }
          }
        });
      });
    });
    
    // Store unregister function
    unregisterRef.current = unregister;
    
    // Cleanup on unmount
    return () => {
      if (unregisterRef.current) {
        unregisterRef.current();
        unregisterRef.current = null;
      }
    };
  }, []); // Run only once on mount
  
  // Browser unload handler
  useEffect(() => {
    const handleBeforeUnload = (e) => {
      if (hasActiveProcess) {
        e.preventDefault();
        e.returnValue = getMessage();
        return getMessage();
      }
    };
    
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [hasActiveProcess, getMessage]);
  
  return {
    // State
    hasActiveProcess,
    activeProcessName: getActiveProcessName(),
    isCapturing,
    isProcessing,
    isRedoingDetection,
    
    // Actions
    stopActiveProcesses,
    
    // Utilities
    canNavigate: !hasActiveProcess
  };
}
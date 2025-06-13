import React, { useEffect, useState } from 'react';
import { useDataStore, useProcessingStore, useAppStore } from '../../stores';
import ConfirmModal from '../modals/ConfirmModal';

/**
 * HOC to wrap components that need process protection
 * @param {Component} WrappedComponent - Component to wrap
 * @param {Object} options - Guard options
 */
export function withProcessGuard(WrappedComponent, options = {}) {
  const {
    processName = 'Process',
    allowForceStop = true,
    customGuards = [],
    beforeNavigate,
    afterNavigate
  } = options;

  return function ProcessGuardedComponent(props) {
    const [showConfirm, setShowConfirm] = useState(false);
    const [pendingNavigation, setPendingNavigation] = useState(null);
    
    // Store states
    const { isCapturing, stopCapture } = useDataStore();
    const { isProcessing, stopProcessing } = useProcessingStore();
    const { notify } = useAppStore();
    
    // Check if any process is active
    const hasActiveProcess = isCapturing || isProcessing || customGuards.some(guard => guard());
    
    // Browser unload handler
    useEffect(() => {
      const handleBeforeUnload = (e) => {
        if (hasActiveProcess) {
          e.preventDefault();
          e.returnValue = 'You have unsaved changes. Are you sure you want to leave?';
          return e.returnValue;
        }
      };
      
      window.addEventListener('beforeunload', handleBeforeUnload);
      return () => window.removeEventListener('beforeunload', handleBeforeUnload);
    }, [hasActiveProcess]);
    
    // Get active process name
    const getActiveProcessName = () => {
      if (isCapturing) return 'Recording';
      if (isProcessing) return 'Processing';
      return processName;
    };
    
    // Stop all active processes
    const stopActiveProcesses = async () => {
      try {
        if (isCapturing) await stopCapture();
        if (isProcessing) await stopProcessing();
        
        // Call custom stop handlers
        for (const guard of customGuards) {
          if (guard.stop) await guard.stop();
        }
        
        return true;
      } catch (error) {
        console.error('Error stopping processes:', error);
        notify.error('Failed to stop processes');
        return false;
      }
    };
    
    // Enhanced navigation handler
    const handleNavigation = async (navigationFn, ...args) => {
      if (!hasActiveProcess) {
        // Call before navigate hook
        if (beforeNavigate) await beforeNavigate();
        
        // Perform navigation
        const result = await navigationFn(...args);
        
        // Call after navigate hook
        if (afterNavigate) await afterNavigate();
        
        return result;
      }
      
      // Store pending navigation
      setPendingNavigation({ fn: navigationFn, args });
      setShowConfirm(true);
      return false;
    };
    
    // Confirm handler
    const handleConfirm = async () => {
      setShowConfirm(false);
      
      if (allowForceStop) {
        const stopped = await stopActiveProcesses();
        if (stopped && pendingNavigation) {
          // Execute pending navigation
          const { fn, args } = pendingNavigation;
          await fn(...args);
        }
      }
      
      setPendingNavigation(null);
    };
    
    // Cancel handler
    const handleCancel = () => {
      setShowConfirm(false);
      setPendingNavigation(null);
    };
    
    // Wrap all navigation props
    const wrappedProps = {
      ...props,
      // Wrap navigation functions
      onNavigate: props.onNavigate ? 
        (...args) => handleNavigation(props.onNavigate, ...args) : undefined,
      onBack: props.onBack ? 
        (...args) => handleNavigation(props.onBack, ...args) : undefined,
      onClose: props.onClose ? 
        (...args) => handleNavigation(props.onClose, ...args) : undefined,
      
      // Provide guard state
      hasActiveProcess,
      activeProcessName: getActiveProcessName(),
      canNavigate: !hasActiveProcess
    };
    
    return (
      <>
        <WrappedComponent {...wrappedProps} />
        
        {showConfirm && (
          <ConfirmModal
            title={`${getActiveProcessName()} in Progress`}
            message={`${getActiveProcessName()} is currently running. ${
              allowForceStop 
                ? 'Do you want to stop it and continue?' 
                : 'Please wait for it to complete.'
            }`}
            confirmText={allowForceStop ? 'Stop & Continue' : 'Wait'}
            cancelText={allowForceStop ? 'Keep Running' : 'Cancel'}
            onConfirm={handleConfirm}
            onCancel={handleCancel}
          />
        )}
      </>
    );
  };
}

// Convenient hook for functional components
export function useProcessGuard(options = {}) {
  const { isCapturing } = useDataStore();
  const { isProcessing } = useProcessingStore();
  
  const hasActiveProcess = isCapturing || isProcessing;
  
  const checkNavigation = async (callback) => {
    if (!hasActiveProcess) {
      return callback();
    }
    
    const confirmed = await useAppStore.getState().confirm({
      title: 'Process in Progress',
      message: options.message || 'A process is currently running. Do you want to stop it?',
      confirmText: 'Stop & Continue',
      cancelText: 'Keep Running'
    });
    
    if (confirmed && options.onStop) {
      await options.onStop();
      return callback();
    }
    
    return false;
  };
  
  return {
    hasActiveProcess,
    checkNavigation,
    isCapturing,
    isProcessing
  };
}
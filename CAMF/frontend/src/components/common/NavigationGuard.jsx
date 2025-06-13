import React, { useEffect } from 'react';
import { useAppStore, useDataStore, useProcessingStore } from '../../stores';
import ConfirmModal from '../modals/ConfirmModal';
import { CaptureService } from '../../services';

export default function NavigationGuard() {
  const pendingNavigation = useAppStore(state => state.pendingNavigation);
  const clearPendingNavigation = useAppStore(state => state.clearPendingNavigation);
  const confirmPendingNavigation = useAppStore(state => state.confirmPendingNavigation);
  const confirmModal = useAppStore(state => state.modals.confirm);
  const openModal = useAppStore(state => state.openModal);
  const closeModal = useAppStore(state => state.closeModal);
  const registerGuard = useAppStore(state => state.registerGuard);
  const { isCapturing, stopCapture } = useDataStore();
  const { isProcessing, activeProcesses, clearActiveProcesses } = useProcessingStore();
  
  const confirm = useAppStore(state => state.confirm);
  
  // Register navigation guard on mount
  useEffect(() => {
    const guardId = 'navigation-guard';
    const unregister = registerGuard(guardId, async (to, navState) => {
      // Check if any process is active
      const hasActiveProcess = isCapturing || isProcessing || activeProcesses.length > 0;
      
      if (hasActiveProcess) {
        const processNames = [];
        if (isCapturing) processNames.push('Capture');
        if (isProcessing) processNames.push('Processing');
        if (activeProcesses.length > 0) {
          processNames.push(...activeProcesses.map(p => p.name || 'Detection'));
        }
        
        const confirmed = await confirm({
          title: 'Active Process Warning',
          message: `You have active processes running: ${processNames.join(', ')}. ` +
                   'Leaving this page will cancel all processes. Do you want to continue?',
          confirmText: 'Leave & Cancel',
          cancelText: 'Stay',
          variant: 'warning'
        });
        
        if (confirmed) {
          // Cancel all active processes
          if (isCapturing) {
            try {
              await stopCapture();
            } catch (error) {
              console.error('Error stopping capture:', error);
            }
          }
          
          // Clear all active processes
          clearActiveProcesses();
          
          return true;
        }
        
        return false;
      }
      
      return true;
    });
    
    return () => useAppStore.getState().unregisterGuard(guardId);
  }, [registerGuard, isCapturing, isProcessing, activeProcesses, confirm, stopCapture, clearActiveProcesses]);
  
  // The ConfirmModal is shown via the global ModalManager
  // This component only handles the navigation guard logic
  return null;
}

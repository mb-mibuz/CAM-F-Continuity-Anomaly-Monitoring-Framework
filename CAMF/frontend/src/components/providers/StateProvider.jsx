import React, { createContext, useContext, useEffect } from 'react';
import { 
  useAppStore,
  useDataStore,
  useProcessingStore
} from '../../stores';
import SSEService from '../../services/SSEService';
import sseEventBridge from '../../services/SSEEventBridge';

const StateContext = createContext(null);

export const useGlobalState = () => {
  const context = useContext(StateContext);
  if (!context) {
    throw new Error('useGlobalState must be used within StateProvider');
  }
  return context;
};

export default function StateProvider({ children }) {
  // Initialize SSE connection and event bridge
  useEffect(() => {
    const initializeSSE = async () => {
      try {
        await SSEService.connect();
        sseEventBridge.initialize();
        console.log('[StateProvider] SSE initialized');
      } catch (error) {
        console.error('[StateProvider] Failed to initialize SSE:', error);
      }
    };
    
    initializeSSE();
    
    // Cleanup on unmount
    return () => {
      sseEventBridge.destroy();
      SSEService.disconnect();
    };
  }, []);
  
  // Subscribe to store changes for side effects
  useEffect(() => {
    // Subscribe to capture state changes
    const unsubCapture = useDataStore.subscribe(
      (state) => state.isCapturing,
      (isCapturing) => {
        if (isCapturing) {
          console.log('Capture started');
          // Prevent system sleep during capture
          if (window.electronAPI?.preventSleep) {
            window.electronAPI.preventSleep(true);
          }
        } else {
          console.log('Capture stopped');
          if (window.electronAPI?.preventSleep) {
            window.electronAPI.preventSleep(false);
          }
        }
      }
    );
    
    // Subscribe to processing state changes
    const unsubProcessing = useProcessingStore.subscribe(
      (state) => state.isProcessing,
      (isProcessing) => {
        if (isProcessing) {
          console.log('Processing started');
          document.title = 'CAMF - Processing...';
        } else {
          console.log('Processing stopped');
          document.title = 'CAMF';
        }
      }
    );
    
    // Subscribe to theme changes
    const unsubTheme = useAppStore.subscribe(
      (state) => state.preferences.theme,
      (theme) => {
        document.documentElement.classList.toggle('dark', theme === 'dark');
      }
    );
    
    return () => {
      unsubCapture();
      unsubProcessing();
      unsubTheme();
    };
  }, []);
  
  // Global keyboard shortcuts
  useEffect(() => {
    const handleGlobalShortcuts = (e) => {
      const preferences = useAppStore.getState().preferences;
      const shortcuts = preferences.shortcuts || {};
      const dataStore = useDataStore.getState();
      const appStore = useAppStore.getState();
      
      // Don't handle shortcuts if user is typing or shortcuts are disabled
      if (!preferences.enableHotkeys || 
          e.target.tagName === 'INPUT' || 
          e.target.tagName === 'TEXTAREA' || 
          e.target.contentEditable === 'true') {
        return;
      }
      
      const key = e.key.toLowerCase();
      const ctrl = e.ctrlKey || e.metaKey;
      
      // Capture shortcuts
      if (shortcuts.startCapture && key === shortcuts.startCapture && !dataStore.isCapturing) {
        e.preventDefault();
        const location = appStore.getCurrentLocation();
        if (location.page === 'monitoring') {
          window.dispatchEvent(new CustomEvent('shortcut:startCapture'));
        }
      } else if (shortcuts.stopCapture && key === shortcuts.stopCapture && dataStore.isCapturing) {
        e.preventDefault();
        dataStore.stopCapture();
      }
      
      // Navigation shortcuts
      else if (shortcuts.nextFrame && key === shortcuts.nextFrame && !dataStore.isCapturing) {
        e.preventDefault();
        dataStore.navigateFrame('next');
      } else if (shortcuts.prevFrame && key === shortcuts.prevFrame && !dataStore.isCapturing) {
        e.preventDefault();
        dataStore.navigateFrame('prev');
      }
      
      // Save shortcut
      else if (ctrl && key === 's') {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent('shortcut:save'));
      }
    };
    
    window.addEventListener('keydown', handleGlobalShortcuts);
    return () => window.removeEventListener('keydown', handleGlobalShortcuts);
  }, []);
  
  // Provide combined state context
  const contextValue = {
    // Direct store access
    appStore: useAppStore,
    dataStore: useDataStore,
    processingStore: useProcessingStore,
    
    // Common actions
    navigate: useAppStore.getState().navigate,
    addNotification: useAppStore.getState().addNotification,
    openModal: useAppStore.getState().openModal,
    
    // Guards
    canNavigate: () => {
      const data = useDataStore.getState();
      const processing = useProcessingStore.getState();
      return data.canNavigate() && processing.canNavigate();
    }
  };
  
  return (
    <StateContext.Provider value={contextValue}>
      {children}
    </StateContext.Provider>
  );
}
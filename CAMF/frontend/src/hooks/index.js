export { useCapture } from '../queries/hooks/useCapture';
export { useFrameNavigation } from './useFrameNavigation';
export { useSSE, useSSEChannel, useSSEEvents } from './useSSE';
export { useProcessGuard } from './useProcessGuard';
export { usePredictiveFrames, usePredictiveProgress } from './usePredictiveFrames';
export { 
  useSelectiveSubscription, 
  useMultipleSelections, 
  useComputedValue, 
  useRenderMonitor,
  createSelector,
  commonSelectors 
} from './useSelectiveSubscription';

// Utility hooks
export { useAsyncState } from './useAsyncState';
export { useAutoSave } from './useAutoSave';
export { useDebounce } from './useDebounce';
export { useFrameCache } from './useFrameCache';
export { useKeyboardShortcuts } from './useKeyboardShortcuts';
export { useLocalStorage } from './useLocalStorage';
export { usePolling } from './usePolling';
export { useStoreActions } from './useStoreActions';
export { useDetectorConfig } from './useDetectorConfig';
export { useSourcePreview } from './useSourcePreview';

// Combined monitoring hook
export { useMonitoring } from './useMonitoring';

// Re-export React Query hooks
export * from '../queries/hooks';
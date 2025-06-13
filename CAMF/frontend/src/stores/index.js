// Core stores
export { default as useAppStore } from './appStore';
export { default as useDataStore } from './dataStore';
export { default as useProcessingStore } from './processingStore';

// Utils
export * from './utils/shallow';

// Combined store hook
export const useStore = () => ({
  app: useAppStore(),
  data: useDataStore(),
  processing: useProcessingStore()
});

// Reset all stores (useful for logout or cleanup)
export const resetAllStores = () => {
  useAppStore.getState().reset();
  useDataStore.getState().reset();
  useProcessingStore.getState().resetProcessingState();
};


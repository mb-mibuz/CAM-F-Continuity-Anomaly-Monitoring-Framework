import { useAppStore, useDataStore, useProcessingStore } from '../index';

/**
 * Hook to access multiple stores at once
 * @param {Object} selectors - Object with store selectors
 * @returns {Object} Combined store state
 */
export function useCombinedStore(selectors = {}) {
  const app = useAppStore(selectors.app || (s => s));
  const data = useDataStore(selectors.data || (s => s));
  const processing = useProcessingStore(selectors.processing || (s => s));
  
  return {
    app,
    data,
    processing
  };
}
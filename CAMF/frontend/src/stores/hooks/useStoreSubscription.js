import { useEffect } from 'react';

/**
 * Subscribe to specific store state changes
 * @param {Function} store - Zustand store hook
 * @param {Function} selector - State selector function
 * @param {Function} callback - Callback when selected state changes
 */
export function useStoreSubscription(store, selector, callback) {
  useEffect(() => {
    const unsubscribe = store.subscribe(
      (state) => selector(state),
      callback
    );
    
    return unsubscribe;
  }, [store, selector, callback]);
}


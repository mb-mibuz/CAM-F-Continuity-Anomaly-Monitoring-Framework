import { useMemo } from 'react';

/**
 * Hook to memoize store actions to prevent unnecessary re-renders
 * @param {Function} store - Zustand store hook
 * @param {string[]} actionNames - Array of action names to extract
 * @returns {Object} Object with memoized actions
 */
export function useStoreActions(store, actionNames) {
  return useMemo(() => {
    const state = store.getState();
    const actions = {};
    
    actionNames.forEach(name => {
      if (typeof state[name] === 'function') {
        actions[name] = state[name];
      }
    });
    
    return actions;
  }, [store, actionNames]);
}
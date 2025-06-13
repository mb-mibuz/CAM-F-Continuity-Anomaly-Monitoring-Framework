import { useEffect, useRef } from 'react';

/**
 * Hook for polling an async function at intervals
 * @param {Function} asyncFn - Async function to poll
 * @param {number} interval - Polling interval in ms
 * @param {boolean} enabled - Whether polling is enabled
 * @param {Array} deps - Dependencies array
 */
export function usePolling(asyncFn, interval, enabled = true, deps = []) {
  const savedCallback = useRef(asyncFn);
  const intervalRef = useRef(null);
  
  useEffect(() => {
    savedCallback.current = asyncFn;
  }, [asyncFn]);
  
  useEffect(() => {
    if (!enabled) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }
    
    const tick = async () => {
      await savedCallback.current();
    };
    
    // Call immediately
    tick();
    
    // Then set up interval
    intervalRef.current = setInterval(tick, interval);
    
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [interval, enabled, ...deps]);
}
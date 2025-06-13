import { useEffect, useRef } from 'react';

/**
 * Hook for auto-saving data at intervals
 * @param {Function} saveFunction - Function to call for saving
 * @param {any} data - Data to save
 * @param {number} interval - Save interval in ms (default: 30000)
 * @param {boolean} enabled - Whether auto-save is enabled
 */
export function useAutoSave(saveFunction, data, interval = 30000, enabled = true) {
  const timeoutRef = useRef(null);
  const lastSavedRef = useRef(JSON.stringify(data));
  
  useEffect(() => {
    if (!enabled) return;
    
    const currentData = JSON.stringify(data);
    
    // Only save if data has changed
    if (currentData !== lastSavedRef.current) {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
      
      timeoutRef.current = setTimeout(() => {
        saveFunction(data);
        lastSavedRef.current = currentData;
      }, interval);
    }
    
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [data, saveFunction, interval, enabled]);
}
import { useState, useCallback, useRef, useEffect } from 'react';

/**
 * Hook for managing async operations with loading/error states
 * @param {Function} asyncFunction - Async function to execute
 * @returns {Object} State and execute function
 */
export function useAsyncState(asyncFunction) {
  const [state, setState] = useState({
    loading: false,
    error: null,
    data: null
  });
  
  const mountedRef = useRef(true);
  const abortControllerRef = useRef(null);
  
  useEffect(() => {
    return () => {
      mountedRef.current = false;
      abortControllerRef.current?.abort();
    };
  }, []);
  
  const execute = useCallback(async (...args) => {
    setState({ loading: true, error: null, data: null });
    
    // Cancel previous request
    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();
    
    try {
      const result = await asyncFunction(...args, {
        signal: abortControllerRef.current.signal
      });
      
      if (mountedRef.current) {
        setState({ loading: false, error: null, data: result });
      }
      
      return result;
    } catch (error) {
      if (error.name === 'AbortError') {
        console.log('Request aborted');
      } else if (mountedRef.current) {
        setState({ loading: false, error, data: null });
      }
      throw error;
    }
  }, [asyncFunction]);
  
  const reset = useCallback(() => {
    setState({ loading: false, error: null, data: null });
  }, []);
  
  return { ...state, execute, reset };
}
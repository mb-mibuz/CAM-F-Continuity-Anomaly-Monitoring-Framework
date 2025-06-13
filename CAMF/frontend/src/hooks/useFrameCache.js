import { useRef, useCallback, useEffect } from 'react';

/**
 * Hook for managing frame blob URL cache
 * @param {number} maxSize - Maximum cache size (default: 100)
 * @returns {Object} Cache operations
 */
export function useFrameCache(maxSize = 100) {
  const cacheRef = useRef(new Map());
  const orderRef = useRef([]);
  
  const get = useCallback((key) => {
    return cacheRef.current.get(key);
  }, []);
  
  const set = useCallback((key, blob) => {
    // If already exists, remove from order
    if (cacheRef.current.has(key)) {
      const oldUrl = cacheRef.current.get(key);
      URL.revokeObjectURL(oldUrl);
      orderRef.current = orderRef.current.filter(k => k !== key);
    }
    
    // Create new URL
    const url = URL.createObjectURL(blob);
    cacheRef.current.set(key, url);
    orderRef.current.push(key);
    
    // Evict oldest if over limit
    while (orderRef.current.length > maxSize) {
      const oldestKey = orderRef.current.shift();
      const oldUrl = cacheRef.current.get(oldestKey);
      URL.revokeObjectURL(oldUrl);
      cacheRef.current.delete(oldestKey);
    }
    
    return url;
  }, [maxSize]);
  
  const clear = useCallback(() => {
    cacheRef.current.forEach(url => URL.revokeObjectURL(url));
    cacheRef.current.clear();
    orderRef.current = [];
  }, []);
  
  const remove = useCallback((key) => {
    if (cacheRef.current.has(key)) {
      const url = cacheRef.current.get(key);
      URL.revokeObjectURL(url);
      cacheRef.current.delete(key);
      orderRef.current = orderRef.current.filter(k => k !== key);
    }
  }, []);
  
  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clear();
    };
  }, [clear]);
  
  return { get, set, clear, remove };
}
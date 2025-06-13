import { useRef, useMemo, useDebugValue } from 'react';
import { useStore } from 'zustand';
import { shallow } from '../stores/utils/shallow';

/**
 * Optimized hook for selective store subscriptions with memoization
 * Prevents unnecessary re-renders by only subscribing to specific store slices
 * 
 * @param {Function} store - The zustand store hook
 * @param {Function} selector - Function to select specific state
 * @param {Function} equalityFn - Optional equality function (defaults to shallow)
 * @returns {*} Selected state
 */
export function useSelectiveSubscription(store, selector, equalityFn = shallow) {
  const renderCount = useRef(0);
  
  // Memoize the selector for performance
  const memoizedSelector = useMemo(
    () => selector,
    // Only recreate if selector reference changes
    [selector]
  );
  
  // Use zustand's built-in subscription with equality check
  const selectedState = useStore(store, memoizedSelector, equalityFn);
  
  // Track render count in development
  if (process.env.NODE_ENV === 'development') {
    renderCount.current++;
    useDebugValue({
      renderCount: renderCount.current,
      selectedState
    });
  }
  
  return selectedState;
}

/**
 * Hook for multiple selective subscriptions with computed values
 * 
 * @param {Object} subscriptions - Object mapping keys to [store, selector] tuples
 * @returns {Object} Object with selected values
 */
export function useMultipleSelections(subscriptions) {
  const renderCount = useRef(0);
  const previousValues = useRef({});
  
  const results = useMemo(() => {
    const newResults = {};
    let hasChanges = false;
    
    for (const [key, [store, selector, equalityFn = shallow]] of Object.entries(subscriptions)) {
      const value = store.getState();
      const selected = selector(value);
      
      // Check if this specific value changed
      if (!equalityFn(previousValues.current[key], selected)) {
        hasChanges = true;
        previousValues.current[key] = selected;
      }
      
      newResults[key] = selected;
    }
    
    // Only increment render count if something actually changed
    if (hasChanges && process.env.NODE_ENV === 'development') {
      renderCount.current++;
    }
    
    return newResults;
  }, [subscriptions]);
  
  // Subscribe to each store
  Object.entries(subscriptions).forEach(([key, [store, selector, equalityFn = shallow]]) => {
    useStore(store, selector, equalityFn);
  });
  
  if (process.env.NODE_ENV === 'development') {
    useDebugValue({
      renderCount: renderCount.current,
      subscriptions: Object.keys(subscriptions)
    });
  }
  
  return results;
}

/**
 * Create a memoized selector with dependencies
 * 
 * @param {Function} selector - The selector function
 * @param {Array} deps - Dependencies for memoization
 * @returns {Function} Memoized selector
 */
export function createSelector(selector, deps = []) {
  let lastArgs = null;
  let lastResult = null;
  
  return (state) => {
    const args = deps.map(dep => 
      typeof dep === 'function' ? dep(state) : state[dep]
    );
    
    // Check if dependencies changed
    if (lastArgs && args.every((arg, i) => arg === lastArgs[i])) {
      return lastResult;
    }
    
    lastArgs = args;
    lastResult = selector(state, ...args);
    return lastResult;
  };
}

/**
 * Hook for computed values based on multiple store values
 * 
 * @param {Function} computeFn - Function to compute derived value
 * @param {Array} dependencies - Array of [store, selector] tuples
 * @returns {*} Computed value
 */
export function useComputedValue(computeFn, dependencies) {
  const values = dependencies.map(([store, selector]) => 
    useSelectiveSubscription(store, selector)
  );
  
  return useMemo(
    () => computeFn(...values),
    values
  );
}

/**
 * Performance monitoring hook for development
 * Tracks render counts and helps identify optimization opportunities
 */
export function useRenderMonitor(componentName) {
  const renderCount = useRef(0);
  const renderTimes = useRef([]);
  const lastRenderTime = useRef(Date.now());
  
  if (process.env.NODE_ENV === 'development') {
    renderCount.current++;
    
    const now = Date.now();
    const timeSinceLastRender = now - lastRenderTime.current;
    lastRenderTime.current = now;
    
    renderTimes.current.push(timeSinceLastRender);
    if (renderTimes.current.length > 10) {
      renderTimes.current.shift();
    }
    
    const avgRenderTime = renderTimes.current.reduce((a, b) => a + b, 0) / renderTimes.current.length;
    
    // Warn if rendering too frequently
    if (renderCount.current > 10 && avgRenderTime < 50) {
      console.warn(
        `[Performance] ${componentName} is rendering frequently:`,
        {
          renderCount: renderCount.current,
          avgTimeBetweenRenders: `${avgRenderTime.toFixed(2)}ms`,
          suggestion: 'Consider using more selective subscriptions or memoization'
        }
      );
    }
    
    useDebugValue({
      component: componentName,
      renderCount: renderCount.current,
      avgRenderTime: `${avgRenderTime.toFixed(2)}ms`
    });
  }
}

// Export common selectors for reuse
export const commonSelectors = {
  // Capture selectors
  captureStatus: createSelector(
    state => ({
      isCapturing: state.isCapturing,
      progress: state.captureProgress,
      source: state.source
    }),
    ['isCapturing', 'captureProgress', 'source']
  ),
  
  captureFrameInfo: createSelector(
    state => ({
      frameCount: state.frameCount,
      currentFrameIndex: state.currentFrameIndex,
      currentFrame: state.currentFrame,
      referenceFrame: state.referenceFrame
    }),
    ['frameCount', 'currentFrameIndex', 'currentFrame', 'referenceFrame']
  ),
  
  // UI selectors
  modalStates: state => state.modals,
  notifications: state => state.notifications,
  
  // Processing selectors
  processingStatus: createSelector(
    state => ({
      isProcessing: state.isProcessing,
      progress: state.processingProgress,
      errors: state.processingErrors
    }),
    ['isProcessing', 'processingProgress', 'processingErrors']
  ),
  
  // Project selectors
  currentContext: createSelector(
    state => ({
      project: state.currentProject,
      scene: state.currentScene,
      angle: state.currentAngle,
      take: state.currentTake
    }),
    ['currentProject', 'currentScene', 'currentAngle', 'currentTake']
  )
};
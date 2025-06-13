import { subscribeWithSelector } from 'zustand/middleware';

/**
 * Logger middleware for development
 */
export const logger = (config) => (set, get, api) => 
  config(
    (...args) => {
      if (process.env.NODE_ENV === 'development') {
        console.log('  applying', args);
      }
      set(...args);
      if (process.env.NODE_ENV === 'development') {
        console.log('  new state', get());
      }
    },
    get,
    api
  );

/**
 * Performance tracking middleware
 */
export const performanceTracker = (config) => (set, get, api) => {
  const trackedActions = new Map();
  
  return config(
    (...args) => {
      const startTime = performance.now();
      const actionName = args[0]?.type || 'unknown';
      
      set(...args);
      
      const endTime = performance.now();
      const duration = endTime - startTime;
      
      // Track performance metrics
      if (!trackedActions.has(actionName)) {
        trackedActions.set(actionName, []);
      }
      
      trackedActions.get(actionName).push(duration);
      
      // Log slow actions
      if (duration > 16) { // Longer than one frame at 60fps
        console.warn(`Slow action: ${actionName} took ${duration.toFixed(2)}ms`);
      }
    },
    get,
    {
      ...api,
      getPerformanceMetrics: () => {
        const metrics = {};
        trackedActions.forEach((durations, action) => {
          metrics[action] = {
            count: durations.length,
            average: durations.reduce((a, b) => a + b, 0) / durations.length,
            max: Math.max(...durations),
            min: Math.min(...durations)
          };
        });
        return metrics;
      }
    }
  );
};

/**
 * Action sanitizer for Redux DevTools
 */
export const actionSanitizer = (action) => {
  // Remove sensitive data or large payloads
  if (action.type === 'updateFrame' && action.payload?.frameData) {
    return {
      ...action,
      payload: {
        ...action.payload,
        frameData: '<FRAME_DATA>'
      }
    };
  }
  
  return action;
};

/**
 * State sanitizer for Redux DevTools
 */
export const stateSanitizer = (state) => {
  // Sanitize large data structures
  if (state.captureStore?.previewFrame) {
    return {
      ...state,
      captureStore: {
        ...state.captureStore,
        previewFrame: '<PREVIEW_FRAME>',
        currentFrame: '<CURRENT_FRAME>',
        referenceFrame: '<REFERENCE_FRAME>'
      }
    };
  }
  
  return state;
};

/**
 * Create store with all middleware
 */
export const createStoreWithMiddleware = (storeCreator, options = {}) => {
  const {
    name = 'store',
    logging = process.env.NODE_ENV === 'development',
    performance = process.env.NODE_ENV === 'development',
    persist = false,
    persistOptions = {}
  } = options;
  
  let middleware = [subscribeWithSelector];
  
  if (logging) {
    middleware.push(logger);
  }
  
  if (performance) {
    middleware.push(performanceTracker);
  }
  
  if (persist) {
    const { persist } = require('zustand/middleware');
    middleware.push((config) => persist(config, {
      name,
      ...persistOptions
    }));
  }
  
  // Add devtools last
  if (process.env.NODE_ENV === 'development') {
    const { devtools } = require('zustand/middleware');
    middleware.push((config) => devtools(config, {
      name,
      actionSanitizer,
      stateSanitizer
    }));
  }
  
  // Apply middleware in reverse order
  return middleware.reduceRight(
    (acc, middleware) => middleware(acc),
    storeCreator
  );
};
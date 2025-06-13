/**
 * Create a selector that only re-renders when selected values change
 */
export const createSelector = (selector) => {
  let prev;
  
  return (state) => {
    const next = selector(state);
    if (prev === next) return prev;
    prev = next;
    return next;
  };
};

/**
 * Combine multiple store states
 */
export const combineStores = (...stores) => {
  return (selector) => {
    const states = stores.map(store => store(selector));
    return Object.assign({}, ...states);
  };
};

/**
 * Create async action with error handling
 */
export const createAsyncAction = (action) => {
  return async (...args) => {
    try {
      return await action(...args);
    } catch (error) {
      console.error('Async action error:', error);
      throw error;
    }
  };
};

/**
 * Debounce store updates
 */
export const debounceUpdate = (fn, delay) => {
  let timeoutId;
  
  return (...args) => {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => fn(...args), delay);
  };
};
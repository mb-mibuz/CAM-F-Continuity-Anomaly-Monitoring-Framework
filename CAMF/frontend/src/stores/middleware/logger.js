const logger = (config) => (set, get, api) =>
  config(
    (...args) => {
      const prevState = get();
      set(...args);
      const nextState = get();
      
      if (process.env.NODE_ENV === 'development') {
        console.group(`[${new Date().toLocaleTimeString()}] State Update`);
        console.log('Previous State:', prevState);
        console.log('Next State:', nextState);
        console.log('Diff:', getDiff(prevState, nextState));
        console.groupEnd();
      }
    },
    get,
    api
  );

function getDiff(prev, next) {
  const diff = {};
  
  // Find changed properties
  Object.keys(next).forEach(key => {
    if (prev[key] !== next[key]) {
      diff[key] = {
        prev: prev[key],
        next: next[key]
      };
    }
  });
  
  return diff;
}

export default logger;
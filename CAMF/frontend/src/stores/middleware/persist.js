const persist = (config, options) => (set, get, api) => {
  const {
    name,
    storage = localStorage,
    serialize = JSON.stringify,
    deserialize = JSON.parse,
    partialize,
    version = 0,
    migrate
  } = options;

  // Load persisted state
  const loadPersistedState = () => {
    try {
      const storedValue = storage.getItem(name);
      if (!storedValue) return null;
      
      const { state, version: storedVersion } = deserialize(storedValue);
      
      // Handle migration
      if (migrate && storedVersion !== version) {
        return migrate(state, storedVersion);
      }
      
      return state;
    } catch (error) {
      console.error('Error loading persisted state:', error);
      return null;
    }
  };

  // Save state to storage
  const saveState = (state) => {
    try {
      const stateToStore = partialize ? partialize(state) : state;
      storage.setItem(name, serialize({ state: stateToStore, version }));
    } catch (error) {
      console.error('Error persisting state:', error);
    }
  };

  // Initialize with persisted state
  const persistedState = loadPersistedState();
  if (persistedState) {
    set(persistedState, true);
  }

  // Wrap set to persist on changes
  return config(
    (...args) => {
      set(...args);
      saveState(get());
    },
    get,
    api
  );
};

export default persist;
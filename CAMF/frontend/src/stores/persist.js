import { persist } from 'zustand/middleware';

/**
 * Create a persisted version of a store
 * @param {Function} storeCreator - Store creator function
 * @param {Object} options - Persistence options
 */
export function createPersistedStore(storeCreator, options) {
  return persist(storeCreator, {
    name: options.name,
    storage: {
      getItem: async (name) => {
        try {
          const value = localStorage.getItem(name);
          return value ? JSON.parse(value) : null;
        } catch (error) {
          console.error('Error loading persisted state:', error);
          return null;
        }
      },
      setItem: async (name, value) => {
        try {
          localStorage.setItem(name, JSON.stringify(value));
        } catch (error) {
          console.error('Error persisting state:', error);
        }
      },
      removeItem: async (name) => {
        try {
          localStorage.removeItem(name);
        } catch (error) {
          console.error('Error removing persisted state:', error);
        }
      }
    },
    partialize: options.partialize,
    version: options.version || 1,
    migrate: options.migrate
  });
}
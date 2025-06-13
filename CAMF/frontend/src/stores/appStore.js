import { create } from 'zustand';
import { devtools, subscribeWithSelector } from 'zustand/middleware';
import { immer } from 'zustand/middleware/immer';
import { enableMapSet } from 'immer';

// Enable MapSet support for Immer
enableMapSet();

// Store refresh functions outside of Zustand to avoid re-render loops
const pageRefreshFunctions = new Map();

const STORE_NAME = 'app-store';
const VERSION = 1;

const defaultPreferences = {
  theme: 'light',
  showTooltips: true,
  autoSaveInterval: 30000,
  confirmBeforeDelete: true,
  compactMode: false,
  defaultCaptureSource: 'camera',
  enableHotkeys: true,
  playbackSpeed: 1,
  framePreloadRadius: 5,
  showDetectorLogs: true,
  showPerformanceMetrics: false,
  maxRecentProjects: 10,
  maxRecentScenes: 5,
  shortcuts: {
    startCapture: ' ',  // Spacebar
    stopCapture: 'escape',
    nextFrame: 'arrowright',
    prevFrame: 'arrowleft',
    save: 's'
  }
};

const useAppStore = create(
  subscribeWithSelector(
    devtools(
      immer((set, get) => ({
        // UI State (from uiStore)
        modals: {
          newProject: { isOpen: false, data: null },
          newScene: { isOpen: false, data: null },
          newAngle: { isOpen: false, data: null },
          newTake: { isOpen: false, data: null },
          sceneConfig: { isOpen: false, data: null },
          detectorConfig: { isOpen: false, data: null },
          sourceSelection: { isOpen: false, data: null },
          sourceDisconnected: { isOpen: false, data: null },
          videoUpload: { isOpen: false, data: null },
          referenceCapture: { isOpen: false, data: null },
          confirm: { isOpen: false, data: null },
          rename: { isOpen: false, data: null },
          frameLink: { isOpen: false, data: null },
          uploadDetectors: { isOpen: false, data: null },
          managePlugins: { isOpen: false, data: null },
          processGuard: { isOpen: false, data: null }
        },
        
        notifications: [],
        notificationIdCounter: 0,
        
        globalLoading: false,
        globalError: null,
        
        // Navigation State (already in uiStore)
        history: [{ path: '/', state: null }],
        currentIndex: 0,
        guards: new Map(),
        pendingNavigation: null,
        refreshHandlers: new Map(),
        isRefreshing: false,
        
        // Session State (from sessionStore)
        user: null,
        isAuthenticated: false,
        recentProjects: [],
        recentScenes: [],
        connectionStatus: {
          websocket: 'disconnected',
          api: 'unknown'
        },
        serverInfo: {
          resources: {
            cpu: 0,
            memory: 0,
            gpuAvailable: false
          },
          warnings: []
        },
        
        // Combined Preferences
        preferences: defaultPreferences,
        
        // Modal Actions
        openModal: (modalName, data = null) => set((state) => {
          if (state.modals[modalName]) {
            state.modals[modalName] = { isOpen: true, data };
          }
        }),
        
        closeModal: (modalName) => set((state) => {
          if (state.modals[modalName]) {
            state.modals[modalName] = { isOpen: false, data: null };
          }
        }),
        
        closeAllModals: () => set((state) => {
          Object.keys(state.modals).forEach(modalName => {
            state.modals[modalName] = { isOpen: false, data: null };
          });
        }),
        
        updateModalData: (modalName, data) => set((state) => {
          if (state.modals[modalName]) {
            state.modals[modalName].data = data;
          }
        }),
        
        // Notification Actions
        addNotification: (notification) => set((state) => {
          const id = state.notificationIdCounter + 1;
          state.notificationIdCounter = id;
          
          const newNotification = {
            id,
            type: 'info',
            duration: 5000,
            ...notification,
            timestamp: new Date().toISOString()
          };
          
          state.notifications.push(newNotification);
          
          if (newNotification.duration && newNotification.duration > 0) {
            setTimeout(() => {
              get().removeNotification(id);
            }, newNotification.duration);
          }
        }),
        
        removeNotification: (id) => set((state) => {
          state.notifications = state.notifications.filter(n => n.id !== id);
        }),
        
        clearNotifications: () => set((state) => {
          state.notifications = [];
        }),
        
        // Loading/Error Actions
        setGlobalLoading: (loading) => set((state) => {
          state.globalLoading = loading;
        }),
        
        setGlobalError: (error) => set((state) => {
          state.globalError = error;
          if (error) {
            state.addNotification({
              type: 'error',
              title: 'Error',
              message: error.message || 'An unexpected error occurred',
              duration: 0
            });
          }
        }),
        
        clearGlobalError: () => set((state) => {
          state.globalError = null;
        }),
        
        // Navigation Actions
        navigate: (path, options = {}) => {
          const state = get();
          const { replace = false, state: navState = null } = options;
          
          if (state.guards.size > 0) {
            const guardPromises = Array.from(state.guards.values()).map(guard => {
              if (typeof guard === 'function') {
                return guard(path, navState);
              }
              return true; // If not a function, allow navigation
            });
            
            Promise.all(guardPromises).then(results => {
              const canNavigate = results.every(result => result !== false);
              
              if (canNavigate) {
                set((state) => {
                  if (replace && state.currentIndex >= 0) {
                    state.history[state.currentIndex] = { path, state: navState };
                  } else {
                    state.history = state.history.slice(0, state.currentIndex + 1);
                    state.history.push({ path, state: navState });
                    state.currentIndex = state.history.length - 1;
                  }
                  state.pendingNavigation = null;
                });
                
                // Only pass simple serializable data to pushState
                window.history.pushState(null, '', path);
              } else {
                set((state) => {
                  state.pendingNavigation = { path, state: navState };
                });
              }
            });
          } else {
            set((state) => {
              if (replace && state.currentIndex >= 0) {
                state.history[state.currentIndex] = { path, state: navState };
              } else {
                state.history = state.history.slice(0, state.currentIndex + 1);
                state.history.push({ path, state: navState });
                state.currentIndex = state.history.length - 1;
              }
            });
            
            window.history.pushState(null, '', path);
          }
        },
        
        canGoBack: () => {
          const state = get();
          return state.currentIndex > 0;
        },
        
        canGoForward: () => {
          const state = get();
          return state.currentIndex < state.history.length - 1;
        },
        
        goBack: () => {
          const state = get();
          if (state.currentIndex > 0) {
            const targetPath = state.history[state.currentIndex - 1].path;
            
            // Check guards
            if (state.guards.size > 0) {
              const guardPromises = Array.from(state.guards.values()).map(guard => {
                if (typeof guard === 'function') {
                  return guard(targetPath, null);
                }
                return true;
              });
              
              Promise.all(guardPromises).then(results => {
                const canNavigate = results.every(result => result !== false);
                
                if (canNavigate) {
                  set((state) => {
                    state.currentIndex -= 1;
                    const { path } = state.history[state.currentIndex];
                    window.history.replaceState(null, '', path);
                  });
                }
              });
            } else {
              set((state) => {
                state.currentIndex -= 1;
                const { path } = state.history[state.currentIndex];
                window.history.replaceState(null, '', path);
              });
            }
          }
        },
        
        goForward: () => set((state) => {
          if (state.currentIndex < state.history.length - 1) {
            state.currentIndex += 1;
            const { path } = state.history[state.currentIndex];
            // Use replaceState instead of pushState when navigating history
            window.history.replaceState(null, '', path);
          }
        }),
        
        registerGuard: (id, guardFn) => set((state) => {
          state.guards.set(id, guardFn);
        }),
        
        unregisterGuard: (id) => set((state) => {
          state.guards.delete(id);
        }),
        
        registerRefreshHandler: (id, handler) => set((state) => {
          state.refreshHandlers.set(id, handler);
        }),
        
        unregisterRefreshHandler: (id) => set((state) => {
          state.refreshHandlers.delete(id);
        }),
        
        refresh: async () => {
          const state = get();
          set((state) => { state.isRefreshing = true; });
          
          try {
            // Call global refresh handlers
            const handlers = Array.from(state.refreshHandlers.values());
            await Promise.all(handlers.map(handler => handler()));
            
            // Call current page refresh function if exists
            const currentLocation = state.getCurrentLocation();
            const pageRefreshFn = pageRefreshFunctions.get(currentLocation.page);
            if (pageRefreshFn) {
              await pageRefreshFn();
            }
          } finally {
            set((state) => { state.isRefreshing = false; });
          }
        },
        
        registerRefreshFunction: (page, refreshFn) => {
          // Store in external Map to avoid re-render loops
          pageRefreshFunctions.set(page, refreshFn);
          
          // Return unregister function
          return () => {
            pageRefreshFunctions.delete(page);
          };
        },
        
        clearPendingNavigation: () => set((state) => {
          state.pendingNavigation = null;
        }),
        
        confirmPendingNavigation: () => {
          const state = get();
          if (state.pendingNavigation) {
            const { path, state: navState } = state.pendingNavigation;
            state.navigate(path, { state: navState });
          }
        },
        
        getCurrentLocation: () => {
          const state = get();
          if (state.currentIndex >= 0 && state.history[state.currentIndex]) {
            const current = state.history[state.currentIndex];
            const path = current.path || window.location.pathname;
            
            // Parse the path to extract page and params
            const pathParts = path.split('/').filter(Boolean);
            const page = pathParts[0] || 'home';
            
            // Extract params based on the page
            const params = {};
            if (page === 'scenes' && pathParts[1]) {
              params.projectId = parseInt(pathParts[1], 10);
            } else if (page === 'takes' && pathParts[1] && pathParts[2]) {
              params.projectId = parseInt(pathParts[1], 10);
              params.sceneId = parseInt(pathParts[2], 10);
            } else if (page === 'monitoring' && pathParts[1] && pathParts[2] && pathParts[3]) {
              params.projectId = parseInt(pathParts[1], 10);
              params.sceneId = parseInt(pathParts[2], 10);
              params.angleId = parseInt(pathParts[3], 10);
              if (pathParts[4]) {
                params.takeId = parseInt(pathParts[4], 10);
              }
            }
            
            // Merge with state data (like projectName, sceneName, etc.)
            if (current.state && typeof current.state === 'object') {
              Object.assign(params, current.state);
            }
            
            return { page, params, path };
          }
          
          // Default location if no history
          return { page: 'home', params: {}, path: '/' };
        },
        
        confirm: (options) => {
          return new Promise((resolve) => {
            set((state) => {
              state.modals.confirm = {
                isOpen: true,
                data: {
                  ...options,
                  onConfirm: () => {
                    set((state) => {
                      state.modals.confirm = { isOpen: false, data: null };
                    });
                    resolve(true);
                  },
                  onCancel: () => {
                    set((state) => {
                      state.modals.confirm = { isOpen: false, data: null };
                    });
                    resolve(false);
                  }
                }
              };
            });
          });
        },
        
        registerGuard: (id, guardFn) => {
          if (typeof guardFn !== 'function') {
            console.error(`Guard ${id} must be a function`);
            return () => {};
          }
          
          // Check if already registered
          const existingGuard = get().guards.get(id);
          if (existingGuard) {
            console.warn(`Guard ${id} is already registered, replacing...`);
          }
          
          // Use a new Map to avoid immer issues
          set((state) => {
            const newGuards = new Map(state.guards);
            newGuards.set(id, guardFn);
            state.guards = newGuards;
          });
          
          // Return unregister function
          let isUnregistered = false;
          return () => {
            if (isUnregistered) return; // Prevent double unregister
            isUnregistered = true;
            
            // Use a new Map to avoid immer issues
            set((state) => {
              const newGuards = new Map(state.guards);
              newGuards.delete(id);
              state.guards = newGuards;
            });
          };
        },
        
        unregisterGuard: (id) => set((state) => {
          const newGuards = new Map(state.guards);
          newGuards.delete(id);
          state.guards = newGuards;
        }),
        
        // Session Actions
        login: (user) => set((state) => {
          state.user = user;
          state.isAuthenticated = true;
        }),
        
        logout: () => set((state) => {
          state.user = null;
          state.isAuthenticated = false;
          state.recentProjects = [];
          state.recentScenes = [];
        }),
        
        updateConnectionStatus: (service, status) => set((state) => {
          state.connectionStatus[service] = status;
        }),
        
        updateServerInfo: (info) => set((state) => {
          state.serverInfo = { ...state.serverInfo, ...info };
        }),
        
        addRecentProject: (project) => set((state) => {
          const filtered = state.recentProjects.filter(p => p.id !== project.id);
          state.recentProjects = [project, ...filtered].slice(0, state.preferences.maxRecentProjects);
        }),
        
        addRecentScene: (scene) => set((state) => {
          const filtered = state.recentScenes.filter(s => s.id !== scene.id);
          state.recentScenes = [scene, ...filtered].slice(0, state.preferences.maxRecentScenes);
        }),
        
        // Preference Actions
        updatePreferences: (updates) => set((state) => {
          state.preferences = { ...state.preferences, ...updates };
        }),
        
        resetPreferences: () => set((state) => {
          state.preferences = defaultPreferences;
        }),
        
        // Utility Actions
        getModalState: (modalName) => {
          const state = get();
          return state.modals[modalName] || { isOpen: false, data: null };
        },
        
        isAnyModalOpen: () => {
          const state = get();
          return Object.values(state.modals).some(modal => modal.isOpen);
        },
        
        hasNotifications: () => {
          const state = get();
          return state.notifications.length > 0;
        },
        
        getUnreadNotificationCount: () => {
          const state = get();
          return state.notifications.filter(n => !n.read).length;
        },
        
        markNotificationRead: (id) => set((state) => {
          const notification = state.notifications.find(n => n.id === id);
          if (notification) {
            notification.read = true;
          }
        }),
        
        // Reset
        reset: () => set((state) => {
          // Reset UI state
          Object.keys(state.modals).forEach(modalName => {
            state.modals[modalName] = { isOpen: false, data: null };
          });
          state.notifications = [];
          state.notificationIdCounter = 0;
          state.globalLoading = false;
          state.globalError = null;
          
          // Reset navigation state
          state.history = [];
          state.currentIndex = -1;
          state.guards.clear();
          state.pendingNavigation = null;
          state.refreshHandlers.clear();
          state.pageRefreshFunctions.clear();
          state.isRefreshing = false;
          
          // Reset session state
          state.user = null;
          state.isAuthenticated = false;
          state.recentProjects = [];
          state.recentScenes = [];
          state.connectionStatus = {
            websocket: 'disconnected',
            api: 'unknown'
          };
          state.serverInfo = {
            resources: {
              cpu: 0,
              memory: 0,
              gpuAvailable: false
            },
            warnings: []
          };
          
          // Keep preferences
        })
      })),
      {
        name: STORE_NAME
      }
    )
  )
);

// Store persistence is handled by the persist middleware in persist.js
// To enable persistence, wrap the store creation with createPersistedStore

// Browser history integration
if (typeof window !== 'undefined') {
  window.addEventListener('popstate', (event) => {
    const state = useAppStore.getState();
    const targetIndex = event.state?.index ?? 0;
    
    if (targetIndex !== state.currentIndex) {
      useAppStore.setState({ currentIndex: targetIndex });
    }
  });
}

export default useAppStore;
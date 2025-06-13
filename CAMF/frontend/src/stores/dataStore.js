import { create } from 'zustand';
import { devtools, subscribeWithSelector } from 'zustand/middleware';
import { immer } from 'zustand/middleware/immer';
import { enableMapSet } from 'immer';
import useProcessingStore from './processingStore';

// Enable MapSet support for Immer
enableMapSet();

const useDataStore = create(
  subscribeWithSelector(
    devtools(
      immer((set, get) => ({
        // ========== PROJECT HIERARCHY (from projectStore) ==========
        // Current context
        currentProject: null,
        currentScene: null,
        currentAngle: null,
        currentTake: null,
        
        // Cached data
        projects: [],
        scenes: new Map(), // projectId -> scenes[]
        angles: new Map(), // sceneId -> angles[]
        takes: new Map(), // angleId -> takes[]
        
        // Loading states
        loadingStates: {
          projects: false,
          scenes: false,
          angles: false,
          takes: false
        },
        
        // ========== CAPTURE & FRAME MANAGEMENT (from captureStore) ==========
        // Source management
        source: null,
        availableSources: {
          cameras: [],
          monitors: [],
          windows: []
        },
        
        // Capture state
        isCapturing: false,
        captureSession: null,
        captureProgress: {
          capturedFrames: 0,
          processedFrames: 0,
          duration: '00:00',
          isComplete: false,
          frameRate: 0,
          startTime: null
        },
        
        // Preview state
        isPreviewActive: false,
        previewFrame: null,
        previewError: null,
        
        // Source validation
        sourceStatus: {
          isConnected: false,
          lastChecked: null,
          error: null
        },
        
        // Frame management
        frameCount: 0,
        currentFrameIndex: 0,
        latestFrameIndex: 0,
        currentFrame: null,
        referenceFrame: null,
        isNavigatingManually: false,
        hasProcessedFrames: false,
        
        // Detector error management
        detectorErrors: [],
        
        // Processing state
        isProcessing: false,
        isRedoingDetection: false,
        
        // ========== PROJECT ACTIONS ==========
        setCurrentContext: (context) => set((state) => {
          state.currentProject = context.project || state.currentProject;
          state.currentScene = context.scene || state.currentScene;
          state.currentAngle = context.angle || state.currentAngle;
          state.currentTake = context.take || state.currentTake;
        }),
        
        setProjects: (projects) => set((state) => {
          state.projects = projects;
        }),
        
        setScenesForProject: (projectId, scenes) => set((state) => {
          state.scenes.set(projectId, scenes);
        }),
        
        setAnglesForScene: (sceneId, angles) => set((state) => {
          state.angles.set(sceneId, angles);
        }),
        
        setTakesForAngle: (angleId, takes) => set((state) => {
          state.takes.set(angleId, takes);
        }),
        
        setLoadingState: (key, loading) => set((state) => {
          state.loadingStates[key] = loading;
        }),
        
        // CRUD operations
        addProject: (project) => set((state) => {
          state.projects.push(project);
        }),
        
        updateProject: (projectId, updates) => set((state) => {
          const index = state.projects.findIndex(p => p.id === projectId);
          if (index !== -1) {
            Object.assign(state.projects[index], updates);
          }
        }),
        
        removeProject: (projectId) => set((state) => {
          // Remove project
          state.projects = state.projects.filter(p => p.id !== projectId);
          
          // Clean up associated data
          const scenesToRemove = state.scenes.get(projectId) || [];
          scenesToRemove.forEach(scene => {
            const anglesToRemove = state.angles.get(scene.id) || [];
            anglesToRemove.forEach(angle => {
              state.takes.delete(angle.id);
            });
            state.angles.delete(scene.id);
          });
          state.scenes.delete(projectId);
        }),
        
        // Scene operations
        addScene: (projectId, scene) => set((state) => {
          const projectScenes = state.scenes.get(projectId) || [];
          state.scenes.set(projectId, [...projectScenes, scene]);
        }),
        
        updateScene: (sceneId, updates) => set((state) => {
          // Find and update scene in all projects
          for (const [projectId, scenes] of state.scenes.entries()) {
            const sceneIndex = scenes.findIndex(s => s.id === sceneId);
            if (sceneIndex !== -1) {
              Object.assign(scenes[sceneIndex], updates);
            }
          }
        }),
        
        // Computed values
        getCurrentProjectScenes: () => {
          const state = get();
          return state.currentProject 
            ? state.scenes.get(state.currentProject.id) || []
            : [];
        },
        
        getCurrentSceneAngles: () => {
          const state = get();
          return state.currentScene
            ? state.angles.get(state.currentScene.id) || []
            : [];
        },
        
        getCurrentAngleTakes: () => {
          const state = get();
          return state.currentAngle
            ? state.takes.get(state.currentAngle.id) || []
            : [];
        },
        
        getReferenceTakeForAngle: (angleId) => {
          const state = get();
          const takes = state.takes.get(angleId) || [];
          return takes.find(t => t.is_reference);
        },
        
        // WebSocket event handlers for takes
        updateTakeStatus: (takeId, status) => set((state) => {
          // Find and update take in all angles
          for (const [angleId, takes] of state.takes.entries()) {
            const takeIndex = takes.findIndex(t => t.id === takeId);
            if (takeIndex !== -1) {
              takes[takeIndex].status = status;
            }
          }
          
          // Update current take if it matches
          if (state.currentTake?.id === takeId) {
            state.currentTake.status = status;
          }
        }),
        
        updateTakeFrameCount: (takeId, frameCount) => set((state) => {
          // Find and update take in all angles
          for (const [angleId, takes] of state.takes.entries()) {
            const takeIndex = takes.findIndex(t => t.id === takeId);
            if (takeIndex !== -1) {
              takes[takeIndex].frame_count = frameCount;
            }
          }
          
          // Update current take if it matches
          if (state.currentTake?.id === takeId) {
            state.currentTake.frame_count = frameCount;
          }
        }),
        
        updateTakeProcessingResults: (takeId, results) => set((state) => {
          const processedAt = new Date().toISOString();
          
          // Find and update take in all angles
          for (const [angleId, takes] of state.takes.entries()) {
            const takeIndex = takes.findIndex(t => t.id === takeId);
            if (takeIndex !== -1) {
              takes[takeIndex].processing_results = results;
              takes[takeIndex].processed_at = processedAt;
            }
          }
          
          // Update current take if it matches
          if (state.currentTake?.id === takeId) {
            state.currentTake.processing_results = results;
            state.currentTake.processed_at = processedAt;
          }
        }),
        
        // ========== CAPTURE ACTIONS ==========
        setSource: (source) => set((state) => {
          console.log('[dataStore.setSource] Setting source:', source);
          state.source = source;
          state.previewError = null;
          state.sourceStatus.isConnected = !!source;
          console.log('[dataStore.setSource] Current preview frame:', state.previewFrame ? 'exists' : 'null');
        }),
        
        clearSource: () => set((state) => {
          state.source = null;
          state.previewFrame = null;
          state.previewError = null;
          state.sourceStatus.isConnected = false;
          state.isPreviewActive = false;
        }),
        
        updateAvailableSources: (sources) => set((state) => {
          state.availableSources = sources;
        }),
        
        // Enhanced capture actions
        startCapture: async (takeId, options = {}) => {
          const state = get();
          
          if (state.isCapturing) {
            throw new Error('Capture already in progress');
          }
          
          if (!state.source) {
            throw new Error('No capture source selected');
          }
          
          // Don't clear frame cache - let the forceReload flag handle cache updates
          // This prevents blob URLs from being revoked unnecessarily
          
          set((state) => {
            state.isCapturing = true;
            state.isPreviewActive = false;
            // Don't clear preview frame - keep showing it until first frame is captured
            // Don't clear current frame either - keep it visible during transition
            state.frameCount = 0; // Reset frame count
            state.currentFrameIndex = 0; // Reset frame index
            state.latestFrameIndex = 0;
            state.captureSession = {
              takeId,
              startTime: Date.now(),
              frameRate: options.frameRate || 24,
              referenceFrameCount: options.frame_count_limit
            };
            state.captureProgress = {
              capturedFrames: 0,
              processedFrames: 0,
              duration: '00:00',
              isComplete: false,
              frameRate: options.frameRate || 24,
              startTime: Date.now()
            };
          });
          
          // Add to active processes in processing store
          useProcessingStore.getState().addActiveProcess({
            id: `capture-${takeId}`,
            type: 'capture',
            name: 'Video Capture',
            takeId
          });
        },
        
        stopCapture: () => set((state) => {
          state.isCapturing = false;
          state.captureProgress.isComplete = true;
          
          // Don't clear current frame - let frame sync handle the reload
          // This prevents the "blink" when recording stops
          
          // Remove from active processes
          if (state.captureSession?.takeId) {
            useProcessingStore.getState().removeActiveProcess(`capture-${state.captureSession.takeId}`);
          }
        }),
        
        updateCaptureProgress: (progress) => set((state) => {
          Object.assign(state.captureProgress, progress);
          
          // Calculate duration
          if (state.captureProgress.startTime) {
            const elapsed = Date.now() - state.captureProgress.startTime;
            const seconds = Math.floor(elapsed / 1000);
            const minutes = Math.floor(seconds / 60);
            const displaySeconds = seconds % 60;
            state.captureProgress.duration = 
              `${minutes.toString().padStart(2, '0')}:${displaySeconds.toString().padStart(2, '0')}`;
          }
        }),
        
        // Preview actions
        setPreviewActive: (active) => set((state) => {
          state.isPreviewActive = active;
          if (!active) {
            state.previewError = null;
          }
        }),
        
        updatePreviewFrame: (frame) => set((state) => {
          console.log('dataStore.updatePreviewFrame called:', {
            hasFrame: !!frame,
            frameLength: frame ? frame.length : 0,
            frameType: frame ? typeof frame : 'null',
            framePrefix: frame ? frame.substring(0, 50) : 'null',
            previousFrame: !!state.previewFrame
          });
          // Only update if actually changing
          if (frame !== state.previewFrame) {
            state.previewFrame = frame;
            state.previewError = null;
          }
        }),
        
        setPreviewError: (error) => set((state) => {
          state.previewError = error;
          state.previewFrame = null;
        }),
        
        // Source status
        updateSourceStatus: (status) => set((state) => {
          Object.assign(state.sourceStatus, {
            ...status,
            lastChecked: Date.now()
          });
        }),
        
        // WebSocket event handlers
        setCaptureError: (error) => set((state) => {
          state.isCapturing = false;
          state.captureProgress.error = error;
          state.sourceStatus.error = error;
        }),
        
        setCurrentFrame: (frameIndex) => set((state) => {
          state.captureProgress.capturedFrames = frameIndex + 1;
        }),
        
        updatePreview: (preview) => set((state) => {
          if (state.isPreviewActive) {
            state.previewFrame = preview;
          }
        }),
        
        setSourceDisconnected: (disconnected) => set((state) => {
          if (disconnected) {
            state.sourceStatus.isConnected = false;
            state.sourceStatus.error = 'Source disconnected';
            if (state.isCapturing) {
              state.isCapturing = false;
              state.captureProgress.isComplete = true;
            }
          }
        }),
        
        pauseCapture: () => set((state) => {
          if (state.isCapturing && state.captureSession) {
            state.captureSession.paused = true;
          }
        }),
        
        // Frame navigation
        setCurrentFrameIndex: (index) => set((state) => {
          const clampedIndex = Math.max(0, Math.min(index, state.frameCount - 1));
          state.currentFrameIndex = clampedIndex;
          state.isNavigatingManually = clampedIndex !== state.latestFrameIndex;
        }),
        
        navigateFrame: (direction) => set((state) => {
          const { currentFrameIndex, frameCount } = state;
          let newIndex = currentFrameIndex;
          
          switch (direction) {
            case 'first':
              newIndex = 0;
              break;
            case 'prev':
              newIndex = Math.max(0, currentFrameIndex - 1);
              break;
            case 'next':
              newIndex = Math.min(frameCount - 1, currentFrameIndex + 1);
              break;
            case 'last':
              newIndex = frameCount - 1;
              break;
            default:
              return;
          }
          
          state.currentFrameIndex = newIndex;
          state.isNavigatingManually = newIndex !== state.latestFrameIndex;
        }),
        
        returnToLatest: () => set((state) => {
          state.currentFrameIndex = state.latestFrameIndex;
          state.isNavigatingManually = false;
        }),
        
        updateFrameCount: (count) => set((state) => {
          state.frameCount = count;
          if (count > 0 && !state.isNavigatingManually) {
            state.latestFrameIndex = count - 1;
            state.currentFrameIndex = count - 1;
          }
        }),
        
        setLatestFrameIndex: (index) => set((state) => {
          state.latestFrameIndex = index;
          if (!state.isNavigatingManually) {
            state.currentFrameIndex = index;
          }
        }),
        
        setTotalFrames: (count) => set((state) => {
          state.frameCount = count;
          if (!state.isNavigatingManually) {
            state.latestFrameIndex = Math.max(0, count - 1);
            state.currentFrameIndex = Math.max(0, count - 1);
          }
        }),
        
        updateCurrentFrame: (frame) => set((state) => {
          state.currentFrame = frame;
        }),
        
        updateReferenceFrame: (frame) => set((state) => {
          state.referenceFrame = frame;
        }),
        
        clearReferenceFrame: () => set((state) => {
          state.referenceFrame = null;
        }),
        
        setReferenceTake: (takeId, frameCount) => set((state) => {
          state.referenceTakeId = takeId;
          state.referenceFrameCount = frameCount;
        }),
        
        setHasProcessedFrames: (hasProcessed) => set((state) => {
          state.hasProcessedFrames = hasProcessed;
        }),
        
        // Detector error management
        updateDetectorErrors: (errors) => set((state) => {
          state.detectorErrors = errors;
        }),
        
        clearDetectorErrors: () => set((state) => {
          state.detectorErrors = [];
        }),
        
        // Frame result management (placeholders for SSE compatibility)
        updateFrameResults: (takeId, frameIndex, results) => {
          // Placeholder - frame results are currently handled differently
          console.log('[dataStore] updateFrameResults called:', { takeId, frameIndex, results });
        },
        
        markFrameProcessed: (takeId, frameIndex) => {
          // Placeholder - frame processing status handled elsewhere
          console.log('[dataStore] markFrameProcessed called:', { takeId, frameIndex });
        },
        
        removeFrameFromCache: (takeId, frameIndex) => {
          // Placeholder - frame cache managed elsewhere
          console.log('[dataStore] removeFrameFromCache called:', { takeId, frameIndex });
        },
        
        // Processing state
        startRedoDetection: () => set((state) => {
          state.isRedoingDetection = true;
          state.isProcessing = true;
          state.detectorErrors = [];
        }),
        
        stopProcessing: () => set((state) => {
          state.isProcessing = false;
          state.isRedoingDetection = false;
        }),
        
        completeRedoDetection: () => set((state) => {
          state.isRedoingDetection = false;
          state.isProcessing = false;
        }),
        
        // ========== COMPUTED VALUES ==========
        canNavigate: () => {
          const state = get();
          return !state.isCapturing;
        },
        
        requiresCleanup: () => {
          const state = get();
          return state.captureSession !== null && !state.captureProgress.isComplete;
        },
        
        getCaptureStatus: () => {
          const state = get();
          return {
            isActive: state.isCapturing,
            progress: state.captureProgress,
            session: state.captureSession
          };
        },
        
        // ========== RESET ACTIONS ==========
        resetCaptureState: () => set((state) => {
          state.isCapturing = false;
          state.captureSession = null;
          state.captureProgress = {
            capturedFrames: 0,
            processedFrames: 0,
            duration: '00:00',
            isComplete: false,
            frameRate: 0,
            startTime: null
          };
          // Reset frame state
          state.frameCount = 0;
          state.currentFrameIndex = 0;
          state.latestFrameIndex = 0;
          state.currentFrame = null;
          state.referenceFrame = null;
          state.isNavigatingManually = false;
        }),
        
        resetProjectState: () => set((state) => {
          state.currentProject = null;
          state.currentScene = null;
          state.currentAngle = null;
          state.currentTake = null;
          state.projects = [];
          state.scenes.clear();
          state.angles.clear();
          state.takes.clear();
          state.loadingStates = {
            projects: false,
            scenes: false,
            angles: false,
            takes: false
          };
        }),
        
        reset: () => {
          get().resetCaptureState();
          get().resetProjectState();
        }
      })),
      {
        name: 'data-store'
      }
    )
  )
);

export default useDataStore;
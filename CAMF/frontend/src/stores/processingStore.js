import { create } from 'zustand';
import { devtools, subscribeWithSelector } from 'zustand/middleware';
import { immer } from 'zustand/middleware/immer';
import { enableMapSet } from 'immer';

// Enable MapSet support for Immer
enableMapSet();

const useProcessingStore = create(
  subscribeWithSelector(
    devtools(
      immer((set, get) => ({
        // Processing state
        isProcessing: false,
        isRedoingDetection: false,
        processingSession: null,
        processingQueue: [],
        activeProcesses: [], // Array of active process objects
        
        // Progress tracking
        processingProgress: {
          currentFrame: 0,
          totalFrames: 0,
          processedFrames: 0,
          failedFrames: 0,
          detectorProgress: {}
        },
        
        // Error tracking
        processingErrors: [],
        detectorErrors: new Map(), // frameId -> errors[]
        
        // Actions
        startProcessing: (takeId, options = {}) => set((state) => {
          state.isProcessing = true;
          state.isRedoingDetection = options.isRedo || false;
          state.processingSession = {
            takeId,
            startTime: Date.now(),
            referenceTakeId: options.referenceTakeId,
            detectors: options.detectors || []
          };
          state.processingProgress = {
            currentFrame: 0,
            totalFrames: options.totalFrames || 0,
            processedFrames: 0,
            failedFrames: 0,
            detectorProgress: {}
          };
          
          // Add to active processes
          state.activeProcesses.push({
            id: `processing-${takeId}`,
            type: 'processing',
            name: options.isRedo ? 'Re-detection' : 'Detection',
            takeId,
            startTime: Date.now()
          });
          
          if (state.isRedoingDetection) {
            state.detectorErrors.clear();
            state.processingErrors = [];
          }
        }),
        
        addActiveProcess: (process) => set((state) => {
          state.activeProcesses.push({
            id: process.id || `process-${Date.now()}`,
            startTime: Date.now(),
            ...process
          });
        }),
        
        removeActiveProcess: (processId) => set((state) => {
          state.activeProcesses = state.activeProcesses.filter(p => p.id !== processId);
        }),
        
        clearActiveProcesses: () => set((state) => {
          state.activeProcesses = [];
        }),
        
        stopProcessing: () => set((state) => {
          state.isProcessing = false;
          state.isRedoingDetection = false;
          if (state.processingSession) {
            state.processingSession.endTime = Date.now();
            // Remove from active processes
            state.activeProcesses = state.activeProcesses.filter(
              p => p.id !== `processing-${state.processingSession.takeId}`
            );
          }
        }),
        
        updateProcessingProgress: (progress) => set((state) => {
          Object.assign(state.processingProgress, progress);
        }),
        
        addProcessingError: (error) => set((state) => {
          state.processingErrors.push({
            ...error,
            timestamp: Date.now()
          });
        }),
        
        addDetectorError: (frameId, error) => set((state) => {
          if (!state.detectorErrors.has(frameId)) {
            state.detectorErrors.set(frameId, []);
          }
          state.detectorErrors.get(frameId).push(error);
        }),
        
        clearDetectorErrors: () => set((state) => {
          state.detectorErrors.clear();
          state.processingErrors = [];
        }),
        
        // WebSocket event handlers
        completeProcessing: (takeId) => set((state) => {
          if (state.processingSession?.takeId === takeId) {
            state.isProcessing = false;
            state.isRedoingDetection = false;
            state.processingSession.endTime = Date.now();
            
            // IMPORTANT: Remove from active processes
            state.activeProcesses = state.activeProcesses.filter(
              p => p.id !== `processing-${takeId}`
            );
          }
        }),
        
        updateDetectorProgress: (detector, progress) => set((state) => {
          state.processingProgress.detectorProgress[detector] = progress;
        }),
        
        updateDetectorResults: (detectorId, results) => set((state) => {
          if (!state.processingSession) return;
          
          if (!state.processingSession.results) {
            state.processingSession.results = {};
          }
          
          state.processingSession.results[detectorId] = results;
        }),
        
        // Computed values
        getProcessingStatus: () => {
          const state = get();
          return {
            isActive: state.isProcessing,
            isRedo: state.isRedoingDetection,
            progress: state.processingProgress,
            session: state.processingSession
          };
        },
        
        getErrorsForFrame: (frameId) => {
          const state = get();
          return state.detectorErrors.get(frameId) || [];
        },
        
        getTotalErrors: () => {
          const state = get();
          let total = 0;
          state.detectorErrors.forEach(errors => {
            total += errors.length;
          });
          return total;
        },
        
        canNavigate: () => {
          const state = get();
          return !state.isProcessing;
        },
        
        // Reset
        resetProcessingState: () => set((state) => {
          state.isProcessing = false;
          state.isRedoingDetection = false;
          state.processingSession = null;
          state.processingProgress = {
            currentFrame: 0,
            totalFrames: 0,
            processedFrames: 0,
            failedFrames: 0,
            detectorProgress: {}
          };
        })
      })),
      {
        name: 'processing-store'
      }
    )
  )
);

export default useProcessingStore;
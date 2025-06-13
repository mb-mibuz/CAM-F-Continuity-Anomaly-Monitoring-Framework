// Project hooks
export {
  useProjects,
  useProject,
  useCreateProject,
  useUpdateProject,
  useDeleteProject
} from './useProjects';

// Scene hooks
export {
  useScenes,
  useScene,
  useSceneWithAngles,
  useCreateScene,
  useUpdateScene,
  useDeleteScene
} from './useScenes';

// Angle hooks
export {
  useAngles,
  useCreateAngle,
  useUpdateAngle
} from './useAngles';

// Take hooks
export {
  useTakes,
  useTake,
  useTakeWithDetails,
  useCreateTake,
  useUpdateTake,
  useDeleteTake,
  useSetReferenceTake,
  useReferenceTake,
  useClearTakeData
} from './useTakes';

// Capture hooks
export {
  useCaptureSources,
  useCameras,
  useMonitors,
  useWindows
} from './useCaptureSources';

export {
  useStartCapture,
  useStopCapture,
  useCaptureStatus,
  useCaptureProgress
} from './useCaptureOperations';

// Detector hooks
export {
  useDetectors,
  useInstalledDetectors,
  useDetectorSchema,
  useSceneDetectorConfigs,
  useSaveDetectorConfig,
  useInstallDetector,
  useUninstallDetector
} from './useDetectors';

// Processing hooks
export {
  useProcessingStatus,
  useProcessingStatusForTake,
  useStartProcessing,
  useStopProcessing,
  useRestartProcessing
} from './useProcessing';

// Frame hooks
export {
  useFrameCount,
  useFrameWithBoundingBoxes,
  useTakeErrors,
  useContinuousErrors
} from './useFrames';

// Export hooks
export {
  useExportProject,
  useExportScene,
  useExportTake
} from './useExport';

// Custom capture hook
export { useCapture } from './useCapture';
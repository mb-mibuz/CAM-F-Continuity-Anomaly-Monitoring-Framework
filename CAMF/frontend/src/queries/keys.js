/**
 * Query key factory for consistent key generation
 */
export const queryKeys = {
  all: ['camf'],
  
  projects: {
    all: () => [...queryKeys.all, 'projects'],
    list: (filters) => [...queryKeys.projects.all(), 'list', filters],
    detail: (id) => [...queryKeys.projects.all(), 'detail', id],
    location: (id) => [...queryKeys.projects.all(), 'location', id]
  },
  
  scenes: {
    all: () => [...queryKeys.all, 'scenes'],
    byProject: (projectId) => [...queryKeys.scenes.all(), 'project', projectId],
    detail: (id) => [...queryKeys.scenes.all(), 'detail', id],
    detectorConfigs: (id) => [...queryKeys.scenes.all(), 'detector-configs', id],
    size: (id) => [...queryKeys.scenes.all(), 'size', id]
  },
  
  angles: {
    all: () => [...queryKeys.all, 'angles'],
    byScene: (sceneId) => [...queryKeys.angles.all(), 'scene', sceneId],
    detail: (id) => [...queryKeys.angles.all(), 'detail', id],
    referenceTake: (id) => [...queryKeys.angles.all(), 'reference', id]
  },
  
  takes: {
    all: () => [...queryKeys.all, 'takes'],
    byAngle: (angleId) => [...queryKeys.takes.all(), 'angle', angleId],
    detail: (id) => [...queryKeys.takes.all(), 'detail', id],
    errors: (id, params) => [...queryKeys.takes.all(), 'errors', id, params],
    continuousErrors: (id) => [...queryKeys.takes.all(), 'continuous-errors', id],
    size: (id) => [...queryKeys.takes.all(), 'size', id]
  },
  
  frames: {
    all: () => [...queryKeys.all, 'frames'],
    byTake: (takeId) => [...queryKeys.frames.all(), 'take', takeId],
    count: (takeId) => [...queryKeys.frames.byTake(takeId), 'count'],
    single: (takeId, frameId) => [...queryKeys.frames.byTake(takeId), 'frame', frameId],
    withBoundingBoxes: (takeId, frameId) => [...queryKeys.frames.single(takeId, frameId), 'bounding-boxes']
  },
  
  capture: {
    all: () => [...queryKeys.all, 'capture'],
    status: () => [...queryKeys.capture.all(), 'status'],
    detailedStatus: (takeId) => [...queryKeys.capture.all(), 'detailed-status', takeId],
    progress: (takeId) => [...queryKeys.capture.all(), 'progress', takeId],
    sources: {
      all: () => [...queryKeys.capture.all(), 'sources'],
      cameras: () => [...queryKeys.capture.sources.all(), 'cameras'],
      monitors: () => [...queryKeys.capture.sources.all(), 'monitors'],
      windows: () => [...queryKeys.capture.sources.all(), 'windows']
    }
  },
  
  detectors: {
    all: () => [...queryKeys.all, 'detectors'],
    list: () => [...queryKeys.detectors.all(), 'list'],
    installed: () => [...queryKeys.detectors.all(), 'installed'],
    schema: (name) => [...queryKeys.detectors.all(), 'schema', name]
  },
  
  processing: {
    all: () => [...queryKeys.all, 'processing'],
    status: () => [...queryKeys.processing.all(), 'status'],
    statusForTake: (takeId) => [...queryKeys.processing.all(), 'status', takeId]
  }
};
import { queryClient } from './queryClient';
import { queryKeys } from './keys';
import { api } from '../utils/api';

/**
 * Prefetch data for better UX
 */
export const prefetch = {
  projects: async () => {
    await queryClient.prefetchQuery({
      queryKey: queryKeys.projects.all(),
      queryFn: () => api.getProjects('created_at', 'desc')
    });
  },
  
  scenesForProject: async (projectId) => {
    await queryClient.prefetchQuery({
      queryKey: queryKeys.scenes.byProject(projectId),
      queryFn: () => api.getScenes(projectId)
    });
  },
  
  anglesForScene: async (sceneId) => {
    await queryClient.prefetchQuery({
      queryKey: queryKeys.angles.byScene(sceneId),
      queryFn: () => api.getAngles(sceneId)
    });
  },
  
  takesForAngle: async (angleId) => {
    await queryClient.prefetchQuery({
      queryKey: queryKeys.takes.byAngle(angleId),
      queryFn: () => api.getTakes(angleId)
    });
  },
  
  detectors: async () => {
    await queryClient.prefetchQuery({
      queryKey: queryKeys.detectors.list(),
      queryFn: api.getDetectors
    });
  }
};
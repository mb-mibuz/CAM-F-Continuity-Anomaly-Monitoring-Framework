import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../../utils/api';
import { queryKeys } from '../keys';
import { useAppStore } from '../../stores';

export function useScenes(projectId) {
  return useQuery({
    queryKey: queryKeys.scenes.byProject(projectId),
    queryFn: () => api.getScenes(projectId),
    enabled: !!projectId,
    select: (data) => {
      // Ensure we always return an array
      if (Array.isArray(data)) return data;
      if (data?.scenes) return data.scenes;
      return [];
    }
  });
}

export function useScene(sceneId) {
  return useQuery({
    queryKey: queryKeys.scenes.detail(sceneId),
    queryFn: () => api.getScene(sceneId),
    enabled: !!sceneId
  });
}

export function useUpdateScene() {
  const queryClient = useQueryClient();
  const addNotification = useAppStore(state => state.addNotification);
  
  return useMutation({
    mutationFn: ({ sceneId, data }) => api.updateScene(sceneId, data),
    onSuccess: (data, variables) => {
      queryClient.setQueryData(queryKeys.scenes.detail(variables.sceneId), data);
      queryClient.invalidateQueries({ queryKey: queryKeys.scenes.all() });
      addNotification({ type: 'success', message: 'Scene updated successfully' });
    },
    onError: (error) => {
      addNotification({ type: 'error', message: `Failed to update scene: ${error.message}` });
    }
  });
}

export function useDeleteScene() {
  const queryClient = useQueryClient();
  const addNotification = useAppStore(state => state.addNotification);
  
  return useMutation({
    mutationFn: (sceneId) => api.deleteScene(sceneId),
    onSuccess: (_, sceneId) => {
      queryClient.removeQueries({ queryKey: queryKeys.scenes.detail(sceneId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.scenes.all() });
      addNotification({ type: 'success', message: 'Scene deleted successfully' });
    },
    onError: (error) => {
      addNotification({ type: 'error', message: `Failed to delete scene: ${error.message}` });
    }
  });
}

export function useSceneWithAngles(sceneId) {
  const queryClient = useQueryClient();
  
  return useQuery({
    queryKey: [...queryKeys.scenes.detail(sceneId), 'with-angles'],
    queryFn: async () => {
      const [scene, angles] = await Promise.all([
        api.getScene(sceneId),
        api.getAngles(sceneId)
      ]);
      
      // Load takes count for each angle
      const anglesWithInfo = await Promise.all(angles.map(async (angle) => {
        const takes = await api.getTakes(angle.id);
        return {
          ...angle,
          takes,
          takes_count: takes.length
        };
      }));
      
      return {
        ...scene,
        angles: anglesWithInfo
      };
    },
    enabled: !!sceneId
  });
}

export function useCreateScene() {
  const queryClient = useQueryClient();
  const addNotification = useAppStore(state => state.addNotification);
  
  return useMutation({
    mutationFn: (sceneData) => api.createScene(sceneData),
    onSuccess: (data, variables) => {
      // Invalidate scenes list for the project
      queryClient.invalidateQueries({ 
        queryKey: queryKeys.scenes.byProject(variables.projectId || variables.project_id) 
      });
      addNotification({ type: 'success', message: 'Scene created successfully' });
    },
    onError: (error) => {
      addNotification({ type: 'error', message: `Failed to create scene: ${error.message}` });
    }
  });
}
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../../utils/api';
import { queryKeys } from '../keys';
import { useAppStore } from '../../stores';

export function useAngles(sceneId) {
  return useQuery({
    queryKey: queryKeys.angles.byScene(sceneId),
    queryFn: () => api.getAngles(sceneId),
    enabled: !!sceneId
  });
}

export function useCreateAngle() {
  const queryClient = useQueryClient();
  const addNotification = useAppStore(state => state.addNotification);
  
  return useMutation({
    mutationFn: (angleData) => api.createAngle(angleData),
    onSuccess: (data, variables) => {
      // Invalidate angles list for the scene
      queryClient.invalidateQueries({ 
        queryKey: queryKeys.angles.byScene(variables.sceneId || variables.scene_id) 
      });
      addNotification({ type: 'success', message: 'Angle created successfully' });
    },
    onError: (error) => {
      addNotification({ type: 'error', message: `Failed to create angle: ${error.message}` });
    }
  });
}

export function useUpdateAngle() {
  const queryClient = useQueryClient();
  const addNotification = useAppStore(state => state.addNotification);
  
  return useMutation({
    mutationFn: ({ angleId, data }) => api.updateAngle(angleId, data),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.angles.all() });
      addNotification({ type: 'success', message: 'Angle updated successfully' });
    },
    onError: (error) => {
      addNotification({ type: 'error', message: `Failed to update angle: ${error.message}` });
    }
  });
}
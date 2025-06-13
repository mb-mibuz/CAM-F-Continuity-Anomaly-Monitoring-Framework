import { useMutation } from '@tanstack/react-query';
import { api } from '../../utils/api';
import { useAppStore } from '../../stores';

export function useExportProject() {
  const addNotification = useAppStore(state => state.addNotification);
  
  return useMutation({
    mutationFn: ({ projectId }) => api.exportProject(projectId),
    onSuccess: () => {
      addNotification({ type: 'success', message: 'Project exported successfully' });
    },
    onError: (error) => {
      addNotification({ type: 'error', message: `Failed to export project: ${error.message}` });
    }
  });
}

export function useExportScene() {
  const addNotification = useAppStore(state => state.addNotification);
  
  return useMutation({
    mutationFn: ({ sceneId, options = {} }) => api.exportScene(sceneId, options),
    onSuccess: () => {
      addNotification({ type: 'success', message: 'Scene exported successfully' });
    },
    onError: (error) => {
      addNotification({ type: 'error', message: `Failed to export scene: ${error.message}` });
    }
  });
}

export function useExportTake() {
  const addNotification = useAppStore(state => state.addNotification);
  
  return useMutation({
    mutationFn: ({ takeId, options = {} }) => api.exportTake(takeId, options),
    onSuccess: () => {
      addNotification({ type: 'success', message: 'Take exported successfully' });
    },
    onError: (error) => {
      addNotification({ type: 'error', message: `Failed to export take: ${error.message}` });
    }
  });
}
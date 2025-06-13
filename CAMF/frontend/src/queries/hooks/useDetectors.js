import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../../utils/api';
import { queryKeys } from '../keys';
import { useAppStore } from '../../stores';
import { buildApiUrl } from '../../config';

export function useDetectors() {
  return useQuery({
    queryKey: queryKeys.detectors.list(),
    queryFn: api.getDetectors,
    select: (data) => {
      if (Array.isArray(data)) return data;
      if (data?.detectors) return data.detectors;
      return [];
    }
  });
}

export function useInstalledDetectors() {
  return useQuery({
    queryKey: queryKeys.detectors.installed(),
    queryFn: async () => {
      const response = await fetch(buildApiUrl('api/detectors/installed'));
      if (!response.ok) throw new Error('Failed to fetch installed detectors');
      const data = await response.json();
      console.log('Installed detectors data:', data); // Debug log
      return data.detectors || [];
    }
  });
}

export function useDetectorSchema(detectorName) {
  return useQuery({
    queryKey: queryKeys.detectors.schema(detectorName),
    queryFn: () => api.getDetectorSchema(detectorName),
    enabled: !!detectorName
  });
}

export function useSceneDetectorConfigs(sceneId) {
  return useQuery({
    queryKey: queryKeys.scenes.detectorConfigs(sceneId),
    queryFn: () => api.getSceneDetectorConfigs(sceneId),
    enabled: !!sceneId
  });
}

export function useInstallDetector() {
  const queryClient = useQueryClient();
  const addNotification = useAppStore(state => state.addNotification);
  
  return useMutation({
    mutationFn: async (file) => {
      const formData = new FormData();
      formData.append('file', file);
      
      const response = await fetch(buildApiUrl('api/detectors/install?force_reinstall=true'), {
        method: 'POST',
        body: formData
      });
      
      if (!response.ok) {
        const error = await response.text();
        throw new Error(error);
      }
      
      return response.json();
    },
    onSuccess: () => {
      // Invalidate all detector-related queries
      queryClient.invalidateQueries({ queryKey: queryKeys.detectors.all() });
      queryClient.invalidateQueries({ queryKey: queryKeys.detectors.list() });
      queryClient.invalidateQueries({ queryKey: queryKeys.detectors.installed() });
      addNotification({ type: 'success', message: 'Detector installed successfully' });
    },
    onError: (error) => {
      addNotification({ type: 'error', message: `Failed to install detector: ${error.message}` });
    }
  });
}

export function useUninstallDetector() {
  const queryClient = useQueryClient();
  const addNotification = useAppStore(state => state.addNotification);
  
  return useMutation({
    mutationFn: async (detectorName) => {
      const response = await fetch(buildApiUrl(`api/detectors/uninstall/${detectorName}`), {
        method: 'DELETE'
      });
      
      if (!response.ok) {
        throw new Error('Failed to uninstall detector');
      }
      
      return response.json();
    },
    onSuccess: (_, detectorName) => {
      // Invalidate all detector-related queries
      queryClient.invalidateQueries({ queryKey: queryKeys.detectors.all() });
      queryClient.invalidateQueries({ queryKey: queryKeys.detectors.list() });
      queryClient.invalidateQueries({ queryKey: queryKeys.detectors.installed() });
      addNotification({ type: 'success', message: `${detectorName} uninstalled successfully` });
    },
    onError: (error) => {
      addNotification({ type: 'error', message: `Failed to uninstall detector: ${error.message}` });
    }
  });
}

export function useSaveDetectorConfig() {
  const queryClient = useQueryClient();
  const addNotification = useAppStore(state => state.addNotification);
  
  return useMutation({
    mutationFn: ({ sceneId, detectorName, config }) => 
      api.saveDetectorConfig(sceneId, detectorName, config),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ 
        queryKey: queryKeys.scenes.detectorConfigs(variables.sceneId) 
      });
      addNotification({ type: 'success', message: 'Detector configuration saved' });
    },
    onError: (error) => {
      addNotification({ type: 'error', message: `Failed to save detector config: ${error.message}` });
    }
  });
}
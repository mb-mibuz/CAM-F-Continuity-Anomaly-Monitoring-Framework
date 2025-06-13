import { useQuery } from '@tanstack/react-query';
import { api } from '../../utils/api';
import { queryKeys } from '../keys';

export function useCaptureSources() {
  return useQuery({
    queryKey: queryKeys.capture.sources.all(),
    queryFn: async () => {
      console.log('useCaptureSources - fetching sources...');
      const result = await api.getCaptureSources();
      console.log('useCaptureSources - result:', result);
      return result;
    },
    staleTime: 2000, // Consider sources fresh for 2 seconds
    refetchInterval: 5000, // Refetch every 5 seconds
  });
}

export function useCameras() {
  return useQuery({
    queryKey: queryKeys.capture.sources.cameras(),
    queryFn: api.getCameras,
    staleTime: 5000,
  });
}

export function useMonitors() {
  return useQuery({
    queryKey: queryKeys.capture.sources.monitors(),
    queryFn: api.getMonitors,
    staleTime: 5000,
  });
}

export function useWindows() {
  return useQuery({
    queryKey: queryKeys.capture.sources.windows(),
    queryFn: api.getWindows,
    staleTime: 5000,
  });
}
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../utils/api';
import { queryKeys } from '../keys';
import { useDataStore, useAppStore } from '../../stores';

export function useStartCapture() {
  const addNotification = useAppStore(state => state.addNotification);
  const startCapture = useDataStore(state => state.startCapture);
  
  return useMutation({
    mutationFn: (data) => api.startCapture(data),
    onSuccess: (data, variables) => {
      startCapture(variables.take_id, {
        frame_count_limit: variables.frame_count_limit,
        skip_detectors: variables.skip_detectors
      });
    },
    onError: (error) => {
      addNotification({ type: 'error', message: `Failed to start capture: ${error.message}` });
    }
  });
}

export function useStopCapture() {
  const addNotification = useAppStore(state => state.addNotification);
  const stopCapture = useDataStore(state => state.stopCapture);
  
  return useMutation({
    mutationFn: api.stopCapture,
    onSuccess: () => {
      stopCapture();
    },
    onError: (error) => {
      addNotification({ type: 'error', message: `Failed to stop capture: ${error.message}` });
    }
  });
}

export function useCaptureStatus() {
  return useQuery({
    queryKey: queryKeys.capture.status(),
    queryFn: api.getCaptureStatus,
    refetchInterval: 1000, // Poll every second
  });
}

export function useCaptureProgress(takeId, enabled = false) {
  return useQuery({
    queryKey: queryKeys.capture.progress(takeId),
    queryFn: () => api.getCaptureProgress(takeId),
    enabled: !!takeId && enabled,
    refetchInterval: 500, // Poll every 500ms
  });
}
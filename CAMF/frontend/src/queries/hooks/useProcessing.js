import { useQuery, useMutation } from '@tanstack/react-query';
import { api } from '../../utils/api';
import { queryKeys } from '../keys';
import { useDataStore, useAppStore, useProcessingStore } from '../../stores';

export function useProcessingStatus(enabled = false) {
  return useQuery({
    queryKey: queryKeys.processing.status(),
    queryFn: api.getProcessingStatus,
    enabled,
    refetchInterval: (data) => {
      // Poll while processing
      return data?.is_processing ? 1000 : false;
    }
  });
}

export function useProcessingStatusForTake(takeId, enabled = false) {
  return useQuery({
    queryKey: queryKeys.processing.statusForTake(takeId),
    queryFn: () => api.getProcessingStatusForTake(takeId),
    enabled: !!takeId && enabled,
    refetchInterval: 1000 // Poll every second
  });
}

export function useStopProcessing() {
  const stopProcessing = useProcessingStore(state => state.stopProcessing);
  const addNotification = useAppStore(state => state.addNotification);
  
  return useMutation({
    mutationFn: api.stopProcessing,
    onSuccess: () => {
      stopProcessing();
      addNotification({ type: 'success', message: 'Processing stopped' });
    },
    onError: (error) => {
      addNotification({ type: 'error', message: `Failed to stop processing: ${error.message}` });
    }
  });
}

export function useStartProcessing() {
  const startProcessing = useDataStore(state => state.startProcessing);
  const addNotification = useAppStore(state => state.addNotification);
  
  return useMutation({
    mutationFn: ({ takeId, referenceTakeId }) => 
      api.startProcessing(takeId, referenceTakeId),
    onSuccess: () => {
      startProcessing();
      addNotification({ type: 'success', message: 'Processing started' });
    },
    onError: (error) => {
      addNotification({ type: 'error', message: `Failed to start processing: ${error.message}` });
    }
  });
}

export function useRestartProcessing() {
  const startRedoDetection = useDataStore(state => state.startRedoDetection);
  const addNotification = useAppStore(state => state.addNotification);
  
  return useMutation({
    mutationFn: ({ takeId, referenceTakeId }) => 
      api.restartProcessing(takeId, referenceTakeId),
    onSuccess: () => {
      startRedoDetection();
      addNotification({ type: 'success', message: 'Reprocessing started' });
    },
    onError: (error) => {
      addNotification({ type: 'error', message: `Failed to restart processing: ${error.message}` });
    }
  });
}
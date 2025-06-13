import { useQuery, useMutation, useQueryClient, useQueries } from '@tanstack/react-query';
import { api } from '../../utils/api';
import { queryKeys } from '../keys';
import { useAppStore } from '../../stores';

export function useTakes(angleId) {
  return useQuery({
    queryKey: queryKeys.takes.byAngle(angleId),
    queryFn: () => api.getTakes(angleId),
    enabled: !!angleId
  });
}

export function useTake(takeId) {
  return useQuery({
    queryKey: queryKeys.takes.detail(takeId),
    queryFn: () => api.getTake(takeId),
    enabled: !!takeId
  });
}

export function useTakeWithDetails(takeId) {
  const queries = useQueries({
    queries: [
      {
        queryKey: queryKeys.takes.detail(takeId),
        queryFn: () => api.getTake(takeId),
        enabled: !!takeId
      },
      {
        queryKey: queryKeys.frames.count(takeId),
        queryFn: () => api.getFrameCount(takeId),
        enabled: !!takeId
      },
      {
        queryKey: queryKeys.takes.errors(takeId),
        queryFn: () => api.getTakeErrors(takeId),
        enabled: !!takeId
      }
    ]
  });
  
  const [takeQuery, frameCountQuery, errorsQuery] = queries;
  
  return {
    take: takeQuery.data,
    frameCount: frameCountQuery.data || 0,
    errors: errorsQuery.data || [],
    isLoading: queries.some(q => q.isLoading),
    isError: queries.some(q => q.isError)
  };
}

export function useCreateTake() {
  const queryClient = useQueryClient();
  const addNotification = useAppStore(state => state.addNotification);
  
  return useMutation({
    mutationFn: (takeData) => api.createTake(takeData),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ 
        queryKey: queryKeys.takes.byAngle(variables.angleId) 
      });
      addNotification({ type: 'success', message: 'Take created successfully' });
    },
    onError: (error) => {
      addNotification({ type: 'error', message: `Failed to create take: ${error.message}` });
    }
  });
}

export function useUpdateTake() {
  const queryClient = useQueryClient();
  const addNotification = useAppStore(state => state.addNotification);
  
  return useMutation({
    mutationFn: ({ takeId, data }) => api.updateTake(takeId, data),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ 
        queryKey: queryKeys.takes.detail(variables.takeId) 
      });
      addNotification({ type: 'success', message: 'Take updated successfully' });
    },
    onError: (error) => {
      addNotification({ type: 'error', message: `Failed to update take: ${error.message}` });
    }
  });
}

export function useDeleteTake() {
  const queryClient = useQueryClient();
  const addNotification = useAppStore(state => state.addNotification);
  
  return useMutation({
    mutationFn: (takeId) => api.deleteTake(takeId),
    onSuccess: (_, takeId) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.takes.all() });
      addNotification({ type: 'success', message: 'Take deleted successfully' });
    },
    onError: (error) => {
      addNotification({ type: 'error', message: `Failed to delete take: ${error.message}` });
    }
  });
}

export function useSetReferenceTake() {
  const queryClient = useQueryClient();
  const addNotification = useAppStore(state => state.addNotification);
  
  return useMutation({
    mutationFn: (takeId) => api.setReferenceTake(takeId),
    onSuccess: (data, takeId) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.takes.all() });
      queryClient.invalidateQueries({ queryKey: queryKeys.angles.all() });
      addNotification({ type: 'success', message: 'Reference take updated' });
    },
    onError: (error) => {
      addNotification({ type: 'error', message: `Failed to set reference take: ${error.message}` });
    }
  });
}

export function useReferenceTake(angleId) {
  return useQuery({
    queryKey: queryKeys.angles.referenceTake(angleId),
    queryFn: () => api.getReferenceTake(angleId),
    enabled: !!angleId
  });
}

export function useClearTakeData() {
  const queryClient = useQueryClient();
  const addNotification = useAppStore(state => state.addNotification);
  
  return useMutation({
    mutationFn: (takeId) => api.clearTakeData(takeId),
    onSuccess: (data, takeId) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.takes.detail(takeId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.frames.byTake(takeId) });
      addNotification({ type: 'success', message: 'Take data cleared' });
    },
    onError: (error) => {
      addNotification({ type: 'error', message: `Failed to clear take data: ${error.message}` });
    }
  });
}
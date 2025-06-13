import { useQuery } from '@tanstack/react-query';
import { api } from '../../utils/api';
import { queryKeys } from '../keys';

export function useFrameCount(takeId, enabled = true) {
  return useQuery({
    queryKey: queryKeys.frames.count(takeId),
    queryFn: () => api.getFrameCount(takeId),
    enabled: !!takeId && enabled,
    refetchInterval: 2000, // Refetch every 2 seconds
  });
}

export function useFrameWithBoundingBoxes(takeId, frameId, enabled = true) {
  return useQuery({
    queryKey: queryKeys.frames.withBoundingBoxes(takeId, frameId),
    queryFn: () => api.getFrameWithBoundingBoxes(takeId, frameId),
    enabled: !!takeId && frameId !== undefined && enabled,
  });
}

export function useTakeErrors(takeId, params = {}, enabled = true) {
  return useQuery({
    queryKey: queryKeys.takes.errors(takeId, params),
    queryFn: () => api.getTakeErrors(takeId, params),
    enabled: !!takeId && enabled,
  });
}

export function useContinuousErrors(takeId, enabled = true) {
  return useQuery({
    queryKey: queryKeys.takes.continuousErrors(takeId),
    queryFn: () => api.getContinuousErrors(takeId),
    enabled: !!takeId && enabled,
    refetchInterval: 5000, // Refetch every 5 seconds
  });
}
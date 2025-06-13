import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Increased cache times for better performance
      staleTime: 1000 * 60 * 10, // 10 minutes - data considered fresh
      cacheTime: 1000 * 60 * 30, // 30 minutes - data kept in cache
      
      // Intelligent retry logic
      retry: (failureCount, error) => {
        // Don't retry on 4xx errors
        if (error?.response?.status >= 400 && error?.response?.status < 500) {
          return false;
        }
        // Retry up to 3 times with exponential backoff
        return failureCount < 3;
      },
      
      // Disable automatic refetches for better control
      refetchOnWindowFocus: false,
      refetchOnReconnect: 'always',
      
      // Keep previous data while fetching new data
      keepPreviousData: true,
      
      // Network mode for offline support
      networkMode: 'online'
    },
    mutations: {
      retry: false,
      // Show optimistic updates immediately
      onError: (error, variables, context) => {
        // Log mutation errors for debugging
        console.error('Mutation error:', error);
      }
    }
  }
});

// Custom cache invalidation patterns
export const invalidatePatterns = {
  // Invalidate all queries for a specific entity
  project: (projectId) => ['projects', projectId],
  scene: (sceneId) => ['scenes', sceneId],
  angle: (angleId) => ['angles', angleId],
  take: (takeId) => ['takes', takeId],
  frame: (frameId) => ['frames', frameId],
  
  // Invalidate list queries
  projectList: () => ['projects'],
  sceneList: (projectId) => ['projects', projectId, 'scenes'],
  angleList: (sceneId) => ['scenes', sceneId, 'angles'],
  takeList: (angleId) => ['angles', angleId, 'takes'],
  frameList: (takeId) => ['takes', takeId, 'frames']
};

// Helper to invalidate related queries
export const invalidateRelatedQueries = (queryClient, type, id) => {
  switch (type) {
    case 'project':
      queryClient.invalidateQueries(invalidatePatterns.project(id));
      queryClient.invalidateQueries(invalidatePatterns.projectList());
      break;
    case 'scene':
      queryClient.invalidateQueries(invalidatePatterns.scene(id));
      // Also invalidate parent project's scene list
      break;
    case 'angle':
      queryClient.invalidateQueries(invalidatePatterns.angle(id));
      // Also invalidate parent scene's angle list
      break;
    case 'take':
      queryClient.invalidateQueries(invalidatePatterns.take(id));
      // Also invalidate parent angle's take list
      break;
    case 'frame':
      queryClient.invalidateQueries(invalidatePatterns.frame(id));
      // Also invalidate parent take's frame list
      break;
  }
};
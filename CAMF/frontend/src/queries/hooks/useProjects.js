import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../../utils/api';
import { queryKeys } from '../keys';
import { useAppStore } from '../../stores';

export function useProjects(sortBy = 'created_at', order = 'desc') {
  return useQuery({
    queryKey: queryKeys.projects.all(),
    queryFn: () => api.getProjects(sortBy, order),
    select: (data) => {
      return data || [];
    }
  });
}

export function useProject(projectId) {
  return useQuery({
    queryKey: queryKeys.projects.detail(projectId),
    queryFn: async () => {
      // Since API doesn't have a single project endpoint, fetch from list
      const projects = await api.getProjects();
      const projectsArray = Array.isArray(projects) ? projects : projects.projects || [];
      return projectsArray.find(p => p.id === projectId);
    },
    enabled: !!projectId
  });
}

export function useCreateProject() {
  const queryClient = useQueryClient();
  const addNotification = useAppStore(state => state.addNotification);
  
  return useMutation({
    mutationFn: (name) => api.createProject(name),
    onSuccess: (data) => {
      // Invalidate projects list
      queryClient.invalidateQueries({ queryKey: queryKeys.projects.all() });
      addNotification({
        type: 'success',
        message: 'Project created successfully'
      });
    },
    onError: (error) => {
      addNotification({
        type: 'error',
        message: `Failed to create project: ${error.message}`
      });
    }
  });
}

export function useUpdateProject() {
  const queryClient = useQueryClient();
  const addNotification = useAppStore(state => state.addNotification);
  
  return useMutation({
    mutationFn: ({ projectId, data }) => api.updateProject(projectId, data),
    onSuccess: (data, variables) => {
      // Update cache optimistically
      queryClient.setQueryData(queryKeys.projects.detail(variables.projectId), data);
      
      // Force refresh of the projects list
      queryClient.invalidateQueries({ queryKey: queryKeys.projects.all() });
      
      // Also update the specific project in any cached lists
      queryClient.setQueriesData(
        { queryKey: queryKeys.projects.all(), exact: false },
        (oldData) => {
          if (!oldData) return oldData;
          const projects = Array.isArray(oldData) ? oldData : oldData.projects || [];
          return projects.map(p => 
            p.id === variables.projectId ? { ...p, ...data } : p
          );
        }
      );
      
      addNotification({
        type: 'success',
        message: 'Project updated successfully'
      });
    },
    onError: (error) => {
      addNotification({
        type: 'error',
        message: `Failed to update project: ${error.message}`
      });
    }
  });
}

export function useDeleteProject() {
  const queryClient = useQueryClient();
  const addNotification = useAppStore(state => state.addNotification);
  
  return useMutation({
    mutationFn: (projectId) => api.deleteProject(projectId),
    onSuccess: (_, projectId) => {
      // Remove from cache
      queryClient.removeQueries({ queryKey: queryKeys.projects.detail(projectId) });
      
      // Invalidate ALL project queries to ensure UI updates
      queryClient.invalidateQueries({ queryKey: queryKeys.projects.all() });
      
      // Also invalidate related data
      queryClient.removeQueries({ queryKey: queryKeys.scenes.byProject(projectId) });
      
      addNotification({
        type: 'success',
        message: 'Project deleted successfully'
      });
    },
    onError: (error) => {
      addNotification({
        type: 'error',
        message: `Failed to delete project: ${error.message}`
      });
    }
  });
}

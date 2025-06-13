import React, { useState, useEffect, useCallback, useRef } from 'react';
import { save } from '@tauri-apps/api/dialog';
import { open as openPath } from '@tauri-apps/api/shell';
import { writeBinaryFile } from '@tauri-apps/api/fs';
import { invoke } from '@tauri-apps/api/tauri';
import { 
  Plus, 
  Github, 
  Folder, 
  Settings, 
  Download, 
  ChevronDown,
  ArrowUp,
  ArrowDown,
  Search
} from 'lucide-react';

// Use new modals from the correct location
import NewProjectModal from '../components/modals/NewProjectModal';
import ManagePluginsModal from '../components/modals/ManagePluginsModal';

// Use new queries hooks
import { useProjects, useCreateProject, useUpdateProject, useDeleteProject } from '../queries/hooks';
import { api } from '../utils/api';
import config, { buildApiUrl } from '../config';
import { useAppStore } from '../stores';

export default function HomePage({ onNavigate, onSetRefresh }) {
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState('created_at');
  const [sortOrder, setSortOrder] = useState('desc');
  const [showSortDropdown, setShowSortDropdown] = useState(false);
  const [showNewProjectModal, setShowNewProjectModal] = useState(false);
  const [showManagePluginsModal, setShowManagePluginsModal] = useState(false);
  
  const { addNotification } = useAppStore();
  
  // Use React Query hooks
  const { data: projects = [], isLoading, error, refetch } = useProjects(sortBy, sortOrder);
  const createProjectMutation = useCreateProject();
  const updateProjectMutation = useUpdateProject();
  const deleteProjectMutation = useDeleteProject();

  // Filter projects based on search
  const filteredProjects = React.useMemo(() => {
    if (!searchQuery) return projects;
    
    return projects.filter(project => 
      project.name && project.name.toLowerCase().includes(searchQuery.toLowerCase())
    );
  }, [searchQuery, projects]);

  // Register refresh function
  useEffect(() => {
    if (onSetRefresh) {
      const unregister = onSetRefresh(() => refetch());
      return () => {
        if (typeof unregister === 'function') {
          unregister();
        }
      };
    }
  }, [onSetRefresh]); // Don't include refetch to avoid loops

  const handleCreateProject = useCallback(async (projectName) => {
    try {
      await createProjectMutation.mutateAsync(projectName);
      setShowNewProjectModal(false);
    } catch (error) {
      console.error('Error creating project:', error);
      alert('Failed to create project: ' + error.message);
    }
  }, [createProjectMutation]);

  const handleProjectClick = useCallback((project) => {
    onNavigate('scenes', { projectId: project.id, projectName: project.name });
  }, [onNavigate]);

  const handleRenameProject = useCallback(async (projectId, newName) => {
    try {
      await updateProjectMutation.mutateAsync({ projectId, data: { name: newName } });
    } catch (error) {
      console.error('Error renaming project:', error);
      alert('Failed to rename project: ' + error.message);
    }
  }, [updateProjectMutation]);

  const handleDeleteProject = useCallback(async (projectId) => {
    try {
      await deleteProjectMutation.mutateAsync(projectId);
    } catch (error) {
      console.error('Error deleting project:', error);
      alert('Failed to delete project: ' + error.message);
    }
  }, [deleteProjectMutation]);

  const handleExportProject = useCallback(async (projectId, projectName) => {
    try {
      // First check if project has content
      const scenes = await api.getScenes(projectId);
      let hasContent = false;
      
      for (const scene of scenes) {
        const angles = await api.getAngles(scene.id);
        for (const angle of angles) {
          const takes = await api.getTakes(angle.id);
          if (takes.length > 0) {
            // Check if any take has frames
            for (const take of takes) {
              const response = await fetch(buildApiUrl(`api/frames/take/${take.id}/frame/0`));
              if (response.ok) {
                hasContent = true;
                break;
              }
            }
          }
          if (hasContent) break;
        }
        if (hasContent) break;
      }
      
      if (!hasContent) {
        alert('Cannot export project: No content to export. Please capture some takes first.');
        return;
      }
      
      const filePath = await save({
        defaultPath: `${projectName}_report.pdf`,
        filters: [{
          name: 'PDF',
          extensions: ['pdf']
        }]
      });
      
      if (filePath) {
        // Get the PDF blob from the API
        const blob = await api.exportProject(projectId, {});
        
        // Convert blob to Uint8Array for Tauri
        const arrayBuffer = await blob.arrayBuffer();
        const uint8Array = new Uint8Array(arrayBuffer);
        
        // Write the file using Tauri
        await writeBinaryFile(filePath, uint8Array);
        
        addNotification({ 
          type: 'success', 
          message: 'Project exported successfully!',
          duration: 7000 
        });
      }
    } catch (error) {
      console.error('Error exporting project:', error);
      alert('Failed to export project: ' + error.message);
    }
  }, []);

  const handleOpenProjectLocation = useCallback(async (projectId) => {
    try {
      const response = await fetch(buildApiUrl(`api/projects/${projectId}/location`));
      if (!response.ok) {
        throw new Error('Failed to get project location');
      }
      
      const data = await response.json();
      const projectPath = data.location;
      
      if (projectPath) {
        console.log('Opening project location:', projectPath);
        await invoke('open_folder', { path: projectPath });
      } else {
        alert('Project folder not found. Try creating a scene first.');
      }
    } catch (error) {
      console.error('Error opening project location:', error);
      alert('Failed to open project location: ' + error.message);
    }
  }, []);

  const handleOpenGitHub = useCallback(() => {
    openPath('https://github.com/mb-mibuz/CAM-F-Continuity-Anomaly-Monitoring-Framework');
  }, []);

  const handleOpenProjectFiles = useCallback(async () => {
    try {
      const response = await fetch(buildApiUrl('api/system/storage-path'));
      if (response.ok) {
        const data = await response.json();
        const storagePath = data.path;
        
        if (storagePath) {
          console.log('Opening storage directory:', storagePath);
          await invoke('open_folder', { path: storagePath });
          return;
        }
      }
    } catch (error) {
      console.error('Error:', error);
      alert('Could not open storage folder: ' + error.message);
    }
  }, []);

  const handleDownloadTemplate = useCallback(async () => {
    try {
      const { blob, filename } = await api.downloadDetectorTemplate('detector_template');
      
      // Convert blob to base64 for Tauri
      const reader = new FileReader();
      reader.onloadend = async () => {
        const base64data = reader.result.split(',')[1];
        const uint8Array = new Uint8Array(atob(base64data).split('').map(char => char.charCodeAt(0)));
        
        const filePath = await save({
          defaultPath: 'detector_template.zip',
          filters: [{
            name: 'ZIP',
            extensions: ['zip']
          }]
        });
        
        if (filePath) {
          await writeBinaryFile(filePath, uint8Array);
          alert('Template downloaded successfully!');
        }
      };
      reader.readAsDataURL(blob);
      
    } catch (error) {
      console.error('Error downloading template:', error);
      alert('Failed to download template: ' + error.message);
    }
  }, []);

  const toggleSortOrder = useCallback(() => {
    setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
  }, []);

  const handleSort = useCallback((newSortBy) => {
    setSortBy(newSortBy);
    setShowSortDropdown(false);
  }, []);

  return (
    <div className="flex h-full">
      {/* Left sidebar */}
      <div className="w-[306px] flex flex-col px-9 py-6">
        <button 
          onClick={() => setShowNewProjectModal(true)}
          className="bg-primary text-white px-3 py-1.5 rounded-[10px] w-[120px] h-8 flex items-center justify-center btn-hover"
        >
          <span className="text-14 font-medium">New Project</span>
        </button>

        <div className="relative my-4">
          <div className="separator-line w-[180px]"></div>
        </div>

        <button 
          onClick={handleOpenGitHub}
          className="flex items-center gap-2 py-2 btn-hover"
        >
          <Github size={25} strokeWidth={1.5} />
          <span className="text-14 font-normal">CAMF GitHub</span>
        </button>

        <button 
          onClick={handleOpenProjectFiles}
          className="flex items-center gap-2 py-2 btn-hover"
        >
          <Folder size={25} strokeWidth={1.5} />
          <span className="text-14 font-normal">Project files</span>
        </button>

        <div className="mt-6 mb-3">
          <span className="text-12 font-medium text-primary uppercase">Continuity</span>
        </div>

        <button 
          onClick={() => setShowManagePluginsModal(true)}
          className="flex items-center gap-2 py-2 btn-hover"
        >
          <Settings size={25} strokeWidth={1.5} />
          <span className="text-14 font-normal">Manage Plugins</span>
        </button>

        <button 
          onClick={handleDownloadTemplate}
          className="flex items-center gap-2 py-2 btn-hover"
        >
          <Download size={25} strokeWidth={1.5} />
          <span className="text-14 font-normal">Download template</span>
        </button>
      </div>

      {/* Vertical separator */}
      <div className="w-px bg-black opacity-50"></div>

      {/* Right content area */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-9 py-6">
          <div className="flex items-center gap-4">
            <h1 className="text-18 font-semibold">Recent Projects</h1>
            
            {/* Sort dropdown */}
            <div className="relative flex items-center gap-2">
              <button 
                onClick={() => setShowSortDropdown(!showSortDropdown)}
                className="flex items-center gap-2 btn-hover"
              >
                <span className="text-12 font-medium uppercase">
                  {sortBy === 'created_at' ? 'RECENT' : sortBy === 'name' ? 'NAME' : 'SIZE'}
                </span>
                <ChevronDown size={14} strokeWidth={2.2} />
              </button>
              
              {showSortDropdown && (
                <div className="absolute top-full mt-1 bg-white border border-gray-200 rounded shadow-lg z-10">
                  <button 
                    onClick={() => handleSort('created_at')}
                    className="block w-full text-left px-4 py-2 hover:bg-gray-100 text-14"
                  >
                    Recent
                  </button>
                  <button 
                    onClick={() => handleSort('name')}
                    className="block w-full text-left px-4 py-2 hover:bg-gray-100 text-14"
                  >
                    Name
                  </button>
                </div>
              )}
              
              <div className="w-px h-4 bg-black mx-2"></div>
              
              <button onClick={toggleSortOrder} className="btn-hover">
                {sortOrder === 'asc' ? (
                  <ArrowUp size={14} strokeWidth={2} />
                ) : (
                  <ArrowDown size={14} strokeWidth={2} />
                )}
              </button>
            </div>
          </div>

          {/* Search */}
          <div className="flex items-center gap-2">
            <span className="text-12 font-medium">Search</span>
            <div className="relative">
              <input 
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Project..."
                className="w-[218px] pb-1 text-12 italic text-text-light focus:text-black focus:not-italic outline-none"
              />
              <div className="absolute bottom-0 left-0 right-0 h-px bg-black"></div>
            </div>
          </div>
        </div>

        {/* Projects grid */}
        <div className="flex-1 overflow-y-auto px-9 pb-6">
          {isLoading ? (
            <div className="flex items-center justify-center h-full">
              <p className="text-text-gray">Loading projects...</p>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-full">
              <p className="text-red-600 mb-4">{error.message}</p>
              <button 
                onClick={() => refetch()}
                className="px-4 py-2 bg-primary text-white rounded hover:opacity-80"
              >
                Retry
              </button>
            </div>
          ) : filteredProjects.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <p className="text-text-gray">
                {searchQuery ? 'No projects match your search' : 'No projects found. Create a new project to get started!'}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
              {filteredProjects.map(project => (
                <ProjectCard 
                  key={project.id}
                  project={project}
                  onClick={() => handleProjectClick(project)}
                  onRename={(newName) => handleRenameProject(project.id, newName)}
                  onDelete={() => handleDeleteProject(project.id)}
                  onExport={() => handleExportProject(project.id, project.name)}
                  onOpenLocation={() => handleOpenProjectLocation(project.id)}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Modals */}
      {showNewProjectModal && (
        <NewProjectModal 
          onClose={() => setShowNewProjectModal(false)}
          onSave={handleCreateProject}
        />
      )}

      {showManagePluginsModal && (
        <ManagePluginsModal 
          onClose={() => setShowManagePluginsModal(false)}
        />
      )}
    </div>
  );
}

// Project Card Component
function ProjectCard({ project, onClick, onRename, onDelete, onExport, onOpenLocation }) {
  const [showDropdown, setShowDropdown] = useState(false);
  const [showRenameModal, setShowRenameModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  const formatDate = (dateString) => {
    if (!dateString) return 'Just now';
    
    const date = new Date(dateString);
    
    // Check if date is valid
    if (isNaN(date.getTime())) {
      return 'Just now';
    }
    
    const now = new Date();
    const diffTime = Math.abs(now - date);
    const diffMinutes = Math.floor(diffTime / (1000 * 60));
    const diffHours = Math.floor(diffTime / (1000 * 60 * 60));
    const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
    
    if (diffMinutes < 1) return 'Just now';
    if (diffMinutes < 60) return `${diffMinutes} minute${diffMinutes === 1 ? '' : 's'} ago`;
    if (diffHours < 24) return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`;
    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return '1 day ago';
    if (diffDays < 30) return `${diffDays} days ago`;
    if (diffDays < 365) {
      const months = Math.floor(diffDays / 30);
      return months === 1 ? '1 month ago' : `${months} months ago`;
    }
    const years = Math.floor(diffDays / 365);
    return years === 1 ? '1 year ago' : `${years} years ago`;
  };

  return (
    <>
      <div 
        className="w-full max-w-[357px] h-[262px] border-0.25 border-black card-hover cursor-pointer"
        onClick={onClick}
      >
        {/* Thumbnail */}
        <div className="h-[201px] bg-card-gray relative overflow-hidden">
          <img 
            src={buildApiUrl(`api/projects/${project.id}/thumbnail`)}
            alt={`${project.name} thumbnail`}
            className="w-full h-full object-cover"
            onError={(e) => {
              // Hide image on error to show gray background
              e.target.style.display = 'none';
            }}
          />
        </div>
        
        {/* Content */}
        <div className="h-[60px] px-4 py-2.5 flex items-center justify-between">
          <div className="flex-1 pr-2">
            <h3 className="text-14 font-normal truncate">{project.name}</h3>
            <p className="text-12 font-normal text-text-gray">{formatDate(project.last_modified || project.created_at)}</p>
          </div>
          
          <div className="flex items-center gap-2 flex-shrink-0">
            {/* Edit button */}
            <button 
              onClick={(e) => {
                e.stopPropagation();
                setShowRenameModal(true);
              }}
              className="w-6 h-6 flex items-center justify-center btn-hover"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M11.5 2.5L13.5 4.5L11.5 2.5ZM12.5 1.5L8 6L7 9L10 8L14.5 3.5C14.8 3.2 15 2.8 15 2.5C15 2.2 14.8 1.8 14.5 1.5C14.2 1.2 13.8 1 13.5 1C13.2 1 12.8 1.2 12.5 1.5V1.5Z" stroke="black" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M13 9V13C13 13.5 12.5 14 12 14H3C2.5 14 2 13.5 2 13V4C2 3.5 2.5 3 3 3H7" stroke="black" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
            
            {/* More options button */}
            <div className="relative">
              <button 
                onClick={(e) => {
                  e.stopPropagation();
                  setShowDropdown(!showDropdown);
                }}
                className="w-6 h-6 flex items-center justify-center btn-hover"
              >
                <svg width="16" height="4" viewBox="0 0 16 4" fill="none">
                  <circle cx="2" cy="2" r="1.5" fill="black"/>
                  <circle cx="8" cy="2" r="1.5" fill="black"/>
                  <circle cx="14" cy="2" r="1.5" fill="black"/>
                </svg>
              </button>
              
              {showDropdown && (
                <div className="absolute right-0 top-full mt-1 bg-white border border-gray-200 rounded shadow-lg z-10 w-40">
                  <button 
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowDropdown(false);
                      onOpenLocation();
                    }}
                    className="block w-full text-left px-4 py-2 hover:bg-gray-100 text-14"
                  >
                    Open location
                  </button>
                  <button 
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowDropdown(false);
                      onExport();
                    }}
                    className="block w-full text-left px-4 py-2 hover:bg-gray-100 text-14"
                  >
                    Export as PDF
                  </button>
                  <button 
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowDropdown(false);
                      setShowDeleteModal(true);
                    }}
                    className="block w-full text-left px-4 py-2 hover:bg-gray-100 text-14 text-red-600"
                  >
                    Delete
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Modals */}
      {showRenameModal && (
        <RenameModal 
          title="Rename Project"
          currentName={project.name}
          onClose={() => setShowRenameModal(false)}
          onSave={(newName) => {
            onRename(newName);
            setShowRenameModal(false);
          }}
        />
      )}

      {showDeleteModal && (
        <ConfirmModal 
          title="Delete Project"
          message={`Are you sure you want to delete "${project.name}"? This action cannot be undone.`}
          confirmText="Delete"
          onConfirm={() => {
            onDelete();
            setShowDeleteModal(false);
          }}
          onCancel={() => setShowDeleteModal(false)}
        />
      )}
    </>
  );
}

import RenameModal from '../components/modals/RenameModal';
import ConfirmModal from '../components/modals/ConfirmModal';
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { save } from '@tauri-apps/api/dialog';
import { invoke } from '@tauri-apps/api/tauri';
import { useExportGuard } from '../hooks/useExportGuard';
import {
  Plus,
  ChevronUp,
  ChevronDown,
  Search,
  Settings,
  FileText
} from 'lucide-react';

// Use new modals from the correct location
import NewSceneModal from '../components/modals/NewSceneModal';
import SceneConfigModal from '../components/modals/SceneConfigModal';
import DetectorConfigModal from '../components/modals/DetectorConfigModal';
import RenameModal from '../components/modals/RenameModal';
import ConfirmModal from '../components/modals/ConfirmModal';

// Use new query hooks
import { 
  useScenes, 
  useCreateScene, 
  useUpdateScene, 
  useDeleteScene,
  useAngles,
  useTakes
} from '../queries/hooks';
import { api } from '../utils/api';
import config, { buildApiUrl } from '../config';

export default function ScenesPage({ projectId, projectName, onNavigate, onSetRefresh }) {
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState('name');
  const [sortOrder, setSortOrder] = useState('asc');
  const [showDropdown, setShowDropdown] = useState(null);
  const [selectedScene, setSelectedScene] = useState(null);
  
  // Modal states
  const [showNewSceneModal, setShowNewSceneModal] = useState(false);
  const [showSceneConfigModal, setShowSceneConfigModal] = useState(false);
  const [showDetectorConfigModal, setShowDetectorConfigModal] = useState(false);
  const [showRenameModal, setShowRenameModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showSceneSettingsModal, setShowSceneSettingsModal] = useState(false);
  const [showDetectorSettingsModal, setShowDetectorSettingsModal] = useState(false);
  
  // Scene creation flow state
  const [newSceneData, setNewSceneData] = useState({
    name: '',
    frame_rate: 1.0,
    resolution: '1080p',
    image_quality: 90,
    enabledDetectors: [],
    detectorConfigs: {}
  });
  
  // Export guard
  const { exportScene: exportSceneWithGuard } = useExportGuard();
  
  // Use React Query hooks
  const { data: scenes = [], isLoading, error, refetch } = useScenes(projectId);
  const createSceneMutation = useCreateScene();
  const updateSceneMutation = useUpdateScene();
  const deleteSceneMutation = useDeleteScene();
  
  // Debug logging
  React.useEffect(() => {
    if (scenes.length > 0) {
      console.log('Scenes from API:', scenes);
    }
  }, [scenes]);

  // Enrich scenes with additional data
  const [enrichedScenes, setEnrichedScenes] = useState([]);
  const enrichmentInProgress = useRef(false);
  const prevScenesRef = useRef(null);
  
  useEffect(() => {
    // Check if scenes actually changed by comparing IDs
    const sceneIds = scenes.map(s => s.id).sort().join(',');
    const prevSceneIds = prevScenesRef.current;
    
    if (sceneIds === prevSceneIds) {
      return; // No actual change in scenes
    }
    
    prevScenesRef.current = sceneIds;
    
    const enrichScenes = async () => {
      if (!scenes.length) {
        setEnrichedScenes([]);
        return;
      }
      
      // Prevent concurrent enrichment
      if (enrichmentInProgress.current) {
        return;
      }
      enrichmentInProgress.current = true;

      const scenesWithInfo = await Promise.all(scenes.map(async (scene) => {
        try {
          const angles = await api.getAngles(scene.id);
          let totalTakes = 0;
          let totalSize = 0;
          
          // Skip size calculation - endpoints not implemented
          // TODO: Implement size endpoints in backend or calculate differently
          /*
          // Get scene folder size
          try {
            const sceneSizeResponse = await fetch(buildApiUrl(`api/scenes/${scene.id}/size`));
            if (sceneSizeResponse.ok) {
              const sceneSizeData = await sceneSizeResponse.json();
              totalSize += sceneSizeData.size_bytes || 0;
            }
          } catch (error) {
            console.error(`Error getting scene folder size:`, error);
          }
          */
          
          // Get takes count only (skip sizes)
          for (const angle of angles) {
            const takes = await api.getTakes(angle.id);
            totalTakes += takes.length;
            
            // Skip size fetching for now
            /*
            for (const take of takes) {
              try {
                const sizeResponse = await fetch(buildApiUrl(`api/takes/${take.id}/size`));
                if (sizeResponse.ok) {
                  const sizeData = await sizeResponse.json();
                  totalSize += sizeData.size_bytes || 0;
                }
              } catch (error) {
                console.error(`Error getting size for take ${take.id}:`, error);
              }
            }
            */
          }
          
          const size_mb = Math.round(totalSize / (1024 * 1024));
          
          return {
            ...scene,
            angles,
            takes_count: totalTakes,
            size_mb: size_mb,
            last_frame: null
          };
        } catch (error) {
          console.error(`Error loading info for scene ${scene.id}:`, error);
          return {
            ...scene,
            angles: [],
            takes_count: 0,
            size_mb: 0,
            last_frame: null
          };
        }
      }));
      
      setEnrichedScenes(scenesWithInfo);
      enrichmentInProgress.current = false;
    };

    enrichScenes();
  }, [scenes]); // Re-enrich when scenes data changes (including names)

  // Filter and sort scenes
  const filteredScenes = React.useMemo(() => {
    let filtered = [...enrichedScenes];
    
    // Apply search filter
    if (searchQuery) {
      filtered = filtered.filter(scene =>
        scene.name.toLowerCase().includes(searchQuery.toLowerCase())
      );
    }
    
    // Apply sorting
    filtered.sort((a, b) => {
      let aVal, bVal;
      
      switch (sortBy) {
        case 'name':
          aVal = a.name.toLowerCase();
          bVal = b.name.toLowerCase();
          break;
        case 'created_at':
          aVal = new Date(a.created_at);
          bVal = new Date(b.created_at);
          break;
        case 'takes':
          aVal = a.takes_count;
          bVal = b.takes_count;
          break;
        case 'size':
          aVal = a.size_mb;
          bVal = b.size_mb;
          break;
        default:
          aVal = a.name;
          bVal = b.name;
      }
      
      if (sortOrder === 'asc') {
        return aVal > bVal ? 1 : -1;
      } else {
        return aVal < bVal ? 1 : -1;
      }
    });
    
    return filtered;
  }, [enrichedScenes, searchQuery, sortBy, sortOrder]);

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

  const handleSort = useCallback((column) => {
    if (sortBy === column) {
      setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(column);
      setSortOrder('asc');
    }
  }, [sortBy]);

  // Scene creation flow
  const handleNewSceneName = useCallback((sceneName) => {
    setNewSceneData({ 
      ...newSceneData, 
      name: sceneName 
    });
    setShowNewSceneModal(false);
    setShowSceneConfigModal(true);
  }, [newSceneData]);

  const handleSceneConfig = useCallback((config) => {
    setNewSceneData({ 
      ...newSceneData, 
      frame_rate: config.fps,
      resolution: config.resolution,
      image_quality: config.quality 
    });
    setShowSceneConfigModal(false);
    setShowDetectorConfigModal(true);
  }, [newSceneData]);

  const handleDetectorConfig = useCallback(async (enabledDetectors, detectorConfigs) => {
    try {
      const sceneData = {
        projectId: projectId,  // Changed from project_id to projectId to match api.js
        name: newSceneData.name,
        frame_rate: newSceneData.frame_rate || newSceneData.fps || 1.0,
        image_quality: newSceneData.image_quality || newSceneData.quality || 90,
        resolution: newSceneData.resolution || '1080p',
        enabled_detectors: enabledDetectors,
        detector_settings: detectorConfigs
      };
      
      await createSceneMutation.mutateAsync(sceneData);
      
      setShowDetectorConfigModal(false);
      setNewSceneData({ name: '', frame_rate: 1.0, resolution: '1080p', image_quality: 90, enabledDetectors: [], detectorConfigs: {} });
    } catch (error) {
      console.error('Error creating scene:', error);
      alert('Failed to create scene: ' + error.message);
    }
  }, [projectId, newSceneData, createSceneMutation]);

  const handleSceneClick = useCallback((scene) => {
    onNavigate('takes', { 
      projectId, 
      projectName,
      sceneId: scene.id, 
      sceneName: scene.name 
    });
  }, [projectId, projectName, onNavigate]);

  const handleRenameScene = useCallback(async (sceneId, newName) => {
    try {
      await updateSceneMutation.mutateAsync({ sceneId, data: { name: newName } });
      
      // Update the enrichedScenes immediately for instant UI feedback
      setEnrichedScenes(prev => prev.map(scene => 
        scene.id === sceneId ? { ...scene, name: newName } : scene
      ));
      
      // Refetch scenes to ensure data consistency
      refetch();
    } catch (error) {
      console.error('Error renaming scene:', error);
      alert('Failed to rename scene: ' + error.message);
    }
  }, [updateSceneMutation, refetch]);

  const handleDeleteScene = useCallback(async () => {
    try {
      await deleteSceneMutation.mutateAsync(selectedScene.id);
      setShowDeleteModal(false);
      setSelectedScene(null);
    } catch (error) {
      console.error('Error deleting scene:', error);
      alert('Failed to delete scene: ' + error.message);
    }
  }, [selectedScene, deleteSceneMutation]);

  const handleOpenSceneLocation = useCallback(async (scene) => {
    try {
      const response = await fetch(buildApiUrl(`api/scenes/${scene.id}/location`));
      if (!response.ok) {
        throw new Error('Failed to get scene location');
      }
      
      const data = await response.json();
      const scenePath = data.location;
      
      if (scenePath) {
        console.log('Opening scene location:', scenePath);
        await invoke('open_folder', { path: scenePath });
      } else {
        alert('Scene folder not found.');
      }
    } catch (error) {
      console.error('Error opening scene location:', error);
      alert('Failed to open scene location: ' + error.message);
    }
  }, []);

  const handleExportScene = useCallback(async (scene) => {
    const filePath = await save({
      defaultPath: `${scene.name}_report.pdf`,
      filters: [{
        name: 'PDF',
        extensions: ['pdf']
      }]
    });
    
    if (filePath) {
      await exportSceneWithGuard(
        scene.id,
        scene.name,
        filePath,
        async () => {
          for (const angle of scene.angles || []) {
            const takes = await api.getTakes(angle.id);
            if (takes.length > 0) {
              return true;
            }
          }
          return false;
        }
      );
    }
  }, [exportSceneWithGuard]);

  const formatDate = useCallback((dateString) => {
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
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays} days ago`;
    
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined
    });
  }, []);

  const formatSize = useCallback((sizeMB) => {
    if (sizeMB < 1000) {
      return `${sizeMB} MB`;
    }
    return `${(sizeMB / 1000).toFixed(1)} GB`;
  }, []);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-9 py-6">
        <div className="flex items-center gap-4">
          <h1 className="text-18 font-semibold">{projectName}</h1>
          <button 
            onClick={() => setShowNewSceneModal(true)}
            className="bg-primary text-white px-3 py-1.5 rounded-[10px] h-8 flex items-center justify-center btn-hover"
          >
            <span className="text-14 font-medium">New Scene</span>
          </button>
        </div>

        {/* Search */}
        <div className="flex items-center gap-2">
          <span className="text-12 font-medium">Search</span>
          <div className="relative">
            <input 
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Scene..."
              className="w-[218px] pb-1 text-12 italic text-text-light focus:text-black focus:not-italic outline-none"
            />
            <div className="absolute bottom-0 left-0 right-0 h-px bg-black"></div>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <p className="text-gray-500">Loading scenes...</p>
          </div>
        ) : filteredScenes.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <p className="text-gray-500">
              {searchQuery ? 'No scenes match your search' : 'No scenes found. Create a new scene to get started!'}
            </p>
          </div>
        ) : (
          <div className="px-9">
            {/* Table header */}
            <div className="flex items-center border-b border-gray-300 pb-2 mb-2">
              <div className="w-20"></div>
              <button 
                onClick={() => handleSort('name')}
                className="flex-1 flex items-center gap-2 text-12 font-medium uppercase text-left btn-hover"
              >
                NAME
                {sortBy === 'name' && (
                  sortOrder === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />
                )}
              </button>
              <button 
                onClick={() => handleSort('created_at')}
                className="w-32 flex items-center justify-center gap-2 text-12 font-medium uppercase btn-hover"
              >
                RECENT
                {sortBy === 'created_at' && (
                  sortOrder === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />
                )}
              </button>
              <button 
                onClick={() => handleSort('takes')}
                className="w-24 flex items-center justify-center gap-2 text-12 font-medium uppercase btn-hover"
              >
                TAKES
                {sortBy === 'takes' && (
                  sortOrder === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />
                )}
              </button>
              <button 
                onClick={() => handleSort('size')}
                className="w-24 flex items-center justify-center gap-2 text-12 font-medium uppercase btn-hover"
              >
                SIZE
                {sortBy === 'size' && (
                  sortOrder === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />
                )}
              </button>
              <div className="w-12"></div>
            </div>

            {/* Table rows */}
            {filteredScenes.map((scene, index) => (
              <div 
                key={scene.id}
                className="flex items-center h-[85px] border-b border-gray-300 cursor-pointer hover:bg-gray-50"
                onClick={() => handleSceneClick(scene)}
              >
                {/* Thumbnail - 16:9 aspect ratio */}
                <div className="w-24 h-[54px] bg-card-gray mr-4 relative overflow-hidden flex-shrink-0">
                  {/* 96px width * 9/16 = 54px height */}
                  <img 
                    src={buildApiUrl(`api/scenes/${scene.id}/thumbnail`)}
                    alt={`${scene.name} thumbnail`}
                    className="absolute inset-0 w-full h-full object-cover"
                    style={{
                      objectFit: 'cover',
                      objectPosition: 'center'
                    }}
                    onError={(e) => {
                      // Hide image on error to show gray background
                      e.target.style.display = 'none';
                    }}
                  />
                </div>
                
                <div className="flex-1 pr-4">
                  <p className="text-14 truncate" title={scene.name}>{scene.name}</p>
                </div>
                
                <div className="w-32 text-center">
                  <p className="text-14 text-gray-600">{formatDate(scene.created_at)}</p>
                </div>
                
                <div className="w-24 text-center">
                  <p className="text-14">{scene.takes_count}</p>
                </div>
                
                <div className="w-24 text-center">
                  <p className="text-14">{formatSize(scene.size_mb)}</p>
                </div>
                
                <div className="w-12 flex justify-center relative">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowDropdown(showDropdown === index ? null : index);
                    }}
                    className="w-8 h-8 flex items-center justify-center btn-hover rounded"
                  >
                    <svg width="16" height="4" viewBox="0 0 16 4" fill="none">
                      <circle cx="2" cy="2" r="1.5" fill="black"/>
                      <circle cx="8" cy="2" r="1.5" fill="black"/>
                      <circle cx="14" cy="2" r="1.5" fill="black"/>
                    </svg>
                  </button>
                  
                  {showDropdown === index && (
                    <div className="absolute right-0 top-full mt-1 bg-white border border-gray-200 rounded shadow-lg z-[100] w-40">
                      <button 
                        onClick={(e) => {
                          e.stopPropagation();
                          setShowDropdown(null);
                          const currentScene = enrichedScenes.find(s => s.id === scene.id) || scene;
                          setSelectedScene(currentScene);
                          setShowRenameModal(true);
                        }}
                        className="block w-full text-left px-4 py-2 hover:bg-gray-100 text-14"
                      >
                        Rename
                      </button>
                      <button 
                        onClick={(e) => {
                          e.stopPropagation();
                          setShowDropdown(null);
                          handleOpenSceneLocation(scene);
                        }}
                        className="block w-full text-left px-4 py-2 hover:bg-gray-100 text-14"
                      >
                        Open location
                      </button>
                      <button 
                        onClick={(e) => {
                          e.stopPropagation();
                          setShowDropdown(null);
                          handleExportScene(scene);
                        }}
                        className="block w-full text-left px-4 py-2 hover:bg-gray-100 text-14"
                      >
                        Export as PDF
                      </button>
                      <button 
                        onClick={async (e) => {
                          e.stopPropagation();
                          setShowDropdown(null);
                          // Fetch fresh scene data to ensure we have the latest values
                          try {
                            const freshSceneData = await api.getScene(scene.id);
                            console.log('Fresh scene data:', freshSceneData);
                            setSelectedScene(freshSceneData);
                            setShowSceneSettingsModal(true);
                          } catch (error) {
                            console.error('Error fetching scene:', error);
                            // Fallback to existing data
                            const currentScene = enrichedScenes.find(s => s.id === scene.id) || scene;
                            setSelectedScene(currentScene);
                            setShowSceneSettingsModal(true);
                          }
                        }}
                        className="block w-full text-left px-4 py-2 hover:bg-gray-100 text-14"
                      >
                        Scene Settings
                      </button>
                      <button 
                        onClick={(e) => {
                          e.stopPropagation();
                          setShowDropdown(null);
                          const currentScene = enrichedScenes.find(s => s.id === scene.id) || scene;
                          setSelectedScene(currentScene);
                          setShowDetectorSettingsModal(true);
                        }}
                        className="block w-full text-left px-4 py-2 hover:bg-gray-100 text-14"
                      >
                        Detector Config
                      </button>
                      <button 
                        onClick={(e) => {
                          e.stopPropagation();
                          setShowDropdown(null);
                          const currentScene = enrichedScenes.find(s => s.id === scene.id) || scene;
                          setSelectedScene(currentScene);
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
            ))}
          </div>
        )}
      </div>

      {/* Modals */}
      {showNewSceneModal && (
        <NewSceneModal
          onClose={() => setShowNewSceneModal(false)}
          onCreate={handleNewSceneName}
        />
      )}

      {showSceneConfigModal && (
        <SceneConfigModal
          sceneName={newSceneData.name}
          initialFps={newSceneData.frame_rate || 1.0}
          initialQuality={newSceneData.image_quality || 90}
          initialResolution={newSceneData.resolution || '1080p'}
          onBack={() => {
            setShowSceneConfigModal(false);
            setShowNewSceneModal(true);
          }}
          onNext={handleSceneConfig}
          onClose={() => {
            setShowSceneConfigModal(false);
            setNewSceneData({ name: '', frame_rate: 1.0, resolution: '1080p', image_quality: 90 });
          }}
        />
      )}

      {showDetectorConfigModal && (
        <DetectorConfigModal
          sceneName={newSceneData.name}
          sceneConfig={newSceneData}
          onBack={() => {
            setShowDetectorConfigModal(false);
            setShowSceneConfigModal(true);
          }}
          onCreate={handleDetectorConfig}
          onClose={() => {
            setShowDetectorConfigModal(false);
            setNewSceneData({ name: '', frame_rate: 1.0, resolution: '1080p', image_quality: 90 });
          }}
        />
      )}

      {showRenameModal && selectedScene && (
        <RenameModal
          title="Rename Scene"
          currentName={selectedScene.name}
          onClose={() => {
            setShowRenameModal(false);
            setSelectedScene(null);
          }}
          onSave={(newName) => {
            handleRenameScene(selectedScene.id, newName);
            setShowRenameModal(false);
            setSelectedScene(null);
          }}
        />
      )}

      {showDeleteModal && selectedScene && (
        <ConfirmModal
          title="Delete Scene"
          message={`Are you sure you want to delete "${selectedScene.name}"? This will also delete all angles and takes within this scene. This action cannot be undone.`}
          confirmText="Delete"
          onConfirm={handleDeleteScene}
          onCancel={() => {
            setShowDeleteModal(false);
            setSelectedScene(null);
          }}
        />
      )}

      {showSceneSettingsModal && selectedScene && (
        <SceneConfigModal
          key={`scene-config-${selectedScene.id}-${selectedScene.image_quality || 90}-${Date.now()}`}
          sceneName={selectedScene.name}
          initialFps={selectedScene.frame_rate}
          initialQuality={selectedScene.image_quality || 90}
          initialResolution={selectedScene.resolution || '1080p'}
          editMode={true}
          onBack={null}
          onNext={async (config) => {
            try {
              console.log('Updating scene with config:', config);
              console.log('Current selectedScene:', selectedScene);
              
              await updateSceneMutation.mutateAsync({
                sceneId: selectedScene.id,
                data: {
                  // Only update quality since fps and resolution can't be changed
                  image_quality: config.quality
                }
              });
              // Refetch scenes to update the enriched data
              await refetch();
              setShowSceneSettingsModal(false);
              setSelectedScene(null);
            } catch (error) {
              console.error('Error updating scene:', error);
              alert('Failed to update scene settings');
            }
          }}
          onClose={() => {
            setShowSceneSettingsModal(false);
            setSelectedScene(null);
          }}
        />
      )}

      {showDetectorSettingsModal && selectedScene && (
        <DetectorConfigModal
          sceneName={selectedScene.name}
          sceneConfig={selectedScene}
          sceneId={selectedScene.id}
          editMode={true}
          onBack={null}
          onCreate={async () => {
            setShowDetectorSettingsModal(false);
            setSelectedScene(null);
            await refetch();
          }}
          onClose={() => {
            setShowDetectorSettingsModal(false);
            setSelectedScene(null);
          }}
        />
      )}
    </div>
  );
}
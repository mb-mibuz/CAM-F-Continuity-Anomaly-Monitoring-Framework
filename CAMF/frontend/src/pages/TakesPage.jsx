import React, { useState, useEffect, useCallback, useRef } from 'react';
import { save } from '@tauri-apps/api/dialog';
import { invoke } from '@tauri-apps/api/tauri';
import { useExportGuard } from '../hooks/useExportGuard';
import {
  FileText,
  Settings,
  Cpu,
  ChevronDown,
  ChevronUp,
  Star
} from 'lucide-react';

// Use new modals from the correct location
import NewTakeModal from '../components/modals/NewTakeModal';
import SceneConfigModal from '../components/modals/SceneConfigModal';
import DetectorConfigModal from '../components/modals/DetectorConfigModal';
import RenameModal from '../components/modals/RenameModal';
import ConfirmModal from '../components/modals/ConfirmModal';

// Use new query hooks
import {
  useScene,
  useAngles,
  useTakes,
  useCreateAngle,
  useUpdateAngle,
  useCreateTake,
  useUpdateTake,
  useDeleteTake,
  useSetReferenceTake,
  useUpdateScene
} from '../queries/hooks';
import { api } from '../utils/api';

export default function TakesPage({ projectId, projectName, sceneId, sceneName, onNavigate, onSetRefresh }) {
  // Debug logging
  useEffect(() => {
    console.log('TakesPage props:', { projectId, projectName, sceneId, sceneName });
    if (!sceneId) {
      console.error('TakesPage: sceneId is undefined!');
    }
  }, [projectId, projectName, sceneId, sceneName]);
  
  const [collapsedAngles, setCollapsedAngles] = useState({});
  const [showDropdown, setShowDropdown] = useState(null);
  const [showAngleRenameModal, setShowAngleRenameModal] = useState(false);
  const [selectedAngle, setSelectedAngle] = useState(null);
  const dropdownRef = useRef(null);
  
  // Modal states
  const [showNewTakeModal, setShowNewTakeModal] = useState(false);
  const [showSceneConfigModal, setShowSceneConfigModal] = useState(false);
  const [showDetectorConfigModal, setShowDetectorConfigModal] = useState(false);
  const [showRenameModal, setShowRenameModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showReferenceConfirm, setShowReferenceConfirm] = useState(false);
  
  // Selected items for actions
  const [selectedTake, setSelectedTake] = useState(null);
  const [pendingReferenceTake, setPendingReferenceTake] = useState(null);
  
  // Click outside handler for dropdown
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setShowDropdown(null);
      }
    };
    
    if (showDropdown) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => {
        document.removeEventListener('mousedown', handleClickOutside);
      };
    }
  }, [showDropdown]);
  
  // Export guard
  const { exportTake: exportTakeWithGuard, exportScene: exportSceneWithGuard } = useExportGuard();
  
  // Use React Query hooks
  const { data: sceneData } = useScene(sceneId);
  const { data: angles = [], refetch: refetchAngles } = useAngles(sceneId);
  
  // Mutations
  const createAngleMutation = useCreateAngle();
  const updateAngleMutation = useUpdateAngle();
  const createTakeMutation = useCreateTake();
  const updateTakeMutation = useUpdateTake();
  const deleteTakeMutation = useDeleteTake();
  const setReferenceTakeMutation = useSetReferenceTake();
  const updateSceneMutation = useUpdateScene();
  
  // Enrich angles with takes data
  const [anglesWithTakes, setAnglesWithTakes] = useState([]);
  const loadingAnglesRef = useRef(false);
  const prevAnglesRef = useRef([]);
  
  useEffect(() => {
    const loadAnglesWithTakes = async () => {
      // Prevent concurrent loading
      if (loadingAnglesRef.current) {
        return;
      }

      if (!angles || angles.length === 0) {
        if (anglesWithTakes.length !== 0) {
          setAnglesWithTakes([]);
        }
        prevAnglesRef.current = [];
        return;
      }

      // Check if angles have actually changed (including reference_take_id)
      const angleSignature = angles.map(a => `${a.id}:${a.reference_take_id || 'none'}`).sort().join(',');
      const prevAngleSignature = prevAnglesRef.current.map(a => `${a.id}:${a.reference_take_id || 'none'}`).sort().join(',');
      
      if (angleSignature === prevAngleSignature) {
        return; // No change in angles
      }

      loadingAnglesRef.current = true;

      try {
        const enrichedAngles = await Promise.all(angles.map(async (angle) => {
          const takes = await api.getTakes(angle.id);
          const takesList = Array.isArray(takes) ? takes : [];
          takesList.sort((a, b) => a.id - b.id);
          
          return {
            ...angle,
            takes: takesList
          };
        }));
        
        // Sort angles by creation order (most recent first)
        enrichedAngles.sort((a, b) => {
          const dateA = a.created_at ? new Date(a.created_at) : new Date(0);
          const dateB = b.created_at ? new Date(b.created_at) : new Date(0);
          return dateB - dateA;
        });
        
        setAnglesWithTakes(enrichedAngles);
        prevAnglesRef.current = angles;
      } finally {
        loadingAnglesRef.current = false;
      }
    };

    loadAnglesWithTakes();
  }, [angles]);

  // Register refresh function
  useEffect(() => {
    if (onSetRefresh) {
      const unregister = onSetRefresh(() => refetchAngles());
      return () => {
        if (typeof unregister === 'function') {
          unregister();
        }
      };
    }
  }, [onSetRefresh]); // Don't include refetchAngles to avoid loops

  const handleRenameAngle = useCallback(async (angleId, newName) => {
    try {
      await updateAngleMutation.mutateAsync({ angleId, data: { name: newName } });
      
      // Update the anglesWithTakes immediately for instant UI feedback
      setAnglesWithTakes(prev => prev.map(angle => 
        angle.id === angleId ? { ...angle, name: newName } : angle
      ));
      
      // Refetch angles to ensure data consistency
      refetchAngles();
    } catch (error) {
      console.error('Error renaming angle:', error);
      alert('Failed to rename angle: ' + error.message);
    }
  }, [updateAngleMutation, refetchAngles]);

  const toggleAngleCollapse = useCallback((angleId) => {
    setCollapsedAngles(prev => ({
      ...prev,
      [angleId]: !prev[angleId]
    }));
  }, []);

  const handleCreateTake = useCallback(async (takeName, angleId, existingTakeId = null) => {
    try {
      let take;
      
      if (existingTakeId) {
        // Fetch the full take details from the backend to get the is_reference flag
        take = await api.getTake(existingTakeId);
      } else {
        take = await createTakeMutation.mutateAsync({
          angleId: parseInt(angleId, 10),  // Changed from angle_id to angleId
          name: takeName
        });
      }
      
      setShowNewTakeModal(false);
      
      // Refetch angles to ensure the UI is updated with the new take
      await refetchAngles();
      
      // Find the angle to get its name
      const angle = anglesWithTakes.find(a => a.id === angleId);
      
      // Navigate to the newly created take
      onNavigate('monitoring', {
        projectId,
        projectName,
        sceneId,
        sceneName,
        angleId: angleId,
        angleName: angle ? angle.name : '',
        takeId: take.id,
        takeName: take.name || takeName,
        isReference: take.is_reference || !angle?.takes || angle.takes.length === 0
      });
      
    } catch (error) {
      console.error('Error creating take:', error);
      alert('Failed to create take: ' + error.message);
    }
  }, [anglesWithTakes, createTakeMutation, onNavigate, projectId, projectName, sceneId, sceneName, refetchAngles]);

  const handleCreateAngle = useCallback(async (angleName) => {
    try {
      const newAngle = await createAngleMutation.mutateAsync({
        scene_id: parseInt(sceneId, 10),  // Ensure it's a number
        name: angleName
      });
      
      if (!newAngle || !newAngle.id) {
        throw new Error('Invalid response from server');
      }
      
      return newAngle;
    } catch (error) {
      console.error('Error creating angle:', error);
      throw error;
    }
  }, [sceneId, createAngleMutation]);

  const handleTakeClick = useCallback((take, angle) => {
    onNavigate('monitoring', {
      projectId,
      projectName,
      sceneId,
      sceneName,
      angleId: angle.id,
      angleName: angle.name,
      takeId: take.id,
      takeName: take.name,
      isReference: take.is_reference
    });
  }, [projectId, projectName, sceneId, sceneName, onNavigate]);

  const handleRenameTake = useCallback(async (takeId, newName) => {
    try {
      await updateTakeMutation.mutateAsync({ takeId, data: { name: newName } });
      
      // Update the anglesWithTakes immediately for instant UI feedback
      setAnglesWithTakes(prev => prev.map(angle => ({
        ...angle,
        takes: angle.takes.map(take => 
          take.id === takeId ? { ...take, name: newName } : take
        )
      })));
      
      // Refetch angles to ensure data consistency
      refetchAngles();
    } catch (error) {
      console.error('Error renaming take:', error);
      alert('Failed to rename take: ' + error.message);
    }
  }, [updateTakeMutation, refetchAngles]);

  const handleDeleteTake = useCallback(async () => {
    try {
      const takeId = selectedTake.id;
      await deleteTakeMutation.mutateAsync(takeId);
      
      // Update the anglesWithTakes immediately for instant UI feedback
      setAnglesWithTakes(prev => prev.map(angle => ({
        ...angle,
        takes: angle.takes.filter(take => take.id !== takeId)
      })));
      
      setShowDeleteModal(false);
      setSelectedTake(null);
      
      // Refetch angles to ensure data consistency
      refetchAngles();
    } catch (error) {
      console.error('Error deleting take:', error);
      alert('Failed to delete take: ' + error.message);
    }
  }, [selectedTake, deleteTakeMutation, refetchAngles]);

  const handleMakeReference = useCallback(async () => {
    try {
      await setReferenceTakeMutation.mutateAsync(pendingReferenceTake.id);
      
      // Update the local state immediately for instant UI feedback
      setAnglesWithTakes(prev => prev.map(angle => {
        // Find the angle that contains this take
        const hasTake = angle.takes.some(t => t.id === pendingReferenceTake.id);
        if (hasTake) {
          return {
            ...angle,
            reference_take_id: pendingReferenceTake.id,
            takes: angle.takes.map(take => ({
              ...take,
              is_reference: take.id === pendingReferenceTake.id
            }))
          };
        }
        return angle;
      }));
      
      setShowReferenceConfirm(false);
      setPendingReferenceTake(null);
      
      // Refetch angles to ensure data consistency
      refetchAngles();
    } catch (error) {
      console.error('Error setting reference take:', error);
      alert('Failed to set reference take: ' + error.message);
    }
  }, [pendingReferenceTake, setReferenceTakeMutation, refetchAngles]);

  const handleExportTake = useCallback(async (take) => {
    const filePath = await save({
      defaultPath: `${take.name}_report.pdf`,
      filters: [{
        name: 'PDF',
        extensions: ['pdf']
      }]
    });
    
    if (filePath) {
      await exportTakeWithGuard(take.id, take.name, filePath);
    }
  }, [exportTakeWithGuard]);

  const handleExportScene = useCallback(async () => {
    const filePath = await save({
      defaultPath: `${sceneName}_report.pdf`,
      filters: [{
        name: 'PDF',
        extensions: ['pdf']
      }]
    });
    
    if (filePath) {
      await exportSceneWithGuard(
        sceneId, 
        sceneName, 
        filePath,
        async () => {
          for (const angle of anglesWithTakes) {
            if (angle.takes && angle.takes.length > 0) {
              return true;
            }
          }
          return false;
        }
      );
    }
  }, [anglesWithTakes, sceneName, sceneId, exportSceneWithGuard]);

  const handleSceneSettings = useCallback(async (config) => {
    try {
      await updateSceneMutation.mutateAsync({
        sceneId,
        data: {
          image_quality: config.quality
        }
      });
      setShowSceneConfigModal(false);
    } catch (error) {
      console.error('Error updating scene settings:', error);
      alert('Failed to update scene settings');
    }
  }, [sceneId, updateSceneMutation]);

  const renderTakeGrid = useCallback((takes, angle) => {
    const columns = 5;
    const rows = Math.ceil(takes.length / columns);
    
    return (
      <div className="px-4 py-3">
        {Array.from({ length: rows }).map((_, rowIndex) => (
          <div key={rowIndex} className="flex">
            {Array.from({ length: columns }).map((_, colIndex) => {
              const takeIndex = rowIndex * columns + colIndex;
              const take = takes[takeIndex];
              
              return (
                <div 
                  key={colIndex} 
                  className={`flex-1 py-2 ${colIndex > 0 ? 'border-l-[0.25px] border-black' : ''}`}
                >
                  {take ? (
                    <div 
                      className="flex items-center px-4 cursor-pointer hover:bg-gray-50"
                      onClick={() => handleTakeClick(take, angle)}
                    >
                      <div className="flex items-center gap-2 flex-1">
                        {take.is_reference ? (
                          <Star size={16} fill="black" />
                        ) : (
                          <div className="w-4"></div>
                        )}
                        <span className="text-14 truncate max-w-[200px] block" title={take.name}>
                          {take.name.replace(/^temp#\d+_/, '')}
                        </span>
                      </div>
                      
                      <div className="relative ml-8 z-50" ref={showDropdown === `${angle.id}-${take.id}` ? dropdownRef : null}>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setShowDropdown(showDropdown === `${angle.id}-${take.id}` ? null : `${angle.id}-${take.id}`);
                          }}
                          className="w-8 h-8 flex items-center justify-center btn-hover rounded"
                        >
                          <svg width="16" height="4" viewBox="0 0 16 4" fill="none">
                            <circle cx="2" cy="2" r="1.5" fill="black"/>
                            <circle cx="8" cy="2" r="1.5" fill="black"/>
                            <circle cx="14" cy="2" r="1.5" fill="black"/>
                          </svg>
                        </button>
                        
                        {showDropdown === `${angle.id}-${take.id}` && (
                          <div 
                            className="absolute right-0 top-full mt-1 bg-white border border-gray-200 rounded shadow-lg z-[9999] w-48"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <button 
                              onClick={(e) => {
                                e.stopPropagation();
                                setShowDropdown(null);
                                setSelectedTake(take);
                                setShowRenameModal(true);
                              }}
                              className="block w-full text-left px-4 py-2 hover:bg-gray-100 text-14"
                            >
                              Rename take
                            </button>
                            <button 
                              onClick={(e) => {
                                e.stopPropagation();
                                setShowDropdown(null);
                                handleExportTake(take);
                              }}
                              className="block w-full text-left px-4 py-2 hover:bg-gray-100 text-14"
                            >
                              Export take
                            </button>
                            {!take.is_reference && (
                              <button 
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setShowDropdown(null);
                                  setPendingReferenceTake(take);
                                  setShowReferenceConfirm(true);
                                }}
                                className="block w-full text-left px-4 py-2 hover:bg-gray-100 text-14"
                              >
                                Make reference
                              </button>
                            )}
                            <button 
                              onClick={(e) => {
                                e.stopPropagation();
                                setShowDropdown(null);
                                setSelectedTake(take);
                                setShowDeleteModal(true);
                              }}
                              className="block w-full text-left px-4 py-2 hover:bg-gray-100 text-14 text-red-600"
                            >
                              Delete take
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className="px-4">&nbsp;</div>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    );
  }, [handleTakeClick, handleExportTake, showDropdown, setShowDropdown, setSelectedTake, setShowRenameModal, setPendingReferenceTake, setShowReferenceConfirm, setShowDeleteModal]);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-9 py-6">
        <div className="flex items-center gap-4">
          <h1 className="text-18 font-semibold truncate max-w-[400px] block" title={sceneName}>{sceneName}</h1>
          <button 
            onClick={() => setShowNewTakeModal(true)}
            className="bg-primary text-white px-3 py-1.5 rounded-[10px] h-8 flex items-center justify-center btn-hover"
          >
            <span className="text-14 font-medium">New Take</span>
          </button>
        </div>

        {/* Right side buttons */}
        <div className="flex items-center gap-3">
          <button 
            onClick={handleExportScene}
            className="flex items-center gap-2 px-3 py-1.5 btn-hover"
            title="Export Scene"
          >
            <FileText size={20} strokeWidth={1.5} />
            <span className="text-14">Export</span>
          </button>
          
          <button 
            onClick={() => setShowSceneConfigModal(true)}
            className="flex items-center gap-2 px-3 py-1.5 btn-hover"
            title="Scene Settings"
          >
            <Settings size={20} strokeWidth={1.5} />
            <span className="text-14">Scene Settings</span>
          </button>
          
          <button 
            onClick={() => setShowDetectorConfigModal(true)}
            className="flex items-center gap-2 px-3 py-1.5 btn-hover"
            title="Detector Configuration"
          >
            <Cpu size={20} strokeWidth={1.5} />
            <span className="text-14">Detector Config</span>
          </button>
        </div>
      </div>

      {/* Angles and Takes */}
      <div className="flex-1 overflow-y-auto px-9 pb-6">
        {anglesWithTakes.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <p className="text-gray-500">No takes found. Create a new take to get started!</p>
          </div>
        ) : (
          <div className="space-y-4">
            {anglesWithTakes.map((angle) => (
              <div key={angle.id}>
                {/* Angle header */}
                <div className="flex items-center">
                  <div className="flex items-center gap-2">
                    <h3 className="text-16 font-medium truncate max-w-[300px] block" title={angle.name}>{angle.name}</h3>
                    
                    <button 
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedAngle(angle);
                        setShowAngleRenameModal(true);
                      }}
                      className="w-6 h-6 flex items-center justify-center btn-hover"
                      title="Rename angle"
                    >
                      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                        <path d="M11.5 2.5L13.5 4.5L11.5 2.5ZM12.5 1.5L8 6L7 9L10 8L14.5 3.5C14.8 3.2 15 2.8 15 2.5C15 2.2 14.8 1.8 14.5 1.5C14.2 1.2 13.8 1 13.5 1C13.2 1 12.8 1.2 12.5 1.5V1.5Z" stroke="black" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                        <path d="M13 9V13C13 13.5 12.5 14 12 14H3C2.5 14 2 13.5 2 13V4C2 3.5 2.5 3 3 3H7" stroke="black" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    </button>
                  </div>
                  
                  <div className="flex-1 mx-4 h-px bg-black"></div>
                  <button
                    onClick={() => toggleAngleCollapse(angle.id)}
                    className="w-8 h-8 flex items-center justify-center btn-hover"
                  >
                    {collapsedAngles[angle.id] ? (
                      <ChevronDown size={16} strokeWidth={2} />
                    ) : (
                      <ChevronUp size={16} strokeWidth={2} />
                    )}
                  </button>
                </div>
                
                {/* Takes grid */}
                {!collapsedAngles[angle.id] && (
                  angle.takes.length > 0 ? (
                    renderTakeGrid(angle.takes, angle)
                  ) : (
                    <div className="px-4 py-4 text-14 text-gray-500">
                      No takes in this angle
                    </div>
                  )
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Modals */}
      {showNewTakeModal && (
        <NewTakeModal
          angles={anglesWithTakes}
          sceneId={sceneId}
          onClose={() => setShowNewTakeModal(false)}
          onCreate={handleCreateTake}
          onCreateAngle={handleCreateAngle}
        />
      )}

      {showSceneConfigModal && sceneData && (
        <SceneConfigModal
          sceneName={sceneName}
          initialFps={sceneData.frame_rate}
          initialQuality={sceneData.image_quality}
          editMode={true}
          onBack={null}
          onNext={handleSceneSettings}
          onClose={() => setShowSceneConfigModal(false)}
        />
      )}

      {showDetectorConfigModal && (
        <DetectorConfigModal
          sceneName={sceneName}
          sceneConfig={sceneData}
          sceneId={sceneId}
          editMode={true}
          onBack={null}
          onCreate={async () => {
            setShowDetectorConfigModal(false);
          }}
          onClose={() => setShowDetectorConfigModal(false)}
        />
      )}

      {showRenameModal && selectedTake && (
        <RenameModal
          title="Rename Take"
          currentName={selectedTake.name}
          onClose={() => {
            setShowRenameModal(false);
            setSelectedTake(null);
          }}
          onSave={(newName) => {
            handleRenameTake(selectedTake.id, newName);
            setShowRenameModal(false);
            setSelectedTake(null);
          }}
        />
      )}

      {showDeleteModal && selectedTake && (
        <ConfirmModal
          title="Delete Take"
          message={`Are you sure you want to delete "${selectedTake.name}"? This action cannot be undone.`}
          confirmText="Delete"
          onConfirm={handleDeleteTake}
          onCancel={() => {
            setShowDeleteModal(false);
            setSelectedTake(null);
          }}
        />
      )}

      {showAngleRenameModal && selectedAngle && (
        <RenameModal
          title="Rename Angle"
          currentName={selectedAngle.name}
          onClose={() => {
            setShowAngleRenameModal(false);
            setSelectedAngle(null);
          }}
          onSave={(newName) => {
            handleRenameAngle(selectedAngle.id, newName);
            setShowAngleRenameModal(false);
            setSelectedAngle(null);
          }}
        />
      )}

      {showReferenceConfirm && pendingReferenceTake && (
        <ConfirmModal
          title="Set Reference Take"
          message={`Making "${pendingReferenceTake.name}" the reference take will remove the previous reference designation. Do you want to proceed?`}
          confirmText="Yes"
          cancelText="No"
          onConfirm={handleMakeReference}
          onCancel={() => {
            setShowReferenceConfirm(false);
            setPendingReferenceTake(null);
          }}
        />
      )}
    </div>
  );
}
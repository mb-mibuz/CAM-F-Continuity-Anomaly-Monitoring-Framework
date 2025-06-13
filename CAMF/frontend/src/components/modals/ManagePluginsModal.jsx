import React, { useState } from 'react';
import { open as openPath } from '@tauri-apps/api/shell';
import { homeDir } from '@tauri-apps/api/path';
import { useQueryClient } from '@tanstack/react-query';
import ModalBase from './ModalBase';
import ConfirmModal from './ConfirmModal';
import UploadDetectorsModal from './UploadDetectorsModal';
import { useInstalledDetectors } from '../../queries/hooks';
import { DetectorService } from '../../services';
import { useAppStore } from '../../stores';
import { buildApiUrl } from '../../config';
import { queryKeys } from '../../queries/keys';

export default function ManagePluginsModal({ onClose }) {
  const [showDropdown, setShowDropdown] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState({ show: false, directoryName: null, displayName: null });
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showUpdateModal, setShowUpdateModal] = useState(false);
  const [updateDetectorName, setUpdateDetectorName] = useState(null);
  
  const addNotification = useAppStore(state => state.addNotification);
  const refresh = useAppStore(state => state.refresh);
  const detectorService = DetectorService.getInstance();
  const queryClient = useQueryClient();
  
  // Use React Query hook
  const { data: installedDetectors = [], isLoading, refetch } = useInstalledDetectors();
  
  const confirmDeleteDetector = async () => {
    const { directoryName, displayName } = deleteConfirm;
    setDeleteConfirm({ show: false, directoryName: null, displayName: null });
    
    try {
      await detectorService.uninstallDetector(directoryName);
      await refetch(); // Refresh the list
      addNotification({
        type: 'success',
        message: `Successfully deleted "${displayName}"`
      });
    } catch (error) {
      console.error('Error deleting detector:', error);
      addNotification({
        type: 'error',
        message: error.message || 'Failed to delete detector'
      });
    }
  };
  
  const handleOpenLocation = async (detectorName) => {
    try {
      // Get the detector location from the API
      const response = await detectorService.getDetectorLocation(detectorName);
      const location = response.location;
      
      if (!location || !response.exists) {
        addNotification({
          type: 'warning',
          message: 'Detector folder not found.'
        });
        return;
      }
      
      // Use Tauri's invoke to open the folder
      const { invoke } = await import('@tauri-apps/api/tauri');
      await invoke('open_folder', { path: location }).catch(async (error) => {
        console.error('Failed to open with invoke:', error);
        // Fallback to shell open
        await openPath(location).catch((err) => {
          console.error('Failed to open with shell:', err);
          addNotification({
            type: 'error',
            message: 'Unable to open detector location. Please check your file manager.'
          });
        });
      });
    } catch (error) {
      console.error('Error opening location:', error);
      addNotification({
        type: 'error',
        message: 'Unable to get detector location.'
      });
    }
  };
  
  const formatInstallDate = (detector) => {
    // Try multiple possible date fields
    const dateFields = [
      'install_timestamp',
      'install_time',
      'installed_at',
      'installation_date',
      'created_at',
      'install_date',
      'date_installed'
    ];
    
    let dateValue = null;
    for (const field of dateFields) {
      if (detector[field]) {
        dateValue = detector[field];
        break;
      }
    }
    
    // Check metadata
    if (!dateValue && detector.metadata) {
      dateValue = detector.metadata.install_timestamp || 
                 detector.metadata.install_time || 
                 detector.metadata.installed_at;
    }
    
    if (!dateValue) {
      return 'Unknown date';
    }
    
    try {
      let date;
      if (typeof dateValue === 'number' || !isNaN(dateValue)) {
        // Numeric timestamp (in seconds)
        date = new Date(parseFloat(dateValue) * 1000);
      } else {
        // String date
        date = new Date(dateValue);
      }
      
      if (isNaN(date.getTime())) {
        return 'Unknown date';
      }
      
      return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
      });
    } catch (error) {
      console.error('Error formatting date:', error);
      return 'Unknown date';
    }
  };
  
  const handleUploadSuccess = () => {
    refetch(); // Refresh the list
    setShowUploadModal(false);
    setShowUpdateModal(false);
    setUpdateDetectorName(null);
  };
  
  const handleUpdateClick = (detectorName) => {
    setUpdateDetectorName(detectorName);
    setShowUpdateModal(true);
    setShowDropdown(null);
  };
  
  const handleCleanupOrphaned = async () => {
    try {
      const response = await fetch(buildApiUrl('api/detectors/cleanup'), {
        method: 'POST'
      });
      
      if (!response.ok) {
        throw new Error('Cleanup failed');
      }
      
      const result = await response.json();
      
      if (result.total_cleaned > 0) {
        addNotification({
          type: 'success',
          message: `Cleaned up ${result.total_cleaned} orphaned detector${result.total_cleaned > 1 ? 's' : ''}`
        });
        
        // Refresh the detector list
        refetch();
        
        // Also invalidate detector queries to refresh everywhere
        queryClient.invalidateQueries({ queryKey: queryKeys.detectors.list() });
      } else {
        addNotification({
          type: 'info',
          message: 'No orphaned detectors found'
        });
      }
      
      if (result.errors && result.errors.length > 0) {
        console.error('Cleanup errors:', result.errors);
      }
    } catch (error) {
      console.error('Error cleaning up detectors:', error);
      addNotification({
        type: 'error',
        message: 'Failed to clean up orphaned detectors'
      });
    }
  };
  
  const getDetectorDisplayName = (detector) => {
    return detector.display_name || detector.detector_name || detector.name || 'Unknown Detector';
  };
  
  const getDetectorDirectoryName = (detector) => {
    return detector.directory_name || detector.detector_dir_name || detector.detector_name || detector.name;
  };
  
  const getDetectorVersion = (detector) => {
    return detector.version || '1.0.0';
  };
  
  return (
    <>
      <ModalBase onClose={onClose} size="large">
        <div className="p-8 h-[600px] flex flex-col">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-2">
              <h2 className="text-18 font-semibold">Manage Plugins</h2>
              <button
                onClick={() => setShowUploadModal(true)}
                className="w-8 h-8 flex items-center justify-center btn-hover rounded border border-gray-300"
                title="Upload Detectors"
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M8 12V4M8 4L5 7M8 4L11 7" stroke="black" strokeWidth="1.5" strokeLinecap="round"/>
                  <path d="M14 14H2" stroke="black" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
              </button>
            </div>
            <button
              onClick={handleCleanupOrphaned}
              className="px-3 py-1 text-12 border border-gray-300 rounded btn-hover"
              title="Clean up orphaned detector files"
            >
              Clean Up
            </button>
          </div>
          
          {/* Installed detectors */}
          <div className="flex-1 overflow-y-auto min-h-0">
            {isLoading ? (
              <div className="flex items-center justify-center h-full">
                <p className="text-14 text-gray-500">Loading detectors...</p>
              </div>
            ) : installedDetectors.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full">
                <svg width="64" height="64" viewBox="0 0 64 64" fill="none" className="mb-4">
                  <rect x="8" y="8" width="48" height="48" rx="4" stroke="#D1D5DB" strokeWidth="2"/>
                  <path d="M24 32L32 40L40 24" stroke="#D1D5DB" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                <p className="text-16 text-gray-500 mb-2">No detectors installed</p>
                <p className="text-14 text-gray-400">Click the upload icon to add new plugins</p>
              </div>
            ) : (
              <div className="space-y-3">
                {installedDetectors.map((detector, index) => (
                  <div key={getDetectorDirectoryName(detector)} className="flex items-center justify-between border border-gray-200 rounded-lg p-4">
                    <div className="flex-1">
                      <h4 className="text-14 font-medium">{getDetectorDisplayName(detector)}</h4>
                      <p className="text-12 text-gray-600">
                        Version {getDetectorVersion(detector)} • Installed {formatInstallDate(detector)}
                      </p>
                    </div>
                    
                    <div className="relative">
                      <button 
                        onClick={(e) => {
                          e.stopPropagation();
                          setShowDropdown(showDropdown === index ? null : index);
                        }}
                        className="w-8 h-8 flex items-center justify-center btn-hover rounded"
                      >
                        <svg width="4" height="16" viewBox="0 0 4 16" fill="none">
                          <circle cx="2" cy="2" r="1.5" fill="black"/>
                          <circle cx="2" cy="8" r="1.5" fill="black"/>
                          <circle cx="2" cy="14" r="1.5" fill="black"/>
                        </svg>
                      </button>
                      
                      {showDropdown === index && (
                        <div className="absolute right-0 top-full mt-1 bg-white border border-gray-200 rounded shadow-lg z-10 w-40">
                          <button 
                            onClick={() => {
                              handleOpenLocation(getDetectorDirectoryName(detector));
                              setShowDropdown(null);
                            }}
                            className="block w-full text-left px-4 py-2 hover:bg-gray-100 text-14"
                          >
                            Open location
                          </button>
                          <button 
                            onClick={() => {
                              handleUpdateClick(getDetectorDirectoryName(detector));
                            }}
                            className="block w-full text-left px-4 py-2 hover:bg-gray-100 text-14"
                          >
                            Update
                          </button>
                          <button 
                            onClick={() => {
                              setDeleteConfirm({ 
                                show: true, 
                                directoryName: getDetectorDirectoryName(detector),
                                displayName: getDetectorDisplayName(detector)
                              });
                              setShowDropdown(null);
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
        </div>
      </ModalBase>

      {/* Upload modal */}
      {showUploadModal && (
        <UploadDetectorsModal 
          onClose={() => setShowUploadModal(false)}
          onSuccess={handleUploadSuccess}
        />
      )}

      {/* Update modal */}
      {showUpdateModal && (
        <UploadDetectorsModal 
          onClose={() => {
            setShowUpdateModal(false);
            setUpdateDetectorName(null);
          }}
          onSuccess={handleUploadSuccess}
          updateMode={true}
          detectorName={updateDetectorName}
        />
      )}

      {/* Delete detector confirmation modal */}
      {deleteConfirm.show && (
        <ConfirmModal
          title="Delete Detector"
          message={`Are you sure you want to delete "${deleteConfirm.displayName}"? This action cannot be undone.`}
          confirmText="Delete"
          cancelText="Cancel"
          onConfirm={confirmDeleteDetector}
          onCancel={() => setDeleteConfirm({ show: false, directoryName: null, displayName: null })}
        />
      )}
    </>
  );
}
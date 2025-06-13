import React, { useState, useCallback } from 'react';
import { Cpu, ChevronDown, ChevronRight } from 'lucide-react';
import { useAppStore } from '../../../stores';
import { api } from '../../../utils/api';
import DetectorErrorList from '../../../components/monitoring/DetectorErrorList';

export default function DetectorPanel({
  takeId,
  sceneId,
  sceneName,
  errors,
  frameCount,
  isDisabled,
  onErrorClick,
  onMarkFalsePositive
}) {
  const [collapsedErrors, setCollapsedErrors] = useState({});
  const [sortBy, setSortBy] = useState('frame_id');
  const [sortOrder, setSortOrder] = useState('asc');
  
  const { openModal } = useAppStore();

  // Handle error group collapse/expand
  const handleToggleCollapse = useCallback((errorId) => {
    setCollapsedErrors(prev => ({
      ...prev,
      [errorId]: !prev[errorId]
    }));
  }, []);

  // Handle sorting
  const handleSort = useCallback((field) => {
    if (isDisabled) return;
    
    if (sortBy === field) {
      setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(field);
      setSortOrder('asc');
    }
  }, [sortBy, isDisabled]);

  // Handle configure detectors
  const handleConfigureDetectors = useCallback(async () => {
    try {
      // Fetch fresh scene data to get latest detector configs
      const freshSceneData = await api.getScene(sceneId);
      // Fresh scene data fetched for detector config
      
      openModal('detectorConfig', {
        sceneId,
        sceneName: sceneName || freshSceneData?.name || '',
        editMode: true
      });
    } catch (error) {
      console.error('Failed to fetch scene data:', error);
      // Fall back to provided scene name
      openModal('detectorConfig', {
        sceneId,
        sceneName,
        editMode: true
      });
    }
  }, [sceneId, sceneName, openModal]);

  // Sort errors
  const sortedErrors = [...errors].sort((a, b) => {
    const aValue = a.instances ? a.instances[0][sortBy] : a[sortBy];
    const bValue = b.instances ? b.instances[0][sortBy] : b[sortBy];
    
    if (sortBy === 'frame_id') {
      return sortOrder === 'asc' ? aValue - bValue : bValue - aValue;
    }
    
    return sortOrder === 'asc'
      ? String(aValue).localeCompare(String(bValue))
      : String(bValue).localeCompare(String(aValue));
  });

  return (
    <div className="border border-gray-300 rounded-lg bg-white h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
        <h3 className="text-14 font-medium">Detected Errors</h3>
        <button
          onClick={handleConfigureDetectors}
          disabled={isDisabled}
          className={`
            flex items-center gap-2 text-14
            ${isDisabled
              ? 'text-gray-400 cursor-not-allowed'
              : 'text-primary hover:opacity-80'
            }
          `}
        >
          <span>Configure Detectors</span>
          <Cpu size={16} />
        </button>
      </div>

      {/* Column headers */}
      <div className="flex items-center px-4 py-2 border-b border-gray-200 bg-gray-50 text-11">
        <div className="w-8" /> {/* Expand/collapse icon */}
        
        <button
          onClick={() => handleSort('description')}
          disabled={isDisabled}
          className={`
            flex-1 text-left font-medium uppercase
            ${isDisabled ? 'cursor-not-allowed' : 'hover:text-primary'}
          `}
        >
          Error Description
          {sortBy === 'description' && (
            <span className="ml-1">{sortOrder === 'asc' ? '↑' : '↓'}</span>
          )}
        </button>
        
        <button
          onClick={() => handleSort('detector_name')}
          disabled={isDisabled}
          className={`
            w-32 text-left font-medium uppercase
            ${isDisabled ? 'cursor-not-allowed' : 'hover:text-primary'}
          `}
        >
          Detector
          {sortBy === 'detector_name' && (
            <span className="ml-1">{sortOrder === 'asc' ? '↑' : '↓'}</span>
          )}
        </button>
        
        <button
          onClick={() => handleSort('frame_id')}
          disabled={isDisabled}
          className={`
            w-20 text-left font-medium uppercase
            ${isDisabled ? 'cursor-not-allowed' : 'hover:text-primary'}
          `}
        >
          Frame
          {sortBy === 'frame_id' && (
            <span className="ml-1">{sortOrder === 'asc' ? '↑' : '↓'}</span>
          )}
        </button>
        
        <div className="w-24 text-left font-medium uppercase">
          Confidence
        </div>
        
        <div className="w-8" /> {/* False positive flag */}
      </div>

      {/* Error list */}
      <div className="flex-1 overflow-y-auto">
        {sortedErrors.length === 0 ? (
          <div className="flex items-center justify-center py-8 text-gray-500">
            {frameCount === 0 ? 'No frames captured yet' : 'No errors detected'}
          </div>
        ) : (
          <DetectorErrorList
            errors={sortedErrors}
            collapsedErrors={collapsedErrors}
            onToggleCollapse={handleToggleCollapse}
            onErrorClick={onErrorClick}
            onMarkFalsePositive={onMarkFalsePositive}
            isDisabled={isDisabled}
          />
        )}
      </div>
      
      {/* Summary footer */}
      {errors.length > 0 && (
        <div className="px-4 py-2 border-t border-gray-200 bg-gray-50">
          <div className="flex items-center justify-between text-12 text-gray-600">
            <span>
              {errors.length} error{errors.length !== 1 ? 's' : ''} detected
            </span>
            <span>
              {errors.reduce((sum, error) => sum + (error.instances?.length || 1), 0)} total instances
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
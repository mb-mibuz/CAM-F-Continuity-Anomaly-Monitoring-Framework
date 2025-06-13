// src/components/monitoring/DetectorLogSection.jsx
import React from 'react';
import { Cpu, ChevronDown, ChevronRight } from 'lucide-react';

export default function DetectorLogSection({
  detectorErrors,
  collapsedErrors,
  errorSortBy,
  errorSortOrder,
  onToggleCollapse,
  onSortChange,
  onErrorClick,
  onConfigureDetectors,
  frameCount,
  isDisabled = false
}) {
  const sortErrors = (errors) => {
    const sorted = [...errors].sort((a, b) => {
      const aValue = a.instances ? a.instances[0][errorSortBy] : a[errorSortBy];
      const bValue = b.instances ? b.instances[0][errorSortBy] : b[errorSortBy];
      
      if (errorSortBy === 'frame_id') {
        return errorSortOrder === 'asc' ? aValue - bValue : bValue - aValue;
      }
      
      return errorSortOrder === 'asc' 
        ? String(aValue).localeCompare(String(bValue))
        : String(bValue).localeCompare(String(aValue));
    });
    
    return sorted;
  };

  const getConfidenceColor = (confidence) => {
    switch (confidence) {
      case 1: return 'text-red-600';
      case 2: return 'text-yellow-600';
      default: return 'text-gray-600';
    }
  };

  const handleSort = (field) => {
    if (isDisabled) return;
    
    if (errorSortBy === field) {
      onSortChange(field, errorSortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      onSortChange(field, 'asc');
    }
  };

  const sortedErrors = sortErrors(detectorErrors);

  return (
    <div className="border border-gray-300 rounded h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-300">
        <h3 className="text-14 font-medium">Detected</h3>
        <button 
          onClick={onConfigureDetectors}
          disabled={isDisabled}
          className={`flex items-center gap-2 text-14 ${
            isDisabled
              ? 'text-gray-400 cursor-not-allowed'
              : 'hover:opacity-80'
          }`}
        >
          Configure Detectors
          <Cpu size={16} />
        </button>
      </div>

      {/* Column headers */}
      <div className="flex items-center px-4 py-2 border-b border-gray-300 bg-gray-50">
        <div className="w-8"></div>
        <button 
          onClick={() => handleSort('description')}
          disabled={isDisabled}
          className={`flex-1 text-left text-12 font-medium uppercase ${
            isDisabled ? 'cursor-not-allowed' : 'hover:opacity-80'
          }`}
        >
          Error Description
          {errorSortBy === 'description' && (
            <span className="ml-1">{errorSortOrder === 'asc' ? '↑' : '↓'}</span>
          )}
        </button>
        <button 
          onClick={() => handleSort('detector_name')}
          disabled={isDisabled}
          className={`w-32 text-left text-12 font-medium uppercase ${
            isDisabled ? 'cursor-not-allowed' : 'hover:opacity-80'
          }`}
        >
          Detector
          {errorSortBy === 'detector_name' && (
            <span className="ml-1">{errorSortOrder === 'asc' ? '↑' : '↓'}</span>
          )}
        </button>
        <button 
          onClick={() => handleSort('frame_id')}
          disabled={isDisabled}
          className={`w-20 text-left text-12 font-medium uppercase ${
            isDisabled ? 'cursor-not-allowed' : 'hover:opacity-80'
          }`}
        >
          Frame
          {errorSortBy === 'frame_id' && (
            <span className="ml-1">{errorSortOrder === 'asc' ? '↑' : '↓'}</span>
          )}
        </button>
        <div className="w-24 text-left text-12 font-medium uppercase">
          Confidence
        </div>
      </div>

      {/* Error list */}
      <div className="flex-1 overflow-y-auto">
        {sortedErrors.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-500">
            {frameCount === 0 ? 'No frames captured yet' : 'No errors detected'}
          </div>
        ) : (
          sortedErrors.map((error) => {
            const hasInstances = error.instances && error.instances.length > 1;
            const isCollapsed = collapsedErrors[error.id];
            const frameId = error.instances ? error.instances[0].frame_id : error.frame_id;
            const confidence = error.instances ? error.instances[0].confidence : error.confidence;
            
            return (
              <div key={error.id}>
                <div 
                  className={`flex items-center px-4 py-2 border-b-0.5 border-gray-200 ${
                    isDisabled ? '' : 'hover:bg-gray-50 cursor-pointer'
                  }`}
                  onClick={() => !isDisabled && onErrorClick(error)}
                >
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (!isDisabled && hasInstances) {
                        onToggleCollapse(error.id);
                      }
                    }}
                    className={`w-8 ${!hasInstances || isDisabled ? 'invisible' : ''}`}
                  >
                    {isCollapsed ? (
                      <ChevronRight size={16} className="text-gray-400" />
                    ) : (
                      <ChevronDown size={16} className="text-gray-400" />
                    )}
                  </button>
                  <div className="flex-1 text-14">{error.description}</div>
                  <div className="w-32 text-14">{error.detector_name}</div>
                  <div className="w-20 text-14">{frameId}</div>
                  <div className={`w-24 text-14 ${getConfidenceColor(confidence)}`}>
                    {confidence === 1 ? 'Error' : 'Likely Error'}
                  </div>
                </div>
                
                {hasInstances && !isCollapsed && (
                  <div className="bg-gray-50">
                    {error.instances.map((instance, idx) => (
                      <div 
                        key={idx} 
                        className={`flex items-center px-4 py-1 ${
                          isDisabled ? '' : 'hover:bg-gray-100 cursor-pointer'
                        }`}
                        onClick={() => !isDisabled && onErrorClick({ ...error, frame_id: instance.frame_id })}
                      >
                        <div className="w-8"></div>
                        <div className="flex-1 text-14 text-gray-600">Instance {idx + 1}</div>
                        <div className="w-32"></div>
                        <div className="w-20 text-14">{instance.frame_id}</div>
                        <div className={`w-24 text-14 ${getConfidenceColor(instance.confidence)}`}>
                          {instance.confidence === 1 ? 'Error' : 'Likely Error'}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
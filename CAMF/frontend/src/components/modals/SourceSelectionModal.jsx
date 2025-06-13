import React, { useState, useEffect } from 'react';
import ModalBase from './ModalBase';
import { Monitor, Camera, AppWindow, Check, AlertCircle } from 'lucide-react';
import { useSourcePreview } from '../../hooks/useSourcePreview';
import { usePolling } from '../../hooks/usePolling';
import { useCaptureSources } from '../../queries/hooks';
import config, { buildApiUrl } from '../../config';

export default function SourceSelectionModal({ 
  availableSources, 
  onClose, 
  onSelectSource,
  currentSource 
}) {
  // Initialize with first available tab
  const [activeTab, setActiveTab] = useState(() => {
    // Default to monitor as it's most likely to be available
    return 'monitor';
  });
  const [hoveredTile, setHoveredTile] = useState(null);
  const [selectionError, setSelectionError] = useState(null);
  
  // Use the source preview hook
  const {
    availableSources: sources,
    selectSource,
    clearSource,
    refetchSources,
    isSourceAvailable
  } = useSourcePreview({
    autoStartPreview: false,
    previewQuality: 30,
    onSourceChange: null,
    onPreviewError: (error) => console.error('Preview error:', error)
  });
  
  // Use React Query for sources with polling
  const { data: querySources, refetch, isLoading, error } = useCaptureSources();
  
  // Debug logging
  useEffect(() => {
    console.log('SourceSelectionModal - querySources:', querySources);
    console.log('SourceSelectionModal - sources:', sources);
    console.log('SourceSelectionModal - isLoading:', isLoading);
    console.log('SourceSelectionModal - error:', error);
  }, [querySources, sources, isLoading, error]);
  
  // Poll for source updates
  usePolling(
    refetch,
    2000, // Poll every 2 seconds
    true,
    []
  );
  
  // Fetch sources on mount
  useEffect(() => {
    refetch();
  }, []);
  
  // Get sources for current tab
  const getSourcesForTab = (tab) => {
    // Use query data directly
    if (!querySources) return [];
    
    switch (tab) {
      case 'monitor':
        return querySources.monitors || [];
      case 'window':
        return querySources.windows || [];
      case 'camera':
        return querySources.cameras || [];
      default:
        return [];
    }
  };
  
  const handleSelectSource = async (sourceType, sourceId, sourceName) => {
    setSelectionError(null);
    try {
      // Convert monitor to screen for API compatibility
      const apiSourceType = sourceType === 'monitor' ? 'screen' : sourceType;
      console.log('handleSelectSource:', { sourceType, apiSourceType, sourceId, sourceName });
      
      // Use the selectSource method from the hook
      // This already sets the source via API and updates the store
      const success = await selectSource(apiSourceType, sourceId, sourceName);
      if (success) {
        // Just close the modal - source is already set
        onClose();
      } else {
        setSelectionError(`Failed to select ${sourceName}`);
      }
    } catch (error) {
      console.error('Source selection error:', error);
      setSelectionError(error.message || 'Failed to select source');
    }
  };
  
  const handleMouseEnter = (sourceType, sourceId) => {
    setHoveredTile(`${sourceType}-${sourceId}`);
  };
  
  const handleMouseLeave = () => {
    setHoveredTile(null);
  };
  
  const renderSourceTile = (source, type) => {
    const sourceId = source.id !== undefined ? source.id : source.handle;
    const key = `${type}-${sourceId}`;
    const isHovered = hoveredTile === key;
    const isSelected = currentSource && 
        currentSource.type === type && 
        currentSource.id === sourceId;
    const isAvailable = isSourceAvailable(sourceId);
    
    return (
      <SourceTile
        key={sourceId}
        source={source}
        type={type}
        isHovered={isHovered}
        isSelected={isSelected}
        isAvailable={isAvailable}
        onMouseEnter={() => handleMouseEnter(type, sourceId)}
        onMouseLeave={handleMouseLeave}
        onClick={() => {
          console.log('SourceTile clicked:', { type, sourceId, isAvailable });
          if (isAvailable) {
            handleSelectSource(type, sourceId, source.name || source.title);
          }
        }}
      />
    );
  };
  
  const renderEmptyState = (type) => {
    let icon, message, helpText;
    
    switch (type) {
      case 'monitor':
        icon = <Monitor size={64} />;
        message = 'No displays detected';
        helpText = 'Scanning for displays...';
        break;
      case 'window':
        icon = <AppWindow size={64} />;
        message = 'No windows available';
        helpText = 'Make sure you have applications open';
        break;
      case 'camera':
        icon = <Camera size={64} />;
        message = 'No cameras detected';
        helpText = 'Check if your camera is connected and not in use';
        break;
      default:
        icon = null;
        message = 'No sources available';
        helpText = 'Scanning for sources...';
    }
    
    return (
      <div className="flex flex-col items-center justify-center h-full py-16">
        <div className="text-gray-300 mb-4">{icon}</div>
        <p className="text-16 text-gray-500">{message}</p>
        <p className="text-12 text-gray-400 mt-2">{helpText}</p>
        <div className="mt-4">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
        </div>
      </div>
    );
  };
  
  const renderContent = () => {
    // Show loading state while fetching sources
    if (isLoading && !querySources) {
      return (
        <div className="flex flex-col items-center justify-center h-full py-16">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mb-4"></div>
          <p className="text-16 text-gray-500">Loading sources...</p>
        </div>
      );
    }
    
    // Show error state if there's an error
    if (error) {
      return (
        <div className="flex flex-col items-center justify-center h-full py-16">
          <p className="text-16 text-red-500 mb-4">Failed to load sources</p>
          <button 
            onClick={() => refetch()}
            className="px-4 py-2 bg-primary text-white rounded hover:opacity-80"
          >
            Retry
          </button>
        </div>
      );
    }
    
    const tabSources = getSourcesForTab(activeTab);
    
    if (!tabSources || tabSources.length === 0) {
      return renderEmptyState(activeTab);
    }
    
    return (
      <div className="grid grid-cols-2 gap-4">
        {tabSources.map(source => renderSourceTile(source, activeTab))}
      </div>
    );
  };
  
  return (
    <ModalBase onClose={onClose} size="large">
      <div className="flex flex-col h-[650px]">
        <div className="px-8 pt-8 pb-4">
          <h2 className="text-18 font-semibold">Select Source</h2>
          {selectionError && (
            <div className="mt-2 text-14 text-red-500 bg-red-100 px-3 py-2 rounded">
              {selectionError}
            </div>
          )}
        </div>
        
        <div className="flex border-b border-gray-300">
          <button
            onClick={() => setActiveTab('monitor')}
            className={`flex-1 py-4 text-14 font-medium transition-colors relative ${
              activeTab === 'monitor'
                ? 'text-primary'
                : 'text-gray-600 hover:text-black'
            }`}
          >
            <div className="flex items-center justify-center gap-2">
              <Monitor size={18} />
              <span>Entire Screen</span>
            </div>
            {activeTab === 'monitor' && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary"></div>
            )}
          </button>
          
          <button
            onClick={() => setActiveTab('window')}
            className={`flex-1 py-4 text-14 font-medium transition-colors relative ${
              activeTab === 'window'
                ? 'text-primary'
                : 'text-gray-600 hover:text-black'
            }`}
          >
            <div className="flex items-center justify-center gap-2">
              <AppWindow size={18} />
              <span>Applications</span>
            </div>
            {activeTab === 'window' && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary"></div>
            )}
          </button>
          
          <button
            onClick={() => setActiveTab('camera')}
            className={`flex-1 py-4 text-14 font-medium transition-colors relative ${
              activeTab === 'camera'
                ? 'text-primary'
                : 'text-gray-600 hover:text-black'
            }`}
          >
            <div className="flex items-center justify-center gap-2">
              <Camera size={18} />
              <span>Devices</span>
            </div>
            {activeTab === 'camera' && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary"></div>
            )}
          </button>
        </div>
        
        <div className="flex-1 overflow-y-auto px-8 py-6">
          {renderContent()}
        </div>
      </div>
    </ModalBase>
  );
}

// Extracted SourceTile component for better organization
function SourceTile({ source, type, isHovered, isSelected, isAvailable, onMouseEnter, onMouseLeave, onClick }) {
  const [previewFrame, setPreviewFrame] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  
  const sourceId = source.id !== undefined ? source.id : source.handle;
  
  // Simplified preview fetching
  useEffect(() => {
    let isMounted = true;
    let intervalId;
    
    const fetchPreview = async () => {
      if (!isAvailable) {
        setIsLoading(false);
        return;
      }
      
      try {
        const apiSourceType = type === 'monitor' ? 'screen' : type;
        const response = await fetch(
          buildApiUrl(`api/capture/preview/${apiSourceType}/${sourceId}?quality=30`)
        );
        
        if (response.ok && isMounted) {
          const data = await response.json();
          if (data.frame) {
            setPreviewFrame(`data:image/jpeg;base64,${data.frame}`);
          }
        }
      } catch (error) {
        console.error('Preview error:', error);
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };
    
    // Initial fetch
    fetchPreview();
    
    // Set up polling for preview updates
    intervalId = setInterval(fetchPreview, 1000);
    
    return () => {
      isMounted = false;
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [type, sourceId, isAvailable]);
  
  return (
    <div
      className={`relative cursor-pointer group ${!isAvailable ? 'opacity-50' : ''}`}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      onClick={onClick}
    >
      <div className={`
        relative w-full aspect-video bg-gray-200 rounded-lg overflow-hidden
        border-2 transition-all ${
          isSelected 
            ? 'border-primary' 
            : !isAvailable
            ? 'border-red-300'
            : 'border-gray-300 hover:border-gray-400'
        }
      `}>
        {!isAvailable ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <div className="text-red-500 mb-2">
              <AlertCircle size={32} />
            </div>
            <span className="text-12 text-red-600">Source Unavailable</span>
          </div>
        ) : previewFrame ? (
          <img 
            src={previewFrame} 
            alt={`Preview of ${source.name || source.title}`}
            className="absolute inset-0 w-full h-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center">
            {isLoading ? (
              <div className="flex flex-col items-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mb-2"></div>
                <span className="text-12 text-gray-500">Loading preview...</span>
              </div>
            ) : (
              <div className="text-gray-400">
                {type === 'monitor' && <Monitor size={48} />}
                {type === 'window' && <AppWindow size={48} />}
                {type === 'camera' && <Camera size={48} />}
              </div>
            )}
          </div>
        )}
        
        {isHovered && previewFrame && isAvailable && (
          <div className="absolute inset-0 bg-black bg-opacity-40 flex items-center justify-center">
            <span className="text-white text-14 font-medium">Select Source</span>
          </div>
        )}
        
        {isSelected && (
          <div className="absolute top-2 right-2 w-6 h-6 bg-primary rounded-full flex items-center justify-center">
            <Check size={14} color="white" />
          </div>
        )}
      </div>
      
      {type === 'window' && source.is_minimized && (
        <div className="absolute top-2 left-2 bg-black bg-opacity-70 text-white text-10 px-2 py-1 rounded">
          Minimized
        </div>
      )}
      
      <div className="mt-2 flex items-center gap-2">
        <div className={`${!isAvailable ? 'text-red-500' : 'text-gray-600'}`}>
          {type === 'monitor' && <Monitor size={16} />}
          {type === 'window' && <AppWindow size={16} />}
          {type === 'camera' && <Camera size={16} />}
        </div>
        <span className="text-14 truncate flex-1" title={source.name || source.title}>
          {source.name || source.title}
        </span>
        {type === 'window' && source.process_name && (
          <span className="text-12 text-gray-500">
            ({source.process_name})
          </span>
        )}
      </div>
      
      {type === 'window' && !previewFrame && !isLoading && isAvailable && (
        <div className="text-10 text-gray-500 mt-1">
          {source.is_minimized ? 'Window is minimized' : 'Window may be protected'}
        </div>
      )}
    </div>
  );
}
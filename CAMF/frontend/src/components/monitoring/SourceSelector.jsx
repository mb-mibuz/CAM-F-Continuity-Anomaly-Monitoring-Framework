import React, { useState } from 'react';
import { Airplay } from 'lucide-react';
import { useAppStore } from '../../stores';
import SourceSelectionModal from '../modals/SourceSelectionModal';

export default function SourceSelector({
  source,
  disabled = false,
  onSelectSource,
  className = ''
}) {
  const [showModal, setShowModal] = useState(false);
  const { addNotification } = useAppStore();

  const handleSourceSelect = async (sourceType, sourceId, sourceName) => {
    try {
      if (onSelectSource) {
        // Create source object format expected by captureStore
        const sourceObj = {
          type: sourceType,
          id: sourceId,
          name: sourceName
        };
        await onSelectSource(sourceObj);
      }
      setShowModal(false);
    } catch (error) {
      console.error('Failed to select source:', error);
      addNotification({ type: 'error', message: 'Failed to set capture source' });
    }
  };

  const getSourceLabel = () => {
    if (!source) {
      return 'Select Source';
    }
    
    if (disabled && source.name) {
      return `${source.name} (Locked)`;
    }
    
    return source.name || 'Unknown Source';
  };

  return (
    <>
      <button
        onClick={() => !disabled && setShowModal(true)}
        disabled={disabled}
        className={`
          flex items-center gap-2 transition-all duration-150
          ${disabled
            ? 'text-gray-400 cursor-not-allowed'
            : 'text-gray-800 hover:text-black hover:scale-105'
          }
          ${className}
        `}
        title={source ? `Source: ${source.name}` : "Select Capture Source"}
      >
        <Airplay size={20} strokeWidth={1.5} className="flex-shrink-0" />
        <span className="text-14 truncate">{getSourceLabel()}</span>
      </button>

      {showModal && !disabled && (
        <SourceSelectionModal
          currentSource={source}
          onClose={() => setShowModal(false)}
          onSelectSource={handleSourceSelect}
        />
      )}
    </>
  );
}
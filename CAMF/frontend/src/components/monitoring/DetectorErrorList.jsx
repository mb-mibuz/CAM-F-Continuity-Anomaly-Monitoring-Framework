import React from 'react';
import { ChevronDown, ChevronUp, Flag } from 'lucide-react';

export default function DetectorErrorList({
  errors,
  collapsedErrors,
  onToggleCollapse,
  onErrorClick,
  onMarkFalsePositive,
  isDisabled
}) {
  const getConfidenceColor = (confidence) => {
    if (confidence >= 0.8) return 'text-red-600';      // High confidence error
    if (confidence >= 0.5) return 'text-yellow-600';   // Medium confidence
    if (confidence > 0) return 'text-gray-600';        // Low confidence
    return 'text-purple-600';                          // Detector failure (-1)
  };

  const getConfidenceLabel = (confidence) => {
    if (confidence === -1) return 'Failed';
    if (confidence >= 0.8) return `High (${Math.round(confidence * 100)}%)`;
    if (confidence >= 0.5) return `Medium (${Math.round(confidence * 100)}%)`;
    if (confidence > 0) return `Low (${Math.round(confidence * 100)}%)`;
    return 'No Error';
  };

  return (
    <div className="divide-y divide-gray-200">
      {errors.map((error) => {
        const hasInstances = error.instances && error.instances.length > 1;
        const isCollapsed = collapsedErrors[error.id];
        const frameId = error.instances ? error.instances[0].frame_id : error.frame_id;
        const confidence = error.instances ? error.instances[0].confidence : error.confidence;
        
        return (
          <div key={error.id}>
            {/* Main error row */}
            <div
              className={`
                flex items-center px-4 py-2 relative
                ${isDisabled ? '' : 'hover:bg-gray-50 cursor-pointer'}
              `}
              onClick={() => !isDisabled && onErrorClick(error)}
            >
              {/* Expand/collapse button on the left */}
              <div className="w-8 flex items-center justify-center">
                {hasInstances && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (!isDisabled) {
                        onToggleCollapse(error.id);
                      }
                    }}
                    className={`p-1 rounded hover:bg-gray-200 ${isDisabled ? 'cursor-not-allowed' : ''}`}
                  >
                    {isCollapsed ? (
                      <ChevronDown size={14} className="text-gray-400" />
                    ) : (
                      <ChevronUp size={14} className="text-gray-400" />
                    )}
                  </button>
                )}
              </div>
              
              {/* Error description with instances count */}
              <div className="flex-1 flex items-center pr-2">
                <span className="text-12">
                  {error.description}
                </span>
                {hasInstances && (
                  <span className="ml-2 text-11 text-gray-500">
                    ({error.instances.length} instances)
                  </span>
                )}
              </div>
              
              {/* Detector name */}
              <div className="w-32 text-12 text-gray-600">
                {error.detector_name}
              </div>
              
              {/* Frame number */}
              <div className="w-20 text-12">
                {frameId !== undefined ? frameId : '-'}
              </div>
              
              {/* Confidence level */}
              <div className={`w-24 text-12 ${getConfidenceColor(confidence)}`}>
                {getConfidenceLabel(confidence)}
              </div>
              
              {/* False positive flag */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  if (!isDisabled && onMarkFalsePositive) {
                    onMarkFalsePositive(error);
                  }
                }}
                className={`
                  w-8 h-8 flex items-center justify-center rounded
                  ${isDisabled ? 'opacity-50 cursor-not-allowed' : 'hover:bg-gray-200 text-gray-500 hover:text-gray-700'}
                  ${error.is_false_positive ? 'text-red-500' : ''}
                `}
                title={error.is_false_positive ? "Marked as false positive" : "Mark as false positive"}
                disabled={isDisabled}
              >
                <Flag size={14} className={error.is_false_positive ? 'fill-current' : ''} />
              </button>
            </div>
            
            {/* Expanded instances */}
            {hasInstances && !isCollapsed && (
              <div className="bg-gray-50">
                {error.instances.map((instance, idx) => (
                  <div
                    key={`${error.id}-${idx}`}
                    className={`
                      flex items-center px-4 py-1
                      ${isDisabled ? '' : 'hover:bg-gray-100 cursor-pointer'}
                    `}
                    onClick={() => !isDisabled && onErrorClick({ 
                      ...error, 
                      frame_id: instance.frame_id 
                    })}
                  >
                    <div className="w-8" /> {/* Spacer */}
                    <div className="flex-1 text-12 text-gray-600">
                      Instance {idx + 1}
                    </div>
                    <div className="w-32" /> {/* Detector name spacer */}
                    <div className="w-20 text-12">{instance.frame_id}</div>
                    <div className={`w-24 text-12 ${getConfidenceColor(instance.confidence)}`}>
                      {getConfidenceLabel(instance.confidence)}
                    </div>
                    
                    {/* False positive flag for instance */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        if (!isDisabled && onMarkFalsePositive) {
                          onMarkFalsePositive({ 
                            ...error, 
                            frame_id: instance.frame_id,
                            confidence: instance.confidence 
                          });
                        }
                      }}
                      className={`
                        w-8 h-8 flex items-center justify-center rounded
                        ${isDisabled ? 'opacity-50 cursor-not-allowed' : 'hover:bg-gray-200 text-gray-500 hover:text-gray-700'}
                        ${instance.is_false_positive ? 'text-red-500' : ''}
                      `}
                      title={instance.is_false_positive ? "Marked as false positive" : "Mark as false positive"}
                      disabled={isDisabled}
                    >
                      <Flag size={14} className={instance.is_false_positive ? 'fill-current' : ''} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
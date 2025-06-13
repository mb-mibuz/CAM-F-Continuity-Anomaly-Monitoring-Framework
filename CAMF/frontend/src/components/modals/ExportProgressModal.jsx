import React from 'react';
import { X, FileText, Loader2 } from 'lucide-react';

export default function ExportProgressModal({ isOpen, onClose, progress = {} }) {
  if (!isOpen) return null;

  const {
    status = 'preparing',
    currentStep = '',
    stepsCompleted = 0,
    totalSteps = 0,
    message = ''
  } = progress;

  // Calculate progress percentage
  const progressPercentage = totalSteps > 0 ? (stepsCompleted / totalSteps) * 100 : 0;

  // Map status to user-friendly messages
  const getStatusMessage = () => {
    switch (status) {
      case 'preparing':
        return 'Preparing export...';
      case 'gathering_data':
        return 'Gathering project data...';
      case 'processing_frames':
        return 'Processing frames...';
      case 'generating_pdf':
        return 'Generating PDF document...';
      case 'finalizing':
        return 'Finalizing export...';
      case 'complete':
        return 'Export complete!';
      case 'error':
        return 'Export failed';
      default:
        return message || 'Processing...';
    }
  };

  const isComplete = status === 'complete';
  const hasError = status === 'error';

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black bg-opacity-50 z-50 animate-fade-in" />
      
      {/* Modal */}
      <div className="fixed inset-0 flex items-center justify-center z-50 p-4">
        <div className="bg-gray-800 rounded-lg shadow-xl max-w-md w-full animate-slide-up">
          {/* Header */}
          <div className="p-6 border-b border-gray-700">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <FileText className="w-6 h-6 text-blue-500" />
                <h2 className="text-xl font-semibold text-gray-100">
                  Exporting PDF
                </h2>
              </div>
              {/* Disable close button during export */}
              {(isComplete || hasError) && (
                <button
                  onClick={onClose}
                  className="text-gray-400 hover:text-gray-200 transition-colors"
                >
                  <X size={20} />
                </button>
              )}
            </div>
          </div>

          {/* Content */}
          <div className="p-6">
            {/* Status message */}
            <div className="flex items-center justify-center mb-6">
              {!isComplete && !hasError && (
                <Loader2 className="w-8 h-8 text-blue-500 animate-spin mr-3" />
              )}
              <p className={`text-lg ${hasError ? 'text-red-400' : 'text-gray-200'}`}>
                {getStatusMessage()}
              </p>
            </div>

            {/* Progress bar */}
            {!hasError && totalSteps > 0 && (
              <div className="mb-4">
                <div className="w-full bg-gray-700 rounded-full h-2 overflow-hidden">
                  <div
                    className="bg-blue-500 h-full transition-all duration-300 ease-out"
                    style={{ width: `${progressPercentage}%` }}
                  />
                </div>
                <p className="text-sm text-gray-400 mt-2 text-center">
                  Step {stepsCompleted} of {totalSteps}
                </p>
              </div>
            )}

            {/* Current step details */}
            {currentStep && !hasError && (
              <p className="text-sm text-gray-400 text-center">
                {currentStep}
              </p>
            )}

            {/* Completion message */}
            {isComplete && (
              <div className="text-center">
                <p className="text-green-400 mb-2">Export completed successfully!</p>
                <p className="text-sm text-gray-400">
                  The file manager will open shortly...
                </p>
              </div>
            )}

            {/* Error message */}
            {hasError && message && (
              <div className="mt-4 p-3 bg-red-900/20 border border-red-700 rounded">
                <p className="text-sm text-red-400">{message}</p>
              </div>
            )}
          </div>

          {/* Footer - only show close button when complete or error */}
          {(isComplete || hasError) && (
            <div className="p-6 pt-0">
              <button
                onClick={onClose}
                className="w-full px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded transition-colors"
              >
                Close
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
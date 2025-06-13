import React, { useState } from 'react';
import ModalBase from './ModalBase';

export default function FalsePositiveModal({ isOpen, onClose, error, onConfirm }) {
  const [reason, setReason] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (isSubmitting) return;
    
    setIsSubmitting(true);
    try {
      await onConfirm(error, reason);
      setReason('');
      onClose();
    } catch (error) {
      console.error('Failed to mark as false positive:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!error) return null;

  return (
    <ModalBase
      isOpen={isOpen}
      onClose={onClose}
      title="Mark as False Positive"
      size="medium"
    >
      <div className="p-8 space-y-6">
        {/* Header */}
        <div>
          <h3 className="text-lg font-semibold text-gray-900 mb-1">Mark as False Positive</h3>
          <p className="text-sm text-gray-600">
            This will mark the detected error as a false positive, excluding it from future reports.
          </p>
        </div>

        {/* Error details */}
        <div className="bg-gray-50 p-5 rounded-lg">
          <h4 className="font-medium text-gray-900 mb-3">Error Details</h4>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-gray-500">Detector:</span>{' '}
              <span className="font-medium text-gray-900">{error.detector_name}</span>
            </div>
            <div>
              <span className="text-gray-500">Frame:</span>{' '}
              <span className="font-medium text-gray-900">#{error.frame_id}</span>
            </div>
            <div className="col-span-2">
              <span className="text-gray-500">Description:</span>{' '}
              <span className="font-medium text-gray-900">{error.description}</span>
            </div>
            <div>
              <span className="text-gray-500">Confidence:</span>{' '}
              <span className="font-medium text-gray-900">
                {Math.round((error.confidence || 0) * 100)}%
              </span>
            </div>
            {error.error_group_id && (
              <div>
                <span className="text-gray-500">Group ID:</span>{' '}
                <span className="font-mono text-xs text-gray-900">
                  {error.error_group_id.substring(0, 8)}...
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Reason input */}
        <div>
          <label htmlFor="reason" className="block text-sm font-medium text-gray-700 mb-2">
            Reason for marking as false positive
          </label>
          <textarea
            id="reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Please provide a reason (e.g., 'Clock is correctly positioned', 'Not a continuity error', 'Expected change in scene')"
            className="w-full px-4 py-3 border border-gray-300 rounded-lg 
                     bg-white text-gray-900
                     focus:outline-none focus:ring-2 focus:ring-black focus:border-transparent
                     placeholder-gray-400"
            rows={4}
          />
          <p className="mt-2 text-xs text-gray-500">
            This information helps improve detector accuracy over time.
          </p>
        </div>

        {/* Action buttons */}
        <div className="flex justify-end gap-3 pt-4 border-t border-gray-200">
          <button
            onClick={onClose}
            disabled={isSubmitting}
            className="px-5 py-2.5 text-gray-700 hover:text-gray-900 
                     font-medium rounded-lg hover:bg-gray-100
                     disabled:opacity-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={isSubmitting || !reason.trim()}
            className="px-5 py-2.5 bg-red-600 text-white font-medium rounded-lg 
                     hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed
                     transition-colors flex items-center gap-2"
          >
            {isSubmitting ? (
              <>
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                Marking...
              </>
            ) : (
              'Mark as False Positive'
            )}
          </button>
        </div>
      </div>
    </ModalBase>
  );
}
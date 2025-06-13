import React from 'react';
import ModalBase from './ModalBase';
import { AlertTriangle } from 'lucide-react';

export default function SourceDisconnectedModal({ 
  sourceName, 
  onSaveFrames, 
  onRestartTake,
  onClose 
}) {
  return (
    <ModalBase onClose={() => {}}>
      <div className="p-8">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-12 h-12 rounded-full bg-yellow-100 flex items-center justify-center">
            <AlertTriangle size={24} className="text-yellow-600" />
          </div>
          <div>
            <h2 className="text-18 font-semibold">Source Disconnected</h2>
            <p className="text-14 text-gray-600">
              {sourceName || 'The capture source'} was disconnected during recording
            </p>
          </div>
        </div>
        
        <p className="text-14 text-gray-700 mb-6">
          The recording was interrupted. You can save the frames captured so far, or restart the take from the beginning.
        </p>
        
        <div className="flex justify-end gap-3">
          <button 
            onClick={onRestartTake}
            className="px-4 py-2 text-14 font-medium bg-white border border-gray-300 rounded hover:bg-gray-50"
          >
            Restart Take
          </button>
          <button 
            onClick={onSaveFrames}
            className="px-4 py-2 text-14 font-medium text-white bg-primary rounded hover:opacity-80"
          >
            Save Captured Frames
          </button>
        </div>
      </div>
    </ModalBase>
  );
}
import React from 'react';
import ModalBase from './ModalBase';

export default function ConfirmModal({ title, message, confirmText = 'Yes', cancelText = 'No', onConfirm, onCancel }) {
  return (
    <ModalBase onClose={onCancel}>
      <div className="p-8">
        <h2 className="text-18 font-semibold mb-4">{title}</h2>
        
        <p className="text-14 text-gray-700 mb-6">{message}</p>
        
        <div className="flex justify-end gap-3">
          <button 
            onClick={onCancel}
            className="px-4 py-2 text-14 font-medium bg-white border border-gray-300 rounded hover:bg-gray-50"
          >
            {cancelText}
          </button>
          <button 
            onClick={onConfirm}
            className="px-4 py-2 text-14 font-medium text-white bg-red-600 rounded hover:bg-red-700"
          >
            {confirmText}
          </button>
        </div>
      </div>
    </ModalBase>
  );
}
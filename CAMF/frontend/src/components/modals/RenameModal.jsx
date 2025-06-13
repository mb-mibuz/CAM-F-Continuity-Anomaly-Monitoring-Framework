// src/components/modals/RenameModal.jsx
import React, { useState } from 'react';
import ModalBase from './ModalBase';
import { validateName, sanitizeName } from '../../utils/nameValidator';

export default function RenameModal({ title, currentName, onClose, onSave }) {
  const [newName, setNewName] = useState(currentName);
  const [error, setError] = useState('');

  const handleNameChange = (e) => {
    const value = e.target.value;
    setNewName(value);
    
    // Clear error when user types
    if (error) {
      setError('');
    }
  };

  const handleSave = () => {
    const sanitized = sanitizeName(newName);
    const validation = validateName(sanitized);
    
    if (!validation.isValid) {
      setError(validation.error);
      return;
    }
    
    if (sanitized !== currentName) {
      onSave(sanitized);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      handleSave();
    }
  };

  return (
    <ModalBase onClose={onClose}>
      <div className="p-8">
        <h2 className="text-18 font-semibold mb-6">{title}</h2>
        
        <div className="mb-6">
          <label className="block text-14 font-medium mb-2">Name</label>
          <input 
            type="text"
            value={newName}
            onChange={handleNameChange}
            onKeyPress={handleKeyPress}
            className={`w-full px-3 py-2 border rounded focus:outline-none ${
              error ? 'border-red-500 focus:border-red-500' : 'border-gray-300 focus:border-black'
            }`}
            autoFocus
          />
          {error && (
            <p className="mt-1 text-12 text-red-600">{error}</p>
          )}
        </div>
        
        <div className="flex justify-end gap-3">
          <button 
            onClick={onClose}
            className="px-4 py-2 text-14 font-medium bg-white border border-gray-300 rounded hover:bg-gray-50"
          >
            Cancel
          </button>
          <button 
            onClick={handleSave}
            disabled={!newName.trim() || newName.trim() === currentName || error}
            className={`px-4 py-2 text-14 font-medium text-white rounded ${
              newName.trim() && newName.trim() !== currentName && !error
                ? 'bg-primary hover:opacity-80' 
                : 'bg-gray-300 cursor-not-allowed'
            }`}
          >
            Save
          </button>
        </div>
      </div>
    </ModalBase>
  );
}
// src/components/modals/NewProjectModal.jsx
import React, { useState } from 'react';
import ModalBase from './ModalBase';
import { validateName, sanitizeName } from '../../utils/nameValidator';

export default function NewProjectModal({ onClose, onSave }) {
  const [projectName, setProjectName] = useState('');
  const [error, setError] = useState('');

  const handleNameChange = (e) => {
    const value = e.target.value;
    setProjectName(value);
    
    // Clear error when user types
    if (error) {
      setError('');
    }
  };

  const handleSave = () => {
    const sanitized = sanitizeName(projectName);
    const validation = validateName(sanitized);
    
    if (!validation.isValid) {
      setError(validation.error);
      return;
    }
    
    // Actually call onSave!
    onSave(sanitized);
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      handleSave();
    }
  };

  return (
    <ModalBase onClose={onClose}>
      <div className="p-8">
        <h2 className="text-18 font-semibold mb-6">New Project</h2>
        
        <div className="mb-6">
          <label className="block text-14 font-medium mb-2">Project Name</label>
          <input 
            type="text"
            value={projectName}
            onChange={handleNameChange}
            onKeyPress={handleKeyPress}
            placeholder="Enter project name"
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
            disabled={!projectName.trim() || error}
            className={`px-4 py-2 text-14 font-medium text-white rounded ${
              projectName.trim() && !error
                ? 'bg-primary hover:opacity-80' 
                : 'bg-gray-300 cursor-not-allowed'
            }`}
          >
            Create
          </button>
        </div>
      </div>
    </ModalBase>
  );
}
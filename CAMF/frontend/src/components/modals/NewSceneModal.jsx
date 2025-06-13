// src/components/modals/NewSceneModal.jsx
import React, { useState } from 'react';
import ModalBase from './ModalBase';
import { validateName, sanitizeName } from '../../utils/nameValidator';

export default function NewSceneModal({ onClose, onCreate }) {
  const [sceneName, setSceneName] = useState('');
  const [error, setError] = useState('');

  const handleNameChange = (e) => {
    const value = e.target.value;
    setSceneName(value);
    
    if (error) {
      setError('');
    }
  };

  const handleCreate = () => {
    const sanitized = sanitizeName(sceneName);
    const validation = validateName(sanitized);
    
    if (!validation.isValid) {
      setError(validation.error);
      return;
    }
    
    // Only pass the name, configuration will be done in the next step
    onCreate(sanitized);
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleCreate();
    }
  };

  return (
    <ModalBase onClose={onClose}>
      <div className="p-8">
        <h2 className="text-18 font-semibold mb-6">New Scene</h2>
        
        <div className="mb-4">
          <label className="block text-14 font-medium mb-2">Scene Name</label>
          <input 
            type="text"
            value={sceneName}
            onChange={handleNameChange}
            onKeyPress={handleKeyPress}
            placeholder="Enter scene name"
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
            onClick={handleCreate}
            disabled={!sceneName.trim() || error}
            className={`px-4 py-2 text-14 font-medium text-white rounded ${
              sceneName.trim() && !error
                ? 'bg-primary hover:opacity-80' 
                : 'bg-gray-300 cursor-not-allowed'
            }`}
          >
            Next
          </button>
        </div>
      </div>
    </ModalBase>
  );
}
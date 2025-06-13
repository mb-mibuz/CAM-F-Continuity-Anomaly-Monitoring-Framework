// src/components/modals/VideoUploadModal.jsx
import React, { useState, useRef } from 'react';
import ModalBase from './ModalBase';
import { Upload, X, Film } from 'lucide-react';

export default function VideoUploadModal({ onClose, onUpload }) {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [error, setError] = useState('');
  const fileInputRef = useRef(null);

  const allowedExtensions = ['.mp4', '.avi', '.mov', '.mkv', '.webm'];

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const validateFile = (file) => {
    const ext = file.name.toLowerCase().slice(file.name.lastIndexOf('.'));
    if (!allowedExtensions.includes(ext)) {
      setError(`Invalid file type. Allowed formats: ${allowedExtensions.join(', ')}`);
      return false;
    }
    
    // Check file size (max 2GB)
    const maxSize = 2 * 1024 * 1024 * 1024;
    if (file.size > maxSize) {
      setError('File size too large. Maximum size is 2GB.');
      return false;
    }
    
    setError('');
    return true;
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      if (validateFile(file)) {
        setSelectedFile(file);
      }
    }
  };

  const handleFileSelect = (e) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      if (validateFile(file)) {
        setSelectedFile(file);
      }
    }
  };

  const handleUpload = () => {
    if (selectedFile) {
      onUpload(selectedFile);
    }
  };

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' GB';
  };

  return (
    <ModalBase onClose={onClose} size="medium">
      <div className="p-8">
        <h2 className="text-18 font-semibold mb-6">Upload Video</h2>
        
        <div
          className={`relative border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
            dragActive 
              ? 'border-primary bg-gray-50' 
              : selectedFile 
                ? 'border-green-500 bg-green-50' 
                : 'border-gray-300 hover:border-gray-400'
          }`}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          onClick={() => !selectedFile && fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={allowedExtensions.join(',')}
            onChange={handleFileSelect}
            className="hidden"
          />
          
          {selectedFile ? (
            <div className="space-y-3">
              <Film size={48} className="mx-auto text-green-600" />
              <div>
                <p className="text-16 font-medium">{selectedFile.name}</p>
                <p className="text-14 text-gray-600">{formatFileSize(selectedFile.size)}</p>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedFile(null);
                  setError('');
                }}
                className="mx-auto flex items-center gap-2 px-3 py-1 text-14 bg-white border border-gray-300 rounded hover:bg-gray-50"
              >
                <X size={16} />
                Remove
              </button>
            </div>
          ) : (
            <>
              <Upload size={48} className="mx-auto text-gray-400 mb-4" />
              <p className="text-16 font-medium mb-2">
                Drag and drop video file here
              </p>
              <p className="text-14 text-gray-600 mb-4">
                or click to browse
              </p>
              <p className="text-12 text-gray-500">
                Supported formats: {allowedExtensions.join(', ')}
              </p>
            </>
          )}
        </div>
        
        {error && (
          <p className="mt-3 text-14 text-red-600">{error}</p>
        )}
        
        <div className="flex justify-end gap-3 mt-6">
          <button 
            onClick={onClose}
            className="px-4 py-2 text-14 font-medium bg-white border border-gray-300 rounded hover:bg-gray-50"
          >
            Cancel
          </button>
          <button 
            onClick={handleUpload}
            disabled={!selectedFile || error}
            className={`px-4 py-2 text-14 font-medium text-white rounded ${
              selectedFile && !error
                ? 'bg-primary hover:opacity-80' 
                : 'bg-gray-300 cursor-not-allowed'
            }`}
          >
            Upload
          </button>
        </div>
      </div>
    </ModalBase>
  );
}
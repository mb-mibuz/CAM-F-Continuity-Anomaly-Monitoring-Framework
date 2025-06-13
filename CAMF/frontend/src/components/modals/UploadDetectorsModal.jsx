import React, { useState, useRef } from 'react';
import ModalBase from './ModalBase';
import ConfirmModal from './ConfirmModal';
import { DetectorService } from '../../services';
import { useAppStore } from '../../stores';

export default function UploadDetectorsModal({ onClose, onSuccess, updateMode = false, detectorName = null }) {
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const [uploadProgress, setUploadProgress] = useState({});
  const [currentUploadingFile, setCurrentUploadingFile] = useState(null);
  
  const fileInputRef = useRef(null);
  const addNotification = useAppStore(state => state.addNotification);
  const detectorService = DetectorService.getInstance();
  
  // Maximum file size (500MB)
  const MAX_FILE_SIZE = 500 * 1024 * 1024;

  const handleClose = () => {
    if (uploading) {
      setShowCancelConfirm(true);
    } else {
      onClose();
    }
  };

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' GB';
  };

  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files);
    
    if (selectedFiles.length + files.length > 10) {
      addNotification({ type: "warning", message: 'You can only select up to 10 files at a time.'});
      return;
    }
    
    const newFiles = files.filter(f => 
      f.name.endsWith('.zip') && 
      !selectedFiles.some(sf => sf.name === f.name)
    );
    
    setSelectedFiles([...selectedFiles, ...newFiles]);
    
    // Reset the input so the same file can be selected again
    e.target.value = null;
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    
    if (updateMode && selectedFiles.length > 0) return;
    
    const files = Array.from(e.dataTransfer.files);
    const zipFiles = files.filter(file => file.name.endsWith('.zip'));
    
    if (selectedFiles.length + zipFiles.length > 10) {
      addNotification({ type: "warning", message: 'You can only select up to 10 files at a time.'});
      return;
    }
    
    const newFiles = zipFiles.filter(f => !selectedFiles.some(sf => sf.name === f.name));
    setSelectedFiles([...selectedFiles, ...newFiles]);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    if (!updateMode || selectedFiles.length === 0) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const removeFile = (index) => {
    setSelectedFiles(selectedFiles.filter((_, i) => i !== index));
  };

  const handleUpload = async () => {
    if (selectedFiles.length === 0) return;
    
    setUploading(true);
    setUploadProgress({});
    let successCount = 0;
    let failCount = 0;
    const errors = [];
    
    for (const file of selectedFiles) {
      try {
        setCurrentUploadingFile(file.name);
        console.log(`Processing file: ${file.name}`);
        
        // Check file size
        if (file.size > MAX_FILE_SIZE) {
          throw new Error(`File too large. Maximum size is ${formatFileSize(MAX_FILE_SIZE)}`);
        }
        
        // Simulate upload progress (0-90%)
        let progress = 0;
        const progressInterval = setInterval(() => {
          progress += Math.random() * 20;
          if (progress > 90) progress = 90;
          setUploadProgress(prev => ({
            ...prev,
            [file.name]: Math.round(progress)
          }));
        }, 300);
        
        try {
          // Wait a bit to show upload progress
          await new Promise(resolve => setTimeout(resolve, 1500));
          
          // Clear interval and set to 100% for processing
          clearInterval(progressInterval);
          setUploadProgress(prev => ({
            ...prev,
            [file.name]: 100
          }));
          
          // Install detector using service (this is the processing phase)
          const result = await detectorService.installDetector(file);
          
          successCount++;
        } catch (error) {
          clearInterval(progressInterval);
          throw error;
        }
        
      } catch (error) {
        console.error(`Failed to upload ${file.name}:`, error);
        failCount++;
        errors.push(`${file.name}: ${error.message}`);
      }
      
      // Small delay before removing the progress bar
      await new Promise(resolve => setTimeout(resolve, 300));
      
      // Clear progress for this file
      setUploadProgress(prev => {
        const newProgress = { ...prev };
        delete newProgress[file.name];
        return newProgress;
      });
    }
    
    setUploading(false);
    setCurrentUploadingFile(null);
    
    if (successCount > 0) {
      if (failCount > 0) {
        addNotification({ type: "warning", message: `Installed/Updated ${successCount} detector(s) successfully. ${failCount} failed:\n\n${errors.join('\n')}`});
      } else {
        addNotification({ type: "success", message: `Successfully installed/updated ${successCount} detector(s).`});
      }
      // Small delay to ensure notification is shown before closing
      setTimeout(() => {
        onSuccess();
      }, 300);
    } else {
      addNotification({ type: "error", message: `Failed to install/update detectors:\n\n${errors.join('\n')}`});
    }
  };

  const handleCancelUpload = () => {
    setShowCancelConfirm(false);
    setUploading(false);
    setSelectedFiles([]);
    setUploadProgress({});
    setCurrentUploadingFile(null);
    onClose();
  };

  const getUploadButtonText = () => {
    if (uploading) return 'Uploading...';
    if (updateMode) return 'Update';
    return 'Upload';
  };

  return (
    <>
      <ModalBase onClose={handleClose} size="medium">
        <div className="p-8">
          <h2 className="text-18 font-semibold mb-6">
            {updateMode ? `Update ${detectorName}` : 'Upload Detectors'}
          </h2>
          
          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".zip"
            multiple={!updateMode}
            onChange={handleFileSelect}
            style={{ display: 'none' }}
          />
          
          <div 
            className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors ${
              isDragging ? 'border-primary bg-gray-50' : 'border-gray-300'
            }`}
            onClick={() => fileInputRef.current?.click()}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
          >
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" className="mx-auto mb-4">
              <path d="M24 16V32M24 16L18 22M24 16L30 22" stroke="#888" strokeWidth="2" strokeLinecap="round"/>
              <path d="M40 28V36C40 38 38 40 36 40H12C10 40 8 38 8 36V28" stroke="#888" strokeWidth="2" strokeLinecap="round"/>
              <path d="M8 20V12C8 10 10 8 12 8H36C38 8 40 10 40 12V20" stroke="#888" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            <p className="text-14 text-gray-600 mb-2">
              Drop detector ZIP files here or click to browse
            </p>
            <p className="text-12 text-gray-500">
              {updateMode ? 'Select one file to update' : 'Accepts .zip files, multiple selection allowed (max 10)'}
            </p>
            <p className="text-12 text-gray-400 mt-1">
              Maximum file size: 500MB
            </p>
          </div>
          
          {/* Selected files */}
          {selectedFiles.length > 0 && (
            <div className="mt-4 space-y-2">
              {!updateMode && (
                <p className="text-12 text-gray-600">{selectedFiles.length}/10 files selected</p>
              )}
              {selectedFiles.map((file, index) => (
                <div key={index} className="bg-gray-50 px-3 py-2 rounded">
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <span className="text-14">{file.name}</span>
                      <span className="text-12 text-gray-500 ml-2">
                        ({formatFileSize(file.size)})
                      </span>
                    </div>
                    <button 
                      onClick={() => removeFile(index)}
                      disabled={uploading}
                      className={`text-18 font-semibold ${
                        uploading ? 'text-gray-400 cursor-not-allowed' : 'text-red-600 hover:text-red-700'
                      }`}
                    >
                      ×
                    </button>
                  </div>
                  
                  {/* Upload progress */}
                  {uploading && uploadProgress[file.name] !== undefined && (
                    <div className="mt-2">
                      <div className="flex items-center justify-between text-12 text-gray-600 mb-1">
                        <span>
                          {uploadProgress[file.name] < 100 ? 'Uploading...' : 'Validating...'}
                        </span>
                        <span>{uploadProgress[file.name]}%</span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2">
                        <div 
                          className={`h-2 rounded-full transition-all duration-300 ${
                            uploadProgress[file.name] < 100 ? 'bg-primary' : 'bg-blue-500'
                          }`}
                          style={{ width: `${uploadProgress[file.name]}%` }}
                        />
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
          
          {/* Action buttons */}
          <div className="flex justify-end gap-3 mt-6">
            <button 
              onClick={handleClose}
              disabled={uploading}
              className={`px-4 py-2 text-14 font-medium rounded ${
                uploading 
                  ? 'bg-gray-100 text-gray-400 cursor-not-allowed' 
                  : 'bg-white border border-gray-300 hover:bg-gray-50'
              }`}
            >
              Cancel
            </button>
            <button 
              onClick={handleUpload}
              disabled={selectedFiles.length === 0 || uploading}
              className={`px-4 py-2 text-14 font-medium text-white rounded ${
                selectedFiles.length > 0 && !uploading
                  ? 'bg-primary hover:opacity-80'
                  : 'bg-gray-300 cursor-not-allowed'
              }`}
            >
              {getUploadButtonText()}
            </button>
          </div>
        </div>
      </ModalBase>

      {/* Cancel confirmation modal */}
      {showCancelConfirm && (
        <ConfirmModal
          title="Cancel Upload"
          message="Upload is in progress. Are you sure you want to cancel?"
          confirmText="Yes, Cancel"
          cancelText="Continue Uploading"
          onConfirm={handleCancelUpload}
          onCancel={() => setShowCancelConfirm(false)}
        />
      )}
    </>
  );
}
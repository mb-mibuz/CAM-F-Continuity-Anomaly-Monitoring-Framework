import { useState, useCallback } from 'react';
import { useAppStore } from '../stores';
import { handleError } from '../services/ErrorHandler';
import config, { buildApiUrl } from '../config';

export function useVideoUpload() {
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState(null);
  
  const uploadVideo = useCallback(async (takeId, file) => {
    setUploading(true);
    setProgress(0);
    setError(null);
    
    const appStore = useAppStore.getState();
    
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      // Create XMLHttpRequest for progress tracking
      const xhr = new XMLHttpRequest();
      
      // Track upload progress
      xhr.upload.addEventListener('progress', (event) => {
        if (event.lengthComputable) {
          const percentComplete = (event.loaded / event.total) * 100;
          setProgress(Math.round(percentComplete));
        }
      });
      
      // Handle completion
      const uploadPromise = new Promise((resolve, reject) => {
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              const response = JSON.parse(xhr.responseText);
              resolve(response);
            } catch (e) {
              reject(new Error('Invalid response from server'));
            }
          } else {
            reject(new Error(`Upload failed: ${xhr.statusText}`));
          }
        };
        
        xhr.onerror = () => reject(new Error('Network error during upload'));
        xhr.onabort = () => reject(new Error('Upload cancelled'));
      });
      
      // Start upload
      xhr.open('POST', buildApiUrl(`api/upload/video/${takeId}`));
      xhr.send(formData);
      
      const result = await uploadPromise;
      
      appStore.addNotification({ type: 'success', message: `Video uploaded successfully: ${file.name}` });
      setUploading(false);
      setProgress(100);
      
      return result;
      
    } catch (err) {
      const errorMessage = err.message || 'Failed to upload video';
      setError(errorMessage);
      setUploading(false);
      
      handleError(err, 'Video Upload', { takeId, fileName: file.name });
      appStore.addNotification({ type: 'error', message: errorMessage });
      
      throw err;
    }
  }, []);
  
  const reset = useCallback(() => {
    setUploading(false);
    setProgress(0);
    setError(null);
  }, []);
  
  return {
    uploadVideo,
    uploading,
    progress,
    error,
    reset
  };
}
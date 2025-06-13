import React, { useState, useEffect } from 'react';
import ModalBase from './ModalBase';
import { useUpdateScene } from '../../queries/hooks/useScenes';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../../queries/keys';

export default function SceneConfigModal({ 
  sceneName,
  sceneId,
  onBack, 
  onNext, 
  onClose, 
  editMode = false,
  initialFps = 1.0,
  initialQuality = 90,
  initialResolution = '1080p'
}) {
  const [fps, setFps] = useState(initialFps.toString());
  const [quality, setQuality] = useState(initialQuality);
  const [resolution, setResolution] = useState(initialResolution);
  
  const updateScene = useUpdateScene();
  const queryClient = useQueryClient();
  
  const resolutionOptions = [
    { value: '4K', label: '4K (3840×2160)' },
    { value: '1440p', label: '1440p (2560×1440)' },
    { value: '1080p', label: '1080p (1920×1080)' },
    { value: '720p', label: '720p (1280×720)' },
    { value: '480p', label: '480p (854×480)' },
    { value: '360p', label: '360p (640×360)' }
  ];

  useEffect(() => {
    console.log('[SceneConfigModal] Initial values:', {
      initialFps,
      initialQuality,
      initialResolution,
      sceneId,
      sceneName,
      editMode
    });
    setFps(initialFps.toString());
    setQuality(initialQuality);
    setResolution(initialResolution);
  }, [initialFps, initialQuality, initialResolution]);

  const handleFpsChange = (e) => {
    const value = e.target.value;
    
    // Allow empty string for backspace
    if (value === '') {
      setFps('');
      return;
    }
    
    // Only allow numbers and decimal point
    if (/^\d*\.?\d*$/.test(value)) {
      // Prevent multiple decimal points
      const decimalCount = (value.match(/\./g) || []).length;
      if (decimalCount <= 1) {
        setFps(value);
      }
    }
  };

  const handleNext = async () => {
    const fpsValue = parseFloat(fps);
    
    // Validate FPS
    if (isNaN(fpsValue) || fpsValue <= 0) {
      alert('Please enter a valid frame rate greater than 0');
      return;
    }
    
    // In edit mode, save scene settings
    if (editMode && sceneId) {
      try {
        await updateScene.mutateAsync({
          sceneId,
          data: {
            image_quality: quality
            // Note: frame_rate and resolution cannot be changed after scene creation
          }
        });
        console.log('[SceneConfigModal] Scene updated successfully with quality:', quality);
        
        // Invalidate scene queries to force refresh
        await queryClient.invalidateQueries({ queryKey: queryKeys.scenes.detail(sceneId) });
        
        onClose();
      } catch (error) {
        console.error('Failed to update scene:', error);
      }
    } else if (onNext) {
      // In create mode, pass settings to next step
      onNext({ fps: fpsValue, quality, resolution });
    } else {
      // Fallback - just close
      onClose();
    }
  };

  const calculateSecondsPerFrame = (fpsValue) => {
    return (1 / fpsValue).toFixed(2);
  };

  return (
    <ModalBase onClose={onClose} size="medium">
      <div className="p-8">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-18 font-semibold">
            {editMode ? 'Scene Settings' : 'Scene Configuration'}
          </h2>
          {!editMode && onBack && (
            <button
              onClick={onBack}
              className="text-14 text-gray-600 hover:text-black"
            >
              ← Back
            </button>
          )}
        </div>
        
        <p className="text-14 text-gray-600 mb-6">
          {editMode ? `Update settings for "${sceneName}"` : `Configure settings for "${sceneName}"`}
        </p>
        
        {editMode && (
          <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded">
            <p className="text-14 text-yellow-800">
              Note: Frame rate and resolution cannot be changed after scene creation
            </p>
          </div>
        )}
        
        {/* Configuration Fields */}
        <div className="space-y-6 mb-8">
          {/* FPS and Resolution Row */}
          <div className="grid grid-cols-2 gap-4">
            {/* FPS Input */}
            <div>
              <label className="block text-14 font-medium mb-2">Frame Rate (FPS)</label>
              <input
                type="text"
                value={fps}
                onChange={handleFpsChange}
                disabled={editMode}
                placeholder="e.g., 24, 30, 0.5"
                className={`w-full px-3 py-2 border rounded focus:outline-none ${
                  editMode 
                    ? 'bg-gray-100 border-gray-200 cursor-not-allowed' 
                    : 'border-gray-300 focus:border-black'
                }`}
              />
              {fps && parseFloat(fps) > 0 && parseFloat(fps) < 1 && (
                <p className="text-12 text-gray-600 mt-1">
                  = 1 frame every {calculateSecondsPerFrame(parseFloat(fps))} seconds
                </p>
              )}
            </div>
            
            {/* Resolution Dropdown */}
            <div>
              <label className="block text-14 font-medium mb-2">Resolution</label>
              <select
                value={resolution}
                onChange={(e) => setResolution(e.target.value)}
                disabled={editMode}
                className={`w-full px-3 py-2 border rounded focus:outline-none ${
                  editMode 
                    ? 'bg-gray-100 border-gray-200 cursor-not-allowed' 
                    : 'border-gray-300 focus:border-black'
                }`}
              >
                {resolutionOptions.map(opt => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          
          {/* Quality Slider */}
          <div>
            <label className="block text-14 font-medium mb-2">
              Image Quality ({quality}%)
            </label>
            <div className="relative flex items-center h-5">
              <div 
                className="absolute inset-x-0 h-0.5 rounded-full"
                style={{
                  background: `linear-gradient(to right, #515151 0%, #515151 ${((quality - 10) / 90) * 100}%, #D1D5DB ${((quality - 10) / 90) * 100}%, #D1D5DB 100%)`
                }}
              />
              <input
                type="range"
                min="10"
                max="100"
                value={quality}
                onChange={(e) => setQuality(Number(e.target.value))}
                className="relative w-full appearance-none bg-transparent cursor-pointer z-10"
              />
            </div>
            <div className="flex justify-between text-12 text-gray-500 mt-1">
              <span>Low (10%)</span>
              <span>High (100%)</span>
            </div>
          </div>
        </div>
        
        <div className="flex justify-end gap-3">
          <button 
            onClick={onClose}
            className="px-4 py-2 text-14 font-medium bg-white border border-gray-300 rounded hover:bg-gray-50"
          >
            Cancel
          </button>
          <button 
            onClick={handleNext}
            className="px-4 py-2 text-14 font-medium text-white bg-primary rounded hover:opacity-80"
          >
            {editMode ? 'Save' : 'Next'}
          </button>
        </div>
      </div>
    </ModalBase>
  );
}
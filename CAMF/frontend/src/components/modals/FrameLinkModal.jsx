import React, { useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import ModalBase from './ModalBase';
import { FrameService } from '../../services';
import { useTakeErrors } from '../../queries/hooks';

export default function FrameLinkModal({ onClose, onConfirm, maxFrame, takeId }) {
  const [frameNumber, setFrameNumber] = useState(0);
  const [frameInput, setFrameInput] = useState('0');
  const [framePreview, setFramePreview] = useState(null);
  const [loading, setLoading] = useState(false);
  
  const frameService = FrameService.getInstance();
  
  // Use React Query for errors
  const { data: frameErrors = [] } = useTakeErrors(takeId, {
    frameId: frameNumber,
    enabled: frameNumber >= 0
  });
  
  useEffect(() => {
    loadFramePreview(0);
    
    return () => {
      // Cleanup blob URL on unmount
      if (framePreview && framePreview.startsWith('blob:')) {
        URL.revokeObjectURL(framePreview);
      }
    };
  }, []);
  
  const loadFramePreview = async (frameNum) => {
    setLoading(true);
    try {
      // Use FrameService for loading frames
      const frameData = await frameService.loadFrame(takeId, frameNum, {
        withBoundingBoxes: true,
        forceReload: true
      });
      
      // Clean up previous preview
      if (framePreview && framePreview.startsWith('blob:')) {
        URL.revokeObjectURL(framePreview);
      }
      
      setFramePreview(frameData);
    } catch (error) {
      console.error('Error loading frame preview:', error);
      setFramePreview(null);
    } finally {
      setLoading(false);
    }
  };
  
  const handleFrameInputChange = (e) => {
    const value = e.target.value;
    
    // Only allow numbers
    if (value !== '' && !/^\d+$/.test(value)) {
      return;
    }
    
    setFrameInput(value);
    
    if (value === '') {
      return;
    }
    
    const frameNum = parseInt(value);
    
    // Validate frame number
    if (frameNum >= 0 && frameNum <= maxFrame) {
      setFrameNumber(frameNum);
      loadFramePreview(frameNum);
    }
  };
  
  const handleFrameInputBlur = () => {
    // Reset input to current frame number if invalid
    if (frameInput === '' || parseInt(frameInput) < 0 || parseInt(frameInput) > maxFrame) {
      setFrameInput(frameNumber.toString());
    }
  };
  
  const handleFrameNavigation = (direction) => {
    let newFrame = frameNumber;
    
    if (direction === 'prev' && frameNumber > 0) {
      newFrame = frameNumber - 1;
    } else if (direction === 'next' && frameNumber < maxFrame) {
      newFrame = frameNumber + 1;
    }
    
    if (newFrame !== frameNumber) {
      setFrameNumber(newFrame);
      setFrameInput(newFrame.toString());
      loadFramePreview(newFrame);
    }
  };
  
  const handleSliderChange = (e) => {
    const newFrame = parseInt(e.target.value);
    setFrameNumber(newFrame);
    setFrameInput(newFrame.toString());
    loadFramePreview(newFrame);
  };
  
  const handleConfirm = () => {
    onConfirm(frameNumber);
  };
  
  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      handleConfirm();
    }
  };
  
  // Get color for detector
  const getDetectorColor = (detectorName, index) => {
    const colors = [
      '#EF4444', '#F59E0B', '#10B981', '#3B82F6', '#8B5CF6',
      '#EC4899', '#14B8A6', '#F97316', '#06B6D4', '#6366F1'
    ];
    return colors[index % colors.length];
  };
  
  return (
    <ModalBase onClose={onClose} size="medium">
      <div className="p-6">
        <h2 className="text-16 font-semibold mb-4">Link Frame</h2>
        
        {/* Frame navigation controls */}
        <div className="mb-3">
          <div className="flex items-center gap-2">
            <button
              onClick={() => handleFrameNavigation('prev')}
              disabled={frameNumber === 0}
              className={`w-7 h-7 flex items-center justify-center ${
                frameNumber === 0
                  ? 'text-gray-300 cursor-not-allowed'
                  : 'hover:bg-gray-100 rounded'
              }`}
            >
              <ChevronLeft size={18} />
            </button>
            
            <button
              onClick={() => handleFrameNavigation('next')}
              disabled={frameNumber >= maxFrame}
              className={`w-7 h-7 flex items-center justify-center ${
                frameNumber >= maxFrame
                  ? 'text-gray-300 cursor-not-allowed'
                  : 'hover:bg-gray-100 rounded'
              }`}
            >
              <ChevronRight size={18} />
            </button>
            
            <div className="flex-1 mx-3">
              <input
                type="range"
                min="0"
                max={maxFrame}
                value={frameNumber}
                onChange={handleSliderChange}
                className="w-full"
              />
            </div>
            
            <div className="flex items-center gap-1 text-13">
              <input
                type="text"
                value={frameInput}
                onChange={handleFrameInputChange}
                onBlur={handleFrameInputBlur}
                onKeyPress={handleKeyPress}
                className="w-14 px-2 py-1 border border-gray-300 rounded text-center focus:outline-none focus:border-black"
              />
              <span className="text-gray-500">/ {maxFrame}</span>
            </div>
          </div>
        </div>
        
        {/* Frame preview */}
        <div className="mb-4">
          <div className="relative bg-gray-100 rounded overflow-hidden" style={{ height: '280px' }}>
            {loading ? (
              <div className="absolute inset-0 flex items-center justify-center">
                <p className="text-gray-500 text-14">Loading...</p>
              </div>
            ) : framePreview ? (
              <img 
                src={framePreview} 
                alt={`Frame ${frameNumber}`}
                className="w-full h-full object-contain"
              />
            ) : (
              <div className="absolute inset-0 flex items-center justify-center">
                <p className="text-gray-500 text-14">
                  {maxFrame < 0 ? 'No frames available' : 'Frame not found'}
                </p>
              </div>
            )}
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
            onClick={handleConfirm}
            disabled={loading || !framePreview}
            className={`px-4 py-2 text-14 font-medium text-white rounded ${
              !loading && framePreview
                ? 'bg-primary hover:opacity-80' 
                : 'bg-gray-300 cursor-not-allowed'
            }`}
          >
            Link Frame
          </button>
        </div>
      </div>
    </ModalBase>
  );
}
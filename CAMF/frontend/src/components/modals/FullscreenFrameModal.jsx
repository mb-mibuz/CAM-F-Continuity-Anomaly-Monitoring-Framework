import React, { useState, useEffect, useRef } from 'react';
import { X, Maximize2, ChevronLeft, ChevronRight } from 'lucide-react';
import ModalBase from './ModalBase';

export default function FullscreenFrameModal({ 
  isOpen, 
  onClose, 
  frameData,
  frameNumber,
  totalFrames,
  onFrameChange,
  frameRate = 24,
  currentTime = 0,
  detectorResults = [],
  isCapturing = false,
  onNavigate,
  getCurrentFrame
}) {
  const [scale, setScale] = useState(1);
  const [minScale, setMinScale] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [isInitialized, setIsInitialized] = useState(false);
  const containerRef = useRef(null);
  const imageRef = useRef(null);
  const scrollContainerRef = useRef(null);

  // Calculate optimal scale only when modal first opens
  useEffect(() => {
    if (isOpen && containerRef.current && imageRef.current && !isInitialized) {
      const container = containerRef.current;
      const img = imageRef.current;
      
      // Wait for image to load
      const updateScale = () => {
        const containerWidth = container.clientWidth;
        const containerHeight = container.clientHeight - 120; // Account for controls
        const imgWidth = img.naturalWidth || img.width;
        const imgHeight = img.naturalHeight || img.height;
        
        if (imgWidth && imgHeight) {
          const scaleX = containerWidth / imgWidth;
          const scaleY = containerHeight / imgHeight;
          const optimalScale = Math.min(scaleX, scaleY) * 0.98; // 98% to maximize frame size
          setScale(optimalScale);
          setMinScale(optimalScale); // Set minimum scale to fit-to-screen
          setIsInitialized(true);
        }
      };

      if (img.complete) {
        updateScale();
      } else {
        img.onload = updateScale;
      }
    }
  }, [isOpen, isInitialized]);

  // Reset position when scale changes to fit
  useEffect(() => {
    if (scale <= minScale) {
      setPosition({ x: 0, y: 0 });
    }
  }, [scale, minScale]);

  const handleZoom = (delta) => {
    setScale(prev => {
      const newScale = prev + delta;
      // Prevent zooming out below fit-to-screen scale
      return Math.max(minScale, Math.min(3, newScale));
    });
  };

  const handleWheel = (e) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      const delta = e.deltaY > 0 ? -0.1 : 0.1;
      handleZoom(delta);
    }
  };

  // Mouse drag handlers
  const handleMouseDown = (e) => {
    if (scale > minScale) {
      setIsDragging(true);
      setDragStart({
        x: e.clientX - position.x,
        y: e.clientY - position.y
      });
      e.preventDefault();
    }
  };

  const handleMouseMove = (e) => {
    if (isDragging && scale > minScale) {
      const newX = e.clientX - dragStart.x;
      const newY = e.clientY - dragStart.y;
      
      // Calculate bounds to prevent dragging image out of view
      if (containerRef.current && imageRef.current) {
        const container = containerRef.current;
        const imgWidth = imageRef.current.naturalWidth * scale;
        const imgHeight = imageRef.current.naturalHeight * scale;
        const maxX = Math.max(0, (imgWidth - container.clientWidth) / 2);
        const maxY = Math.max(0, (imgHeight - container.clientHeight) / 2);
        
        setPosition({
          x: Math.max(-maxX, Math.min(maxX, newX)),
          y: Math.max(-maxY, Math.min(maxY, newY))
        });
      }
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  // Add/remove global mouse listeners
  useEffect(() => {
    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      return () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [isDragging, dragStart, scale, position]);

  // Handle frame navigation
  const handleFrameNavigate = (direction) => {
    if (onNavigate) {
      onNavigate(direction);
    }
  };

  const handleFrameIndexChange = (newIndex) => {
    if (onFrameChange) {
      onFrameChange(newIndex);
    }
  };

  const resetZoom = () => {
    setScale(minScale); // Reset to fit-to-screen instead of 1
    setPosition({ x: 0, y: 0 }); // Reset position
  };

  // Get the current frame data - either from prop or callback
  const currentFrameData = frameData || (getCurrentFrame && getCurrentFrame());

  return (
    <ModalBase
      isOpen={isOpen}
      onClose={onClose}
      className="fullscreen-modal"
      size="fullscreen"
    >
      <div className="flex flex-col h-full bg-gray-900">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <div className="flex items-center gap-4">
            <Maximize2 className="w-5 h-5 text-gray-400" />
            <h2 className="text-lg font-semibold text-white">Fullscreen Frame View</h2>
            <span className="text-sm text-gray-400">
              Frame {frameNumber || 1} of {totalFrames || 0}
            </span>
          </div>
          
          <div className="flex items-center gap-4">
            {/* Zoom controls */}
            <div className="flex items-center gap-2 bg-gray-800 rounded-lg px-3 py-1">
              <button
                onClick={() => handleZoom(-0.1)}
                className="text-gray-400 hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                disabled={scale <= minScale}
              >
                -
              </button>
              <span className="text-sm text-gray-300 min-w-[60px] text-center">
                {Math.round(scale * 100)}%
              </span>
              <button
                onClick={() => handleZoom(0.1)}
                className="text-gray-400 hover:text-white transition-colors"
              >
                +
              </button>
              <button
                onClick={resetZoom}
                className="text-xs text-gray-400 hover:text-white ml-2"
              >
                Fit
              </button>
            </div>

            <button
              onClick={onClose}
              className="p-2 hover:bg-gray-800 rounded-lg transition-colors"
            >
              <X className="w-5 h-5 text-gray-400" />
            </button>
          </div>
        </div>

        {/* Main content area */}
        <div 
          ref={containerRef}
          className="flex-1 overflow-hidden bg-black relative flex items-center justify-center"
          onWheel={handleWheel}
          onMouseDown={handleMouseDown}
          style={{
            cursor: scale > minScale ? (isDragging ? 'grabbing' : 'grab') : 'default'
          }}
        >
          <div 
            ref={scrollContainerRef}
            className="w-full h-full overflow-hidden"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}
          >
            <div 
              className="relative"
              style={{
                transform: `translate(${position.x}px, ${position.y}px) scale(${scale})`,
                transformOrigin: 'center',
                transition: isDragging ? 'none' : 'transform 0.1s ease-out',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
            >
              {currentFrameData ? (
                <>
                  <img
                    ref={imageRef}
                    key={`frame-${frameNumber || 1}`}
                    src={currentFrameData}
                    alt={`Frame ${frameNumber || 1}`}
                    className="max-w-none block"
                    style={{
                      width: '100%',
                      height: '100%',
                      objectFit: 'contain'
                    }}
                    onLoad={() => {
                      // Only update minScale when frame dimensions change
                      if (containerRef.current && imageRef.current) {
                        const container = containerRef.current;
                        const img = imageRef.current;
                        const containerWidth = container.clientWidth;
                        const containerHeight = container.clientHeight - 120;
                        const imgWidth = img.naturalWidth || img.width;
                        const imgHeight = img.naturalHeight || img.height;
                        
                        if (imgWidth && imgHeight) {
                          const scaleX = containerWidth / imgWidth;
                          const scaleY = containerHeight / imgHeight;
                          const optimalScale = Math.min(scaleX, scaleY) * 0.98;
                          setMinScale(optimalScale);
                          
                          // Only set scale if not initialized
                          if (!isInitialized) {
                            setScale(optimalScale);
                            setIsInitialized(true);
                          }
                        }
                      }
                    }}
                  />
                  
                  {/* Overlay detector results if any */}
                  {detectorResults.length > 0 && (
                    <div 
                      className="absolute inset-0 pointer-events-none"
                    >
                      {detectorResults.map((result, idx) => {
                        if (result.bounding_boxes && result.bounding_boxes.length > 0) {
                          return result.bounding_boxes.map((box, boxIdx) => {
                            // Determine border color based on confidence/severity
                            const getBorderColor = () => {
                              if (result.confidence >= 0.9) return 'border-red-500';
                              if (result.confidence >= 0.8) return 'border-orange-500';
                              if (result.confidence >= 0.7) return 'border-yellow-500';
                              return 'border-blue-500';
                            };
                            
                            const getBgColor = () => {
                              if (result.confidence >= 0.9) return 'bg-red-500';
                              if (result.confidence >= 0.8) return 'bg-orange-500';
                              if (result.confidence >= 0.7) return 'bg-yellow-500';
                              return 'bg-blue-500';
                            };
                            
                            return (
                              <div
                                key={`${idx}-${boxIdx}`}
                                className={`absolute border-2 ${getBorderColor()}`}
                                style={{
                                  left: `${box.x}px`,
                                  top: `${box.y}px`,
                                  width: `${box.width}px`,
                                  height: `${box.height}px`,
                                }}
                              >
                                <span className={`absolute -top-6 left-0 ${getBgColor()} text-white text-xs px-1 py-0.5 rounded whitespace-nowrap`}>
                                  {box.label || result.description || result.detector_name}
                                </span>
                                {result.confidence > 0 && (
                                  <span className={`absolute -bottom-5 right-0 ${getBgColor()} text-white text-xs px-1 py-0.5 rounded`}>
                                    {Math.round(result.confidence * 100)}%
                                  </span>
                                )}
                              </div>
                            );
                          });
                        }
                        return null;
                      })}
                    </div>
                  )}
                </>
              ) : (
                <div className="flex items-center justify-center h-64">
                  <p className="text-gray-500">No frame data available</p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Frame navigation controls */}
        <div className="border-t border-gray-700 bg-gray-900 py-4">
          <div className="max-w-2xl mx-auto px-4">
            <div className="flex items-center gap-2 w-full">
              {/* Navigation buttons */}
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleFrameNavigate('prev')}
                  disabled={isCapturing || !totalFrames || (frameNumber || 1) <= 1}
                  className={`
                    w-8 h-8 flex items-center justify-center rounded
                    transition-all duration-150
                    ${isCapturing || !totalFrames || (frameNumber || 1) <= 1
                      ? 'text-gray-600 cursor-not-allowed'
                      : 'text-gray-300 hover:text-white hover:bg-gray-800'
                    }
                  `}
                  title="Previous frame"
                >
                  <ChevronLeft size={20} strokeWidth={1.5} />
                </button>
                
                <button
                  onClick={() => handleFrameNavigate('next')}
                  disabled={isCapturing || !totalFrames || (frameNumber || 1) >= totalFrames}
                  className={`
                    w-8 h-8 flex items-center justify-center rounded
                    transition-all duration-150
                    ${isCapturing || !totalFrames || (frameNumber || 1) >= totalFrames
                      ? 'text-gray-600 cursor-not-allowed'
                      : 'text-gray-300 hover:text-white hover:bg-gray-800'
                    }
                  `}
                  title="Next frame"
                >
                  <ChevronRight size={20} strokeWidth={1.5} />
                </button>
              </div>
              
              {/* Slider */}
              <div className="flex-1 px-2">
                <div className="relative flex items-center h-5">
                  <div 
                    className="absolute inset-x-0 h-0.5 rounded-full"
                    style={{
                      background: `linear-gradient(to right, #9CA3AF 0%, #9CA3AF ${totalFrames > 0 ? ((frameNumber - 1) / (totalFrames - 1)) * 100 : 0}%, #4B5563 ${totalFrames > 0 ? ((frameNumber - 1) / (totalFrames - 1)) * 100 : 0}%, #4B5563 100%)`
                    }}
                  />
                  <input
                    type="range"
                    min="0"
                    max={Math.max(0, totalFrames - 1)}
                    value={(frameNumber || 1) - 1}
                    onChange={(e) => handleFrameIndexChange(parseInt(e.target.value))}
                    disabled={isCapturing || !totalFrames}
                    className={`
                      relative w-full appearance-none bg-transparent cursor-pointer z-10
                      ${isCapturing || !totalFrames ? 'opacity-50 cursor-not-allowed' : ''}
                    `}
                    style={{
                      '--thumb-color': isCapturing || !totalFrames ? '#6B7280' : '#E5E7EB'
                    }}
                  />
                </div>
              </div>
              
              {/* Frame counter */}
              <div className="text-14 text-gray-300 whitespace-nowrap">
                {totalFrames > 0 ? (
                  <>
                    <span className="font-medium">{frameNumber || 1}</span>
                    <span className="mx-1">/</span>
                    <span>{totalFrames}</span>
                    <span className="ml-1 text-gray-500">frames</span>
                  </>
                ) : (
                  <span className="text-gray-500">0 frames</span>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </ModalBase>
  );
}
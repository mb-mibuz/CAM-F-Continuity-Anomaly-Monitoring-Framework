import React from 'react';

export default function FrameDisplay({
  frame,
  frameIndex,
  totalFrames,
  isLoading = false,
  isReference = false,
  isCapturing = false,
  hasErrors = false,
  showBoundingBoxes = false,
  boundingBoxes = [],
  showPlaceholder = false,
  placeholderText = 'No frames captured',
  showFrameCounterDuringCapture = false,
  showRecordingOverlay = false
}) {
  console.log('[FrameDisplay] Rendering with:', { 
    hasFrame: !!frame, 
    frameType: typeof frame,
    framePrefix: frame ? frame.substring(0, 50) : null,
    frameIndex, 
    totalFrames, 
    isLoading,
    showPlaceholder,
    isValidDataUrl: frame ? frame.startsWith('data:') : false,
    isValidBlobUrl: frame ? frame.startsWith('blob:') : false
  });
  
  return (
    <div className="relative bg-gray-200 rounded-lg overflow-hidden w-full" style={{ aspectRatio: '16/9' }}>
      {/* Frame content */}
      {frame && frame.length > 0 && !showPlaceholder ? (
        <img 
          key={frame}
          src={frame} 
          alt={isReference ? "Reference frame" : "Current frame"}
          className="absolute inset-0 w-full h-full object-contain"
          onError={(e) => {
            console.error('[FrameDisplay] Image failed to load:', {
              src: e.target.src?.substring(0, 100),
              error: e
            });
          }}
          onLoad={() => {
            console.log('[FrameDisplay] Image loaded successfully');
          }}
        />
      ) : (
        <div className="absolute inset-0 flex items-center justify-center text-gray-500">
          <div className="text-center">
            {isLoading ? (
              <>
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-500 mb-2 mx-auto" />
                <p className="text-14">Loading frame...</p>
              </>
            ) : (
              <p className="text-16">{placeholderText}</p>
            )}
          </div>
        </div>
      )}
      
      {/* Frame counter overlay - hide during capture unless explicitly requested */}
      {frame && frame.length > 0 && totalFrames > 0 && (!isCapturing || showFrameCounterDuringCapture) && (
        <div className="absolute bottom-2 right-2 bg-black bg-opacity-70 text-white text-12 px-2 py-1 rounded">
          Frame {frameIndex + 1} of {totalFrames}
        </div>
      )}
      
      {/* Status indicators */}
      {/* Recording overlay - only show on current frame, not reference */}
      {showRecordingOverlay && isCapturing && !isReference && (
        <div className="absolute top-2 right-2">
          <div className="flex items-center gap-2 bg-red-600 text-white px-3 py-1.5 rounded-full">
            <div className="w-2 h-2 bg-white rounded-full animate-pulse" />
            <span className="text-12 font-medium">Recording in progress...</span>
          </div>
        </div>
      )}
      
      {hasErrors && showBoundingBoxes && (
        <div className="absolute top-2 left-2">
          <div className="bg-yellow-500 text-white text-12 px-2 py-1 rounded">
            Errors detected
          </div>
        </div>
      )}
      
      {/* Render bounding boxes */}
      {showBoundingBoxes && boundingBoxes && boundingBoxes.length > 0 && (
        <svg className="absolute inset-0 w-full h-full pointer-events-none">
          {boundingBoxes.map((box, index) => {
            // Convert bounding box coordinates to percentages for responsive rendering
            // Assuming box has x, y, width, height in pixels relative to original image
            const x = (box.x / 1920) * 100; // Assuming 1920x1080 resolution
            const y = (box.y / 1080) * 100;
            const width = (box.width / 1920) * 100;
            const height = (box.height / 1080) * 100;
            
            return (
              <g key={index}>
                <rect
                  x={`${x}%`}
                  y={`${y}%`}
                  width={`${width}%`}
                  height={`${height}%`}
                  fill="none"
                  stroke={box.confidence > 0.8 ? "#ef4444" : box.confidence > 0.5 ? "#f59e0b" : "#3b82f6"}
                  strokeWidth="2"
                  strokeDasharray={box.confidence < 0.5 ? "5,5" : "none"}
                />
                {box.label && (
                  <text
                    x={`${x}%`}
                    y={`${y - 0.5}%`}
                    fill="white"
                    fontSize="12"
                    fontWeight="600"
                    style={{
                      filter: 'drop-shadow(0 0 2px rgba(0,0,0,0.8))'
                    }}
                  >
                    {box.label} ({Math.round(box.confidence * 100)}%)
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
}
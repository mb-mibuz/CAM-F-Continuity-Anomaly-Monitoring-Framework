import React from 'react';
import { X } from 'lucide-react';

export default function ProcessingOverlay({
  processedFrames,
  totalFrames,
  onStop,
  message = 'Processing frames...'
}) {
  const progress = totalFrames > 0 ? (processedFrames / totalFrames) * 100 : 0;
  
  return (
    <div className="absolute inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl p-8 max-w-md w-full mx-4">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-18 font-semibold">Processing</h3>
          {onStop && (
            <button
              onClick={onStop}
              className="p-1 hover:bg-gray-100 rounded transition-colors"
              title="Cancel processing"
            >
              <X size={20} />
            </button>
          )}
        </div>
        
        {/* Message */}
        <p className="text-14 text-gray-600 mb-4">{message}</p>
        
        {/* Progress info */}
        <div className="mb-4">
          <div className="flex justify-between text-14 mb-2">
            <span>Progress</span>
            <span className="font-medium">
              {processedFrames} / {totalFrames} frames
            </span>
          </div>
          
          {/* Progress bar */}
          <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-primary transition-all duration-300 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
          
          {/* Percentage */}
          <div className="mt-2 text-center text-12 text-gray-500">
            {Math.round(progress)}% complete
          </div>
        </div>
        
        {/* Estimated time (optional) */}
        {processedFrames > 0 && processedFrames < totalFrames && (
          <div className="text-12 text-gray-500 text-center">
            <EstimatedTime 
              processedFrames={processedFrames}
              totalFrames={totalFrames}
            />
          </div>
        )}
      </div>
    </div>
  );
}

// Helper component for estimated time
function EstimatedTime({ processedFrames, totalFrames }) {
  const [startTime] = React.useState(Date.now());
  const [currentTime, setCurrentTime] = React.useState(Date.now());
  
  React.useEffect(() => {
    const interval = setInterval(() => {
      setCurrentTime(Date.now());
    }, 1000);
    
    return () => clearInterval(interval);
  }, []);
  
  const elapsed = currentTime - startTime;
  const framesPerMs = processedFrames / elapsed;
  const remainingFrames = totalFrames - processedFrames;
  const estimatedRemaining = remainingFrames / framesPerMs;
  
  const formatTime = (ms) => {
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const displaySeconds = seconds % 60;
    
    if (minutes > 0) {
      return `${minutes}m ${displaySeconds}s`;
    }
    return `${displaySeconds}s`;
  };
  
  if (elapsed < 2000) {
    return <span>Estimating time remaining...</span>;
  }
  
  return (
    <span>
      Approximately {formatTime(estimatedRemaining)} remaining
    </span>
  );
}
import React, { useState, useEffect, useRef } from 'react';
import { Activity, Pause, Play } from 'lucide-react';

export default function ProcessingProgressBar({
  processedPairs = 0,
  totalPairs = 0,
  isCapturing = false,
  isPaused = false,
  onPause,
  onResume,
  className = ''
}) {
  // Track timing information
  const [startTime] = useState(Date.now());
  const [processedFrameTimes, setProcessedFrameTimes] = useState([]);
  const [estimatedTimeRemaining, setEstimatedTimeRemaining] = useState(null);
  const [averageProcessingTime, setAverageProcessingTime] = useState(null);
  const lastProcessedRef = useRef(processedPairs);
  
  // Update timing when frames are processed
  useEffect(() => {
    if (processedPairs > lastProcessedRef.current && processedPairs > 0) {
      const currentTime = Date.now();
      const newFrameTime = currentTime;
      
      setProcessedFrameTimes(prev => {
        const times = [...prev, newFrameTime];
        // Keep only last 10 frame times for moving average
        if (times.length > 10) {
          times.shift();
        }
        return times;
      });
      
      lastProcessedRef.current = processedPairs;
    }
  }, [processedPairs]);
  
  // Calculate average processing time and estimate remaining time
  useEffect(() => {
    if (processedFrameTimes.length >= 2) {
      // Calculate average time between frames
      const timeDiffs = [];
      for (let i = 1; i < processedFrameTimes.length; i++) {
        timeDiffs.push(processedFrameTimes[i] - processedFrameTimes[i - 1]);
      }
      
      const avgTime = timeDiffs.reduce((a, b) => a + b, 0) / timeDiffs.length;
      setAverageProcessingTime(avgTime);
      
      // Estimate remaining time
      const remainingPairs = totalPairs - processedPairs;
      if (remainingPairs > 0 && !isCapturing) {
        // Only show estimate when not capturing (fixed number of frames)
        setEstimatedTimeRemaining(remainingPairs * avgTime);
      } else if (isCapturing && processedPairs < totalPairs) {
        // During capture, show estimate based on frames queued but not processed
        const queuedFrames = totalPairs - processedPairs;
        setEstimatedTimeRemaining(queuedFrames * avgTime);
      } else {
        setEstimatedTimeRemaining(null);
      }
    }
  }, [processedFrameTimes, processedPairs, totalPairs, isCapturing]);
  
  const formatTime = (ms) => {
    if (!ms || ms < 0) return '--:--';
    
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    
    if (hours > 0) {
      return `${hours}h ${minutes % 60}m`;
    } else if (minutes > 0) {
      return `${minutes}m ${(seconds % 60).toString().padStart(2, '0')}s`;
    } else {
      return `${seconds}s`;
    }
  };
  
  const formatProcessingSpeed = () => {
    if (!averageProcessingTime || averageProcessingTime === 0) return null;
    const framesPerSecond = 1000 / averageProcessingTime;
    return `${framesPerSecond.toFixed(1)} frames/sec`;
  };
  
  // Calculate progress percentage
  const progress = totalPairs > 0 ? (processedPairs / totalPairs) * 100 : 0;
  const isProcessing = processedPairs < totalPairs || (isCapturing && totalPairs > 0);
  
  if (!isProcessing && processedPairs === 0) {
    return null; // Don't show if nothing to process
  }
  
  return (
    <div className={`bg-gray-50 border border-gray-200 rounded-lg p-4 ${className}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Activity 
            size={16} 
            className={`${isPaused ? 'text-gray-400' : 'text-green-500 animate-pulse'}`} 
          />
          <span className="text-14 font-medium">
            {isCapturing ? 'Live Processing' : 'Processing Frames'}
          </span>
        </div>
        
        {/* Pause/Resume button */}
        {isProcessing && onPause && onResume && (
          <button
            onClick={isPaused ? onResume : onPause}
            className="p-1.5 hover:bg-gray-200 rounded transition-colors"
            title={isPaused ? 'Resume processing' : 'Pause processing'}
          >
            {isPaused ? <Play size={14} /> : <Pause size={14} />}
          </button>
        )}
      </div>
      
      {/* Progress info */}
      <div className="space-y-2">
        <div className="flex justify-between text-12 text-gray-600">
          <span>
            {processedPairs} / {isCapturing ? `${totalPairs}+` : totalPairs} frame pairs
          </span>
          <span>{Math.round(progress)}%</span>
        </div>
        
        {/* Progress bar */}
        <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all duration-300 ease-out ${
              isPaused ? 'bg-gray-400' : 'bg-blue-500'
            }`}
            style={{ width: `${Math.min(progress, 100)}%` }}
          />
        </div>
        
        {/* Time and speed info */}
        <div className="flex justify-between text-11 text-gray-500">
          <div className="flex items-center gap-3">
            {formatProcessingSpeed() && (
              <span className="font-medium">{formatProcessingSpeed()}</span>
            )}
            {estimatedTimeRemaining && !isPaused && (
              <span>~{formatTime(estimatedTimeRemaining)} remaining</span>
            )}
            {isPaused && (
              <span className="text-orange-600 font-medium">Paused</span>
            )}
          </div>
          
          {/* Status text */}
          <span className="text-gray-600">
            {isCapturing ? 'Processing while capturing' : 
             processedPairs === totalPairs ? 'Completed' : 'Processing'}
          </span>
        </div>
      </div>
    </div>
  );
}
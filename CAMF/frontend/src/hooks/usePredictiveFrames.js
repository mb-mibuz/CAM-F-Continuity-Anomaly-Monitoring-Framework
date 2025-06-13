import { useState, useEffect, useRef, useCallback } from 'react';
import { useDataStore } from '../stores';

/**
 * Hook for predictive frame counting with smooth animations
 * Calculates expected frames based on FPS and reconciles with server
 */
export function usePredictiveFrames() {
  const { captureProgress, isCapturing } = useDataStore();
  const [predictedFrames, setPredictedFrames] = useState(0);
  const [displayFrames, setDisplayFrames] = useState(0);
  const animationRef = useRef(null);
  const lastUpdateRef = useRef(Date.now());
  const reconciliationRef = useRef(null);
  
  // Calculate expected frames based on elapsed time and FPS
  const calculateExpectedFrames = useCallback(() => {
    if (!isCapturing || !captureProgress.startTime) return 0;
    
    const elapsed = Date.now() - captureProgress.startTime;
    const expectedFrames = Math.floor((elapsed / 1000) * (captureProgress.frameRate || 24));
    return expectedFrames;
  }, [isCapturing, captureProgress.startTime, captureProgress.frameRate]);
  
  // Smooth animation between predicted and actual values
  const animateToTarget = useCallback((target, duration = 500) => {
    if (animationRef.current) {
      cancelAnimationFrame(animationRef.current);
    }
    
    const start = displayFrames;
    const startTime = Date.now();
    
    const animate = () => {
      const elapsed = Date.now() - startTime;
      const progress = Math.min(elapsed / duration, 1);
      
      // Easing function for smooth animation
      const easeInOutQuad = progress < 0.5
        ? 2 * progress * progress
        : 1 - Math.pow(-2 * progress + 2, 2) / 2;
      
      const current = Math.floor(start + (target - start) * easeInOutQuad);
      setDisplayFrames(current);
      
      if (progress < 1) {
        animationRef.current = requestAnimationFrame(animate);
      }
    };
    
    animationRef.current = requestAnimationFrame(animate);
  }, [displayFrames]);
  
  // Update predictions continuously
  useEffect(() => {
    if (!isCapturing) {
      setPredictedFrames(0);
      setDisplayFrames(0);
      return;
    }
    
    const updatePrediction = () => {
      const expected = calculateExpectedFrames();
      setPredictedFrames(expected);
      
      // If we haven't received an update in a while, show predicted value
      const timeSinceLastUpdate = Date.now() - lastUpdateRef.current;
      if (timeSinceLastUpdate > 1000) {
        animateToTarget(expected, 300);
      }
    };
    
    // Update predictions every 100ms for smooth counter
    const interval = setInterval(updatePrediction, 100);
    updatePrediction();
    
    return () => clearInterval(interval);
  }, [isCapturing, calculateExpectedFrames, animateToTarget]);
  
  // Reconcile with actual server values
  useEffect(() => {
    if (!isCapturing) return;
    
    const actualFrames = captureProgress.capturedFrames;
    const timeSinceLastUpdate = Date.now() - lastUpdateRef.current;
    
    // If we just got an update, reconcile smoothly
    if (actualFrames !== displayFrames) {
      lastUpdateRef.current = Date.now();
      
      // Clear any pending reconciliation
      if (reconciliationRef.current) {
        clearTimeout(reconciliationRef.current);
      }
      
      // Smooth transition to actual value
      animateToTarget(actualFrames, 500);
      
      // After reconciliation, continue with predictions
      reconciliationRef.current = setTimeout(() => {
        setPredictedFrames(actualFrames);
      }, 500);
    }
  }, [captureProgress.capturedFrames, isCapturing, displayFrames, animateToTarget]);
  
  // Cleanup
  useEffect(() => {
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
      if (reconciliationRef.current) {
        clearTimeout(reconciliationRef.current);
      }
    };
  }, []);
  
  return {
    displayFrames,
    predictedFrames,
    actualFrames: captureProgress.capturedFrames,
    isReconciling: Math.abs(displayFrames - captureProgress.capturedFrames) > 5,
    confidence: calculateConfidence(predictedFrames, captureProgress.capturedFrames)
  };
}

/**
 * Calculate confidence in prediction (0-1)
 */
function calculateConfidence(predicted, actual) {
  if (!predicted || !actual) return 1;
  const difference = Math.abs(predicted - actual);
  const percentDiff = difference / actual;
  return Math.max(0, 1 - percentDiff);
}

/**
 * Hook for smooth progress bars with estimation
 */
export function usePredictiveProgress() {
  const { processingProgress, isProcessing } = useDataStore(state => ({
    processingProgress: state.captureProgress,
    isProcessing: state.isCapturing
  }));
  
  const [displayProgress, setDisplayProgress] = useState(0);
  const [estimatedCompletion, setEstimatedCompletion] = useState(null);
  const animationRef = useRef(null);
  const startTimeRef = useRef(null);
  const progressHistoryRef = useRef([]);
  
  // Calculate progress percentage
  const calculateProgress = useCallback(() => {
    const { processedFrames, totalFrames } = processingProgress;
    if (!totalFrames) return 0;
    return (processedFrames / totalFrames) * 100;
  }, [processingProgress]);
  
  // Estimate completion time based on progress history
  const estimateCompletion = useCallback(() => {
    const history = progressHistoryRef.current;
    if (history.length < 2 || !isProcessing) return null;
    
    // Calculate average processing rate
    const recentHistory = history.slice(-5); // Last 5 data points
    const rates = [];
    
    for (let i = 1; i < recentHistory.length; i++) {
      const timeDiff = recentHistory[i].time - recentHistory[i - 1].time;
      const progressDiff = recentHistory[i].progress - recentHistory[i - 1].progress;
      if (timeDiff > 0 && progressDiff > 0) {
        rates.push(progressDiff / timeDiff);
      }
    }
    
    if (rates.length === 0) return null;
    
    const avgRate = rates.reduce((a, b) => a + b, 0) / rates.length;
    const remainingProgress = 100 - displayProgress;
    const estimatedMs = remainingProgress / avgRate;
    
    return Date.now() + estimatedMs;
  }, [displayProgress, isProcessing]);
  
  // Smooth animation to target progress
  const animateProgress = useCallback((target) => {
    if (animationRef.current) {
      cancelAnimationFrame(animationRef.current);
    }
    
    const start = displayProgress;
    const startTime = Date.now();
    const duration = 1000; // 1 second for smooth transitions
    
    const animate = () => {
      const elapsed = Date.now() - startTime;
      const progress = Math.min(elapsed / duration, 1);
      
      // Easing function
      const easeOutQuart = 1 - Math.pow(1 - progress, 4);
      
      const current = start + (target - start) * easeOutQuart;
      setDisplayProgress(current);
      
      if (progress < 1) {
        animationRef.current = requestAnimationFrame(animate);
      }
    };
    
    animationRef.current = requestAnimationFrame(animate);
  }, [displayProgress]);
  
  // Track progress changes
  useEffect(() => {
    if (!isProcessing) {
      setDisplayProgress(0);
      setEstimatedCompletion(null);
      progressHistoryRef.current = [];
      startTimeRef.current = null;
      return;
    }
    
    if (!startTimeRef.current) {
      startTimeRef.current = Date.now();
    }
    
    const actualProgress = calculateProgress();
    
    // Add to history
    progressHistoryRef.current.push({
      time: Date.now(),
      progress: actualProgress
    });
    
    // Keep only last 10 entries
    if (progressHistoryRef.current.length > 10) {
      progressHistoryRef.current.shift();
    }
    
    // Animate to new progress
    animateProgress(actualProgress);
    
    // Update completion estimate
    const estimate = estimateCompletion();
    setEstimatedCompletion(estimate);
  }, [processingProgress, isProcessing, calculateProgress, animateProgress, estimateCompletion]);
  
  // Cleanup
  useEffect(() => {
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, []);
  
  // Format estimated time
  const formatEstimatedTime = useCallback(() => {
    if (!estimatedCompletion) return null;
    
    const remaining = Math.max(0, estimatedCompletion - Date.now());
    const seconds = Math.floor(remaining / 1000);
    const minutes = Math.floor(seconds / 60);
    const displaySeconds = seconds % 60;
    
    if (minutes > 0) {
      return `${minutes}m ${displaySeconds}s remaining`;
    }
    return `${displaySeconds}s remaining`;
  }, [estimatedCompletion]);
  
  return {
    displayProgress,
    actualProgress: calculateProgress(),
    estimatedTime: formatEstimatedTime(),
    estimatedCompletion,
    isEstimating: progressHistoryRef.current.length >= 2,
    confidence: calculateProgressConfidence(progressHistoryRef.current)
  };
}

/**
 * Calculate confidence in progress estimation
 */
function calculateProgressConfidence(history) {
  if (history.length < 3) return 0;
  
  // Calculate variance in progress rates
  const rates = [];
  for (let i = 1; i < history.length; i++) {
    const timeDiff = history[i].time - history[i - 1].time;
    const progressDiff = history[i].progress - history[i - 1].progress;
    if (timeDiff > 0) {
      rates.push(progressDiff / timeDiff);
    }
  }
  
  if (rates.length < 2) return 0;
  
  const mean = rates.reduce((a, b) => a + b, 0) / rates.length;
  const variance = rates.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / rates.length;
  const stdDev = Math.sqrt(variance);
  
  // Lower variance = higher confidence
  const normalizedStdDev = stdDev / (mean || 1);
  return Math.max(0, 1 - normalizedStdDev);
}
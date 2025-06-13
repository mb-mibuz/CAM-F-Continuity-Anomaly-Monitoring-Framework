import React, { useEffect, useRef, useState } from 'react';
import { useRenderMonitor } from '../../hooks';
import { useStore } from '../../stores';

/**
 * Performance monitoring overlay for development
 * Shows render counts, cache stats, and optimization suggestions
 */
export default function PerformanceMonitor() {
  const [isVisible, setIsVisible] = useState(false);
  const [metrics, setMetrics] = useState({
    fps: 0,
    renderCounts: {},
    cacheStats: null,
    storeUpdates: {},
    memoryUsage: null
  });
  
  const frameCount = useRef(0);
  const lastTime = useRef(performance.now());
  const renderTracker = useRef(new Map());
  const storeUpdateTracker = useRef(new Map());
  
  // Toggle visibility with keyboard shortcut
  useEffect(() => {
    const handleKeyPress = (e) => {
      if (e.ctrlKey && e.shiftKey && e.key === 'P') {
        setIsVisible(prev => !prev);
      }
    };
    
    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, []);
  
  // Track FPS
  useEffect(() => {
    if (!isVisible) return;
    
    let animationId;
    
    const trackFPS = () => {
      frameCount.current++;
      const currentTime = performance.now();
      
      if (currentTime >= lastTime.current + 1000) {
        const fps = Math.round((frameCount.current * 1000) / (currentTime - lastTime.current));
        frameCount.current = 0;
        lastTime.current = currentTime;
        
        setMetrics(prev => ({ ...prev, fps }));
      }
      
      animationId = requestAnimationFrame(trackFPS);
    };
    
    animationId = requestAnimationFrame(trackFPS);
    
    return () => cancelAnimationFrame(animationId);
  }, [isVisible]);
  
  // Update metrics periodically
  useEffect(() => {
    if (!isVisible) return;
    
    const updateMetrics = () => {
      // Cache stats removed - no longer using intelligent cache
      const cacheStats = null;
      
      // Get memory usage if available
      let memoryUsage = null;
      if (performance.memory) {
        memoryUsage = {
          used: Math.round(performance.memory.usedJSHeapSize / 1048576),
          total: Math.round(performance.memory.totalJSHeapSize / 1048576),
          limit: Math.round(performance.memory.jsHeapSizeLimit / 1048576)
        };
      }
      
      // Get render counts
      const renderCounts = {};
      renderTracker.current.forEach((count, component) => {
        renderCounts[component] = count;
      });
      
      // Get store update counts
      const storeUpdates = {};
      storeUpdateTracker.current.forEach((count, store) => {
        storeUpdates[store] = count;
      });
      
      setMetrics(prev => ({
        ...prev,
        cacheStats,
        memoryUsage,
        renderCounts,
        storeUpdates
      }));
    };
    
    const interval = setInterval(updateMetrics, 1000);
    updateMetrics();
    
    return () => clearInterval(interval);
  }, [isVisible]);
  
  // Track component renders
  useEffect(() => {
    if (!isVisible) return;
    
    // Hook into React DevTools if available
    if (window.__REACT_DEVTOOLS_GLOBAL_HOOK__) {
      const hook = window.__REACT_DEVTOOLS_GLOBAL_HOOK__;
      
      const originalOnCommitFiberRoot = hook.onCommitFiberRoot;
      hook.onCommitFiberRoot = (id, root) => {
        // Track renders
        const fiber = root.current;
        if (fiber && fiber.elementType && fiber.elementType.name) {
          const componentName = fiber.elementType.name;
          renderTracker.current.set(
            componentName, 
            (renderTracker.current.get(componentName) || 0) + 1
          );
        }
        
        // Call original
        if (originalOnCommitFiberRoot) {
          originalOnCommitFiberRoot(id, root);
        }
      };
      
      return () => {
        hook.onCommitFiberRoot = originalOnCommitFiberRoot;
      };
    }
  }, [isVisible]);
  
  // Track store updates
  useEffect(() => {
    if (!isVisible) return;
    
    const stores = useStore();
    const unsubscribers = [];
    
    Object.entries(stores).forEach(([storeName, store]) => {
      if (store && store.subscribe) {
        const unsubscribe = store.subscribe(() => {
          storeUpdateTracker.current.set(
            storeName,
            (storeUpdateTracker.current.get(storeName) || 0) + 1
          );
        });
        unsubscribers.push(unsubscribe);
      }
    });
    
    return () => {
      unsubscribers.forEach(unsub => unsub());
    };
  }, [isVisible]);
  
  if (!isVisible || process.env.NODE_ENV !== 'development') {
    return null;
  }
  
  // Calculate optimization suggestions
  const suggestions = [];
  
  // High render count warning
  Object.entries(metrics.renderCounts).forEach(([component, count]) => {
    if (count > 50) {
      suggestions.push({
        type: 'warning',
        message: `${component} rendered ${count} times - consider memoization`
      });
    }
  });
  
  // Low cache hit rate
  if (metrics.cacheStats && metrics.cacheStats.hitRate < 0.7) {
    suggestions.push({
      type: 'info',
      message: `Cache hit rate is ${Math.round(metrics.cacheStats.hitRate * 100)}% - consider adjusting TTL`
    });
  }
  
  // High memory usage
  if (metrics.memoryUsage && metrics.memoryUsage.used / metrics.memoryUsage.total > 0.8) {
    suggestions.push({
      type: 'warning',
      message: `Memory usage is high (${metrics.memoryUsage.used}MB / ${metrics.memoryUsage.total}MB)`
    });
  }
  
  return (
    <div className="fixed bottom-4 right-4 bg-black bg-opacity-90 text-white p-4 rounded-lg shadow-lg z-50 w-80 font-mono text-12">
      <div className="flex justify-between items-center mb-3">
        <h3 className="text-14 font-bold">Performance Monitor</h3>
        <button
          onClick={() => setIsVisible(false)}
          className="text-gray-400 hover:text-white"
        >
          ✕
        </button>
      </div>
      
      {/* FPS Counter */}
      <div className="mb-3">
        <div className="flex justify-between">
          <span>FPS:</span>
          <span className={metrics.fps < 30 ? 'text-red-400' : 'text-green-400'}>
            {metrics.fps}
          </span>
        </div>
      </div>
      
      {/* Memory Usage */}
      {metrics.memoryUsage && (
        <div className="mb-3">
          <div className="text-gray-400 mb-1">Memory Usage:</div>
          <div className="bg-gray-800 rounded h-4 overflow-hidden">
            <div
              className="bg-gradient-to-r from-green-500 to-yellow-500 h-full transition-all"
              style={{ width: `${(metrics.memoryUsage.used / metrics.memoryUsage.total) * 100}%` }}
            />
          </div>
          <div className="text-10 text-gray-400 mt-1">
            {metrics.memoryUsage.used}MB / {metrics.memoryUsage.total}MB
          </div>
        </div>
      )}
      
      {/* Cache Stats */}
      {metrics.cacheStats && (
        <div className="mb-3">
          <div className="text-gray-400 mb-1">Cache Performance:</div>
          <div className="grid grid-cols-2 gap-2 text-10">
            <div>Entries: {metrics.cacheStats.entries}</div>
            <div>Hit Rate: {Math.round(metrics.cacheStats.hitRate * 100)}%</div>
            <div>Fresh: {metrics.cacheStats.fresh}</div>
            <div>Stale: {metrics.cacheStats.stale}</div>
          </div>
        </div>
      )}
      
      {/* Hot Components */}
      {Object.keys(metrics.renderCounts).length > 0 && (
        <div className="mb-3">
          <div className="text-gray-400 mb-1">Hot Components:</div>
          <div className="space-y-1">
            {Object.entries(metrics.renderCounts)
              .sort(([, a], [, b]) => b - a)
              .slice(0, 5)
              .map(([component, count]) => (
                <div key={component} className="flex justify-between text-10">
                  <span className="truncate">{component}</span>
                  <span className={count > 30 ? 'text-yellow-400' : ''}>{count}</span>
                </div>
              ))}
          </div>
        </div>
      )}
      
      {/* Store Updates */}
      {Object.keys(metrics.storeUpdates).length > 0 && (
        <div className="mb-3">
          <div className="text-gray-400 mb-1">Store Updates:</div>
          <div className="grid grid-cols-2 gap-2 text-10">
            {Object.entries(metrics.storeUpdates).map(([store, count]) => (
              <div key={store}>
                {store}: <span className={count > 50 ? 'text-yellow-400' : ''}>{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      
      {/* Optimization Suggestions */}
      {suggestions.length > 0 && (
        <div>
          <div className="text-gray-400 mb-1">Suggestions:</div>
          <div className="space-y-1">
            {suggestions.map((suggestion, index) => (
              <div
                key={index}
                className={`text-10 ${
                  suggestion.type === 'warning' ? 'text-yellow-400' : 'text-blue-400'
                }`}
              >
                • {suggestion.message}
              </div>
            ))}
          </div>
        </div>
      )}
      
      <div className="text-10 text-gray-500 mt-3 text-center">
        Press Ctrl+Shift+P to toggle
      </div>
    </div>
  );
}
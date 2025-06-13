import { api } from '../utils/api';
import { useDataStore } from '../stores';
import { buildApiUrl } from '../config';

/**
 * Singleton service for frame loading and caching
 */
class FrameService {
  static instance = null;
  
  constructor() {
    this.frameCache = new Map();
    this.cacheOrder = [];
    this.maxCacheSize = 100;
    this.loadingFrames = new Set();
  }
  
  static getInstance() {
    if (!this.instance) {
      this.instance = new FrameService();
    }
    return this.instance;
  }
  
  /**
   * Get cache key for a frame
   */
  getCacheKey(takeId, frameIndex, withBoundingBoxes = false) {
    return `${takeId}-${frameIndex}${withBoundingBoxes ? '-bb' : ''}`;
  }
  
  /**
   * Load a frame
   */
  async loadFrame(takeId, frameIndex, options = {}) {
    const { withBoundingBoxes = false, forceReload = false } = options;
    const cacheKey = this.getCacheKey(takeId, frameIndex, withBoundingBoxes);
    
    console.log('[FrameService] loadFrame called:', { takeId, frameIndex, withBoundingBoxes, cacheKey, forceReload });
    
    // Only force reload when explicitly requested
    // During capture, we don't need to force reload existing frames
    const shouldForceReload = forceReload;
    
    // Check cache first
    if (!shouldForceReload && this.frameCache.has(cacheKey)) {
      const cachedFrame = this.frameCache.get(cacheKey);
      // Keep blob URLs in cache - they're still valid until explicitly cleared
      // The forceReload flag will handle refreshing when needed
      console.log('[FrameService] Returning cached frame');
      return cachedFrame;
    }
    
    // Check if already loading
    if (this.loadingFrames.has(cacheKey)) {
      // Wait for existing load
      return new Promise((resolve) => {
        const checkInterval = setInterval(() => {
          if (!this.loadingFrames.has(cacheKey)) {
            clearInterval(checkInterval);
            resolve(this.frameCache.get(cacheKey) || null);
          }
        }, 50);
      });
    }
    
    // Mark as loading
    this.loadingFrames.add(cacheKey);
    
    try {
      let frameData;
      
      if (withBoundingBoxes) {
        // Load frame with bounding boxes drawn
        const response = await api.getFrameWithBoundingBoxes(takeId, frameIndex);
        if (response?.frame) {
          frameData = response.frame;
        }
      } else {
        // Load raw frame
        const url = buildApiUrl(`api/frames/take/${takeId}/frame/${frameIndex}?t=${Date.now()}`);
        console.log('[FrameService] Fetching frame from:', url);
        
        const response = await fetch(url, {
          headers: {
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
          }
        });
        
        console.log('[FrameService] Response status:', response.status);
        
        if (response.ok) {
          const blob = await response.blob();
          console.log('[FrameService] Blob size:', blob.size);
          frameData = URL.createObjectURL(blob);
          console.log('[FrameService] Created object URL:', frameData);
        } else {
          const errorText = await response.text();
          
          // Handle 404 errors gracefully
          if (response.status === 404) {
            console.log('[FrameService] Frame not found (404):', { takeId, frameIndex });
            
            // For 404 errors with forceReload, retry once after a delay
            if (options.forceReload && !options._retried) {
              console.log('[FrameService] Frame not found, retrying after delay...');
              this.loadingFrames.delete(cacheKey);
              await new Promise(resolve => setTimeout(resolve, 300));
              return this.loadFrame(takeId, frameIndex, { ...options, _retried: true });
            }
            
            // Return null without throwing for 404s
            return null;
          }
          
          // Log other errors
          console.error('[FrameService] Error response:', response.status, errorText);
        }
      }
      
      if (frameData) {
        this.cacheFrame(cacheKey, frameData);
        return frameData;
      }
      
      return null;
    } catch (error) {
      console.error('Error loading frame:', error);
      throw error;
    } finally {
      this.loadingFrames.delete(cacheKey);
    }
  }
  
  /**
   * Load multiple frames (for preloading)
   */
  async loadFrames(takeId, startIndex, endIndex, options = {}) {
    const promises = [];
    
    for (let i = startIndex; i <= endIndex; i++) {
      promises.push(this.loadFrame(takeId, i, options));
    }
    
    return Promise.all(promises);
  }
  
  /**
   * Cache a frame
   */
  cacheFrame(key, data) {
    // If already cached, move to end
    if (this.frameCache.has(key)) {
      const index = this.cacheOrder.indexOf(key);
      if (index > -1) {
        this.cacheOrder.splice(index, 1);
      }
      
      // Only revoke old URL if it's different from the new one
      const oldData = this.frameCache.get(key);
      if (oldData && oldData !== data && oldData.startsWith('blob:')) {
        URL.revokeObjectURL(oldData);
      }
    }
    
    // Add to cache
    this.frameCache.set(key, data);
    this.cacheOrder.push(key);
    
    // Evict oldest if over limit
    while (this.cacheOrder.length > this.maxCacheSize) {
      const oldestKey = this.cacheOrder.shift();
      const oldData = this.frameCache.get(oldestKey);
      
      if (oldData && oldData.startsWith('blob:')) {
        URL.revokeObjectURL(oldData);
      }
      
      this.frameCache.delete(oldestKey);
    }
  }
  
  /**
   * Clear cache for a specific take
   */
  clearTakeFrames(takeId) {
    const keysToRemove = [];
    
    for (const key of this.frameCache.keys()) {
      if (key.startsWith(`${takeId}-`)) {
        keysToRemove.push(key);
      }
    }
    
    keysToRemove.forEach(key => {
      const data = this.frameCache.get(key);
      if (data && data.startsWith('blob:')) {
        URL.revokeObjectURL(data);
      }
      
      this.frameCache.delete(key);
      
      const index = this.cacheOrder.indexOf(key);
      if (index > -1) {
        this.cacheOrder.splice(index, 1);
      }
    });
  }
  
  /**
   * Clear all cached frames
   */
  clearAllFrames() {
    // Revoke all blob URLs
    for (const data of this.frameCache.values()) {
      if (data && data.startsWith('blob:')) {
        URL.revokeObjectURL(data);
      }
    }
    
    this.frameCache.clear();
    this.cacheOrder = [];
  }
  
  /**
   * Preload frames around current index
   */
  async preloadAroundIndex(takeId, currentIndex, radius = 5, options = {}) {
    const store = useDataStore.getState();
    const frameCount = store.frameCount;
    
    if (frameCount === 0) return;
    
    const startIndex = Math.max(0, currentIndex - radius);
    const endIndex = Math.min(frameCount - 1, currentIndex + radius);
    
    // Load frames in background
    this.loadFrames(takeId, startIndex, endIndex, options).catch(error => {
      console.error('Error preloading frames:', error);
    });
  }
  
  /**
   * Get cache statistics
   */
  getCacheStats() {
    return {
      size: this.frameCache.size,
      maxSize: this.maxCacheSize,
      usage: (this.frameCache.size / this.maxCacheSize) * 100
    };
  }
  
  /**
   * Update frame in store and handle preloading
   */
  async updateCurrentFrame(takeId, frameIndex, options = {}) {
    const store = useDataStore.getState();
    
    try {
      console.log('[FrameService] updateCurrentFrame:', { takeId, frameIndex, options });
      
      // Load the frame
      const frameData = await this.loadFrame(takeId, frameIndex, options);
      
      if (frameData) {
        store.updateCurrentFrame(frameData);
        
        // Preload nearby frames
        this.preloadAroundIndex(takeId, frameIndex, 3, options);
      } else {
        console.error('[FrameService] No frame data returned for:', { takeId, frameIndex });
      }
      
      return frameData;
    } catch (error) {
      console.error('Error updating current frame:', error);
      throw error;
    }
  }
  
  /**
   * Update reference frame in store
   */
  async updateReferenceFrame(takeId, frameIndex, options = {}) {
    const store = useDataStore.getState();
    
    if (!takeId) {
      store.updateReferenceFrame(null);
      return null;
    }
    
    try {
      const frameData = await this.loadFrame(takeId, frameIndex, options);
      
      if (frameData) {
        store.updateReferenceFrame(frameData);
      } else {
        // No frame data - clear the reference frame
        store.updateReferenceFrame(null);
      }
      
      return frameData;
    } catch (error) {
      // Handle 404 errors gracefully for reference frames
      if (error.message && error.message.includes('404')) {
        console.log('Reference frame not found, clearing reference frame display');
        store.updateReferenceFrame(null);
        return null;
      }
      
      console.error('Error updating reference frame:', error);
      // Clear reference frame on error
      store.updateReferenceFrame(null);
      return null;
    }
  }
  
  /**
   * Clear the reference frame
   */
  clearReferenceFrame() {
    // Clear reference frame from store
    useDataStore.getState().clearReferenceFrame();
  }
}

export default FrameService;
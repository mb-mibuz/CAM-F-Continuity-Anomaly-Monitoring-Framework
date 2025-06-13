/**
 * Frontend Configuration Module
 * 
 * Centralizes all configuration values and provides environment-based settings.
 * Uses import.meta.env for Vite environment variables.
 */

// Development defaults
const DEFAULTS = {
  API_BASE_URL: 'http://127.0.0.1:8000',
  API_TIMEOUT: 30000, // 30 seconds
  SSE_URL: 'http://127.0.0.1:8000/api/sse/stream',
  SSE_RECONNECT_DELAY: 1000,
  SSE_MAX_RECONNECT_DELAY: 30000,
  POLLING_INTERVAL: 1000, // 1 second
  FRAME_CACHE_SIZE: 50,
  FRAME_PRELOAD_COUNT: 5,
  MAX_UPLOAD_SIZE: 5 * 1024 * 1024 * 1024, // 5GB
  SUPPORTED_VIDEO_FORMATS: ['mp4', 'avi', 'mov', 'mkv', 'webm'],
  SUPPORTED_IMAGE_FORMATS: ['jpg', 'jpeg', 'png', 'bmp', 'webp'],
  DEBUG_MODE: false,
};

// Environment variable mapping
const getEnvVar = (key, defaultValue) => {
  // In Vite, environment variables are accessed via import.meta.env
  const envKey = `VITE_${key}`;
  return import.meta.env?.[envKey] || defaultValue;
};

// Build configuration object
const config = {
  // API Configuration
  api: {
    baseUrl: getEnvVar('API_BASE_URL', DEFAULTS.API_BASE_URL),
    timeout: parseInt(getEnvVar('API_TIMEOUT', DEFAULTS.API_TIMEOUT)),
    endpoints: {
      // Projects
      projects: '/api/projects',
      project: (id) => `/api/projects/${id}`,
      
      // Scenes
      scenes: '/api/scenes',
      scene: (id) => `/api/scenes/${id}`,
      scenesByProject: (projectId) => `/api/scenes?project_id=${projectId}`,
      
      // Angles
      angles: '/api/angles',
      angle: (id) => `/api/angles/${id}`,
      anglesByScene: (sceneId) => `/api/angles?scene_id=${sceneId}`,
      
      // Takes
      takes: '/api/takes',
      take: (id) => `/api/takes/${id}`,
      takesByAngle: (angleId) => `/api/takes?angle_id=${angleId}`,
      
      // Frames
      frames: '/api/frames',
      frame: (id) => `/api/frames/${id}`,
      framesByTake: (takeId) => `/api/frames?take_id=${takeId}`,
      frameData: (frameId) => `/api/frames/${frameId}/data`,
      frameByTakeAndIndex: (takeId, frameIndex) => `/api/frames/take/${takeId}/frame/${frameIndex}`,
      
      // Capture
      captureSources: '/api/capture/sources',
      captureStart: '/api/capture/start',
      captureStop: '/api/capture/stop',
      captureFrame: '/api/capture/frame',
      videoUpload: '/api/capture/upload',
      
      // Detectors
      detectors: '/api/detectors',
      detector: (id) => `/api/detectors/${id}`,
      detectorConfig: (sceneId) => `/api/scenes/${sceneId}/detector-config`,
      detectorStatus: '/api/detectors/status',
      
      // Processing
      processingStart: '/api/processing/start',
      processingStop: '/api/processing/stop',
      processingStatus: '/api/processing/status',
      
      // Notes
      notes: '/api/notes',
      note: (id) => `/api/notes/${id}`,
      notesByFrame: (frameId) => `/api/notes?frame_id=${frameId}`,
      
      // Export
      export: '/api/export/pdf',
      
      // Session
      session: '/api/session',
      sessionCreate: '/api/session/create',
      sessionRestore: '/api/session/restore',
      
      // Health
      health: '/health',
      version: '/api/version',
    }
  },
  
  // SSE Configuration
  sse: {
    url: getEnvVar('SSE_URL', DEFAULTS.SSE_URL),
    reconnectDelay: parseInt(getEnvVar('SSE_RECONNECT_DELAY', DEFAULTS.SSE_RECONNECT_DELAY)),
    maxReconnectDelay: parseInt(getEnvVar('SSE_MAX_RECONNECT_DELAY', DEFAULTS.SSE_MAX_RECONNECT_DELAY)),
    events: {
      // Frame events
      FRAME_CAPTURED: 'frame_captured',
      FRAME_PROCESSED: 'frame_processed',
      
      // Detector events
      DETECTOR_STATUS: 'detector_status',
      DETECTOR_ERROR: 'detector_error',
      DETECTOR_RESULT: 'detector_result',
      
      // Processing events
      PROCESSING_STARTED: 'processing_started',
      PROCESSING_STOPPED: 'processing_stopped',
      PROCESSING_PROGRESS: 'processing_progress',
      
      // System events
      SERVICE_STATUS: 'service_status',
      ERROR: 'error',
    }
  },
  
  // Polling Configuration
  polling: {
    interval: parseInt(getEnvVar('POLLING_INTERVAL', DEFAULTS.POLLING_INTERVAL)),
    endpoints: {
      detectorStatus: true,
      processingStatus: true,
      frameUpdates: false, // Use SSE instead
    }
  },
  
  // Frame Configuration
  frames: {
    cacheSize: parseInt(getEnvVar('FRAME_CACHE_SIZE', DEFAULTS.FRAME_CACHE_SIZE)),
    preloadCount: parseInt(getEnvVar('FRAME_PRELOAD_COUNT', DEFAULTS.FRAME_PRELOAD_COUNT)),
    loadTimeout: 5000, // 5 seconds
  },
  
  // Upload Configuration
  upload: {
    maxSize: parseInt(getEnvVar('MAX_UPLOAD_SIZE', DEFAULTS.MAX_UPLOAD_SIZE)),
    supportedVideoFormats: DEFAULTS.SUPPORTED_VIDEO_FORMATS,
    supportedImageFormats: DEFAULTS.SUPPORTED_IMAGE_FORMATS,
    chunkSize: 5 * 1024 * 1024, // 5MB chunks
  },
  
  // UI Configuration
  ui: {
    notifications: {
      duration: 3000, // 3 seconds
      position: 'top-right',
    },
    animations: {
      enabled: true,
      duration: 200, // milliseconds
    },
    theme: {
      mode: 'dark', // 'light' | 'dark' | 'system'
    }
  },
  
  // Debug Configuration
  debug: {
    enabled: getEnvVar('DEBUG_MODE', DEFAULTS.DEBUG_MODE) === 'true',
    logLevel: getEnvVar('LOG_LEVEL', 'warn'), // 'error' | 'warn' | 'info' | 'debug'
    showDevTools: getEnvVar('SHOW_DEV_TOOLS', 'false') === 'true',
  },
  
  // Feature Flags
  features: {
    experimentalDetectors: getEnvVar('FEATURE_EXPERIMENTAL_DETECTORS', 'false') === 'true',
    batchProcessing: getEnvVar('FEATURE_BATCH_PROCESSING', 'true') === 'true',
    advancedExport: getEnvVar('FEATURE_ADVANCED_EXPORT', 'true') === 'true',
    multiUserSession: getEnvVar('FEATURE_MULTI_USER', 'false') === 'true',
  }
};

// Helper function to build full API URL
export const buildApiUrl = (endpoint) => {
  const baseUrl = config.api.baseUrl;
  // Remove trailing slash from base URL and leading slash from endpoint
  const cleanBase = baseUrl.replace(/\/$/, '');
  const cleanEndpoint = endpoint.replace(/^\//, '');
  return `${cleanBase}/${cleanEndpoint}`;
};

// Helper function to build SSE URL
export const buildSseUrl = (path = '/api/sse') => {
  const sseUrl = config.sse.url;
  const cleanUrl = sseUrl.replace(/\/$/, '');
  const cleanPath = path.replace(/^\//, '');
  return `${cleanUrl}/${cleanPath}`;
};

// Environment detection
export const isDevelopment = import.meta.env?.MODE === 'development';
export const isProduction = import.meta.env?.MODE === 'production';
export const isTest = import.meta.env?.MODE === 'test';

// Validate configuration on load
const validateConfig = () => {
  const errors = [];
  
  if (!config.api.baseUrl) {
    errors.push('API_BASE_URL is not configured');
  }
  
  if (!config.sse.url) {
    errors.push('SSE_URL is not configured');
  }
  
  if (config.upload.maxSize <= 0) {
    errors.push('MAX_UPLOAD_SIZE must be positive');
  }
  
  if (errors.length > 0) {
    console.error('Configuration errors:', errors);
    if (isProduction) {
      throw new Error('Invalid configuration: ' + errors.join(', '));
    }
  }
};

// Run validation
validateConfig();

// Log configuration in development
if (isDevelopment && config.debug.enabled) {
  console.log('Frontend configuration loaded:', {
    api: config.api.baseUrl,
    sse: config.sse.url,
    debug: config.debug.enabled,
    features: config.features,
  });
}

export default config;
import { handleError, NetworkError } from '../services/ErrorHandler';
import { prepareEntityForAPI, checkDuplicateName } from './crudValidation';
import config, { buildApiUrl } from '../config';

const API_BASE = config.api.baseUrl + '/api';

class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.status = status;
    this.data = data;
    this.name = 'ApiError';
  }
}

// Request interceptor
async function request(url, options = {}) {
  const defaultOptions = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers
    }
  };
  
  // Merge options
  const finalOptions = { ...defaultOptions, ...options };
  
  // React Query handles caching, so we just perform the request
  return performRequest(url, finalOptions);
}

// Perform the actual request
async function performRequest(url, options) {
  try {
    const response = await fetch(url, options);
    
    // Handle non-2xx responses
    if (!response.ok) {
      const errorData = await response.text();
      let parsedError;
      
      try {
        parsedError = JSON.parse(errorData);
      } catch {
        parsedError = { message: errorData };
      }
      
      throw new ApiError(
        parsedError.message || `HTTP ${response.status}: ${response.statusText}`,
        response.status,
        parsedError
      );
    }
    
    // Handle empty responses
    if (response.status === 204 || response.headers.get('content-length') === '0') {
      return null;
    }
    
    // Parse JSON response
    return await response.json();
  } catch (error) {
    if (error instanceof ApiError) {
      // Don't show notifications for expected frame 404 errors
      const isFrameRequest = url.includes('/frames/take/') && url.includes('/frame/');
      const isNotFoundError = error.status === 404;
      
      if (!isFrameRequest || !isNotFoundError) {
        // Log API errors for non-frame requests or non-404 errors
        handleError(error, 'API Request', { url, options });
      }
      
      throw error;
    }
    
    // Network or other errors
    const networkError = new NetworkError(
      error.message || 'Network error',
      error.code
    );
    handleError(networkError, 'Network Request', { url, options });
    
    throw new ApiError(
      error.message || 'Network error',
      0,
      { originalError: error }
    );
  }
}

export const api = {
  // Projects
  async getProjects(sortBy = 'created_at', order = 'desc') {
    const response = await request(`${API_BASE}/projects?sort_by=${sortBy}&order=${order}`);
    return response; // Backend returns array directly
  },

  async createProject(name) {
    const data = prepareEntityForAPI('project', { name });
    return request(`${API_BASE}/projects`, {
      method: 'POST',
      body: JSON.stringify(data)
    });
  },

  async updateProject(projectId, data) {
    return request(`${API_BASE}/projects/${projectId}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
  },

  async deleteProject(projectId) {
    return request(`${API_BASE}/projects/${projectId}`, {
      method: 'DELETE'
    });
  },

  // Scenes
  async getScenes(projectId) {
    try {
      const response = await request(`${API_BASE}/projects/${projectId}/scenes`);
      return response; // Backend returns array directly
    } catch (error) {
      if (error.status === 404) {
        return [];
      }
      throw error;
    }
  },

  async getScene(sceneId) {
    return request(`${API_BASE}/scenes/${sceneId}`);
  },

  async createScene(data) {
    // Don't use prepareEntityForAPI for scene as it has complex detector settings
    const { projectId, ...sceneData } = data;
    return request(`${API_BASE}/projects/${projectId}/scenes`, {
      method: 'POST',
      body: JSON.stringify(sceneData)
    });
  },

  async updateScene(sceneId, data) {
    return request(`${API_BASE}/scenes/${sceneId}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
  },

  async deleteScene(sceneId) {
    return request(`${API_BASE}/scenes/${sceneId}`, {
      method: 'DELETE'
    });
  },

  // Angles
  async getAngles(sceneId) {
    try {
      const data = await request(`${API_BASE}/scenes/${sceneId}/angles`);
      return Array.isArray(data) ? data : [];
    } catch (error) {
      if (error.status === 404) {
        return [];
      }
      throw error;
    }
  },
  
  async getAngle(angleId) {
    return request(`${API_BASE}/angles/${angleId}`);
  },

  async createAngle(data) {
    const { sceneId, ...angleData } = data;
    return request(`${API_BASE}/scenes/${sceneId}/angles`, {
      method: 'POST',
      body: JSON.stringify(angleData)
    });
  },

  async updateAngle(angleId, data) {
    return request(`${API_BASE}/angles/${angleId}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
  },

  // Takes
  async getTakes(angleId) {
    try {
      const data = await request(`${API_BASE}/angles/${angleId}/takes`);
      return Array.isArray(data) ? data : [];
    } catch (error) {
      if (error.status === 404) {
        return [];
      }
      throw error;
    }
  },

  async getTake(takeId) {
    return request(`${API_BASE}/takes/${takeId}`);
  },

  async createTake(data) {
    const { angleId, ...takeData } = data;
    return request(`${API_BASE}/angles/${angleId}/takes`, {
      method: 'POST',
      body: JSON.stringify(takeData)
    });
  },

  async updateTake(takeId, data) {
    return request(`${API_BASE}/takes/${takeId}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
  },

  async deleteTake(takeId) {
    return request(`${API_BASE}/takes/${takeId}`, {
      method: 'DELETE'
    });
  },

  async setReferenceTake(takeId) {
    const take = await this.getTake(takeId);
    if (!take) throw new Error('Take not found');
    
    return request(`${API_BASE}/angles/${take.angle_id}/set-reference-take`, {
      method: 'POST',
      body: JSON.stringify({ take_id: takeId })
    });
  },

  async getReferenceTake(angleId) {
    try {
      return await request(`${API_BASE}/angles/${angleId}/reference-take`);
    } catch (error) {
      if (error.status === 404) {
        return null;
      }
      throw error;
    }
  },

  async clearTakeData(takeId) {
    return request(`${API_BASE}/takes/${takeId}/clear`, {
      method: 'POST'
    });
  },

  // Frames
  async getFrameCount(takeId) {
    try {
      const data = await request(`${API_BASE}/frames/take/${takeId}/count`);
      return data?.frame_count || 0; 
    } catch (error) {
      if (error.status === 404) {
        return 0;
      }
      throw error;
    }
  },

  async getFrameWithBoundingBoxes(takeId, frameId) {
    try {
      // This endpoint returns an image, not JSON
      const url = buildApiUrl(`api/frames/take/${takeId}/frame/${frameId}/with-bounding-boxes`);
      const response = await fetch(url);
      
      if (!response.ok) {
        if (response.status === 404) {
          return null;
        }
        throw new ApiError(
          `HTTP ${response.status}: ${response.statusText}`,
          response.status,
          {}
        );
      }
      
      // Convert to blob URL
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      
      return { frame: objectUrl };
    } catch (error) {
      if (error.status === 404) {
        return null;
      }
      throw error;
    }
  },

  // Errors
  async getTakeErrors(takeId, params = {}) {
    try {
      const queryParams = new URLSearchParams(params).toString();
      const response = await request(`${API_BASE}/errors/take/${takeId}${queryParams ? '?' + queryParams : ''}`);
      return response.errors || []; 
    } catch (error) {
      if (error.status === 404) {
        return [];
      }
      throw error;
    }
  },

  async getGroupedErrors(takeId) {
    try {
      const response = await request(`${API_BASE}/errors/grouped/${takeId}`);
      return response || { errors: [] };
    } catch (error) {
      if (error.status === 404) {
        return { errors: [] };
      }
      throw error;
    }
  },

  async getContinuousErrors(takeId) {
    try {
      const response = await request(`${API_BASE}/errors/continuous/${takeId}`);
      return response.continuous_errors || [];
    } catch (error) {
      if (error.status === 404) {
        return [];
      }
      throw error;
    }
  },

  async markErrorAsFalsePositive(takeId, errorData, reason) {
    // Debug log to see what error data we're sending
    console.log('[API] Marking false positive:', {
      takeId,
      errorData,
      detector_name: errorData.detector_name,
      frame_id: errorData.frame_id,
      error_id: errorData.id
    });
    
    return request(`${API_BASE}/errors/false-positive`, {
      method: 'POST',
      body: JSON.stringify({
        take_id: takeId,
        detector_name: errorData.detector_name,
        frame_id: errorData.frame_id,
        error_id: errorData.id,
        description: errorData.description,  // Add description for group matching
        reason: reason,
        marked_by: 'user'
      })
    });
  },

  // Capture
  async getCaptureStatus() {
    return request(`${API_BASE}/capture/status`);
  },

  async getCaptureSources() {
    try {
      const [camerasResponse, monitorsResponse, windowsResponse] = await Promise.all([
        api.getCameras(),
        api.getMonitors(),
        api.getWindows()
      ]);
      
      return { 
        cameras: camerasResponse.cameras || [], 
        monitors: monitorsResponse.monitors || [], 
        windows: windowsResponse.windows || [] 
      };
    } catch (error) {
      console.error('Error getting capture sources:', error);
      return { cameras: [], monitors: [], windows: [] };
    }
  },


  async getCameras() {
    try {
      const data = await request(`${API_BASE}/capture/sources/cameras`);
      return data; // Return full response object
    } catch (error) {
      console.error('Error getting cameras:', error);
      return { cameras: [] };
    }
  },

  async getMonitors() {
    try {
      const data = await request(`${API_BASE}/capture/sources/monitors`);
      return data; // Return full response object
    } catch (error) {
      console.error('Error getting monitors:', error);
      return { monitors: [] };
    }
  },

  async getWindows() {
    try {
      const data = await request(`${API_BASE}/capture/sources/windows`);
      return data; // Return full response object
    } catch (error) {
      console.error('Error getting windows:', error);
      return { windows: [] };
    }
  },

  async setCameraSource(cameraId) {
    const payload = { 
      type: 'camera', 
      id: parseInt(cameraId, 10)
    };
    console.log('setCameraSource payload:', payload);
    return request(`${API_BASE}/capture/set-source`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  async setScreenSource(monitorId, region = null) {
    const payload = { 
      type: 'screen', 
      id: parseInt(monitorId, 10),
      region 
    };
    console.log('setScreenSource payload:', payload);
    return request(`${API_BASE}/capture/set-source`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  async setWindowSource(windowHandle) {
    const payload = { 
      type: 'window',   
      id: parseInt(windowHandle, 10)
    };
    console.log('setWindowSource payload:', payload);
    return request(`${API_BASE}/capture/set-source`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  async startCapture(data) {
    const { take_id, ...captureData } = data;
    return request(`${API_BASE}/capture/start/${take_id}`, {
      method: 'POST',
      body: JSON.stringify(captureData)
    });
  },

  async stopCapture() {
    return request(`${API_BASE}/capture/stop`, {
      method: 'POST'
    });
  },

  async getCaptureProgress(takeId) {
    try {
      return await request(`${API_BASE}/capture/progress/${takeId}`);
    } catch (error) {
      console.error('Error getting capture progress:', error);
      return { frame_count: 0, is_capturing: false };
    }
  },

  async getDetailedCaptureStatus(takeId) {
    try {
      return await request(`${API_BASE}/capture/status/detailed/${takeId}`);
    } catch (error) {
      console.error('Error getting detailed status:', error);
      return null;
    }
  },

  async startVideoCapture(data) {
    return request(`${API_BASE}/capture/start-video-capture`, {
      method: 'POST',
      body: JSON.stringify(data)
    });
  },

  async getVideoProgress() {
    return request(`${API_BASE}/capture/video-progress`);
  },

  async uploadVideoFile(takeId, file, onProgress) {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE}/upload/video/${takeId}`, {
      method: 'POST',
      body: formData,
      // Don't set Content-Type header - let browser set it with boundary
    });

    if (!response.ok) {
      const error = await response.text();
      throw new ApiError(error || 'Upload failed', response.status);
    }

    return response.json();
  },

  async setComparisonTake(comparisonTakeId, useReference = false) {
    return request(`${API_BASE}/capture/set-comparison-take`, {
      method: 'POST',
      body: JSON.stringify({ 
        comparison_take_id: comparisonTakeId,
        use_reference: useReference
      })
    });
  },

  // Detectors
  async getDetectors() {
    const data = await request(`${API_BASE}/detectors`); 
    return data?.detectors || [];
  },
  
  async stopAllDetectors() {
    return request(`${API_BASE}/detectors/stop-all`, {
      method: 'POST'
    });
  },
  
  async startDetectorsForScene(sceneId, context = {}) {
    return request(`${API_BASE}/detectors/start-for-scene/${sceneId}`, {
      method: 'POST',
      body: JSON.stringify(context)
    });
  },
  
  async startDetector(detectorName, data) {
    return request(`${API_BASE}/detectors/${detectorName}/start`, {
      method: 'POST',
      body: JSON.stringify(data)
    });
  },
  
  async stopDetector(detectorName) {
    return request(`${API_BASE}/detectors/${detectorName}/stop`, {
      method: 'POST'
    });
  },
  
  async updateDetectorConfig(sceneId, detectorName, config) {
    return request(`${API_BASE}/detectors/scene/${sceneId}/detector/${detectorName}/config`, {
      method: 'PUT',
      body: JSON.stringify({ config, enabled: true })
    });
  },

  async getDetectorSchema(detectorName) {
    const data = await request(`${API_BASE}/detectors/${detectorName}/schema`);
    return data?.schema || { fields: {} };
  },

  async getSceneDetectorConfigs(sceneId) {
    return request(`${API_BASE}/detectors/scene/${sceneId}/configurations`);
  },

  async saveDetectorConfig(sceneId, detectorName, config) {
    return request(`${API_BASE}/detectors/scene/${sceneId}/detector/${detectorName}/config`, {
      method: 'PUT',
      body: JSON.stringify(config)
    });
  },

  async downloadDetectorTemplate(detectorName) {
    const response = await fetch(`${API_BASE}/detectors/template/${encodeURIComponent(detectorName)}`, {
      method: 'GET',
    });
    
    if (!response.ok) {
      throw new Error('Failed to download template');
    }
    
    const blob = await response.blob();
    const contentDisposition = response.headers.get('Content-Disposition');
    let filename = `${detectorName.replace(/\s+/g, '_').toLowerCase()}_template.zip`;
    
    if (contentDisposition) {
      const filenameMatch = contentDisposition.match(/filename="(.+)"/);
      if (filenameMatch) {
        filename = filenameMatch[1];
      }
    }
    
    return { blob, filename };
  },

  // Processing
  async startProcessing(takeId, referenceTakeId = null) {
    return request(`${API_BASE}/processing/start`, {
      method: 'POST',
      body: JSON.stringify({ 
        take_id: takeId,
        reference_take_id: referenceTakeId 
      })
    });
  },

  async stopProcessing() {
    return request(`${API_BASE}/processing/stop`, {
      method: 'POST'
    });
  },

  async getProcessingStatus() {
    return request(`${API_BASE}/processing/status`);
  },

  async restartProcessing(takeId, referenceTakeId = null) {
    return request(`${API_BASE}/processing/restart`, {
      method: 'POST',
      body: JSON.stringify({ 
        take_id: takeId,
        reference_take_id: referenceTakeId 
      })
    });
  },

  async getProcessingStatusForTake(takeId) {
    try {
      return await request(`${API_BASE}/processing/status/${takeId}`);
    } catch (error) {
      if (error.status === 404) {
        return { is_processing: false, processed_frames: 0 };
      }
      throw error;
    }
  },

  // Export
  async exportProject(projectId, options = {}) {
    const response = await fetch(`${API_BASE}/export/project/${projectId}/pdf`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(options)
    });
    
    if (!response.ok) {
      const error = await response.text();
      throw new ApiError(error || 'Export failed', response.status);
    }
    
    // Return the blob for the caller to handle
    return await response.blob();
  },

  async exportScene(sceneId, options = {}) {
    const response = await fetch(`${API_BASE}/export/scene/${sceneId}/pdf`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(options)
    });
    
    if (!response.ok) {
      const error = await response.text();
      throw new ApiError(error || 'Export failed', response.status);
    }
    
    // Return the blob for the caller to handle
    return await response.blob();
  },

  async exportTake(takeId, options = {}) {
    const response = await fetch(`${API_BASE}/export/take/${takeId}/pdf`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(options)
    });
    
    if (!response.ok) {
      const error = await response.text();
      throw new ApiError(error || 'Export failed', response.status);
    }
    
    // Return the blob data for the caller to handle
    return await response.blob();
  }
};
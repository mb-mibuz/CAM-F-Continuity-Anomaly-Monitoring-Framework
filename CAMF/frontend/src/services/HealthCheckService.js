import config from '../config';

/**
 * Health Check Service
 * 
 * Provides comprehensive health checks for all system components.
 * Used for monitoring system status and diagnosing issues.
 */
class HealthCheckService {
  constructor() {
    this.healthEndpoints = {
      api: `${config.api.baseUrl}/health`,
      version: `${config.api.baseUrl}/api/version`,
      detectorStatus: `${config.api.baseUrl}/api/detectors/status`,
      captureStatus: `${config.api.baseUrl}/api/capture/status`,
      processingStatus: `${config.api.baseUrl}/api/processing/status`
    };
  }

  /**
   * Check API Gateway health
   */
  async checkAPI() {
    const startTime = Date.now();
    try {
      const response = await fetch(this.healthEndpoints.api, {
        method: 'GET',
        signal: AbortSignal.timeout(5000) // 5 second timeout
      });
      
      const responseTime = Date.now() - startTime;
      
      if (response.ok) {
        const data = await response.json();
        return {
          status: 'ok',
          responseTime,
          message: 'API Gateway is healthy',
          details: data
        };
      } else {
        return {
          status: 'error',
          responseTime,
          message: `API Gateway returned status ${response.status}`,
          error: response.statusText
        };
      }
    } catch (error) {
      return {
        status: 'error',
        responseTime: Date.now() - startTime,
        message: 'Failed to connect to API Gateway',
        error: error.message
      };
    }
  }

  /**
   * Check WebSocket connection
   */
  async checkWebSocket() {
    return new Promise((resolve) => {
      const startTime = Date.now();
      let ws;
      
      const timeout = setTimeout(() => {
        if (ws) ws.close();
        resolve({
          status: 'error',
          responseTime: Date.now() - startTime,
          message: 'WebSocket connection timeout',
          error: 'Connection took too long'
        });
      }, 5000);

      try {
        ws = new WebSocket(`${config.websocket.url}/ws`);
        
        ws.onopen = () => {
          clearTimeout(timeout);
          ws.close();
          resolve({
            status: 'ok',
            responseTime: Date.now() - startTime,
            message: 'WebSocket connection successful'
          });
        };
        
        ws.onerror = (error) => {
          clearTimeout(timeout);
          resolve({
            status: 'error',
            responseTime: Date.now() - startTime,
            message: 'WebSocket connection failed',
            error: error.type || 'Unknown error'
          });
        };
      } catch (error) {
        clearTimeout(timeout);
        resolve({
          status: 'error',
          responseTime: Date.now() - startTime,
          message: 'Failed to create WebSocket connection',
          error: error.message
        });
      }
    });
  }

  /**
   * Check storage service availability
   */
  async checkStorage() {
    const startTime = Date.now();
    try {
      // Try to fetch projects as a proxy for storage health
      const response = await fetch(`${config.api.baseUrl}/api/projects`, {
        method: 'GET',
        signal: AbortSignal.timeout(5000)
      });
      
      const responseTime = Date.now() - startTime;
      
      if (response.ok) {
        return {
          status: 'ok',
          responseTime,
          message: 'Storage service is accessible'
        };
      } else {
        return {
          status: 'error',
          responseTime,
          message: `Storage service returned status ${response.status}`,
          error: response.statusText
        };
      }
    } catch (error) {
      return {
        status: 'error',
        responseTime: Date.now() - startTime,
        message: 'Failed to access storage service',
        error: error.message
      };
    }
  }

  /**
   * Check detector framework status
   */
  async checkDetectors() {
    const startTime = Date.now();
    try {
      const response = await fetch(this.healthEndpoints.detectorStatus, {
        method: 'GET',
        signal: AbortSignal.timeout(5000)
      });
      
      const responseTime = Date.now() - startTime;
      
      if (response.ok) {
        const data = await response.json();
        const activeDetectors = Object.values(data).filter(d => d.status === 'running').length;
        return {
          status: activeDetectors > 0 ? 'ok' : 'warning',
          responseTime,
          message: `${activeDetectors} detector(s) active`,
          details: data
        };
      } else {
        return {
          status: 'error',
          responseTime,
          message: 'Failed to get detector status',
          error: response.statusText
        };
      }
    } catch (error) {
      return {
        status: 'error',
        responseTime: Date.now() - startTime,
        message: 'Failed to check detector status',
        error: error.message
      };
    }
  }

  /**
   * Check capture service status
   */
  async checkCapture() {
    const startTime = Date.now();
    try {
      const response = await fetch(this.healthEndpoints.captureStatus, {
        method: 'GET',
        signal: AbortSignal.timeout(5000)
      });
      
      const responseTime = Date.now() - startTime;
      
      if (response.ok) {
        const data = await response.json();
        return {
          status: 'ok',
          responseTime,
          message: data.is_capturing ? 'Capture in progress' : 'Capture service ready',
          details: data
        };
      } else {
        return {
          status: 'error',
          responseTime,
          message: 'Failed to get capture status',
          error: response.statusText
        };
      }
    } catch (error) {
      return {
        status: 'error',
        responseTime: Date.now() - startTime,
        message: 'Failed to check capture status',
        error: error.message
      };
    }
  }

  /**
   * Check processing service status
   */
  async checkProcessing() {
    const startTime = Date.now();
    try {
      const response = await fetch(this.healthEndpoints.processingStatus, {
        method: 'GET',
        signal: AbortSignal.timeout(5000)
      });
      
      const responseTime = Date.now() - startTime;
      
      if (response.ok) {
        const data = await response.json();
        return {
          status: 'ok',
          responseTime,
          message: data.is_processing ? 'Processing in progress' : 'Processing service ready',
          details: data
        };
      } else {
        return {
          status: 'error',
          responseTime,
          message: 'Failed to get processing status',
          error: response.statusText
        };
      }
    } catch (error) {
      return {
        status: 'error',
        responseTime: Date.now() - startTime,
        message: 'Failed to check processing status',
        error: error.message
      };
    }
  }

  /**
   * Get system version information
   */
  async getVersion() {
    try {
      const response = await fetch(this.healthEndpoints.version, {
        method: 'GET',
        signal: AbortSignal.timeout(3000)
      });
      
      if (response.ok) {
        return await response.json();
      } else {
        return {
          version: 'unknown',
          error: 'Failed to fetch version'
        };
      }
    } catch (error) {
      return {
        version: 'unknown',
        error: error.message
      };
    }
  }

  /**
   * Run all health checks
   */
  async checkAll() {
    const checks = {
      api: await this.checkAPI(),
      websocket: await this.checkWebSocket(),
      storage: await this.checkStorage(),
      detectors: await this.checkDetectors(),
      capture: await this.checkCapture(),
      processing: await this.checkProcessing()
    };
    
    const version = await this.getVersion();
    
    // Determine overall health
    const criticalChecks = ['api', 'storage'];
    const criticalHealthy = criticalChecks.every(
      check => checks[check].status === 'ok'
    );
    
    const allHealthy = Object.values(checks).every(
      c => c.status === 'ok'
    );
    
    const hasWarnings = Object.values(checks).some(
      c => c.status === 'warning'
    );
    
    return {
      healthy: criticalHealthy,
      status: allHealthy ? 'healthy' : (criticalHealthy ? 'degraded' : 'unhealthy'),
      hasWarnings,
      checks,
      version,
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Run continuous health monitoring
   */
  startMonitoring(callback, interval = 30000) {
    // Run initial check
    this.checkAll().then(callback);
    
    // Set up interval
    const intervalId = setInterval(async () => {
      const health = await this.checkAll();
      callback(health);
    }, interval);
    
    // Return stop function
    return () => clearInterval(intervalId);
  }
}

// Export singleton instance
const healthCheckService = new HealthCheckService();
export default healthCheckService;
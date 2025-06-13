/**
 * Global Error Handler Service
 * 
 * Provides centralized error handling, logging, and reporting
 * for both synchronous and asynchronous errors
 */

import { useAppStore } from '../stores';

class ErrorHandler {
  constructor() {
    this.errorLog = [];
    this.maxLogSize = 100;
    this.errorHandlers = new Map();
    this.setupGlobalHandlers();
  }

  setupGlobalHandlers() {
    // Handle unhandled promise rejections
    window.addEventListener('unhandledrejection', (event) => {
      console.error('Unhandled promise rejection:', event.reason);
      this.handleError(event.reason, 'UnhandledPromiseRejection');
      event.preventDefault();
    });

    // Handle global errors
    window.addEventListener('error', (event) => {
      console.error('Global error:', event.error);
      this.handleError(event.error, 'GlobalError', {
        message: event.message,
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno
      });
    });
  }

  /**
   * Register a custom error handler for specific error types
   */
  registerHandler(errorType, handler) {
    this.errorHandlers.set(errorType, handler);
  }

  /**
   * Main error handling method
   */
  handleError(error, context = 'Unknown', metadata = {}) {
    // Normalize error object
    const normalizedError = this.normalizeError(error);
    
    // Add to error log
    const errorEntry = {
      id: Date.now().toString(),
      timestamp: new Date().toISOString(),
      error: normalizedError,
      context,
      metadata,
      stack: normalizedError.stack
    };
    
    this.addToLog(errorEntry);
    
    // Check for custom handler
    const customHandler = this.errorHandlers.get(normalizedError.type);
    if (customHandler) {
      customHandler(normalizedError, context, metadata);
      return;
    }
    
    // Handle based on error type
    switch (normalizedError.type) {
      case 'NetworkError':
        this.handleNetworkError(normalizedError);
        break;
      
      case 'ValidationError':
        this.handleValidationError(normalizedError);
        break;
      
      case 'AuthenticationError':
        this.handleAuthenticationError(normalizedError);
        break;
      
      case 'PermissionError':
        this.handlePermissionError(normalizedError);
        break;
      
      case 'CaptureError':
        this.handleCaptureError(normalizedError);
        break;
      
      case 'ProcessingError':
        this.handleProcessingError(normalizedError);
        break;
      
      case 'StorageError':
        this.handleStorageError(normalizedError);
        break;
      
      default:
        this.handleGenericError(normalizedError);
    }
  }

  /**
   * Normalize various error formats into a consistent structure
   */
  normalizeError(error) {
    if (error instanceof Error) {
      return {
        type: error.constructor.name,
        message: error.message,
        stack: error.stack,
        code: error.code,
        ...error
      };
    }
    
    if (typeof error === 'string') {
      return {
        type: 'StringError',
        message: error,
        stack: new Error().stack
      };
    }
    
    if (error && typeof error === 'object') {
      return {
        type: error.type || 'ObjectError',
        message: error.message || error.detail || JSON.stringify(error),
        code: error.code || error.status,
        ...error
      };
    }
    
    return {
      type: 'UnknownError',
      message: String(error),
      stack: new Error().stack
    };
  }

  /**
   * Add error to log with size management
   */
  addToLog(errorEntry) {
    this.errorLog.push(errorEntry);
    
    // Maintain max log size
    if (this.errorLog.length > this.maxLogSize) {
      this.errorLog.shift();
    }
  }

  /**
   * Error type specific handlers
   */
  handleNetworkError(error) {
    const appStore = useAppStore.getState();
    
    if (error.message.includes('Failed to fetch')) {
      appStore.addNotification({ type: 'error', message: 'Connection to server failed. Please check your network.' });
    } else if (error.code === 'ECONNREFUSED') {
      appStore.addNotification({ type: 'error', message: 'Server is not responding. Please ensure the backend is running.' });
    } else {
      appStore.addNotification({ type: 'error', message: `Network error: ${error.message}` });
    }
  }

  handleValidationError(error) {
    const appStore = useAppStore.getState();
    appStore.addNotification({ type: 'warning', message: `Validation error: ${error.message}` });
  }

  handleAuthenticationError(error) {
    const appStore = useAppStore.getState();
    appStore.addNotification({ type: 'error', message: 'Authentication failed. Please log in again.' });
    // Could trigger logout or redirect to login
  }

  handlePermissionError(error) {
    const appStore = useAppStore.getState();
    appStore.addNotification({ type: 'error', message: `Permission denied: ${error.message}` });
  }

  handleCaptureError(error) {
    const appStore = useAppStore.getState();
    
    if (error.message.includes('source')) {
      appStore.addNotification({ type: 'error', message: 'Capture source error. Please check your camera/screen settings.' });
      appStore.openModal('sourceDisconnected', { error });
    } else {
      appStore.addNotification({ type: 'error', message: `Capture error: ${error.message}` });
    }
  }

  handleProcessingError(error) {
    const appStore = useAppStore.getState();
    appStore.addNotification({ type: 'error', message: `Processing error: ${error.message}`, duration: 0 });
  }

  handleStorageError(error) {
    const appStore = useAppStore.getState();
    
    if (error.message.includes('quota')) {
      appStore.addNotification({ type: 'error', message: 'Storage quota exceeded. Please free up space.' });
    } else {
      appStore.addNotification({ type: 'error', message: `Storage error: ${error.message}` });
    }
  }

  handleGenericError(error) {
    const appStore = useAppStore.getState();
    
    // Don't show notification for canceled requests
    if (error.message?.includes('aborted') || error.message?.includes('canceled')) {
      return;
    }
    
    console.error('Unhandled error:', error);
    appStore.addNotification({
      type: 'error',
      message: `An error occurred: ${error.message}`,
      duration: 10000
    });
  }

  /**
   * Utility methods
   */
  getErrorLog() {
    return [...this.errorLog];
  }

  clearErrorLog() {
    this.errorLog = [];
  }

  getLastError() {
    return this.errorLog[this.errorLog.length - 1];
  }

  /**
   * Export error log for debugging
   */
  exportErrorLog() {
    const logData = {
      exportDate: new Date().toISOString(),
      errorCount: this.errorLog.length,
      errors: this.errorLog
    };
    
    const blob = new Blob([JSON.stringify(logData, null, 2)], {
      type: 'application/json'
    });
    
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `camf-error-log-${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  /**
   * Create custom error classes
   */
  static NetworkError = class extends Error {
    constructor(message, code) {
      super(message);
      this.name = 'NetworkError';
      this.code = code;
    }
  };

  static ValidationError = class extends Error {
    constructor(message, field) {
      super(message);
      this.name = 'ValidationError';
      this.field = field;
    }
  };

  static CaptureError = class extends Error {
    constructor(message, source) {
      super(message);
      this.name = 'CaptureError';
      this.source = source;
    }
  };

  static ProcessingError = class extends Error {
    constructor(message, detector) {
      super(message);
      this.name = 'ProcessingError';
      this.detector = detector;
    }
  };
}

// Create singleton instance
const errorHandler = new ErrorHandler();

// Export for use in async functions
export const handleError = (error, context, metadata) => {
  errorHandler.handleError(error, context, metadata);
};

// Export error classes
export const {
  NetworkError,
  ValidationError,
  CaptureError,
  ProcessingError
} = ErrorHandler;

export default errorHandler;
// utils/AsyncOperationManager.js
import { useAppStore } from '../stores';

class AsyncOperationManager {
  constructor() {
    this.operations = new Map();
    this.globalErrorHandlers = new Set();
  }

  /**
   * Register a global error handler
   */
  onError(handler) {
    this.globalErrorHandlers.add(handler);
    return () => this.globalErrorHandlers.delete(handler);
  }

  /**
   * Create a managed async operation
   */
  createOperation(name, operation, options = {}) {
    const {
      timeout = 30000,
      retries = 0,
      retryDelay = 1000,
      onSuccess,
      onError,
      showNotifications = true
    } = options;

    return async (...args) => {
      const operationId = `${name}-${Date.now()}`;
      const abortController = new AbortController();
      
      // Store operation reference
      this.operations.set(operationId, {
        name,
        startTime: Date.now(),
        abortController,
        status: 'running'
      });

      const appStore = useAppStore.getState();
      
      try {
        // Set up timeout
        const timeoutId = timeout ? setTimeout(() => {
          abortController.abort();
          throw new Error(`Operation '${name}' timed out after ${timeout}ms`);
        }, timeout) : null;

        // Execute with retries
        let lastError;
        for (let attempt = 0; attempt <= retries; attempt++) {
          try {
            const result = await operation(...args, {
              signal: abortController.signal
            });

            // Clear timeout
            if (timeoutId) clearTimeout(timeoutId);

            // Update operation status
            this.operations.set(operationId, {
              ...this.operations.get(operationId),
              status: 'completed',
              endTime: Date.now()
            });

            // Call success handler
            if (onSuccess) onSuccess(result);
            
            // Show success notification
            if (showNotifications && options.successMessage) {
              useAppStore.getState().addNotification({
                type: 'success',
                message: options.successMessage
              });
            }

            return result;

          } catch (error) {
            lastError = error;
            
            // Don't retry on abort
            if (error.name === 'AbortError') {
              throw error;
            }

            // Wait before retry
            if (attempt < retries) {
              await new Promise(resolve => 
                setTimeout(resolve, retryDelay * Math.pow(2, attempt))
              );
              continue;
            }
          }
        }

        // All retries failed
        throw lastError;

      } catch (error) {
        // Update operation status
        this.operations.set(operationId, {
          ...this.operations.get(operationId),
          status: 'failed',
          endTime: Date.now(),
          error
        });

        // Call error handlers
        if (onError) onError(error);
        
        // Call global error handlers
        this.globalErrorHandlers.forEach(handler => handler(error, name));

        // Show error notification
        if (showNotifications) {
          const errorMessage = this.formatError(error, name);
          useAppStore.getState().addNotification({
            type: 'error',
            message: errorMessage
          });
        }

        throw error;

      } finally {
        // Cleanup after delay
        setTimeout(() => {
          this.operations.delete(operationId);
        }, 5000);
      }
    };
  }

  /**
   * Cancel an operation
   */
  cancelOperation(operationId) {
    const operation = this.operations.get(operationId);
    if (operation && operation.status === 'running') {
      operation.abortController.abort();
      operation.status = 'cancelled';
      return true;
    }
    return false;
  }

  /**
   * Cancel all running operations
   */
  cancelAll() {
    for (const [id, operation] of this.operations) {
      if (operation.status === 'running') {
        this.cancelOperation(id);
      }
    }
  }

  /**
   * Get operation statistics
   */
  getStats() {
    const stats = {
      total: this.operations.size,
      running: 0,
      completed: 0,
      failed: 0,
      cancelled: 0
    };

    for (const operation of this.operations.values()) {
      stats[operation.status]++;
    }

    return stats;
  }

  /**
   * Format error message
   */
  formatError(error, operationName) {
    if (error.name === 'AbortError') {
      return `${operationName} was cancelled`;
    }
    
    if (error.message.includes('Network')) {
      return `Network error during ${operationName}`;
    }
    
    if (error.message.includes('timeout')) {
      return `${operationName} timed out - please try again`;
    }
    
    return `${operationName} failed: ${error.message}`;
  }
}

// Create singleton instance
const asyncOperationManager = new AsyncOperationManager();

// Hook for using in components
export function useAsyncOperation(name, operation, options = {}) {
  const [state, setState] = useState({
    loading: false,
    error: null,
    data: null
  });

  const execute = useCallback(
    asyncOperationManager.createOperation(
      name,
      async (...args) => {
        setState({ loading: true, error: null, data: state.data });
        
        try {
          const result = await operation(...args);
          setState({ loading: false, error: null, data: result });
          return result;
        } catch (error) {
          setState({ loading: false, error, data: null });
          throw error;
        }
      },
      options
    ),
    [name, operation, options]
  );

  const cancel = useCallback(() => {
    // Find and cancel the operation
    for (const [id, op] of asyncOperationManager.operations) {
      if (op.name === name && op.status === 'running') {
        asyncOperationManager.cancelOperation(id);
        break;
      }
    }
  }, [name]);

  return { ...state, execute, cancel };
}

export default asyncOperationManager;
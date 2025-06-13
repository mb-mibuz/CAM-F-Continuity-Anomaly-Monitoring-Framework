# CAMF/common/errors.py
"""
Standardized error handling for CAMF.
Provides consistent error types and handling patterns across the codebase.
"""

import logging
from typing import Optional, Dict, Any, Type
from functools import wraps
import traceback
from datetime import datetime

logger = logging.getLogger(__name__)


# Base Exceptions
class CAMFError(Exception):
    """Base exception for all CAMF errors."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.now()


class ConfigurationError(CAMFError):
    """Raised when there's a configuration problem."""


class ServiceError(CAMFError):
    """Raised when a service encounters an error."""


class CaptureError(ServiceError):
    """Raised when capture operations fail."""


class DetectorError(ServiceError):
    """Raised when detector operations fail."""


class StorageError(ServiceError):
    """Raised when storage operations fail."""


class ValidationError(CAMFError):
    """Raised when validation fails."""


class ResourceError(CAMFError):
    """Raised when resource allocation or access fails."""


class CommunicationError(CAMFError):
    """Raised when inter-service communication fails."""


class SecurityError(CAMFError):
    """Raised when security checks fail."""


# Error Context Manager
class ErrorHandler:
    """Context manager for standardized error handling."""
    
    def __init__(self, operation: str, reraise: bool = True, 
                 default_return: Any = None, log_level: int = logging.ERROR):
        self.operation = operation
        self.reraise = reraise
        self.default_return = default_return
        self.log_level = log_level
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            return False
            
        # Log the error with context
        logger.log(
            self.log_level,
            f"Error in {self.operation}: {exc_val}",
            exc_info=True
        )
        
        # Convert to appropriate CAMF error if needed
        if not isinstance(exc_val, CAMFError):
            # Wrap in appropriate error type
            if "config" in self.operation.lower():
                exc_val = ConfigurationError(str(exc_val))
            elif "capture" in self.operation.lower():
                exc_val = CaptureError(str(exc_val))
            elif "detector" in self.operation.lower():
                exc_val = DetectorError(str(exc_val))
            elif "storage" in self.operation.lower():
                exc_val = StorageError(str(exc_val))
            else:
                exc_val = ServiceError(str(exc_val))
        
        # Add operation context
        exc_val.details['operation'] = self.operation
        exc_val.details['traceback'] = traceback.format_exc()
        
        if not self.reraise:
            return True  # Suppress the exception
        
        return False  # Let exception propagate


# Decorator for error handling
def handle_errors(operation: str = None, 
                  error_class: Type[CAMFError] = ServiceError,
                  reraise: bool = True,
                  default_return: Any = None,
                  log_level: int = logging.ERROR):
    """
    Decorator for standardized error handling.
    
    Args:
        operation: Description of the operation being performed
        error_class: Type of error to raise if conversion is needed
        reraise: Whether to reraise the exception after logging
        default_return: Value to return if reraise is False
        log_level: Logging level for the error
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            op_name = operation or f"{func.__module__}.{func.__name__}"
            
            try:
                return func(*args, **kwargs)
            except CAMFError:
                # Already a CAMF error, just reraise
                raise
            except Exception as e:
                # Log the error
                logger.log(
                    log_level,
                    f"Error in {op_name}: {e}",
                    exc_info=True
                )
                
                # Convert to CAMF error
                camf_error = error_class(
                    str(e),
                    details={
                        'operation': op_name,
                        'original_error': type(e).__name__,
                        'traceback': traceback.format_exc()
                    }
                )
                
                if reraise:
                    raise camf_error
                else:
                    return default_return
                    
        return wrapper
    return decorator


# Utility functions for common error patterns
def log_and_continue(operation: str, exception: Exception, 
                     level: int = logging.WARNING) -> None:
    """Log an error and continue execution."""
    logger.log(
        level,
        f"Non-critical error in {operation}: {exception}",
        exc_info=True
    )


def log_and_default(operation: str, exception: Exception, 
                    default: Any, level: int = logging.WARNING) -> Any:
    """Log an error and return a default value."""
    logger.log(
        level,
        f"Error in {operation}, returning default: {exception}",
        exc_info=True
    )
    return default


def retry_on_error(max_attempts: int = 3, delay: float = 1.0, 
                   backoff: float = 2.0, 
                   exceptions: tuple = (Exception,)):
    """
    Decorator to retry a function on error.
    
    Args:
        max_attempts: Maximum number of attempts
        delay: Initial delay between attempts in seconds
        backoff: Multiplier for delay after each attempt
        exceptions: Tuple of exceptions to catch and retry
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_attempts} failed for "
                            f"{func.__name__}: {e}. Retrying in {current_delay}s..."
                        )
                        import time
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"All {max_attempts} attempts failed for {func.__name__}"
                        )
            
            # All attempts failed, raise the last exception
            raise last_exception
            
        return wrapper
    return decorator


# Standard error response formats for APIs
def create_error_response(error: Exception, request_id: Optional[str] = None) -> Dict[str, Any]:
    """Create a standardized error response for APIs."""
    if isinstance(error, CAMFError):
        return {
            "error": {
                "type": type(error).__name__,
                "message": error.message,
                "details": error.details,
                "timestamp": error.timestamp.isoformat()
            },
            "request_id": request_id,
            "success": False
        }
    else:
        return {
            "error": {
                "type": type(error).__name__,
                "message": str(error),
                "timestamp": datetime.now().isoformat()
            },
            "request_id": request_id,
            "success": False
        }


# Common validation patterns
def validate_required(value: Any, name: str, value_type: Type = None) -> Any:
    """Validate that a required value is present and of correct type."""
    if value is None:
        raise ValidationError(f"{name} is required")
    
    if value_type is not None and not isinstance(value, value_type):
        raise ValidationError(
            f"{name} must be of type {value_type.__name__}, "
            f"got {type(value).__name__}"
        )
    
    return value


def validate_range(value: Any, name: str, min_val: Any = None, 
                   max_val: Any = None) -> Any:
    """Validate that a value is within a specified range."""
    if min_val is not None and value < min_val:
        raise ValidationError(f"{name} must be >= {min_val}, got {value}")
    
    if max_val is not None and value > max_val:
        raise ValidationError(f"{name} must be <= {max_val}, got {value}")
    
    return value


def validate_choice(value: Any, name: str, choices: list) -> Any:
    """Validate that a value is one of the allowed choices."""
    if value not in choices:
        raise ValidationError(
            f"{name} must be one of {choices}, got {value}"
        )
    
    return value
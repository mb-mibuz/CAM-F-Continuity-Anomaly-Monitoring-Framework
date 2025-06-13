"""
Caching layer for continuous error grouping.
Prevents recalculation of error groups on every request.
"""
import time
import hashlib
import json
from typing import Dict, Any, List, Optional, Tuple
from threading import RLock

class ContinuousErrorCache:
    """
    Caches continuous error groupings to avoid recalculation.
    Uses content-based cache keys to detect when data changes.
    """
    
    def __init__(self, ttl_seconds: int = 300):  # 5 minute cache
        self.ttl = ttl_seconds
        self._cache: Dict[str, Tuple[Any, float, str]] = {}  # key -> (data, timestamp, content_hash)
        self._lock = RLock()
    
    def _compute_content_hash(self, results: List[Dict[str, Any]]) -> str:
        """Compute hash of results to detect changes."""
        # Create a stable representation
        content = []
        for r in sorted(results, key=lambda x: (x.get('frame_id', 0), x.get('detector_name', ''), x.get('id', 0) or 0)):
            content.append({
                'id': r.get('id'),
                'frame_id': r.get('frame_id'),
                'detector_name': r.get('detector_name'),
                'description': r.get('description'),
                'confidence': r.get('confidence'),
                'is_false_positive': r.get('is_false_positive', False)
            })
        
        content_str = json.dumps(content, sort_keys=True)
        return hashlib.md5(content_str.encode()).hexdigest()
    
    def get(self, take_id: int, results: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        """
        Get cached grouped results if available and content hasn't changed.
        
        Args:
            take_id: Take ID
            results: Current detector results
            
        Returns:
            Cached grouped results or None if cache miss
        """
        with self._lock:
            cache_key = f"take_{take_id}_errors"
            
            if cache_key not in self._cache:
                return None
                
            cached_data, timestamp, cached_hash = self._cache[cache_key]
            
            # Check if expired
            if time.time() - timestamp > self.ttl:
                del self._cache[cache_key]
                return None
                
            # Check if content changed
            current_hash = self._compute_content_hash(results)
            if current_hash != cached_hash:
                del self._cache[cache_key]
                return None
                
            return cached_data
    
    def set(self, take_id: int, results: List[Dict[str, Any]], grouped_results: List[Dict[str, Any]]):
        """
        Cache grouped results.
        
        Args:
            take_id: Take ID
            results: Original detector results
            grouped_results: Grouped/processed results
        """
        with self._lock:
            cache_key = f"take_{take_id}_errors"
            content_hash = self._compute_content_hash(results)
            self._cache[cache_key] = (grouped_results, time.time(), content_hash)
            
            # Clean old entries
            self._clean_expired()
    
    def invalidate(self, take_id: int):
        """Invalidate cache for a specific take."""
        with self._lock:
            cache_key = f"take_{take_id}_errors"
            if cache_key in self._cache:
                del self._cache[cache_key]
    
    def clear(self):
        """Clear entire cache."""
        with self._lock:
            self._cache.clear()
    
    def _clean_expired(self):
        """Remove expired entries."""
        current_time = time.time()
        expired_keys = [
            key for key, (_, timestamp, _) in self._cache.items()
            if current_time - timestamp > self.ttl
        ]
        
        for key in expired_keys:
            del self._cache[key]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            return {
                'size': len(self._cache),
                'ttl_seconds': self.ttl,
                'entries': [
                    {
                        'key': key,
                        'age_seconds': int(time.time() - timestamp),
                        'content_hash': content_hash
                    }
                    for key, (_, timestamp, content_hash) in self._cache.items()
                ]
            }

# Global cache instance
_error_cache = ContinuousErrorCache()

def get_error_cache() -> ContinuousErrorCache:
    """Get the global error cache instance."""
    return _error_cache
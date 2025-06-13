# CAMF/services/detector_framework/result_cache.py
"""
Production-grade result caching system for detector framework.
Implements multi-level caching with LRU in-memory and disk-based storage.
"""

import hashlib
import json
import time
import pickle
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import OrderedDict
from datetime import timedelta
import shutil
import logging

from CAMF.common.models import DetectorResult, ErrorConfidence

logger = logging.getLogger(__name__)


class CacheKey:
    """Generates and manages multi-level cache keys."""
    
    @staticmethod
    def generate_frame_hash(frame_data: bytes) -> str:
        """Generate hash of frame content using MD5 for speed."""
        return hashlib.md5(frame_data).hexdigest()
    
    @staticmethod
    def generate_config_hash(config: Dict[str, Any]) -> str:
        """Generate hash of detector configuration."""
        # Sort keys for consistent hashing
        config_str = json.dumps(config, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()[:16]
    
    @staticmethod
    def generate_composite_key(frame_hash: str, detector_name: str, 
                             detector_version: str, config_hash: str,
                             scene_context: Optional[str] = None) -> str:
        """Generate composite cache key from all components."""
        components = [
            frame_hash,
            detector_name.replace(' ', '_'),
            detector_version,
            config_hash
        ]
        
        if scene_context:
            components.append(scene_context)
        
        return ":".join(components)
    
    @staticmethod
    def parse_composite_key(key: str) -> Dict[str, str]:
        """Parse composite key back to components."""
        parts = key.split(':')
        result = {
            'frame_hash': parts[0] if len(parts) > 0 else '',
            'detector_name': parts[1] if len(parts) > 1 else '',
            'detector_version': parts[2] if len(parts) > 2 else '',
            'config_hash': parts[3] if len(parts) > 3 else '',
        }
        
        if len(parts) > 4:
            result['scene_context'] = parts[4]
        
        return result


class LRUCache:
    """Thread-safe LRU cache implementation."""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.cache = OrderedDict()
        self.lock = threading.RLock()
        self.hits = 0
        self.misses = 0
        self.evictions = 0
    
    def get(self, key: str) -> Optional[List[DetectorResult]]:
        """Get item from cache, updating LRU order."""
        with self.lock:
            if key in self.cache:
                # Move to end (most recently used)
                self.cache.move_to_end(key)
                self.hits += 1
                return self.cache[key]
            else:
                self.misses += 1
                return None
    
    def put(self, key: str, value: List[DetectorResult]):
        """Put item in cache, evicting LRU if needed."""
        with self.lock:
            if key in self.cache:
                # Update existing entry
                self.cache.move_to_end(key)
                self.cache[key] = value
            else:
                # Add new entry
                self.cache[key] = value
                
                # Evict if over capacity
                if len(self.cache) > self.max_size:
                    self.cache.popitem(last=False)  # Remove oldest
                    self.evictions += 1
    
    def invalidate(self, key: str) -> bool:
        """Remove specific key from cache."""
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                return True
            return False
    
    def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching pattern."""
        with self.lock:
            keys_to_remove = [k for k in self.cache.keys() if pattern in k]
            for key in keys_to_remove:
                del self.cache[key]
            return len(keys_to_remove)
    
    def clear(self):
        """Clear entire cache."""
        with self.lock:
            self.cache.clear()
            self.hits = 0
            self.misses = 0
            self.evictions = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self.lock:
            total_requests = self.hits + self.misses
            hit_rate = self.hits / total_requests if total_requests > 0 else 0
            
            return {
                'size': len(self.cache),
                'max_size': self.max_size,
                'hits': self.hits,
                'misses': self.misses,
                'evictions': self.evictions,
                'hit_rate': hit_rate,
                'total_requests': total_requests
            }


class DiskCache:
    """Disk-based cache with size management."""
    
    def __init__(self, cache_dir: str, max_entries: int = 10000, 
                 max_size_mb: int = 1000):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_entries = max_entries
        self.max_size_bytes = max_size_mb * 1024 * 1024
        
        self.index_file = self.cache_dir / "cache_index.json"
        self.index = self._load_index()
        self.lock = threading.RLock()
        
        # Stats
        self.hits = 0
        self.misses = 0
        self.writes = 0
    
    def _load_index(self) -> Dict[str, Dict[str, Any]]:
        """Load cache index from disk."""
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache index: {e}")
                return {}
        return {}
    
    def _save_index(self):
        """Save cache index to disk."""
        with open(self.index_file, 'w') as f:
            json.dump(self.index, f)
    
    def _get_cache_path(self, key: str) -> Path:
        """Get file path for cache key."""
        # Use first 2 chars for directory sharding
        shard = key[:2]
        shard_dir = self.cache_dir / shard
        shard_dir.mkdir(exist_ok=True)
        return shard_dir / f"{key}.pkl"
    
    def get(self, key: str) -> Optional[List[DetectorResult]]:
        """Get item from disk cache."""
        with self.lock:
            if key not in self.index:
                self.misses += 1
                return None
            
            cache_path = self._get_cache_path(key)
            if not cache_path.exists():
                # Index out of sync
                del self.index[key]
                self._save_index()
                self.misses += 1
                return None
            
            try:
                with open(cache_path, 'rb') as f:
                    data = pickle.load(f)
                
                # Update access time
                self.index[key]['last_access'] = time.time()
                self.hits += 1
                
                # Deserialize results
                results = []
                for result_data in data:
                    result = DetectorResult(
                        confidence=ErrorConfidence(result_data['confidence']),
                        description=result_data['description'],
                        frame_id=result_data['frame_id'],
                        detector_name=result_data['detector_name'],
                        bounding_boxes=result_data.get('bounding_boxes', []),
                        metadata=result_data.get('metadata', {}),
                        timestamp=result_data.get('timestamp', time.time())
                    )
                    results.append(result)
                
                return results
                
            except Exception as e:
                print(f"Error reading cache file {cache_path}: {e}")
                # Remove corrupted entry
                del self.index[key]
                cache_path.unlink(missing_ok=True)
                self._save_index()
                self.misses += 1
                return None
    
    def put(self, key: str, value: List[DetectorResult]):
        """Put item in disk cache."""
        with self.lock:
            # Serialize results
            data = []
            for result in value:
                data.append({
                    'confidence': result.confidence if isinstance(result.confidence, (int, float)) else result.confidence.value,
                    'description': result.description,
                    'frame_id': result.frame_id,
                    'detector_name': result.detector_name,
                    'bounding_boxes': result.bounding_boxes,
                    'metadata': result.metadata,
                    'timestamp': result.timestamp
                })
            
            cache_path = self._get_cache_path(key)
            
            try:
                with open(cache_path, 'wb') as f:
                    pickle.dump(data, f)
                
                file_size = cache_path.stat().st_size
                
                self.index[key] = {
                    'size': file_size,
                    'created': time.time(),
                    'last_access': time.time()
                }
                
                self.writes += 1
                
                # Check if we need to evict
                self._evict_if_needed()
                
                # Save index periodically
                if self.writes % 100 == 0:
                    self._save_index()
                
            except Exception as e:
                print(f"Error writing cache file {cache_path}: {e}")
    
    def _evict_if_needed(self):
        """Evict old entries if over limits."""
        # Check entry count
        if len(self.index) > self.max_entries:
            self._evict_lru(len(self.index) - self.max_entries)
        
        # Check total size
        total_size = sum(entry['size'] for entry in self.index.values())
        if total_size > self.max_size_bytes:
            self._evict_until_size(self.max_size_bytes * 0.9)  # 90% target
    
    def _evict_lru(self, count: int):
        """Evict least recently used entries."""
        # Sort by last access time
        sorted_keys = sorted(self.index.keys(), 
                           key=lambda k: self.index[k]['last_access'])
        
        for key in sorted_keys[:count]:
            cache_path = self._get_cache_path(key)
            cache_path.unlink(missing_ok=True)
            del self.index[key]
    
    def _evict_until_size(self, target_size: int):
        """Evict until total size is below target."""
        sorted_keys = sorted(self.index.keys(), 
                           key=lambda k: self.index[k]['last_access'])
        
        total_size = sum(entry['size'] for entry in self.index.values())
        
        for key in sorted_keys:
            if total_size <= target_size:
                break
            
            entry_size = self.index[key]['size']
            cache_path = self._get_cache_path(key)
            cache_path.unlink(missing_ok=True)
            del self.index[key]
            total_size -= entry_size
    
    def invalidate(self, key: str) -> bool:
        """Remove specific key from cache."""
        with self.lock:
            if key in self.index:
                cache_path = self._get_cache_path(key)
                cache_path.unlink(missing_ok=True)
                del self.index[key]
                return True
            return False
    
    def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching pattern."""
        with self.lock:
            keys_to_remove = [k for k in self.index.keys() if pattern in k]
            for key in keys_to_remove:
                cache_path = self._get_cache_path(key)
                cache_path.unlink(missing_ok=True)
                del self.index[key]
            
            if keys_to_remove:
                self._save_index()
            
            return len(keys_to_remove)
    
    def clear(self):
        """Clear entire disk cache."""
        with self.lock:
            # Remove all cache files
            shutil.rmtree(self.cache_dir, ignore_errors=True)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            
            # Reset index
            self.index = {}
            self._save_index()
            
            # Reset stats
            self.hits = 0
            self.misses = 0
            self.writes = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self.lock:
            total_size = sum(entry['size'] for entry in self.index.values())
            total_requests = self.hits + self.misses
            hit_rate = self.hits / total_requests if total_requests > 0 else 0
            
            return {
                'entries': len(self.index),
                'max_entries': self.max_entries,
                'total_size_mb': total_size / (1024 * 1024),
                'max_size_mb': self.max_size_bytes / (1024 * 1024),
                'hits': self.hits,
                'misses': self.misses,
                'writes': self.writes,
                'hit_rate': hit_rate,
                'total_requests': total_requests
            }
    
    def cleanup(self):
        """Clean up resources and save index."""
        with self.lock:
            self._save_index()


class ResultCache:
    """Main result caching system with multi-level storage."""
    
    def __init__(self, cache_dir: str = "detector_cache",
                 memory_size: int = 1000,
                 disk_entries: int = 10000,
                 disk_size_mb: int = 1000,
                 ttl_hours: int = 24):
        """
        Initialize result cache.
        
        Args:
            cache_dir: Directory for disk cache
            memory_size: Max entries in memory cache
            disk_entries: Max entries in disk cache
            disk_size_mb: Max disk cache size in MB
            ttl_hours: Time-to-live for cache entries in hours
        """
        self.memory_cache = LRUCache(max_size=memory_size)
        self.disk_cache = DiskCache(cache_dir, max_entries=disk_entries, 
                                   max_size_mb=disk_size_mb)
        self.ttl = timedelta(hours=ttl_hours)
        
        # Version tracking for invalidation
        self.detector_versions: Dict[str, str] = {}
        
        # Performance tracking
        self.lookup_times = []
        self.lock = threading.RLock()
        
        # Start background cleanup
        self._start_cleanup_thread()
    
    def get(self, frame_hash: str, detector_name: str, detector_version: str,
            config: Dict[str, Any], scene_context: Optional[str] = None) -> Optional[List[DetectorResult]]:
        """Get cached results if available."""
        start_time = time.time()
        
        # Generate cache key
        config_hash = CacheKey.generate_config_hash(config)
        cache_key = CacheKey.generate_composite_key(
            frame_hash, detector_name, detector_version, 
            config_hash, scene_context
        )
        
        # Check memory cache first
        results = self.memory_cache.get(cache_key)
        if results is not None:
            self._record_lookup_time(time.time() - start_time)
            return results
        
        # Check disk cache
        results = self.disk_cache.get(cache_key)
        if results is not None:
            # Promote to memory cache
            self.memory_cache.put(cache_key, results)
            self._record_lookup_time(time.time() - start_time)
            return results
        
        self._record_lookup_time(time.time() - start_time)
        return None
    
    def put(self, frame_hash: str, detector_name: str, detector_version: str,
            config: Dict[str, Any], results: List[DetectorResult],
            scene_context: Optional[str] = None):
        """Cache detector results."""
        # Generate cache key
        config_hash = CacheKey.generate_config_hash(config)
        cache_key = CacheKey.generate_composite_key(
            frame_hash, detector_name, detector_version, 
            config_hash, scene_context
        )
        
        # Update version tracking
        with self.lock:
            self.detector_versions[detector_name] = detector_version
        
        # Store in both caches
        self.memory_cache.put(cache_key, results)
        self.disk_cache.put(cache_key, results)
    
    def invalidate_detector(self, detector_name: str):
        """Invalidate all cache entries for a detector."""
        pattern = f":{detector_name.replace(' ', '_')}:"
        
        memory_count = self.memory_cache.invalidate_pattern(pattern)
        disk_count = self.disk_cache.invalidate_pattern(pattern)
        
        print(f"Invalidated {memory_count} memory and {disk_count} disk entries for {detector_name}")
    
    def invalidate_config(self, detector_name: str, config: Dict[str, Any]):
        """Invalidate cache entries for specific detector config."""
        config_hash = CacheKey.generate_config_hash(config)
        pattern = f":{detector_name.replace(' ', '_')}:*:{config_hash}"
        
        memory_count = self.memory_cache.invalidate_pattern(pattern)
        disk_count = self.disk_cache.invalidate_pattern(pattern)
        
        print(f"Invalidated {memory_count} memory and {disk_count} disk entries for config")
    
    def invalidate_scene(self, scene_context: str):
        """Invalidate all cache entries for a scene."""
        pattern = f":{scene_context}"
        
        memory_count = self.memory_cache.invalidate_pattern(pattern)
        disk_count = self.disk_cache.invalidate_pattern(pattern)
        
        print(f"Invalidated {memory_count} memory and {disk_count} disk entries for scene")
    
    def clear(self):
        """Clear all caches."""
        self.memory_cache.clear()
        self.disk_cache.clear()
        self.detector_versions.clear()
        print("All caches cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        memory_stats = self.memory_cache.get_stats()
        disk_stats = self.disk_cache.get_stats()
        
        # Calculate average lookup time
        avg_lookup_time = 0
        if self.lookup_times:
            avg_lookup_time = sum(self.lookup_times) / len(self.lookup_times) * 1000  # ms
        
        # Overall hit rate
        total_hits = memory_stats['hits'] + disk_stats['hits']
        total_requests = memory_stats['total_requests'] + disk_stats['total_requests']
        overall_hit_rate = total_hits / total_requests if total_requests > 0 else 0
        
        return {
            'memory': memory_stats,
            'disk': disk_stats,
            'overall': {
                'hit_rate': overall_hit_rate,
                'avg_lookup_time_ms': avg_lookup_time,
                'total_requests': total_requests,
                'detector_versions': len(self.detector_versions)
            }
        }
    
    def _record_lookup_time(self, time_seconds: float):
        """Record lookup time for performance tracking."""
        with self.lock:
            self.lookup_times.append(time_seconds)
            # Keep last 1000 lookups
            if len(self.lookup_times) > 1000:
                self.lookup_times.pop(0)
    
    def _start_cleanup_thread(self):
        """Start background thread for TTL cleanup."""
        def cleanup_loop():
            while True:
                try:
                    time.sleep(3600)  # Run every hour
                    self._cleanup_expired()
                except Exception as e:
                    print(f"Cache cleanup error: {e}")
        
        thread = threading.Thread(target=cleanup_loop, daemon=True)
        thread.start()
    
    def _cleanup_expired(self):
        """Remove expired entries based on TTL."""
        current_time = time.time()
        ttl_seconds = self.ttl.total_seconds()
        
        # Clean disk cache
        with self.disk_cache.lock:
            expired_keys = []
            for key, info in self.disk_cache.index.items():
                if current_time - info['created'] > ttl_seconds:
                    expired_keys.append(key)
            
            for key in expired_keys:
                self.disk_cache.invalidate(key)
            
            if expired_keys:
                print(f"Cleaned up {len(expired_keys)} expired cache entries")
    
    def warm_cache(self, frame_hashes: List[str], detector_name: str,
                   detector_version: str, config: Dict[str, Any],
                   results_provider: callable):
        """Pre-populate cache with results."""
        config_hash = CacheKey.generate_config_hash(config)
        warmed = 0
        
        for frame_hash in frame_hashes:
            cache_key = CacheKey.generate_composite_key(
                frame_hash, detector_name, detector_version, config_hash
            )
            
            # Check if already cached
            if self.memory_cache.get(cache_key) is None:
                # Get results from provider
                results = results_provider(frame_hash)
                if results:
                    self.put(frame_hash, detector_name, detector_version, 
                            config, results)
                    warmed += 1
        
        print(f"Warmed cache with {warmed} entries for {detector_name}")
        return warmed
    
    def cleanup(self):
        """Clean up resources."""
        self.disk_cache.cleanup()


# Singleton instance
_result_cache: Optional[ResultCache] = None


def get_result_cache(cache_dir: str = "detector_cache") -> ResultCache:
    """Get or create the result cache singleton."""
    global _result_cache
    if _result_cache is None:
        _result_cache = ResultCache(cache_dir=cache_dir)
    return _result_cache
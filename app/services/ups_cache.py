# UPS Data Cache Module
import time
from typing import Dict, Any, Optional


class UPSCache:
    """Simple TTL-based cache for UPS data"""
    
    def __init__(self):
        self._cache: Dict[str, tuple[float, Dict[str, Any]]] = {}
    
    def get(self, key: str, ttl: float) -> Optional[Dict[str, Any]]:
        """Get cached data if not expired"""
        if key not in self._cache:
            return None
        
        timestamp, data = self._cache[key]
        if time.time() - timestamp > ttl:
            # Data expired, remove from cache
            del self._cache[key]
            return None
        
        return data
    
    def set(self, key: str, data: Dict[str, Any]) -> None:
        """Store data in cache with current timestamp"""
        self._cache[key] = (time.time(), data)
    
    def clear(self) -> None:
        """Clear all cached data"""
        self._cache.clear()
    
    def remove(self, key: str) -> None:
        """Remove specific key from cache"""
        self._cache.pop(key, None)
    
    def size(self) -> int:
        """Get current cache size"""
        return len(self._cache)


# Global cache instance
ups_cache = UPSCache()
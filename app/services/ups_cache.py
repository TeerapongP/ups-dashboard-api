import time
from typing import Dict, Any, Optional

class UPSCache:
    
    def __init__(self):
        self._cache: Dict[str, tuple[float, Dict[str, Any]]] = {}
    
    def get(self, key: str, ttl: float) -> Optional[Dict[str, Any]]:
        if key not in self._cache:
            return None
        
        timestamp, data = self._cache[key]
        if time.time() - timestamp > ttl:
            del self._cache[key]
            return None
        
        return data
    
    def set(self, key: str, data: Dict[str, Any]) -> None:
        self._cache[key] = (time.time(), data)
    
    def clear(self) -> None:
        self._cache.clear()
    
    def remove(self, key: str) -> None:
        self._cache.pop(key, None)
    
    def size(self) -> int:
        return len(self._cache)

ups_cache = UPSCache()
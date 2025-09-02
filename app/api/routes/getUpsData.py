# UPS Data Collection API Routes
from fastapi import FastAPI, HTTPException, Query
from typing import Dict, Any, List, Optional
from app.services.ups_service import ups_service

# Legacy compatibility functions (deprecated)
def get_ups_data(ip: str, config: Dict[str, Any], timeout: float = 1.2, retries: int = 0) -> Dict[str, Any]:
    """Legacy function for backward compatibility"""
    return ups_service._collect_ups_data(ip, config, timeout, retries)


def get_ups_data_cached(ip: str, cfg: Dict[str, Any], timeout: float, retries: int, ttl: float) -> Dict[str, Any]:
    """Legacy function for backward compatibility"""
    return ups_service.get_ups_data(ip, timeout, retries, True, ttl)

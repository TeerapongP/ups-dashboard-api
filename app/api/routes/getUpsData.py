# UPS Data Collection API Routes
from fastapi import FastAPI, HTTPException, Query
from typing import Dict, Any, List, Optional
from .ups_service import ups_service

app = FastAPI(title="UPS Monitor API", version="1.0.0")


@app.get("/ups/{ip}")
async def get_ups_by_ip(
    ip: str,
    timeout: Optional[float] = Query(None, description="SNMP timeout in seconds"),
    retries: Optional[int] = Query(None, description="SNMP retry count"),
    use_cache: bool = Query(True, description="Use cached data if available"),
    cache_ttl: Optional[float] = Query(None, description="Cache TTL in seconds")
) -> Dict[str, Any]:
    """Get UPS data for a specific IP address"""
    try:
        return ups_service.get_ups_data(
            ip=ip,
            timeout=timeout,
            retries=retries,
            use_cache=use_cache,
            cache_ttl=cache_ttl
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error collecting UPS data: {str(e)}")


@app.get("/ups")
async def get_all_ups(
    timeout: Optional[float] = Query(None, description="SNMP timeout in seconds"),
    retries: Optional[int] = Query(None, description="SNMP retry count"),
    use_cache: bool = Query(True, description="Use cached data if available"),
    cache_ttl: Optional[float] = Query(None, description="Cache TTL in seconds")
) -> List[Dict[str, Any]]:
    """Get data for all configured UPS devices"""
    try:
        return ups_service.get_all_ups_data(
            timeout=timeout,
            retries=retries,
            use_cache=use_cache,
            cache_ttl=cache_ttl
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error collecting UPS data: {str(e)}")


@app.get("/ups/devices")
async def get_device_list() -> List[Dict[str, str]]:
    """Get list of configured UPS devices"""
    return ups_service.get_device_list()


@app.post("/ups/cache/clear")
async def clear_cache() -> Dict[str, str]:
    """Clear all cached UPS data"""
    ups_service.clear_cache()
    return {"message": "Cache cleared successfully"}


@app.delete("/ups/{ip}/cache")
async def remove_from_cache(ip: str) -> Dict[str, str]:
    """Remove specific UPS from cache"""
    ups_service.remove_from_cache(ip)
    return {"message": f"UPS {ip} removed from cache"}


# Legacy compatibility functions (deprecated)
def get_ups_data(ip: str, config: Dict[str, Any], timeout: float = 1.2, retries: int = 0) -> Dict[str, Any]:
    """Legacy function for backward compatibility"""
    return ups_service._collect_ups_data(ip, config, timeout, retries)


def get_ups_data_cached(ip: str, cfg: Dict[str, Any], timeout: float, retries: int, ttl: float) -> Dict[str, Any]:
    """Legacy function for backward compatibility"""
    return ups_service.get_ups_data(ip, timeout, retries, True, ttl)

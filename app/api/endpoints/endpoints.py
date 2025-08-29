# app/api/endpoints/endpoints.py
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed as cf_as_completed  # ใช้ของ concurrent.futures
from app.api.routes.getUpsData import DEFAULT_TTL, UPS_OID_MAP, get_ups_data, get_ups_data_cached
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


@router.get("/ups/{ip}")
def read_one(ip: str,
             timeout: float = Query(1.2, ge=0.2, le=10.0),
             retries: int = Query(0, ge=0, le=5),
             ttl: float = Query(0.0, ge=0.0, le=60.0)):
    cfg = UPS_OID_MAP.get(ip)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"UPS {ip} not configured")
    if ttl > 0:
        return get_ups_data_cached(ip, cfg, timeout, retries, ttl)
    return get_ups_data(ip, cfg, timeout=timeout, retries=retries)

@router.get("/ups")
def read_all(timeout: float = Query(1.0, ge=0.2, le=10.0),
             retries: int = Query(0,   ge=0, le=5),
             workers: int = Query(12,  ge=1, le=64),
             ttl: float = Query(DEFAULT_TTL, ge=0.0, le=60.0)):
    items: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(get_ups_data_cached, ip, cfg, timeout, retries, ttl)
                for ip, cfg in UPS_OID_MAP.items()]
        for f in cf_as_completed(futs):  # ใช้ cf_as_completed แทน asyncio.as_completed
            items.append(f.result())
    return {"count": len(items), "items": items}

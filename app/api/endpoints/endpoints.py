# app/api/endpoints/endpoints.py
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed as cf_as_completed  
from app.services.ups_config import UPS_DEVICES, DEFAULT_CONFIG
from app.api.routes.getUpsData import get_ups_data, get_ups_data_cached
from app.services.ups_service import ups_service
from fastapi import APIRouter, HTTPException, Query
from concurrent.futures import as_completed
from db.database import SessionLocal
from app.services.ups_events import persist_status, log_events_for_snapshot   

router = APIRouter()


@router.get("/ups/{ip}")
def read_one(ip: str,
             timeout: float = Query(1.2, ge=0.2, le=10.0),
             retries: int = Query(0, ge=0, le=5),
             ttl: float = Query(0.0, ge=0.0, le=60.0)):
    cfg = UPS_DEVICES.get(ip)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"UPS {ip} not configured")
    if ttl > 0:
        return get_ups_data_cached(ip, cfg, timeout, retries, ttl)
    return get_ups_data(ip, cfg, timeout=timeout, retries=retries)

@router.get("/ups")
def read_all(
    timeout: float = Query(1.0, ge=0.2, le=10.0),
    retries: int = Query(0,   ge=0, le=5),
    workers: int = Query(12,  ge=1, le=64),
    ttl: float = Query(2.0,   ge=0.0, le=60.0),
    persist: bool = Query(True)
):
    items = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [
            ex.submit(
                ups_service.get_ups_data,
                ip=d["ip"],  
                timeout=timeout,
                retries=retries,
                use_cache=True,
                cache_ttl=ttl
            )
            for d in ups_service.get_device_list()
        ]
        for f in as_completed(futs):
            try:
                items.append(f.result())
            except Exception as e:
                items.append({"status": "Error", "error": str(e)})

    # persist ลง DB
    if persist:
        with SessionLocal() as db:
            for snap in items:
                try:
                    ups_id = snap.get("id")
                    if not ups_id:
                        continue
                    persist_status(db, ups_id, snap)
                    log_events_for_snapshot(db, snap)
                except Exception as e:
                    print(f"[persist/log] error for {snap.get('id')}: {e}")
                    db.rollback()  # Rollback this transaction and continue with next
                    continue
            try:
                db.commit()
            except Exception as e:
                print(f"[commit] error: {e}")
                db.rollback()

    return {"count": len(items), "items": items}


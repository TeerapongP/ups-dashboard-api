from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session
from concurrent.futures import ThreadPoolExecutor, as_completed

from db.database import SessionLocal
from app.services.ups_service import ups_service
from app.services.ups_events import (
    ups_event_service,
    _ensure_device,
    persist_status,
    log_events_for_snapshot,
)
from model.model import UPSDevice
from io import BytesIO
from fastapi.responses import StreamingResponse
from app.schemas.report import DailyReportPayload
from app.services.report_service import ReportService
from datetime import datetime

router = APIRouter()


# ---------- DB dependency ----------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------- Helpers ----------
def _resolve_ups_id_by_ip(db: Session, ip: str) -> Optional[str]:
    """หาค่า ups_id (string) จาก ip_address ในตาราง ups_devices"""
    dev = db.query(UPSDevice).filter(UPSDevice.ip_address == ip).first()
    return dev.id if dev else None


# ---------- GET: เครื่องเดียว ----------
@router.get("/ups/{ip}")
def read_one(
    ip: str,
    timeout: float = Query(1.2, ge=0.2, le=10.0),
    retries: int = Query(0, ge=0, le=5),
    ttl: float = Query(0.0, ge=0.0, le=60.0),
    persist: bool = Query(False),
    db: Session = Depends(get_db),
):
    """
    ดึงข้อมูล UPS เครื่องเดียวจาก SNMP (มี cache ตามที่ ups_service จัดการ)
    - persist=True จะเขียน snapshot + event ลงฐานข้อมูลให้ด้วย
    """
    # ใช้ repo ภายใน ups_service เช็ก config/การมีอยู่ของอุปกรณ์
    dev = ups_service.repo.get_device_by_ip(ip)
    if not dev:
        raise HTTPException(status_code=404, detail=f"No device found for ip={ip}")

    data = ups_service.get_ups_data(
        ip=ip,
        timeout=timeout,
        retries=retries,
        use_cache=True,
        cache_ttl=ttl if ttl > 0 else None,
    )

    if persist:
        try:
            ups_id = _ensure_device(db, data)
            persist_status(db, ups_id, data)
            log_events_for_snapshot(db, data)
            db.commit()
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Persist error: {e}")

    return data


# ---------- GET: ทั้งหมด ----------
@router.get("/ups-getall")
def read_all(
    timeout: float = Query(1.0, ge=0.2, le=10.0),
    retries: int = Query(0, ge=0, le=5),
    ttl: float = Query(2.0, ge=0.0, le=60.0),
    per_host_timeout: float | None = Query(None, ge=0.5, le=30.0, description="timeout ต่อเครื่อง (ถ้าไม่ระบุจะคำนวณอัตโนมัติ)"),
    persist: bool = Query(True),
    db: Session = Depends(get_db),
):
    """
    ดึงข้อมูลทุกเครื่องแบบขนานผ่าน ups_service.get_all_ups_data()
    - จะข้าม persist รายการที่ status='error'
    """
    # ดึงผลลัพธ์ทั้งหมดแบบขนาน (มีจัดเรียงตาม IP ให้แล้ว)
    items: List[Dict[str, Any]] = ups_service.get_all_ups_data(
        timeout=timeout,
        retries=retries,
        use_cache=True,
        cache_ttl=ttl if ttl > 0 else None,
        per_host_timeout=per_host_timeout,
    )

    if persist:
        for snap in items:
            # ข้ามถ้า error
            if str(snap.get("status", "")).lower() == "error":
                continue
            try:
                ups_id = _ensure_device(db, snap)
                persist_status(db, ups_id, snap)
                log_events_for_snapshot(db, snap)
            except Exception as e:
                print(f"[persist/log] error for {snap.get('id') or snap.get('ip')}: {e}")
                db.rollback()
                continue
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"[commit] error: {e}")

    return {"count": len(items), "items": items}

@router.get("/daily/{day}/json")
def daily_report_json(day: str, db: Session = Depends(get_db)):
    try:
        return ReportService.get_daily_report(db, day)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))




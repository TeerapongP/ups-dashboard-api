from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status, Query , Path
from sqlalchemy.orm import Session

from db.database import SessionLocal
from app.services.snmp_service import snmp_service
from app.schemas.snmp import (
    DeviceCreatePayload,
    DeviceCreateWithOIDsPayload,
    DeviceUpdatePayload,
)
from model.model import UPSDevice
from datetime import datetime
import ipaddress
from typing import Optional
from sqlalchemy.orm import Session, selectinload
from app.utils.errors import sanitize_db_error
import logging

router = APIRouter(prefix="/snmp", tags=["SNMP / OID"])

# ---------- DB dependency ----------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------- Create: device + OIDs (insert only) ----------
@router.post("/devices/with-oids", status_code=status.HTTP_201_CREATED)
def create_device_with_oids(payload: DeviceCreateWithOIDsPayload, db: Session = Depends(get_db)):
    try:
        result = snmp_service.create_device_with_oids(
            db,
            ip=str(payload.ip),
            brand=payload.brand,
            model=payload.model,
            location=payload.location,
            profile_name=payload.profile_name,
            data=payload.data,
        )
        db.commit()
        return result
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"สร้างอุปกรณ์/ใส่ OID ไม่สำเร็จ: {e}")

# ---------- Update: UPS ----------
@router.put("/devices/{ups_id}", status_code=status.HTTP_200_OK)
def update_device(
    ups_id: str = Path(..., min_length=1, pattern=r"^[A-Za-z0-9_]+$"),
    payload: DeviceUpdatePayload = ...,
    db: Session = Depends(get_db),
):
    try:
        result = snmp_service.update_device(
            db,
            ups_id=ups_id,
            brand=payload.brand,
            model=payload.model,
            location=payload.location,
            is_active=payload.is_active,
            data=payload.data,                 # <<<
            profile_name=payload.profile_name, # <<<
        )
        db.commit()
        return result
    except LookupError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"อัปเดตไม่สำเร็จ: {e}")
    
# ---------- Delete: UPS ----------
@router.delete("/devices/{ups_id}", status_code=status.HTTP_200_OK)
def delete_device(
    ups_id: str = Path(...),   # ไม่ใส่ ge
    db: Session = Depends(get_db),
):
    try:
        result = snmp_service.delete_device(db, ups_id=ups_id)
        db.commit()
        if result.get("deleted", 0) == 0:
            raise HTTPException(status_code=404, detail=f"ไม่พบ UPS id={ups_id}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"ลบไม่สำเร็จ: {e}")


# ---------- View: OIDs by IP (ใช้ในหน้าเดียว) ----------
@router.get("/devices/{ip}/config", status_code=status.HTTP_200_OK)
def get_device_config_for_ip(
    ip: str = Path(..., description="IPv4 เช่น 10.40.1.10"),
    base_profile: str = Query("STANDARD", description="โปรไฟล์ฐานที่จะ merge เช่น STANDARD"),
    override_profile: Optional[str] = Query(
        default=None,
        description="บังคับใช้โปรไฟล์นี้ถ้าเครื่องยังไม่ผูก (เช่น EPPC_935)"),
    db: Session = Depends(get_db),
):
    try:
        cfg = snmp_service.get_single_device_config(
            db, ip=ip, base_profile_name=base_profile, override_profile_name=override_profile
        )
        return {"ip": ip, **cfg}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        http_status, safe = sanitize_db_error(e)
        raise HTTPException(status_code=http_status, detail=safe)



# ---------- helpers ----------
def _ip_to_int(ip: str) -> int:
    try:
        return int(ipaddress.ip_address(ip))
    except Exception:
        return 0

def _pick_timestamp(obj) -> Optional[datetime]:
    """เลือก timestamp ตัวที่มีอยู่จริงจากหลายชื่อฟิลด์"""
    if obj is None:
        return None
    for field in (
        "collected_at", "observed_at", "measured_at",
        "created_at", "updated_at", "timestamp", "ts", "last_seen"
    ):
        v = getattr(obj, field, None)
        if isinstance(v, datetime):
            return v
    return None

def _first_attr(obj: Any, names: list[str]):
    """
    คืนค่าตัวแรกที่พบจาก attribute หรือจาก JSON field (data/snapshot)
    รองรับทั้ง snake_case และ camelCase
    """
    if obj is None:
        return None

    # 1) attributes บน ORM row
    for n in names:
        if hasattr(obj, n):
            v = getattr(obj, n)
            if v is not None:
                return v

    # 2) JSON fields บน row (เช่น .data / .snapshot)
    for j in ("data", "snapshot"):
        blob = getattr(obj, j, None)
        if isinstance(blob, dict):
            for n in names:
                # ตรงชื่อ
                if n in blob and blob[n] is not None:
                    return blob[n]
                # รองรับ path แบบ nested เช่น ("output","L1V")
                if isinstance(n, (tuple, list)) and blob:
                    cur = blob
                    ok = True
                    for k in n:
                        if isinstance(cur, dict) and k in cur:
                            cur = cur[k]
                        else:
                            ok = False
                            break
                    if ok and cur is not None:
                        return cur
    return None

def _latest_status_for_device(device):
    """
    รวมรายการสถานะจากหลาย relationship แล้วหยิบตัวที่เวลาล่าสุด
    คืนคู่ (latest_obj, latest_ts)
    """
    pools = []
    for rel in ("statuses", "status_events", "histories"):
        lst = getattr(device, rel, None)
        if lst:
            pools.extend(lst)

    if not pools:
        return None, None

    latest = max(pools, key=lambda s: _pick_timestamp(s) or datetime.min)
    return latest, _pick_timestamp(latest)

# ---------- endpoint ----------
@router.get("/devices", status_code=status.HTTP_200_OK)
def list_devices(db: Session = Depends(get_db)):
    rows = (
        db.query(UPSDevice)
        .options(
            selectinload(UPSDevice.statuses),
            selectinload(UPSDevice.status_events),
            selectinload(UPSDevice.histories),
        )
        .filter(UPSDevice.is_active == True)
        .all()
    )
    rows.sort(key=lambda r: _ip_to_int(getattr(r, "ip_address", "0.0.0.0")))

    devices = []
    for r in rows:
        latest, ts = _latest_status_for_device(r)

        state = _first_attr(latest, ["state", "status"]) or "Unknown"

        load_pct = _first_attr(latest, [
            "load_percent", "output_load_percent", "output_load_pct",
            "ups_load", "load", "load_pct",
            "loadPercent",  # camelCase (ถ้ามี)
        ])

        temperature = _first_attr(latest, [
            "temperature", "temperature_c", "temp_c", "ups_temperature",
            "temperatureC",  # camelCase จาก /ups-getall
        ])

        # ---------- Fallback คำนวณ loadPercent ----------
        if load_pct is None:
            # VA ก่อน
            output_va = _first_attr(latest, ["output_va", "load_va", "apparent_power_va", "loadVA"])
            rated_va  = _first_attr(r, ["rating_va", "rated_va", "power_va", "capacity_va",
                                        "ratingVA", "ratedVA", "capacityVA"])
            # ถ้ามี W
            output_w  = _first_attr(latest, ["loadW", "output_w", "active_power_w"])
            rated_w   = _first_attr(r, ["ratingW", "ratedW", "power_w", "capacity_w"])

            try:
                if output_va is not None and rated_va:
                    load_pct = round((float(output_va) / float(rated_va)) * 100, 1)
                elif output_w is not None and rated_w:
                    load_pct = round((float(output_w) / float(rated_w)) * 100, 1)
                else:
                    # ลองคำนวณ VA จาก V*A (เฟสเดียว) จาก snapshot JSON: output.{L1V,L1A}
                    v = _first_attr(latest, [("output","L1V")])
                    a = _first_attr(latest, [("output","L1A")])
                    if v is not None and a is not None and rated_va:
                        est_va = float(v) * float(a)
                        load_pct = round((est_va / float(rated_va)) * 100, 1)
            except Exception:
                pass

        last_seen = getattr(r, "last_seen", None) or ts

        devices.append({
            "ups_id": r.id,
            "ip": r.ip_address,
            "brand": r.brand,
            "model": r.model,
            "location": r.location,
            "status": state,
            "temperature": temperature,
            "last_seen": last_seen,
        })

    return devices

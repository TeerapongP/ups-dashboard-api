from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy.orm import Session

from db.database import SessionLocal
from app.services.snmp_service import snmp_service
from app.schemas.snmp import (
    DeviceCreatePayload,
    DeviceCreateWithOIDsPayload,
    DeviceUpdatePayload,
)
from model.model import UPSDevice

router = APIRouter(prefix="/snmp", tags=["SNMP / OID"])

# ---------- DB dependency ----------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------- Create: device (insert only) ----------
@router.post("/devices", status_code=status.HTTP_201_CREATED)
def create_device(payload: DeviceCreatePayload, db: Session = Depends(get_db)):
    try:
        result = snmp_service.create_device(
            db,
            ip=str(payload.ip),
            brand=payload.brand,
            model=payload.model,
            location=payload.location,
            profile_name=payload.profile_name,
        )
        db.commit()
        return result
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"สร้างอุปกรณ์ไม่สำเร็จ: {e}")

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
    ups_id: int = Path(..., ge=1),
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
    ups_id: int = Path(..., ge=1),
    delete_profile: bool = Query(True, description="ลบโปรไฟล์ CUSTOM_* ที่ไม่ถูกใช้งานด้วยหรือไม่"),
    db: Session = Depends(get_db),
):
    try:
        result = snmp_service.delete_device(db, ups_id=ups_id, delete_profile=delete_profile)
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
@router.get("/devices/by-ip/{ip}/oids", status_code=status.HTTP_200_OK)
def get_oids_for_device_by_ip(ip: str, db: Session = Depends(get_db)):
    try:
        return snmp_service.get_oids_for_device_by_ip(db, ip)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))

# (optional) รายการอุปกรณ์สั้น ๆ สำหรับ dropdown
@router.get("/devices", status_code=status.HTTP_200_OK)
def list_devices(db: Session = Depends(get_db)):
    rows = (
        db.query(UPSDevice)
        .filter(UPSDevice.is_active == True)
        .order_by(UPSDevice.id.desc())
        .all()
    )
    return [
        {
            "ups_id": r.id,
            "ip": r.ip_address,
            "brand": r.brand,
            "model": r.model,
            "location": r.location,
        }
        for r in rows
    ]

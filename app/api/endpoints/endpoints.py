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
from app.services.ups_report_service import ups_report_service
from io import BytesIO
from fastapi.responses import StreamingResponse

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
    workers: int = Query(12, ge=1, le=64),
    ttl: float = Query(2.0, ge=0.0, le=60.0),
    persist: bool = Query(True),
    db: Session = Depends(get_db),
):
    """
    ดึงข้อมูลทุกเครื่องแบบขนาน (ThreadPool) และเลือก persist ลงฐานข้อมูลได้
    """
    items: List[Dict[str, Any]] = []

    # เตรียมรายการ IP จากฐานข้อมูลผ่าน ups_service
    dev_list = ups_service.get_device_list()
    if not dev_list:
        return {"count": 0, "items": []}

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [
            ex.submit(
                ups_service.get_ups_data,
                ip=d["ip"],
                timeout=timeout,
                retries=retries,
                use_cache=True,
                cache_ttl=ttl if ttl > 0 else None,
            )
            for d in dev_list
        ]

        for f in as_completed(futs):
            try:
                items.append(f.result())
            except Exception as e:
                items.append({"status": "Error", "error": str(e)})

    if persist:
        for snap in items:
            try:
                ups_id = _ensure_device(db, snap)
                persist_status(db, ups_id, snap)
                log_events_for_snapshot(db, snap)
            except Exception as e:
                # เก็บ error ต่อเครื่อง แต่ไม่ให้ทั้ง batch ล้ม
                print(f"[persist/log] error for {snap.get('id') or snap.get('ip')}: {e}")
                db.rollback()
                continue
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"[commit] error: {e}")

    return {"count": len(items), "items": items}


# ---------- GET: รายงานรายวัน (powerfail/offline เป็นนาที) ----------
@router.get("/report/daily/{date}")
def daily_report(
    date: str,
    use_status_event_powerfail: bool = Query(
        False,
        description="true = อ่าน powerfail จาก ups_status_event (ต้องรองรับ enum 'powerfail'); false = อ่านจาก ups_events.event_type='powerfail'",
    ),
    include_details: bool = Query(
        False,
        description="true = แนบช่วงเหตุการณ์รายเครื่อง (start/end/duration)"
    ),
    db: Session = Depends(get_db),
):
    """
    สรุปนาทีรวมต่อวัน (รวมทุก UPS) ของ offline และ powerfail
    """
    try:
        day = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="รูปแบบวันที่ไม่ถูกต้อง (ต้องเป็น YYYY-MM-DD)")

    devices = db.query(UPSDevice).filter(UPSDevice.is_active == True).all()
    if not devices:
        return []

    total_offline = 0
    total_powerfail = 0
    device_reports = []

    for dev in devices:
        counters = ups_event_service.get_daily_counters(
            db,
            day,
            dev.id,
            use_status_event_powerfail=use_status_event_powerfail,
        )

        # ✅ กรอง: ถ้าไม่มี offline/powerfail เลย ข้าม
        if counters["offline_minutes"] == 0 and counters["powerfail_minutes"] == 0:
            continue

        total_offline += counters["offline_minutes"]
        total_powerfail += counters["powerfail_minutes"]

        row = {
            "ups_id": dev.id,
            "ip": dev.ip_address,
            "offline_minutes": counters["offline_minutes"],
            "powerfail_minutes": counters["powerfail_minutes"],
        }

        if include_details:
            row["details"] = ups_event_service.get_daily_details(
                db, day, dev.id, use_status_event_powerfail=use_status_event_powerfail
            )

        device_reports.append(row)

    # ✅ ถ้า device_reports ว่าง ให้ return [] เลย
    if not device_reports:
        return []

    return {
        "date": date,
        "offline_minutes": total_offline,
        "powerfail_minutes": total_powerfail,
        "devices": device_reports,
    }


@router.get(
    "/report/daily/{date}/blob",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {
                "application/pdf": {"schema": {"type": "string", "format": "binary"}},
                "text/html": {"schema": {"type": "string", "format": "binary"}},
            },
            "description": "Daily report as binary (PDF if available, otherwise HTML).",
        },
        400: {"description": "Bad date format"},
    },
)
def daily_report_blob(
    date: str,
    use_status_event_powerfail: bool = Query(False),
    include_details: bool = Query(False),
    force_html: bool = Query(False, description="บังคับส่ง HTML แทน PDF"),
    db: Session = Depends(get_db),
):
    # 1) parse date
    try:
        day = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="รูปแบบวันที่ไม่ถูกต้อง (YYYY-MM-DD)")

    filename_base = f"ups-downtime-{date}"

    # 2) ถ้าบังคับ HTML ก็ส่ง HTML เลย
    if force_html:
        html_str = ups_report_service.generate_daily_html(
            db, day, use_status_event_powerfail=use_status_event_powerfail, include_details=include_details
        )
        data = html_str.encode("utf-8")
        return StreamingResponse(
            BytesIO(data),
            media_type="text/html",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.html"'},
        )

    # 3) พยายามสร้าง PDF (ถ้า WeasyPrint ไม่พร้อมให้ fallback เป็น HTML)
    try:
        pdf_io = ups_report_service.generate_daily_pdf(
            db, day, use_status_event_powerfail=use_status_event_powerfail, include_details=include_details
        )
    except RuntimeError:
        # Fallback → HTML
        html_str = ups_report_service.generate_daily_html(
            db, day, use_status_event_powerfail=use_status_event_powerfail, include_details=include_details
        )
        data = html_str.encode("utf-8")
        return StreamingResponse(
            BytesIO(data),
            media_type="text/html",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.html"'},
        )

    # ถ้าไม่มีข้อมูลให้ไฟล์ว่าง ๆ (หรือจะ 204 ก็ได้)
    if pdf_io is None:
        return StreamingResponse(
            BytesIO(b""),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.pdf"'},
        )

    # OK → PDF
    return StreamingResponse(
        pdf_io,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename_base}.pdf"'},
    )
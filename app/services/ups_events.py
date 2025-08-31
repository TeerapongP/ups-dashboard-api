# services/ups_events.py
from __future__ import annotations
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import select, func, and_, text
from sqlalchemy.orm import Session
from model.model import UPSStatus, UPSDevice 

TEMP_WARN = 50
TEMP_CRIT = 60
TEMP_CLEAR = 45      # hysteresis ปิดเมื่อ < 45°C

BATT_WARN = 20      # %
BATT_CRIT = 10
BATT_CLEAR = 25     # hysteresis ปิดเมื่อ > 25%

def _ensure_device(session: Session, snap: Dict[str, Any]) -> int:
    """Ensure UPS device exists and return its integer ID"""
    ip_address = snap.get("ip", "0.0.0.0")
    
    # First try to find existing device by IP
    dev = session.execute(
        select(UPSDevice).where(UPSDevice.ip_address == ip_address)
    ).scalars().first()
    
    if not dev:
        # Create new device
        dev = UPSDevice(
            ip_address=ip_address,
            brand=(snap.get("brand") or "Unknown"),
            model=(snap.get("model") or "Unknown"),
            location=(snap.get("location") or "-"),
            capacity_va= snap.get("capacityVA", 0) or 0,
            capacity_w=  snap.get("capacityW", 0) or 0,
            is_active=True,
        )
        session.add(dev)
        session.flush()
    
    return dev.id

def persist_status(session: Session, ups_id: int, snap: dict) -> UPSStatus:
    def safe(v): 
        return None if v is None else v

    st = (snap.get("status") or "").lower()
    status = "online" if st == "online" else ("offline" if st == "offline" else "warning")

    input_ = snap.get("input") or {}
    output = snap.get("output") or {}

    # เก็บ UPSStatus (สถานะล่าสุด)
    row = session.execute(
        select(UPSStatus).where(UPSStatus.ups_id == ups_id).order_by(UPSStatus.timestamp.desc())
    ).scalars().first()

    if row:
        row.timestamp = datetime.utcnow()
        row.status = status
        row.battery_percentage = safe(snap.get("batteryPercent"))
        row.battery_voltage    = safe(snap.get("batteryVDC"))
        row.backup_time_minutes= safe(snap.get("backupTimeMin"))
        row.temperature        = safe(snap.get("temperatureC"))
        row.input_voltage_l1   = safe(input_.get("L1V"))
        row.input_voltage_l2   = safe(input_.get("L2V"))
        row.input_voltage_l3   = safe(input_.get("L3V"))
        row.input_current_l1   = safe(input_.get("L1A"))
        row.input_current_l2   = safe(input_.get("L2A"))
        row.input_current_l3   = safe(input_.get("L3A"))
        row.input_frequency    = safe(input_.get("freqHz"))
        row.output_voltage_l1  = safe(output.get("L1V"))
        row.output_voltage_l2  = safe(output.get("L2V"))
        row.output_voltage_l3  = safe(output.get("L3V"))
        row.output_current_l1  = safe(output.get("L1A"))
        row.output_current_l2  = safe(output.get("L2A"))
        row.output_current_l3  = safe(output.get("L3A"))
        row.output_frequency   = safe(output.get("freqHz"))
        row.output_load_va     = safe(snap.get("loadVA"))
        row.output_load_w      = safe(snap.get("loadW"))
        row.load_percentage    = safe(snap.get("loadPct"))
    else:
        row = UPSStatus(
            ups_id=ups_id,
            timestamp=datetime.utcnow(),
            status=status,
            battery_percentage = safe(snap.get("batteryPercent")),
            battery_voltage    = safe(snap.get("batteryVDC")),
            backup_time_minutes= safe(snap.get("backupTimeMin")),
            temperature        = safe(snap.get("temperatureC")),
            input_voltage_l1   = safe(input_.get("L1V")),
            input_voltage_l2   = safe(input_.get("L2V")),
            input_voltage_l3   = safe(input_.get("L3V")),
            input_current_l1   = safe(input_.get("L1A")),
            input_current_l2   = safe(input_.get("L2A")),
            input_current_l3   = safe(input_.get("L3A")),
            input_frequency    = safe(input_.get("freqHz")),
            output_voltage_l1  = safe(output.get("L1V")),
            output_voltage_l2  = safe(output.get("L2V")),
            output_voltage_l3  = safe(output.get("L3V")),
            output_current_l1  = safe(output.get("L1A")),
            output_current_l2  = safe(output.get("L2A")),
            output_current_l3  = safe(output.get("L3A")),
            output_frequency   = safe(output.get("freqHz")),
            output_load_va     = safe(snap.get("loadVA")),
            output_load_w      = safe(snap.get("loadW")),
            load_percentage    = safe(snap.get("loadPct")),
        )
        session.add(row)

    session.flush()
    return row

def aggregate_to_history(session: Session, ups_id: int):
    now = datetime.utcnow()
    start = now - timedelta(hours=1)

    q = (
        session.query(
            func.avg(UPSStatus.battery_percentage).label("avg_batt"),
            func.min(UPSStatus.battery_percentage).label("min_batt"),
            func.max(UPSStatus.battery_percentage).label("max_batt"),
            func.avg(UPSStatus.temperature).label("avg_temp"),
            func.min(UPSStatus.temperature).label("min_temp"),
            func.max(UPSStatus.temperature).label("max_temp"),
            func.avg(UPSStatus.load_percentage).label("avg_load"),
            func.avg(UPSStatus.input_voltage_l1).label("avg_input"),
            func.avg(UPSStatus.output_voltage_l1).label("avg_output"),
            func.count().label("total_samples")
        )
        .filter(and_(UPSStatus.ups_id == ups_id,
                     UPSStatus.timestamp >= start,
                     UPSStatus.timestamp < now))
    )

    data = q.one()
    if data.total_samples > 0:
        hist = UPSHistory(
            ups_id=ups_id,
            date_hour=start.replace(minute=0, second=0, microsecond=0),
            avg_battery_percentage=data.avg_batt,
            avg_temperature=data.avg_temp,
            avg_load_percentage=data.avg_load,
            avg_input_voltage=data.avg_input,
            avg_output_voltage=data.avg_output,
            min_battery_percentage=data.min_batt,
            max_battery_percentage=data.max_batt,
            min_temperature=data.min_temp,
            max_temperature=data.max_temp,
            total_samples=data.total_samples,
        )
        session.add(hist)
        session.commit()

def _get_open_event(session: Session, ups_id: str, event_type: str) -> Optional[UPSEvent]:
    stmt = (
        select(UPSEvent)
        .where(and_(UPSEvent.ups_id == ups_id,
                    UPSEvent.event_type == event_type,
                    UPSEvent.is_resolved == False))
        .order_by(UPSEvent.start_time.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()

def _open_event(session: Session, ups_id: str, event_type: str, severity: str,
                message: str, event_code: Optional[str], data: Dict[str, Any]) -> UPSEvent:
    ev = UPSEvent(
        ups_id=ups_id,
        event_type=event_type,
        severity=severity,
        event_code=event_code,
        message=message,
        event_data=data or {},
        start_time=datetime.utcnow(),
        is_resolved=False,
    )
    session.add(ev)
    session.flush()
    return ev

def _resolve_event(session: Session, ev: UPSEvent, resolved_by: Optional[str] = None, extra_msg: Optional[str] = None):
    now = datetime.utcnow()
    ev.end_time = now
    ev.is_resolved = True
    ev.duration_seconds = int((now - ev.start_time).total_seconds())
    if extra_msg:
        ev.message = (ev.message or "") + f" | resolved: {extra_msg}"
    if resolved_by:
        ev.resolved_by = resolved_by
    session.add(ev)
    session.flush()

def log_events_for_snapshot(session: Session, snap: Dict[str, Any]):
    
    ups_id = _ensure_device(session, snap)

    # --- power_offline ---
    status = (snap.get("status") or "").lower()
    open_power = _get_open_event(session, ups_id, "power_offline")
    if status == "offline":
        if not open_power:
            _open_event(
                session, ups_id,
                event_type="power_offline",
                severity="critical",
                message="UPS appears OFFLINE",
                event_code="PWR_OFF",
                data={"ip": snap.get("ip"), "location": snap.get("location")}
            )
    else:
        if open_power:
            _resolve_event(session, open_power, extra_msg="UPS back ONLINE")
            # (ทางเลือก) บันทึก event ฟื้นตัว
            _open_event(
                session, ups_id,
                event_type="power_recovered",
                severity="info",
                message="UPS back ONLINE",
                event_code="PWR_ON",
                data={"at": datetime.utcnow().isoformat()}
            )
            # ปิด recovered ทันทีให้เป็น one-shot
            rec = _get_open_event(session, ups_id, "power_recovered")
            if rec:
                _resolve_event(session, rec)

    # --- temp_high ---
    t = snap.get("temperatureC")
    open_temp = _get_open_event(session, ups_id, "temp_high")
    if isinstance(t, (int, float)):
        if t >= TEMP_WARN:
            sev = "critical" if t >= TEMP_CRIT else "warning"
            if not open_temp:
                _open_event(
                    session, ups_id,
                    event_type="temp_high",
                    severity=sev,
                    message=f"High temperature: {t}°C",
                    event_code="TEMP_HIGH",
                    data={"temperatureC": t, "threshold_warn": TEMP_WARN, "threshold_crit": TEMP_CRIT}
                )
            else:
                # อัปเดต severity ถ้าเลื่อนขั้น
                if open_temp.severity == "warning" and sev == "critical":
                    open_temp.severity = "critical"
                    open_temp.message = f"High temperature escalated: {t}°C"
                    session.add(open_temp)
        else:
            # ต่ำกว่า hysteresis -> ปิด
            if open_temp and t < TEMP_CLEAR:
                _resolve_event(session, open_temp, extra_msg=f"temperature back to {t}°C")

    # --- battery_low ---
    b = snap.get("batteryPercent")
    open_batt = _get_open_event(session, ups_id, "battery_low")
    if isinstance(b, (int, float)):
        if b < BATT_WARN:
            sev = "critical" if b < BATT_CRIT else "warning"
            if not open_batt:
                _open_event(
                    session, ups_id,
                    event_type="battery_low",
                    severity=sev,
                    message=f"Low battery: {b}%",
                    event_code="BATT_LOW",
                    data={"batteryPercent": b, "warn": BATT_WARN, "crit": BATT_CRIT}
                )
            else:
                if open_batt.severity == "warning" and sev == "critical":
                    open_batt.severity = "critical"
                    open_batt.message = f"Low battery escalated: {b}%"
                    session.add(open_batt)
        else:
            if open_batt and b > BATT_CLEAR:
                _resolve_event(session, open_batt, extra_msg=f"battery back to {b}%")

def ensure_device_exists(db: Session, ups_id: str, snap: Dict[str, Any]) -> None:
    """Ensure device exists in ups_devices before inserting status/events"""
    row = db.execute(
        text("SELECT id FROM ups_devices WHERE id = :id"),
        {"id": ups_id}
    ).first()

    if not row:
        db.execute(text("""
            INSERT INTO ups_devices 
            (id, ip_address, brand, model, location, capacity_va, capacity_w)
            VALUES (:id, :ip, :brand, :model, :location, :capacity_va, :capacity_w)
        """), {
            "id": ups_id,
            "ip": snap.get("ip", "0.0.0.0"),
            "brand": snap.get("brand", "Unknown"),
            "model": snap.get("model", "Unknown"),
            "location": snap.get("location", "Unknown"),
            "capacity_va": snap.get("capacityVA", 0),
            "capacity_w": snap.get("capacityW", 0),
        })
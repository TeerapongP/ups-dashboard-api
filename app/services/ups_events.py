from __future__ import annotations
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import select, func, and_, text
from sqlalchemy.orm import Session
from model.model import UPSStatus, UPSDevice

TEMP_WARN = 50
TEMP_CRIT = 60
TEMP_CLEAR = 45

BATT_WARN = 20
BATT_CRIT = 10
BATT_CLEAR = 25

def _ensure_device(session: Session, snap: Dict[str, Any]) -> int:
    ip_address = snap.get("ip", "0.0.0.0")
    
    dev = session.execute(
        select(UPSDevice).where(UPSDevice.ip_address == ip_address)
    ).scalars().first()
    
    if not dev:
        try:
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
        except Exception as e:
            device_id = f"UPS_{ip_address.replace('.', '_')}"
            dev = UPSDevice(
                id=device_id,
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

def log_events_for_snapshot(session: Session, snap: Dict[str, Any]):
    device_ip = snap.get("ip", "unknown")
    print(f"Events logging for device {device_ip} - functionality disabled")
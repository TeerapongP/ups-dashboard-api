# app/services/ups_events.py
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import re

from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from datetime import date as _date, datetime as _dt

from model.model import (
    UPSEvent,
    UPSStatusEvent,
    UPSHistory,
    UPSDevice,
    UPSStatus,
)

# สำหรับ _eval_number_string
_ARITH_SAFE = re.compile(r"^[\d\.\s\+\-\*\/\(\)]+$")

# -------------------------
# Utilities
# -------------------------
def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def _parse_collected_at(snap: Dict[str, Any]) -> datetime:
    """
    คืนเป็น naive UTC datetime
    รับได้ทั้ง epoch (int/float) หรือ ISO string
    """
    v = snap.get("collected_at")
    if v is None:
        return datetime.utcnow()
    if isinstance(v, (int, float)):
        try:
            # ใช้ utcfromtimestamp แทน fromtimestamp
            return datetime.utcfromtimestamp(float(v))
        except Exception:
            return datetime.utcnow()
    if isinstance(v, str):
        s = v.strip()
        if s.endswith("Z"):
            s = s[:-1]
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
        ):
            try:
                return datetime.strptime(s, fmt)
            except Exception:
                continue
    return datetime.utcnow()

def _derive_device_id(ip: str) -> str:
    return f"UPS_{ip.replace('.', '_')}"


# -------------------------
# Event Service
# -------------------------
class UPSEventService:
    """
    - log_event(): เพิ่มแถวใน ups_events
    - log_status_change(): ปิด event เก่า + เปิด event สถานะใหม่ใน ups_status_event (append-only)
    - get_daily_counters(): รวม powerfail/offline เป็นนาที (รายวัน)
    - persist_daily_to_history(): บันทึกผลรวมรายวันลง ups_history
    """

    # -------- UPS Events (ทั่วไป) --------
    def log_event(
        self,
        session: Session,
        ups_id: str,
        event_type: str,
        severity: str = "info",
        message: Optional[str] = None,
        event_code: Optional[str] = None,
        event_data: Optional[dict] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> UPSEvent:
        ev = UPSEvent(
            ups_id=ups_id,
            event_type=event_type,
            severity=severity,
            message=message,
            event_code=event_code,
            event_data=event_data,
            start_time=start_time or datetime.utcnow(),
            end_time=end_time,
        )
        session.add(ev)
        session.flush()
        return ev

    # -------- UPS Status Event (state timeline) --------
    def log_status_change(
        self,
        session: Session,
        ups_id: str,
        new_status: str,
        ts: Optional[datetime] = None,
    ) -> UPSStatusEvent:
        """
        ปิด event ล่าสุด (ถ้ามีและยังไม่ปิด) + เปิด event ใหม่ (append-only)
        หมายเหตุ: ตามโมเดลปัจจุบัน enum อนุญาตเฉพาะ online|warning|critical|offline
        """
        ts = ts or datetime.utcnow()

        last = (
            session.execute(
                select(UPSStatusEvent)
                .where(UPSStatusEvent.ups_id == ups_id)
                .order_by(UPSStatusEvent.changed_at.desc())
            )
            .scalars()
            .first()
        )

        # สถานะเหมือนเดิม → ไม่ต้องสร้าง event ใหม่
        if last and last.new_status == new_status:
            return last

        # ปิด event เก่า (ถ้ามีและยังไม่ปิด)
        if last and last.next_changed_at is None:
            last.next_changed_at = ts
            last.duration_sec = int((ts - last.changed_at).total_seconds())
            session.flush()

        # เปิด event ใหม่
        row = UPSStatusEvent(
            ups_id=ups_id,
            old_status=last.new_status if last else None,
            new_status=new_status,
            changed_at=ts,
        )
        session.add(row)
        session.flush()
        return row

    # -------- Reports: daily counters --------
    @staticmethod
    def _overlap_minutes(
        start: datetime,
        end: Optional[datetime],
        day_start: datetime,
        day_end: datetime,
        now: Optional[datetime] = None,
    ) -> int:
        if end is None:
            end = min(now or datetime.utcnow(), day_end)
        if end <= start:
            return 0
        a = max(start, day_start)
        b = min(end, day_end)
        if b <= a:
            return 0
        return int((b - a).total_seconds() // 60)

    def get_daily_counters(
        self,
        session: Session,
        day: datetime,
        ups_id: str,
        *,
        use_status_event_powerfail: bool = False,
        now: Optional[datetime] = None,
    ) -> Dict[str, int]:
        """
        รวมรายวัน (นาที):
          - offline_minutes: จาก ups_status_event.new_status = 'offline'
          - powerfail_minutes:
              - ถ้า use_status_event_powerfail=True และ schema รองรับ 'powerfail' ใน UPSStatusEvent → อ่านจาก ups_status_event
              - ถ้า False (ดีฟอลต์) → อ่านจาก ups_events.event_type='powerfail'
        """
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        now = now or datetime.utcnow()

        offline_minutes = 0
        powerfail_minutes = 0

        # OFFLINE จาก ups_status_event
        rows_off = (
            session.execute(
                select(UPSStatusEvent.changed_at, UPSStatusEvent.next_changed_at)
                .where(
                    and_(
                        UPSStatusEvent.ups_id == ups_id,
                        UPSStatusEvent.new_status == "offline",
                        UPSStatusEvent.changed_at < day_end,
                    )
                )
                .order_by(UPSStatusEvent.changed_at.asc())
            ).all()
        )
        for (start_ts, end_ts) in rows_off:
            offline_minutes += self._overlap_minutes(start_ts, end_ts, day_start, day_end, now=now)

        # POWERFAIL
        if use_status_event_powerfail:
            rows_pf = (
                session.execute(
                    select(UPSStatusEvent.changed_at, UPSStatusEvent.next_changed_at)
                    .where(
                        and_(
                            UPSStatusEvent.ups_id == ups_id,
                            UPSStatusEvent.new_status == "powerfail",
                            UPSStatusEvent.changed_at < day_end,
                        )
                    )
                    .order_by(UPSStatusEvent.changed_at.asc())
                ).all()
            )
            for (s, e) in rows_pf:
                powerfail_minutes += self._overlap_minutes(s, e, day_start, day_end, now=now)
        else:
            # อ่านจาก ups_events(event_type='powerfail')
            rows_ev = (
                session.execute(
                    select(UPSEvent.start_time, UPSEvent.end_time)
                    .where(
                        and_(
                            UPSEvent.ups_id == ups_id,
                            UPSEvent.event_type == "powerfail",
                            UPSEvent.start_time < day_end,
                        )
                    )
                    .order_by(UPSEvent.start_time.asc())
                ).all()
            )
            for (s, e) in rows_ev:
                powerfail_minutes += self._overlap_minutes(s, e, day_start, day_end, now=now)

        return {
            "offline_minutes": int(offline_minutes),
            "powerfail_minutes": int(powerfail_minutes),
        }

    def persist_daily_to_history(
        self,
        session: Session,
        day: datetime,
        ups_id: str,
        *,
        use_status_event_powerfail: bool = False,
        commit: bool = True,
    ) -> UPSHistory:
        """
        เขียนผลรวมรายวันลง ups_history ณ date_hour = 00:00 ของวันนั้น
        - offline_minutes -> offline_minutes
        - powerfail_minutes -> warning_minutes (ถ้าต้องการคอลัมน์แยก บอกเพื่อเพิ่ม schema)
        """
        counters = self.get_daily_counters(
            session, day, ups_id, use_status_event_powerfail=use_status_event_powerfail
        )
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)

        hist = (
            session.execute(
                select(UPSHistory).where(
                    and_(UPSHistory.ups_id == ups_id, UPSHistory.date_hour == day_start)
                )
            )
            .scalars()
            .first()
        )

        if hist:
            hist.offline_minutes = counters["offline_minutes"]
            hist.warning_minutes = counters["powerfail_minutes"]
        else:
            hist = UPSHistory(
                ups_id=ups_id,
                date_hour=day_start,
                offline_minutes=counters["offline_minutes"],
                warning_minutes=counters["powerfail_minutes"],
            )
            session.add(hist)

        if commit:
            session.commit()
        else:
            session.flush()
        return hist


# singleton
ups_event_service = UPSEventService()


# -------------------------
# Persist Snapshot Helpers
# -------------------------
def _ensure_device(session: Session, snap: Dict[str, Any]) -> str:
    """
    ให้แน่ใจว่าเครื่องอยู่ใน ups_devices แล้ว
    - id ใช้สตริง เช่น UPS_10_50_11_11 (ตรงกับ schema ที่ใช้ VARCHAR(50))
    """
    ip_address = snap.get("ip", "0.0.0.0")

    dev = (
        session.execute(select(UPSDevice).where(UPSDevice.ip_address == ip_address))
        .scalars()
        .first()
    )

    if not dev:
        device_id = _derive_device_id(ip_address)
        dev = UPSDevice(
            id=device_id,
            ip_address=ip_address,
            brand=(snap.get("brand") or "Unknown"),
            model=(snap.get("model") or "Unknown"),
            location=(snap.get("location") or "-"),
            capacity_va=int(_to_float(snap.get("capacityVA")) or 0),
            capacity_w=int(_to_float(snap.get("capacityW")) or 0),
            is_active=True,
        )
        session.add(dev)
        session.flush()

    return dev.id


def persist_status(session: Session, ups_id: str, snap: Dict[str, Any]) -> UPSStatus:
    """
    บันทึก UPSStatus 1 แถว (snapshot)
    - ใช้ collected_at เป็น timestamp (fallback = utcnow)
    - map 'powerfail' -> 'warning' สำหรับ UPSStatus.status (เพราะ enum ไม่มี powerfail)
    - log status change ใน ups_status_event (ใช้สถานะที่ map แล้ว)
    - จัดการช่วง UPSEvent สำหรับ powerfail/offline: เปิดเมื่อเข้า/ปิดเมื่อออก
    """
    ts = _parse_collected_at(snap)

    # ตรวจสอบสถานะไฟดับ (L1V = 0 แต่ค่าอื่นยังมี)
    input_ = snap.get("input") or {}
    l1v = _to_float(input_.get("L1V"))
    l2v = _to_float(input_.get("L2V"))
    l3v = _to_float(input_.get("L3V"))
    
    # ตรวจสอบไฟดับ: L1V = 0 แต่มีค่าอื่นๆ ยังมาให้
    is_power_outage = (
        l1v == 0 and 
        (l2v is not None or l3v is not None or 
         snap.get("batteryPercent") is not None or 
         snap.get("loadPct") is not None)
    )
    
    # ตรวจสอบไฟตก: L1V อยู่ในช่วง 1-179V
    is_power_drop = l1v is not None and 1 <= l1v <= 179
    
    st_raw = (snap.get("status") or "").strip().lower()
    
    if is_power_outage:
        status_for_snapshot = "warning"
        st_raw = "power_outage"  # สถานะใหม่สำหรับไฟดับ
    elif is_power_drop:
        status_for_snapshot = "warning" 
        st_raw = "powerfail"  # ไฟตกยังใช้ powerfail เดิม
    elif st_raw in ("online", "offline", "warning", "critical"):
        status_for_snapshot = st_raw
    elif st_raw == "powerfail":
        status_for_snapshot = "warning"
    else:
        status_for_snapshot = "online"

    output = snap.get("output") or {}

    # --- แปลงความถี่จากเดซิ-เฮิร์ตซ์เป็นเฮิร์ตซ์ (หาร 10) ---
    in_freq_raw = _to_float(input_.get("freqHz"))
    out_freq_raw = _to_float(output.get("freqHz"))
    in_freq_hz  = _norm_freq_hz(input_.get("freqHz"))
    out_freq_hz = _norm_freq_hz(output.get("freqHz"))

    row = UPSStatus(
        ups_id=ups_id,
        timestamp=ts,
        status=status_for_snapshot,
        battery_percentage=_to_float(snap.get("batteryPercent")),
        battery_voltage=_to_float(snap.get("batteryVDC")),
        backup_time_minutes=int(_to_float(snap.get("backupTimeMin")) or 0)
        if snap.get("backupTimeMin") is not None
        else None,
        temperature=_to_float(snap.get("temperatureC")),
        input_voltage_l1=_to_float(input_.get("L1V")),
        input_voltage_l2=_to_float(input_.get("L2V")),
        input_voltage_l3=_to_float(input_.get("L3V")),
        input_current_l1=_to_float(input_.get("L1A")),
        input_current_l2=_to_float(input_.get("L2A")),
        input_current_l3=_to_float(input_.get("L3A")),
        input_frequency=in_freq_hz,      # << เปลี่ยนมาใช้ค่าแปลงแล้ว
        input_max_voltage=_to_float(input_.get("maxV")),
        input_min_voltage=_to_float(input_.get("minV")),
        output_voltage_l1=_to_float(output.get("L1V")),
        output_voltage_l2=_to_float(output.get("L2V")),
        output_voltage_l3=_to_float(output.get("L3V")),
        output_current_l1=_to_float(output.get("L1A")),
        output_current_l2=_to_float(output.get("L2A")),
        output_current_l3=_to_float(output.get("L3A")),
        output_frequency=out_freq_hz,    # << เปลี่ยนมาใช้ค่าแปลงแล้ว
        output_load_va=int(_to_float(snap.get("loadVA")) or 0) if snap.get("loadVA") is not None else None,
        output_load_w=int(_to_float(snap.get("loadW")) or 0) if snap.get("loadW") is not None else None,
        load_percentage=_to_float(snap.get("loadPct")),
    )
    session.add(row)
    session.flush()

    # ----- ช่วง power events (powerfail และ power_outage) -----
    if st_raw in ("powerfail", "power_outage"):
        # กำหนด event_type และ message ตามประเภท
        if st_raw == "power_outage":
            event_type = "power_outage"
            base_message = "Power outage detected"
        else:
            event_type = "powerfail" 
            base_message = "Power failure detected"
            
        # ตรวจสอบว่ามี event ประเภทนี้ที่เปิดอยู่หรือไม่
        open_event = (
            session.execute(
                select(UPSEvent)
                .where(
                    and_(
                        UPSEvent.ups_id == ups_id,
                        UPSEvent.event_type == event_type,
                        UPSEvent.end_time.is_(None),
                    )
                )
                .order_by(UPSEvent.start_time.desc())
            )
            .scalars()
            .first()
        )
        
        if not open_event:
            # สร้าง message ที่ละเอียดขึ้นตามสาเหตุ
            input_voltages = [l1v, l2v, l3v]
            
            # ตรวจสอบสาเหตุ
            voltage_issues = []
            for i, voltage in enumerate(input_voltages, 1):
                if voltage is not None:
                    if voltage == 0:
                        voltage_issues.append(f"L{i}: 0V (ไฟดับ)")
                    elif 0 < voltage < 180:
                        voltage_issues.append(f"L{i}: {voltage}V (ไฟตก)")
            
            if voltage_issues:
                message = f"{base_message} - {', '.join(voltage_issues)}"
            else:
                message = base_message
            
            # กำหนด detection_reason
            if st_raw == "power_outage":
                detection_reason = "no_input_power"
            else:
                detection_reason = "voltage_below_threshold"
            
            ups_event_service.log_event(
                session,
                ups_id=ups_id,
                event_type=event_type,
                severity="warning",
                message=message,
                event_data={
                    "input_voltages": {
                        "L1V": input_voltages[0],
                        "L2V": input_voltages[1], 
                        "L3V": input_voltages[2]
                    },
                    "detection_reason": detection_reason
                },
                start_time=ts,
            )
    else:
        # ปิด power events ที่เปิดอยู่ (ทั้ง powerfail และ power_outage)
        for event_type in ["powerfail", "power_outage"]:
            open_event = (
                session.execute(
                    select(UPSEvent)
                    .where(
                        and_(
                            UPSEvent.ups_id == ups_id,
                            UPSEvent.event_type == event_type,
                            UPSEvent.end_time.is_(None),
                        )
                    )
                    .order_by(UPSEvent.start_time.desc())
                )
                .scalars()
                .first()
            )
            if open_event:
                open_event.end_time = ts
                open_event.message = f"{open_event.message} - Power restored"
                session.flush()

    # ----- ช่วง offline -----
    if st_raw == "offline":
        open_off = (
            session.execute(
                select(UPSEvent)
                .where(
                    and_(
                        UPSEvent.ups_id == ups_id,
                        UPSEvent.event_type == "offline",
                        UPSEvent.end_time.is_(None),
                    )
                )
                .order_by(UPSEvent.start_time.desc())
            )
            .scalars()
            .first()
        )
        if not open_off:
            ups_event_service.log_event(
                session,
                ups_id=ups_id,
                event_type="offline",
                severity="critical",
                message="Device is offline",
                start_time=ts,
            )
    else:
        open_off = (
            session.execute(
                select(UPSEvent)
                .where(
                    and_(
                        UPSEvent.ups_id == ups_id,
                        UPSEvent.event_type == "offline",
                        UPSEvent.end_time.is_(None),
                    )
                )
                .order_by(UPSEvent.start_time.desc())
            )
            .scalars()
            .first()
        )
        if open_off:
            open_off.end_time = ts
            session.flush()

    # timeline ของสถานะ (ใช้ค่าที่ map แล้ว)
    ups_event_service.log_status_change(session, ups_id, status_for_snapshot, ts)
    session.flush()
    return row


def log_events_for_snapshot(session: Session, snap: Dict[str, Any]) -> None:
    """
    hook สำหรับ log เพิ่มเติมจาก snapshot (กรณีต้องการ)
    ตอนนี้ยังเป็น stub เอาไว้ต่อยอดเช่น battery_low, temp_high เป็นต้น
    """
    # ตัวอย่างต่อยอด:
    # if (_to_float(snap.get("batteryPercent")) or 100) < 15:
    #     ups_event_service.log_event(session, ups_id, "battery_low", "warning",
    #                                 start_time=_parse_collected_at(snap))
    return


def aggregate_to_history(
    session: Session,
    day,  # str | datetime | date
    ups_id: str,
    *,
    use_status_event_powerfail: bool = False,
    commit: bool = True,
) -> UPSHistory:
    """
    Wrapper ให้ชื่อฟังก์ชันตรงกับที่ที่อื่น import ใช้
    - day รองรับ 'YYYY-MM-DD' | datetime | date
    - เรียกใช้ ups_event_service.persist_daily_to_history ใต้ฝา
    """
    # normalize day -> datetime (naive) ที่เวลา 00:00
    if isinstance(day, str):
        s = day.strip().replace("Z", "")
        parsed = None
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
            try:
                parsed = _dt.strptime(s, fmt)
                break
            except Exception:
                continue
        if parsed is None:
            try:
                parsed = _dt.fromisoformat(s)
            except Exception:
                raise ValueError(f"aggregate_to_history(day): unsupported date string '{day}'")
        day_dt = parsed
    elif isinstance(day, _dt):
        day_dt = day
    elif isinstance(day, _date):
        day_dt = _dt.combine(day, _dt.min.time())
    else:
        raise TypeError("aggregate_to_history(day): day must be str|datetime|date")

    # ตัดเวลาให้เป็นต้นวัน
    day_dt = day_dt.replace(hour=0, minute=0, second=0, microsecond=0)

    return ups_event_service.persist_daily_to_history(
        session,
        day_dt,
        ups_id,
        use_status_event_powerfail=use_status_event_powerfail,
        commit=commit,
    )

def _eval_number_string(s: str) -> Optional[float]:
    """
    รองรับสตริงตัวเลขง่าย ๆ ที่มีเครื่องหมายคำนวณ เช่น '500/10', '50.1'
    ป้องกันด้วย whitelist ของอักขระที่ยอมรับ
    """
    s = s.strip()
    if not _ARITH_SAFE.match(s):
        return None
    try:
        # ใช้ eval แบบ context ว่าง ๆ (ไม่มี builtins) เพื่อความปลอดภัย
        return float(eval(s, {"__builtins__": {}}, {}))
    except Exception:
        return None

def _to_number(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and v.strip() != "":
        # ลอง parse เป็นเลขตรง ๆ ก่อน
        try:
            return float(v.strip())
        except Exception:
            # ถ้าไม่ใช่เลขล้วน อาจเป็นนิพจน์ง่าย ๆ เช่น '500/10'
            return _eval_number_string(v)
    return None

def _norm_freq_hz(v: Any) -> Optional[float]:
    """
    แปลงความถี่ให้เป็นเฮิร์ตซ์ (Hz) เสมอ:
    - ถ้าได้ deci-Hz (ค่าประมาณ >= 100) ให้หาร 10
    - ถ้าได้ Hz อยู่แล้ว (ประมาณ 40–70) ให้คืนตามเดิม
    - รองรับสตริงแบบ '500/10'
    - 0 หรือค่าติดลบ -> None
    """
    x = _to_number(v)
    if x is None:
        return None
    if x <= 0:
        return None
    # heuristic: ถ้าค่า >= 100 ให้ถือว่าเป็น deci-Hz
    hz = x / 10.0 if x >= 100 else x
    # กันค่าเพี้ยนมาก ๆ
    if hz > 1000:  # ไม่สมเหตุสมผลสำหรับ line frequency
        return None
    # ปัดทศนิยมเบา ๆ
    return round(hz, 2)


__all__ = [
    "UPSEventService",
    "ups_event_service",
    "persist_status",
    "log_events_for_snapshot",
    "aggregate_to_history",
]

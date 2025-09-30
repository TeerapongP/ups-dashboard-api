# app/services/report_service.py
from __future__ import annotations

import json
from datetime import datetime, date as _date, time as _time, timedelta
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import text
from sqlalchemy.orm import Session

try:
    from zoneinfo import ZoneInfo
except Exception:  # py<3.9
    from backports.zoneinfo import ZoneInfo  # type: ignore

BKK = ZoneInfo("Asia/Bangkok")


def _ensure_date(day: Optional[Union[str, _date]]) -> _date:
    """
    รับ 'YYYY-MM-DD' | 'YYYY/MM/DD' | ISO string | date | None
    คืนเป็น date (default = วันนี้ตามเวลา Asia/Bangkok)
    """
    if day is None:
        return datetime.now(BKK).date()
    if isinstance(day, _date):
        return day
    if isinstance(day, str):
        s = day.strip().replace("Z", "")
        if not s:
            return datetime.now(BKK).date()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(s, fmt).date()
            except Exception:
                continue
        try:
            return datetime.fromisoformat(s).date()
        except Exception:
            return datetime.now(BKK).date()
    # fallback
    return datetime.now(BKK).date()


def _sid(v: Any) -> Optional[str]:
    """บังคับให้ ups_id เป็นสตริงเสมอ (หรือ None ถ้าไม่มี)"""
    return str(v) if v is not None else None


def _to_jsonable(v: Any) -> Any:
    """แปลงค่าให้ serialize เป็น JSON ได้ง่าย"""
    if isinstance(v, datetime):
        return v.replace(microsecond=0).isoformat()
    try:
        from decimal import Decimal  # lazy import
        if isinstance(v, Decimal):  # type: ignore[name-defined]
            return float(v)
    except Exception:
        pass
    return v


class ReportService:
    @staticmethod
    def _ensure_date(day: Optional[Union[str, _date]]) -> _date:
        return _ensure_date(day)

    @staticmethod
    def get_daily_report(
        db: Session,
        day: Optional[Union[str, _date]],
        *,
        ups_id: Optional[str] = None,
        only_with_events: bool = True,
    ):
        d: _date = ReportService._ensure_date(day)

        # ===== กรอบวันเป็น "เวลาไทย" แล้วทำให้ naive เพื่อให้ตรงกับคอลัมน์ใน DB =====
        start_local = datetime.combine(d, _time.min).replace(tzinfo=BKK)
        end_local = start_local + timedelta(days=1)
        start_dt = start_local.replace(tzinfo=None)
        end_dt = end_local.replace(tzinfo=None)

        # ---------- Devices (active) ----------
        dev_sql = """
            SELECT id, ip_address, brand, model, location, capacity_va, capacity_w
            FROM ups_devices
            WHERE is_active = 1
        """
        params: Dict[str, Any] = {}
        if ups_id:
            dev_sql += " AND id = :uid"
            params["uid"] = ups_id
        dev_sql += " ORDER BY id"
        devs = db.execute(text(dev_sql), params).mappings().all()

        # ---------- Offline windows (overlap-aware + ongoing) ----------
        # ใช้เวลาปัจจุบันแบบไทย โดยไม่ต้องพึ่ง timezone tables:
        #   UTC_TIMESTAMP() + INTERVAL 7 HOUR
        off_sql = """
            SELECT
                ups_id,
                GREATEST(changed_at, :s) AS win_start,
                LEAST(
                    COALESCE(next_changed_at, UTC_TIMESTAMP() + INTERVAL 7 HOUR),
                    :e
                ) AS win_end,
                GREATEST(
                    0,
                    TIMESTAMPDIFF(
                        SECOND,
                        GREATEST(changed_at, :s),
                        LEAST(
                            COALESCE(next_changed_at, UTC_TIMESTAMP() + INTERVAL 7 HOUR),
                            :e
                        )
                    )
                ) AS duration_sec,
                note
            FROM ups_status_event
            WHERE new_status = 'offline'
              AND changed_at < :e
              AND COALESCE(next_changed_at, UTC_TIMESTAMP() + INTERVAL 7 HOUR) > :s
        """
        off_params: Dict[str, Any] = {"s": start_dt, "e": end_dt}
        if ups_id:
            off_sql += " AND ups_id = :uid"
            off_params["uid"] = ups_id
        off_sql += " ORDER BY ups_id, win_start"
        offline = db.execute(text(off_sql), off_params).mappings().all()

        # ---------- PowerFail events ----------
        # (ยังดึงเฉพาะที่เริ่มภายในวัน; ถ้าต้องการ overlap-aware ให้ปรับคล้าย offline)
        pf_sql = """
            SELECT ups_id, start_time, end_time, duration_seconds, message, event_data
            FROM ups_events
            WHERE event_type = 'powerfail'
              AND start_time >= :s AND start_time < :e
        """
        pf_params: Dict[str, Any] = {"s": start_dt, "e": end_dt}
        if ups_id:
            pf_sql += " AND ups_id = :uid"
            pf_params["uid"] = ups_id
        pf_sql += " ORDER BY ups_id, start_time"
        powerfail = db.execute(text(pf_sql), pf_params).mappings().all()

        # ---------- Latest status per device (ก่อนสิ้นวัน) ----------
        last_stat_sql = """
            SELECT e.ups_id, e.new_status, e.changed_at
            FROM ups_status_event e
            INNER JOIN (
                SELECT ups_id, MAX(changed_at) AS last_ts
                FROM ups_status_event
                WHERE changed_at < :e
                {ups_filter_inner}
                GROUP BY ups_id
            ) m ON m.ups_id = e.ups_id AND m.last_ts = e.changed_at
            {ups_filter_outer}
        """
        ups_filter_inner = "AND ups_id = :uid" if ups_id else ""
        ups_filter_outer = "WHERE e.ups_id = :uid" if ups_id else ""
        last_params: Dict[str, Any] = {"e": end_dt}
        if ups_id:
            last_params["uid"] = ups_id

        last_status_rows = db.execute(
            text(
                last_stat_sql.format(
                    ups_filter_inner=ups_filter_inner,
                    ups_filter_outer=ups_filter_outer,
                )
            ),
            last_params,
        ).mappings().all()

        last_status_by_id: Dict[str, Dict[str, Any]] = {
            _sid(r["ups_id"]): {
                "status": r.get("new_status"),
                "at": _to_jsonable(r.get("changed_at")),
            }
            for r in last_status_rows
        }

        # ---------- Build payload ----------
        by_id: Dict[str, dict] = {}

        def ensure_bucket(vid: Any) -> dict:
            sid = _sid(vid)
            if sid not in by_id:
                by_id[sid] = {
                    "meta": {
                        "upsId": sid,
                        "ip": None,
                        "brand": None,
                        "model": None,
                        "location": None,
                        "capacityVA": None,
                        "capacityW": None,
                        "lastStatus": None,
                        "lastStatusAt": None,
                    },
                    "offline": [],
                    "powerFail": [],
                }
            else:
                by_id[sid].setdefault("offline", [])
                by_id[sid].setdefault("powerFail", [])
                by_id[sid]["meta"].setdefault("lastStatus", None)
                by_id[sid]["meta"].setdefault("lastStatusAt", None)
            return by_id[sid]

        # devices meta
        for row in devs:
            sid = _sid(row["id"])
            b = ensure_bucket(sid)
            b["meta"].update(
                {
                    "ip": row.get("ip_address"),
                    "brand": row.get("brand"),
                    "model": row.get("model"),
                    "location": row.get("location"),
                    "capacityVA": _to_jsonable(row.get("capacity_va")),
                    "capacityW": _to_jsonable(row.get("capacity_w")),
                }
            )

        # offline (ใช้ช่วง win_start/win_end และ duration_sec ที่คิด overlap มาแล้ว)
        for r in offline:
            dur = int(r.get("duration_sec") or 0)
            if dur < 0:
                dur = 0
            b = ensure_bucket(r["ups_id"])
            b["offline"].append(
                {
                    "start": _to_jsonable(r.get("win_start")),
                    "end": _to_jsonable(r.get("win_end")),
                    "durationSec": dur,
                    "note": r.get("note"),
                }
            )

        # powerfail
        for r in powerfail:
            b = ensure_bucket(r["ups_id"])
            evd = r.get("event_data")
            if isinstance(evd, str):
                try:
                    evd = json.loads(evd)
                except Exception:
                    evd = {}
            evd = evd or {}
            b["powerFail"].append(
                {
                    "start": _to_jsonable(r.get("start_time")),
                    "end": _to_jsonable(r.get("end_time")),
                    "durationSec": int(r.get("duration_seconds") or 0),
                    "note": r.get("message"),
                    "voltage": _to_jsonable(evd.get("voltage")),
                    "threshold": _to_jsonable(evd.get("threshold")),
                }
            )

        # meta: last status
        for sid, info in last_status_by_id.items():
            b = ensure_bucket(sid)
            b["meta"]["lastStatus"] = info.get("status")
            b["meta"]["lastStatusAt"] = info.get("at")

        devices: List[dict] = list(by_id.values())

        # filter เฉพาะที่มีเหตุการณ์ (ถ้าต้องการ)
        if only_with_events:
            devices = [
                drow
                for drow in devices
                if (len(drow.get("offline") or []) + len(drow.get("powerFail") or [])) > 0
            ]

        # การันตี array เสมอ
        for drow in devices:
            if not isinstance(drow.get("offline"), list):
                drow["offline"] = []
            if not isinstance(drow.get("powerFail"), list):
                drow["powerFail"] = []

        devices.sort(key=lambda x: (x["meta"]["upsId"]))

        return {
            "reportDate": d.isoformat(),
            "periodStart": d.strftime("%d/%m/%Y"),
            "periodEnd": d.strftime("%d/%m/%Y"),
            "generatedAt": datetime.now(BKK).strftime("%d/%m/%Y %H:%M"),
            "periodTotalMinutes": 24 * 60,
            "devices": devices,
        }

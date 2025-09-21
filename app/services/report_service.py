from __future__ import annotations

from datetime import date, datetime, timedelta, time
from typing import Union, Any, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from decimal import Decimal
import json


def _to_jsonable(v: Any):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _sid(v: Any) -> str:
    return "" if v is None else str(v)


class ReportService:
    @staticmethod
    def _ensure_date(day: Union[str, date]) -> date:
        if isinstance(day, date):
            return day
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(day, fmt).date()
            except ValueError:
                continue
        raise ValueError("Invalid date format, expected YYYY-MM-DD or DD/MM/YYYY")

    @staticmethod
    def get_daily_report(
        db: Session,
        day: Union[str, date],
        *,
        ups_id: Optional[str] = None,
        only_with_events: bool = True,
    ):
        d: date = ReportService._ensure_date(day)

        start_dt = datetime.combine(d, time.min)
        end_dt   = start_dt + timedelta(days=1)

        # ---------- Devices (active) ----------
        dev_sql = """
            SELECT id, ip_address, brand, model, location, capacity_va, capacity_w
            FROM ups_devices
            WHERE is_active = 1
        """
        params = {}
        if ups_id:
            dev_sql += " AND id = :uid"
            params["uid"] = ups_id
        dev_sql += " ORDER BY id"
        devs = db.execute(text(dev_sql), params).mappings().all()

        # ---------- Offline windows ----------
        off_sql = """
            SELECT ups_id, changed_at, next_changed_at, duration_sec, note
            FROM ups_status_event
            WHERE new_status = 'offline'
              AND changed_at >= :s AND changed_at < :e
        """
        off_params = {"s": start_dt, "e": end_dt}
        if ups_id:
            off_sql += " AND ups_id = :uid"
            off_params["uid"] = ups_id
        off_sql += " ORDER BY ups_id, changed_at"
        offline = db.execute(text(off_sql), off_params).mappings().all()

        # ---------- PowerFail events ----------
        pf_sql = """
            SELECT ups_id, start_time, end_time, duration_seconds, message, event_data
            FROM ups_events
            WHERE event_type = 'powerfail'
              AND start_time >= :s AND start_time < :e
        """
        pf_params = {"s": start_dt, "e": end_dt}
        if ups_id:
            pf_sql += " AND ups_id = :uid"
            pf_params["uid"] = ups_id
        pf_sql += " ORDER BY ups_id, start_time"
        powerfail = db.execute(text(pf_sql), pf_params).mappings().all()

        # ---------- Latest status per device (ก่อนสิ้นวัน) ----------
        # ดึง new_status ล่าสุดของแต่ละ ups_id ที่ changed_at < end_dt
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
        last_params = {"e": end_dt}
        if ups_id:
            last_params["uid"] = ups_id

        last_status_rows = db.execute(
            text(last_stat_sql.format(ups_filter_inner=ups_filter_inner, ups_filter_outer=ups_filter_outer)),
            last_params
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

        # จากตาราง devices (active)
        for row in devs:
            sid = _sid(row["id"])
            b = ensure_bucket(sid)
            b["meta"].update({
                "ip": row.get("ip_address"),
                "brand": row.get("brand"),
                "model": row.get("model"),
                "location": row.get("location"),
                "capacityVA": _to_jsonable(row.get("capacity_va")),
                "capacityW": _to_jsonable(row.get("capacity_w")),
            })

        # offline
        for r in offline:
            b = ensure_bucket(r["ups_id"])
            b["offline"].append({
                "start": _to_jsonable(r.get("changed_at")),
                "end": _to_jsonable(r.get("next_changed_at")),
                "durationSec": int(r.get("duration_sec") or 0),
                "note": r.get("note"),
            })

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
            b["powerFail"].append({
                "start": _to_jsonable(r.get("start_time")),
                "end": _to_jsonable(r.get("end_time")),
                "durationSec": int(r.get("duration_seconds") or 0),
                "note": r.get("message"),
                "voltage": _to_jsonable(evd.get("voltage")),
                "threshold": _to_jsonable(evd.get("threshold")),
            })

        # ใส่สถานะล่าสุดลง meta
        for sid, info in last_status_by_id.items():
            b = ensure_bucket(sid)
            b["meta"]["lastStatus"] = info.get("status")
            b["meta"]["lastStatusAt"] = info.get("at")

        devices = list(by_id.values())

        # --- ตัดพวกที่ว่างออก ถ้า only_with_events=True ---
        if only_with_events:
            devices = [
                drow for drow in devices
                if (len(drow.get("offline") or []) + len(drow.get("powerFail") or [])) > 0
            ]

        # การันตี array เสมอ
        for drow in devices:
            if not isinstance(drow.get("offline"), list):
                drow["offline"] = []
            if not isinstance(drow.get("powerFail"), list):
                drow["powerFail"] = []
            # (ออปชัน) ถ้าอยากตั้งค่าเริ่มต้นเมื่อไม่พบเหตุการณ์เลย:
            # if drow["meta"]["lastStatus"] is None:
            #     drow["meta"]["lastStatus"] = "online"

        devices.sort(key=lambda x: (x["meta"]["upsId"] or ""))

        return {
            "reportDate": d.isoformat(),
            "periodStart": d.strftime("%d/%m/%Y"),
            "periodEnd": d.strftime("%d/%m/%Y"),
            "generatedAt": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "periodTotalMinutes": 24 * 60,
            "devices": devices,
        }

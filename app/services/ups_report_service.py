# app/services/ups_report_service.py
from __future__ import annotations
from io import BytesIO
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from model.model import UPSDevice, UPSStatusEvent, UPSEvent
from app.services.ups_events import ups_event_service


class UPSReportService:
    def _render_html_to_pdf(self, html: str) -> BytesIO:
        """
        แปลง HTML -> PDF ด้วย WeasyPrint แบบ lazy import
        ถ้า WeasyPrint ยังไม่พร้อม จะ raise RuntimeError ให้ endpoint จัดการ (เช่น 503)
        """
        try:
            from weasyprint import HTML  # ✅ lazy import ตรงนี้
        except Exception as e:
            raise RuntimeError(f"WeasyPrint not available: {e}")

        buf = BytesIO()
        HTML(string=html).write_pdf(buf)
        buf.seek(0)
        return buf

    def generate_daily_pdf(
        self,
        db: Session,
        day: datetime,
        use_status_event_powerfail: bool = False,
        include_details: bool = False,
    ) -> BytesIO | None:
        """สร้าง PDF รายงานรายวัน ถ้าไม่มีข้อมูลจะสร้าง PDF แจ้ง 'No events'"""
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        devices = db.query(UPSDevice).filter(UPSDevice.is_active == True).all()
        if not devices:
            # ไม่มี device เลย → สร้างหน้า No events
            html = f"""
            <!doctype html><html><head><meta charset="utf-8" />
            <style>body{{font-family:Arial,"Noto Sans Thai",sans-serif;}}
            .wrap{{padding:24px}} .title{{font-size:20px;font-weight:700}}
            .muted{{color:#777}}</style></head><body>
            <div class="wrap">
              <div class="title">UPS Downtime Report — {day.date()}</div>
              <p class="muted">ไม่มีอุปกรณ์ที่ Active</p>
            </div>
            </body></html>"""
            return self._render_html_to_pdf(html)

        total_offline = 0
        total_powerfail = 0
        rows_html: List[str] = []
        details_html: List[str] = []

        def _append_detail_block(title: str, intervals: List[Dict[str, Any]]) -> str:
            if not intervals:
                return ""
            lis = []
            for it in intervals:
                start = it["start"]
                end = it["end"] or "-"
                dur = it["duration_minutes"]
                lis.append(f"<li><b>{start}</b> → <b>{end}</b> : {dur} นาที</li>")
            return f"""
            <div class="detail-block">
              <div class="detail-title">{title}</div>
              <ul class="detail-list">
                {''.join(lis)}
              </ul>
            </div>
            """

        for dev in devices:
            counters = ups_event_service.get_daily_counters(
                db, day, dev.id, use_status_event_powerfail=use_status_event_powerfail
            )
            off_min = counters["offline_minutes"]
            pf_min = counters["powerfail_minutes"]

            # กรองเครื่องที่ไม่มีเหตุการณ์
            if off_min == 0 and pf_min == 0:
                continue

            total_offline += off_min
            total_powerfail += pf_min

            rows_html.append(
                f"""
                <tr>
                  <td>{dev.id}</td>
                  <td>{dev.ip_address}</td>
                  <td>{dev.location}</td>
                  <td class="num">{off_min}</td>
                  <td class="num">{pf_min}</td>
                </tr>
                """
            )

            if include_details:
                # OFFLINE intervals (จาก ups_status_event)
                offline_intervals: List[Dict[str, Any]] = []
                rows_off = (
                    db.execute(
                        select(UPSStatusEvent.changed_at, UPSStatusEvent.next_changed_at)
                        .where(
                            and_(
                                UPSStatusEvent.ups_id == dev.id,
                                UPSStatusEvent.new_status == 'offline',
                                UPSStatusEvent.changed_at < day_end,
                            )
                        )
                        .order_by(UPSStatusEvent.changed_at.asc())
                    ).all()
                )
                for (start_ts, end_ts) in rows_off:
                    s = max(start_ts, day_start)
                    e = min(end_ts or day_end, day_end)
                    if e > s:
                        offline_intervals.append({
                            "start": s.isoformat(sep=" ", timespec="seconds"),
                            "end": (e.isoformat(sep=" ", timespec="seconds") if end_ts else None),
                            "duration_minutes": int((e - s).total_seconds() // 60),
                        })

                # POWERFAIL intervals (จาก status_event หรือ events ตาม flag)
                powerfail_intervals: List[Dict[str, Any]] = []
                if use_status_event_powerfail:
                    rows_pf = (
                        db.execute(
                            select(UPSStatusEvent.changed_at, UPSStatusEvent.next_changed_at)
                            .where(
                                and_(
                                    UPSStatusEvent.ups_id == dev.id,
                                    UPSStatusEvent.new_status == 'powerfail',
                                    UPSStatusEvent.changed_at < day_end,
                                )
                            )
                            .order_by(UPSStatusEvent.changed_at.asc())
                        ).all()
                    )
                else:
                    rows_pf = (
                        db.execute(
                            select(UPSEvent.start_time, UPSEvent.end_time)
                            .where(
                                and_(
                                    UPSEvent.ups_id == dev.id,
                                    UPSEvent.event_type == 'powerfail',
                                    UPSEvent.start_time < day_end,
                                )
                            )
                            .order_by(UPSEvent.start_time.asc())
                        ).all()
                    )

                for (start_ts, end_ts) in rows_pf:
                    s = max(start_ts, day_start)
                    e = min(end_ts or day_end, day_end)
                    if e > s:
                        powerfail_intervals.append({
                            "start": s.isoformat(sep=" ", timespec="seconds"),
                            "end": (e.isoformat(sep=" ", timespec="seconds") if end_ts else None),
                            "duration_minutes": int((e - s).total_seconds() // 60),
                        })

                details_html.append(
                    f"""
                    <div class="device-detail">
                      <div class="device-header">
                        <div><b>UPS:</b> {dev.id}</div>
                        <div><b>IP:</b> {dev.ip_address}</div>
                        <div><b>Location:</b> {dev.location}</div>
                      </div>
                      {_append_detail_block("OFFLINE", offline_intervals)}
                      {_append_detail_block("POWERFAIL", powerfail_intervals)}
                    </div>
                    """
                )

        # ถ้าไม่มีเหตุการณ์เลย → สร้างหน้า 'No events'
        if not rows_html:
            html = f"""
            <!doctype html><html><head><meta charset="utf-8" />
            <style>body{{font-family:Arial,"Noto Sans Thai",sans-serif;}}
            .wrap{{padding:24px}} .title{{font-size:20px;font-weight:700}}
            .muted{{color:#777}}</style></head><body>
            <div class="wrap">
              <div class="title">UPS Downtime Report — {day.date()}</div>
              <p class="muted">ไม่มีเหตุการณ์ Offline หรือ PowerFail ในวันที่ระบุ</p>
            </div>
            </body></html>"""
            return self._render_html_to_pdf(html)

        # มีเหตุการณ์ → ทำ HTML จริง
        html = f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>UPS Downtime Report - {day.date()}</title>
    <style>
      body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "TH Sarabun New", Arial, "Noto Sans Thai", sans-serif; }}
      .header {{ display:flex; justify-content:space-between; align-items:flex-end; }}
      .title {{ font-size: 22px; font-weight: 700; }}
      .date {{ font-size: 14px; color: #555; }}
      .kpi {{ margin: 16px 0; display:flex; gap:16px; }}
      .kpi .card {{ padding: 10px 14px; border: 1px solid #ddd; border-radius: 8px; }}
      table {{ width:100%; border-collapse: collapse; margin-top: 12px; }}
      th, td {{ border: 1px solid #ddd; padding: 6px 8px; font-size: 12px; }}
      th {{ background: #f7f7f7; text-align: left; }}
      td.num {{ text-align: right; }}
      .section-title {{ margin-top: 24px; font-size: 16px; font-weight: 700; }}
      .device-detail {{ border:1px solid #eee; border-radius:6px; padding:10px; margin:8px 0 14px; }}
      .device-header {{ display:flex; gap:18px; margin-bottom:8px; font-size: 12px; }}
      .detail-block {{ margin: 4px 0 8px; }}
      .detail-title {{ font-weight: 600; font-size: 12px; margin-bottom: 4px; }}
      .detail-list {{ margin: 0 0 0 18px; padding: 0; font-size: 12px; }}
    </style>
  </head>
  <body>
    <div class="header">
      <div class="title">UPS Downtime Report</div>
      <div class="date">{day.date()}</div>
    </div>

    <div class="kpi">
      <div class="card"><b>รวม OFFLINE</b><br>{total_offline} นาที</div>
      <div class="card"><b>รวม POWERFAIL</b><br>{total_powerfail} นาที</div>
      <div class="card"><b>จำนวนอุปกรณ์ (มีเหตุการณ์)</b><br>{len(rows_html)}</div>
    </div>

    <div class="section">
      <div class="section-title">สรุปต่ออุปกรณ์</div>
      <table>
        <thead>
          <tr>
            <th>UPS ID</th>
            <th>IP</th>
            <th>Location</th>
            <th>Offline (นาที)</th>
            <th>PowerFail (นาที)</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows_html)}
        </tbody>
      </table>
    </div>

    {"<div class='section'><div class='section-title'>รายละเอียดเหตุการณ์</div>" + ''.join(details_html) + "</div>" if include_details else ""}

  </body>
</html>
        """
        # ✅ ใช้ helper ที่ lazy import
        return self._render_html_to_pdf(html)


ups_report_service = UPSReportService()

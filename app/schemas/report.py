# app/schemas/report.py
from typing import List, Optional
from pydantic import BaseModel

class EventRow(BaseModel):
    start: str                # ISO string
    end: Optional[str]        # ISO string หรือ None
    durationSec: int
    note: Optional[str] = None
    voltage: Optional[float] = None     # สำหรับ powerfail
    threshold: Optional[float] = None   # สำหรับ powerfail

class DeviceMeta(BaseModel):
    upsId: str
    ip: str
    brand: str
    model: str
    location: str
    capacityVA: Optional[int] = None
    capacityW: Optional[int] = None

class DeviceDailyReport(BaseModel):
    meta: DeviceMeta
    offline: List[EventRow]
    powerFail: List[EventRow]
    # optional: สถิติรวม (ถ้าต้องการ)
    # stats: Optional[dict] = None

class DailyReportPayload(BaseModel):
    reportDate: str           # 'YYYY-MM-DD'
    devices: List[DeviceDailyReport]

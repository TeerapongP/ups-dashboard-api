from __future__ import annotations
from typing import Dict, List, Optional, Union
from pydantic import BaseModel, Field, IPvAnyAddress, validator

OIDValue = Union[str, List[str]]


class DeviceCreatePayload(BaseModel):
    ip: IPvAnyAddress
    brand: Optional[str] = None
    model: Optional[str] = None
    location: Optional[str] = None
    profile_name: Optional[str] = None  # เผื่ออยากตั้งชื่อเอง (ไม่บังคับ)


class DeviceCreateWithOIDsPayload(DeviceCreatePayload):
    data: Dict[str, OIDValue] = Field(
        ..., description="map: oid_key -> primary หรือ [primary, fallback...]"
    )

    @validator("data")
    def not_empty(cls, v):
        if not v:
            raise ValueError("data ว่าง")
        return v


class DeviceUpdatePayload(BaseModel):
    brand: Optional[str] = None
    model: Optional[str] = None
    location: Optional[str] = None
    is_active: Optional[bool] = None
    profile_name: Optional[str] = None  # ถ้าอยากระบุโปรไฟล์ที่จะผูก
    data: Optional[Dict[str, Union[str, List[str]]]] = None  # <-- ใส่ OIDs มาในนี้

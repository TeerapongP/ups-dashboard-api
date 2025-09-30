# app/utils/errors.py
from typing import Tuple
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

def sanitize_db_error(exc: Exception) -> Tuple[int, str]:
    """
    รับ Exception จากชั้น service/db แล้วแปลงเป็น (http_status, safe_message)
    โดยไม่เปิดเผย SQL/พารามิเตอร์
    """
    # เคสกำกับเองจาก service
    msg = str(exc) if exc else ""
    if isinstance(exc, ValueError):
        # ข้อผิดพลาด validation ธรรมดา
        # เช่น "UPS ip=... มีอยู่แล้ว", "data ว่าง", "invalid IPv4"
        return 409 if "มีอยู่แล้ว" in msg or "already exists" in msg else 400, msg

    # ---------- SQLAlchemy ----------
    if isinstance(exc, IntegrityError):
        # MySQL error codes popular: 1062 dup, 1451/1452 FK, 1364 no default
        orig = getattr(exc, "orig", None)
        code = getattr(orig, "args", [None, None])[0] if orig else None
        # duplicate
        if code == 1062:
            # ดูคร่าวๆ ว่าซ้ำอะไร
            if "ip_address" in msg:
                return 409, "เพิ่มไม่สำเร็จ: IP นี้ถูกใช้แล้ว"
            if "PRIMARY" in msg or "for key 'PRIMARY'" in msg:
                return 409, "เพิ่มไม่สำเร็จ: รหัสอุปกรณ์ซ้ำ"
            return 409, "เพิ่ม/แก้ไขไม่สำเร็จ: ข้อมูลซ้ำ"
        # foreign key
        if code in (1451, 1452):
            return 409, "ดำเนินการไม่สำเร็จ: มีข้อมูลที่อ้างอิงอยู่ (Foreign Key)"
        # not null / default
        if code in (1364, 1048):
            return 400, "ข้อมูลไม่ครบถ้วน: มีฟิลด์จำเป็นที่ไม่ได้ระบุ"
        return 400, "คำขอไม่ถูกต้อง: ข้อมูลไม่ผ่านข้อจำกัดของฐานข้อมูล"

    if isinstance(exc, OperationalError):
        # เช่น Field doesn't have a default value ฯลฯ
        return 400, "คำขอไม่ถูกต้อง: ข้อมูลไม่ครบหรือไม่ผ่านข้อจำกัด"

    if isinstance(exc, SQLAlchemyError):
        return 500, "มีปัญหาที่ระบบฐานข้อมูล กรุณาลองใหม่อีกครั้ง"

    # อื่น ๆ
    return 500, "เกิดข้อผิดพลาดที่ระบบ กรุณาลองใหม่อีกครั้ง"

from __future__ import annotations
from typing import Dict, List, Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy import text

from model.model import UPSDevice

class SNMPService:
    # ---------- helpers ----------
    @staticmethod
    def _normalize_oids_map(data: Dict[str, Union[str, List[str]]]) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}
        for k, v in data.items():
            if isinstance(v, str):
                s = v.strip()
                if s:
                    out[k] = [s]
            elif isinstance(v, list):
                lst = [str(x).strip() for x in v if str(x).strip()]
                if lst:
                    out[k] = lst
        return out

    @staticmethod
    def _create_device(
        db: Session,
        ip: str,
        *,
        brand: Optional[str],
        model: Optional[str],
        location: Optional[str],
        profile_name: Optional[str],
    ) -> UPSDevice:
        # บังคับ insert ใหม่เท่านั้น
        exist = db.query(UPSDevice).filter(UPSDevice.ip_address == ip).first()
        if exist:
            raise ValueError(f"UPS ip={ip} มีอยู่แล้ว")

        dev = UPSDevice(
            ip_address=ip,
            brand=(brand or "Unknown"),
            model=(model or "Unknown"),
            location=(location or "-"),
            capacity_va=0,   # ไม่ให้ user กรอก
            capacity_w=0,    # ไม่ให้ user กรอก
            is_active=True,
        )
        db.add(dev)
        db.flush()  # ได้ dev.id

        # สร้าง/ผูกโปรไฟล์เริ่มต้น (CUSTOM_<id>) หรือชื่อที่ส่งมา
        SNMPService._ensure_profile_for_device(db, dev.id, profile_name=profile_name)
        return dev

    @staticmethod
    def _ensure_profile_for_device(db: Session, ups_id: int, profile_name: Optional[str] = None) -> int:
        name = profile_name or f"CUSTOM_{ups_id}"
        row = db.execute(text("SELECT id FROM snmp_profile WHERE name=:n LIMIT 1"), {"n": name}).first()
        if row:
            pid = int(row[0])
        else:
            db.execute(
                text("INSERT INTO snmp_profile (name, vendor, model, notes) VALUES (:n, NULL, NULL, :notes)"),
                {"n": name, "notes": "Auto-created per-device profile"},
            )
            pid = int(db.execute(text("SELECT LAST_INSERT_ID()")).scalar())

        db.execute(
            text("""
                INSERT INTO ups_device_profile (ups_id, profile_id)
                VALUES (:uid, :pid)
                ON DUPLICATE KEY UPDATE profile_id = VALUES(profile_id)
            """),
            {"uid": ups_id, "pid": pid},
        )
        return pid

    @staticmethod
    def _replace_oids_for_profile(db: Session, profile_id: int, key_map: Dict[str, List[str]]) -> Dict[str, int]:
        summary: Dict[str, int] = {}
        for oid_key, oids in key_map.items():
            db.execute(
                text("DELETE FROM snmp_profile_oid WHERE profile_id=:pid AND oid_key=:k"),
                {"pid": profile_id, "k": oid_key},
            )
            pr = 1
            for oid in oids:
                db.execute(
                    text("""
                        INSERT INTO snmp_profile_oid (profile_id, oid_key, oid, priority)
                        VALUES (:pid, :k, :oid, :p)
                    """),
                    {"pid": profile_id, "k": oid_key, "oid": oid, "p": pr},
                )
                pr += 1
            summary[oid_key] = len(oids)
        return summary

    # ---------- public (ตาม requirement ใหม่) ----------
    def create_device(self, db: Session, *, ip: str, brand: Optional[str], model: Optional[str],
                      location: Optional[str], profile_name: Optional[str]) -> dict:
        dev = self._create_device(db, ip, brand=brand, model=model, location=location, profile_name=profile_name)
        # คืน info เบื้องต้น
        row = db.execute(text("SELECT profile_id FROM ups_device_profile WHERE ups_id=:uid"), {"uid": dev.id}).first()
        pid = int(row[0]) if row else None
        return {
            "ups_id": dev.id,
            "ip": dev.ip_address,
            "profile_id": pid,
            "device": {
                "brand": dev.brand,
                "model": dev.model,
                "location": dev.location,
                "is_active": dev.is_active,
            },
        }

    def create_device_with_oids(self, db: Session, *, ip: str, brand: Optional[str], model: Optional[str],
                                location: Optional[str], profile_name: Optional[str],
                                data: Dict[str, Union[str, List[str]]]) -> dict:
        key_map = self._normalize_oids_map(data)
        if not key_map:
            raise ValueError("data ว่าง")

        dev = self._create_device(db, ip, brand=brand, model=model, location=location, profile_name=profile_name)
        pid = self._ensure_profile_for_device(db, dev.id, profile_name=profile_name)
        summary = self._replace_oids_for_profile(db, pid, key_map)

        return {
            "ups_id": dev.id,
            "ip": ip,
            "profile_id": pid,
            "upserted_keys": summary,
        }

    def update_device(self, db: Session, ups_id: int, *, brand: Optional[str], model: Optional[str],
                      location: Optional[str], is_active: Optional[bool]) -> dict:
        dev = db.query(UPSDevice).filter(UPSDevice.id == ups_id).first()
        if not dev:
            raise LookupError(f"ไม่พบ UPS id={ups_id}")

        changed = False
        if brand is not None and dev.brand != brand:
            dev.brand = brand; changed = True
        if model is not None and dev.model != model:
            dev.model = model; changed = True
        if location is not None and dev.location != location:
            dev.location = location; changed = True
        if is_active is not None and dev.is_active != is_active:
            dev.is_active = is_active; changed = True

        if changed:
            db.flush()

        return {
            "ups_id": dev.id,
            "ip": dev.ip_address,
            "device": {
                "brand": dev.brand,
                "model": dev.model,
                "location": dev.location,
                "is_active": dev.is_active,
            },
        }

    def delete_device(self, db: Session, ups_id: int, *, delete_profile: bool = True) -> dict:
        # จำโปรไฟล์ที่ผูก
        prof_row = db.execute(
            text("SELECT profile_id FROM ups_device_profile WHERE ups_id=:uid LIMIT 1"),
            {"uid": ups_id},
        ).first()
        profile_id = int(prof_row[0]) if prof_row else None
        profile_name = None
        if profile_id:
            r2 = db.execute(text("SELECT name FROM snmp_profile WHERE id=:pid"), {"pid": profile_id}).first()
            profile_name = r2[0] if r2 else None

        # เคลียข้อมูลลูกก่อนลบเครื่อง (กัน FK)
        # ups_reading → (input/output/load/battery) จะโดน ON DELETE CASCADE จาก reading
        db.execute(text("DELETE FROM ups_reading WHERE ups_id=:uid"), {"uid": ups_id})
        db.execute(text("DELETE FROM ups_events WHERE ups_id=:uid"), {"uid": ups_id})
        db.execute(text("DELETE FROM ups_status_event WHERE ups_id=:uid"), {"uid": ups_id})
        db.execute(text("DELETE FROM ups_history WHERE ups_id=:uid"), {"uid": ups_id})
        db.execute(text("DELETE FROM ups_device_profile WHERE ups_id=:uid"), {"uid": ups_id})

        # ลบ device
        res = db.execute(text("DELETE FROM ups_devices WHERE id=:uid"), {"uid": ups_id})
        deleted = res.rowcount or 0

        # ถ้าให้ลบโปรไฟล์ และโปรไฟล์ไม่ถูกใช้ที่อื่น และชื่อขึ้นต้น CUSTOM_
        if delete_profile and profile_id:
            cnt = db.execute(
                text("SELECT COUNT(*) FROM ups_device_profile WHERE profile_id=:pid"),
                {"pid": profile_id},
            ).scalar()
            if (cnt == 0) and profile_name and profile_name.startswith("CUSTOM_"):
                # ลบโปรไฟล์ (snmp_profile_oid จะโดน FK CASCADE)
                db.execute(text("DELETE FROM snmp_profile WHERE id=:pid"), {"pid": profile_id})

        return {"deleted": deleted, "profile_deleted": bool(delete_profile and profile_id and profile_name and profile_name.startswith("CUSTOM_"))}

    # ยังเก็บตัวดู OIDs ได้ (ใช้ในหน้า config)
    def get_oids_for_device_by_ip(self, db: Session, ip: str) -> dict:
        dev = db.query(UPSDevice).filter(UPSDevice.ip_address == ip).first()
        if not dev:
            raise LookupError(f"ไม่พบ UPS ip={ip}")

        row = db.execute(
            text("SELECT profile_id FROM ups_device_profile WHERE ups_id=:uid LIMIT 1"),
            {"uid": dev.id},
        ).first()
        if not row:
            return {"ip": ip, "ups_id": dev.id, "profile_id": None, "oids": {}}

        pid = int(row[0])
        rows = db.execute(
            text("""
                SELECT oid_key, oid, priority
                FROM snmp_profile_oid
                WHERE profile_id=:pid
                ORDER BY oid_key ASC, priority ASC
            """),
            {"pid": pid},
        ).mappings().all()

        out: Dict[str, List[str]] = {}
        for r in rows:
            out.setdefault(r["oid_key"], []).append(r["oid"])

        return {"ip": ip, "ups_id": dev.id, "profile_id": pid, "oids": out}

snmp_service = SNMPService()

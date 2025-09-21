from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import text
from sqlalchemy.orm import Session

from model.model import UPSDevice


class SNMPService:
    """
    Service จัดการอุปกรณ์ UPS + โปรไฟล์ SNMP + OIDs

    - PK ของ ups_devices คือสตริง (เช่น 'UPS_10_40_1_10')
    - ช่วยสร้าง ups_id จาก IP และกันซ้ำด้วย suffix __2, __3, ...
    - สร้าง/ผูกโปรไฟล์ 'CUSTOM_<ups_id>' ให้เครื่องโดยอัตโนมัติเมื่อต้องการ
    - ใส่/แทนที่ OIDs ให้โปรไฟล์ โดย auto-seed snmp_oid_key ถ้ายังไม่มี (group_name='misc')
    - ดึง config แบบ merged: STANDARD (base) + โปรไฟล์ของเครื่อง (ทับ base)
    """

    # ---------- helpers (ทั่วไป) ----------
    _IP_RE = re.compile(
        r"^(?:(?:25[0-5]|2[0-4]\d|1?\d{1,2})\.){3}(?:25[0-5]|2[0-4]\d|1?\d{1,2})$"
    )

    @staticmethod
    def _ip_to_id(ip: str) -> str:
        """'10.40.1.10' -> 'UPS_10_40_1_10'"""
        if not ip or not SNMPService._IP_RE.match(ip):
            raise ValueError(f"invalid IPv4: {ip}")
        return "UPS_" + ip.strip().replace(".", "_")

    @staticmethod
    def _ensure_unique_device_id(db: Session, base_id: str) -> str:
        """ถ้า id ซ้ำ เติม __2, __3, ..."""
        row = db.execute(
            text("SELECT 1 FROM ups_devices WHERE id=:id LIMIT 1"), {"id": base_id}
        ).first()
        if not row:
            return base_id
        i = 2
        while True:
            cand = f"{base_id}__{i}"
            r2 = db.execute(
                text("SELECT 1 FROM ups_devices WHERE id=:id LIMIT 1"), {"id": cand}
            ).first()
            if not r2:
                return cand
            i += 1

    @staticmethod
    def _normalize_oids_map(
        data: Dict[str, Union[str, List[str]]]
    ) -> Dict[str, List[str]]:
        """
        รับ payload data ที่อาจเป็น str หรือ list แล้ว normalize เป็น {key: [oid,...]}
        ตัดค่าว่าง/trim ให้อัตโนมัติ
        """
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

    # ---------- helpers (โปรไฟล์/OIDs) ----------
    @staticmethod
    def _profile_id_by_name(db: Session, name: str) -> Optional[int]:
        row = db.execute(
            text("SELECT id FROM snmp_profile WHERE name=:n LIMIT 1"), {"n": name}
        ).first()
        return int(row[0]) if row else None

    @staticmethod
    def _guess_profile_id(
        db: Session, brand: Optional[str], model: Optional[str]
    ) -> Optional[int]:
        """
        เดาโปรไฟล์จาก vendor/model ในตาราง snmp_profile
        ลำดับ: vendor+model > model only > vendor only
        """
        if brand and model:
            r = db.execute(
                text("SELECT id FROM snmp_profile WHERE vendor=:v AND model=:m LIMIT 1"),
                {"v": brand, "m": model},
            ).first()
            if r:
                return int(r[0])
        if model:
            r = db.execute(
                text("SELECT id FROM snmp_profile WHERE model=:m LIMIT 1"),
                {"m": model},
            ).first()
            if r:
                return int(r[0])
        if brand:
            r = db.execute(
                text("SELECT id FROM snmp_profile WHERE vendor=:v LIMIT 1"),
                {"v": brand},
            ).first()
            if r:
                return int(r[0])
        return None

    @staticmethod
    def _oids_map_for_profile(db: Session, profile_id: int) -> Dict[str, str]:
        """
        คืน dict: {oid_key: oid} โดยเลือก OID ตัวที่ priority ต่ำสุด (เช่น 1) ต่อคีย์
        """
        rows = db.execute(
            text(
                """
                SELECT oid_key, oid, priority
                FROM snmp_profile_oid
                WHERE profile_id=:pid
                ORDER BY oid_key ASC, priority ASC
                """
            ),
            {"pid": profile_id},
        ).mappings().all()

        top: Dict[str, str] = {}
        for r in rows:
            k = r["oid_key"]
            if k not in top:  # เจอตัวแรกของคีย์ = priority ต่ำสุด
                top[k] = r["oid"]
        return top

    def _replace_oids_for_profile(
        self, db: Session, profile_id: int, key_map: Dict[str, List[str]]
    ) -> Dict[str, int]:
        """
        แทนที่ OIDs ทั้งชุดสำหรับ profile_id ตาม key_map
        - auto-seed snmp_oid_key ถ้ายังไม่มี (group_name='misc')
        - ลบของเก่าของคีย์นั้นทั้งหมด แล้วใส่ใหม่ตาม priority 1..n
        """
        summary: Dict[str, int] = {}
        for oid_key, oids in key_map.items():
            # auto-seed คีย์ใน snmp_oid_key
            db.execute(
                text(
                    """
                    INSERT IGNORE INTO snmp_oid_key (oid_key, group_name, unit, scale_key, description)
                    VALUES (:k, 'misc', NULL, NULL, 'auto-seeded')
                    """
                ),
                {"k": oid_key},
            )

            # เคลียร์ของเก่าของ key นี้ก่อน
            db.execute(
                text(
                    "DELETE FROM snmp_profile_oid WHERE profile_id=:pid AND oid_key=:k"
                ),
                {"pid": profile_id, "k": oid_key},
            )

            pr = 1
            for oid in oids:
                db.execute(
                    text(
                        """
                        INSERT INTO snmp_profile_oid (profile_id, oid_key, oid, priority)
                        VALUES (:pid, :k, :oid, :p)
                        """
                    ),
                    {"pid": profile_id, "k": oid_key, "oid": oid, "p": pr},
                )
                pr += 1

            summary[oid_key] = len(oids)

        return summary

    def _ensure_profile_for_device(
        self, db: Session, ups_id: str, profile_name: Optional[str] = None
    ) -> int:
        """
        สร้าง/หาโปรไฟล์ แล้วผูกลง ups_device_profile (UPS -> profile)
        ชื่อเริ่มต้น: CUSTOM_<ups_id>
        """
        name = profile_name or f"CUSTOM_{ups_id}"
        row = db.execute(
            text("SELECT id FROM snmp_profile WHERE name=:n LIMIT 1"), {"n": name}
        ).first()
        if row:
            pid = int(row[0])
        else:
            db.execute(
                text(
                    "INSERT INTO snmp_profile (name, vendor, model, notes) "
                    "VALUES (:n, NULL, NULL, :notes)"
                ),
                {"n": name, "notes": "Auto-created per-device profile"},
            )
            pid = int(db.execute(text("SELECT LAST_INSERT_ID()")).scalar())

        db.execute(
            text(
                """
                INSERT INTO ups_device_profile (ups_id, profile_id)
                VALUES (:uid, :pid)
                ON DUPLICATE KEY UPDATE profile_id = VALUES(profile_id)
                """
            ),
            {"uid": ups_id, "pid": pid},
        )
        return pid

    # ---------- public: attach/create profile (+ optional OIDs) ----------
    def ensure_profile_for_device(
        self,
        db: Session,
        ups_id: str,
        *,
        profile_id: Optional[int] = None,
        profile_name: Optional[str] = None,
        vendor: Optional[str] = None,
        model: Optional[str] = None,
        notes: Optional[str] = None,
        oids: Optional[Dict[str, Union[str, List[str]]]] = None,
    ) -> int:
        """
        แนบโปรไฟล์เข้ากับ UPS ถ้าไม่มีโปรไฟล์ให้สร้างได้ และอัปเดต OIDs ได้ในคราวเดียว
        ใช้ร่วมกับ endpoint: POST /devices/{ups_id}/ensure-profile
        body ส่ง profile_id หรือ profile_name (พร้อม meta/oids ได้)
        """
        dev = db.query(UPSDevice).filter(UPSDevice.id == ups_id).first()
        if not dev:
            raise LookupError(f"ไม่พบ UPS id={ups_id}")

        # 1) หา/สร้าง profile_id
        pid: Optional[int] = None

        if profile_id is not None:
            row = db.execute(
                text("SELECT id FROM snmp_profile WHERE id=:pid LIMIT 1"),
                {"pid": profile_id},
            ).first()
            if not row:
                raise LookupError(f"ไม่พบโปรไฟล์ id={profile_id}")
            pid = int(row[0])
        else:
            name = profile_name or f"CUSTOM_{ups_id}"
            row = db.execute(
                text("SELECT id FROM snmp_profile WHERE name=:n LIMIT 1"),
                {"n": name},
            ).first()
            if row:
                pid = int(row[0])
                # อัปเดต meta หากส่งมา
                if any([vendor is not None, model is not None, notes is not None]):
                    db.execute(
                        text(
                            """
                            UPDATE snmp_profile
                               SET vendor = COALESCE(:vendor, vendor),
                                   model  = COALESCE(:model,  model),
                                   notes  = COALESCE(:notes,  notes)
                             WHERE id = :pid
                            """
                        ),
                        {"vendor": vendor, "model": model, "notes": notes, "pid": pid},
                    )
            else:
                # สร้างใหม่
                db.execute(
                    text(
                        """
                        INSERT INTO snmp_profile (name, vendor, model, notes)
                        VALUES (:n, :vendor, :model, :notes)
                        """
                    ),
                    {"n": name, "vendor": vendor, "model": model, "notes": notes},
                )
                pid = int(db.execute(text("SELECT LAST_INSERT_ID()")).scalar())

        assert pid is not None

        # 2) ผูกโปรไฟล์กับ UPS (upsert)
        db.execute(
            text(
                """
                INSERT INTO ups_device_profile (ups_id, profile_id)
                VALUES (:uid, :pid)
                ON DUPLICATE KEY UPDATE profile_id = VALUES(profile_id)
                """
            ),
            {"uid": ups_id, "pid": pid},
        )

        # 3) ถ้ามี oids -> upsert ลง snmp_profile_oid
        if oids:
            key_map = self._normalize_oids_map(oids)
            if key_map:
                self._replace_oids_for_profile(db, pid, key_map)

        return pid

    # ---------- device creation (UPS_ID จาก IP) ----------
    def _create_device(
        self,
        db: Session,
        ip: str,
        *,
        brand: Optional[str],
        model: Optional[str],
        location: Optional[str],
        profile_name: Optional[str],
    ) -> UPSDevice:
        """
        สร้างอุปกรณ์ใหม่เท่านั้น (กัน IP ซ้ำ)
        - สร้าง ups_id จาก IP
        - กำหนด PK = ups_id (string)
        - capacity_va/w = 0
        - ผูก/สร้างโปรไฟล์เริ่มต้น
        """
        exist = db.query(UPSDevice).filter(UPSDevice.ip_address == ip).first()
        if exist:
            raise ValueError(f"UPS ip={ip} มีอยู่แล้ว")

        base_id = self._ip_to_id(ip)
        ups_id = self._ensure_unique_device_id(db, base_id)

        dev = UPSDevice(
            id=ups_id,
            ip_address=ip,
            brand=(brand or "Unknown"),
            model=(model or "Unknown"),
            location=(location or "-"),
            capacity_va=0,
            capacity_w=0,
            is_active=True,
        )
        db.add(dev)
        db.flush()  # dev.id จะเป็นสตริง ups_id

        # ผูก/สร้างโปรไฟล์เริ่มต้น
        self._ensure_profile_for_device(db, dev.id, profile_name=profile_name)
        return dev

    # ---------- public CRUD ----------
    def create_device(
        self,
        db: Session,
        *,
        ip: str,
        brand: Optional[str],
        model: Optional[str],
        location: Optional[str],
        profile_name: Optional[str],
    ) -> dict:
        dev = self._create_device(
            db, ip, brand=brand, model=model, location=location, profile_name=profile_name
        )
        row = db.execute(
            text("SELECT profile_id FROM ups_device_profile WHERE ups_id=:uid"),
            {"uid": dev.id},
        ).first()
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

    def create_device_with_oids(
        self,
        db: Session,
        *,
        ip: str,
        brand: Optional[str],
        model: Optional[str],
        location: Optional[str],
        profile_name: Optional[str],
        data: Dict[str, Union[str, List[str]]],
    ) -> dict:
        key_map = self._normalize_oids_map(data)
        if not key_map:
            raise ValueError("data ว่าง")

        dev = self._create_device(
            db, ip, brand=brand, model=model, location=location, profile_name=profile_name
        )
        pid = self._ensure_profile_for_device(db, dev.id, profile_name=profile_name)
        summary = self._replace_oids_for_profile(db, pid, key_map)

        return {
            "ups_id": dev.id,
            "ip": ip,
            "profile_id": pid,
            "upserted_keys": summary,
        }

    def update_device(
        self,
        db: Session,
        ups_id: str,
        *,
        brand: Optional[str],
        model: Optional[str],
        location: Optional[str],
        is_active: Optional[bool],
        data: Optional[Dict[str, Union[str, List[str]]]] = None,
        profile_name: Optional[str] = None,
    ) -> dict:
        dev = db.query(UPSDevice).filter(UPSDevice.id == ups_id).first()
        if not dev:
            raise LookupError(f"ไม่พบ UPS id={ups_id}")

        changed = False
        if brand is not None and dev.brand != brand:
            dev.brand = brand
            changed = True
        if model is not None and dev.model != model:
            dev.model = model
            changed = True
        if location is not None and dev.location != location:
            dev.location = location
            changed = True
        if is_active is not None and dev.is_active != is_active:
            dev.is_active = is_active
            changed = True

        if changed:
            db.flush()

        # ----- อัปเดต OIDs -----
        if data is not None:
            key_map = self._normalize_oids_map(data)
            if key_map:
                pid = self._ensure_profile_for_device(db, ups_id, profile_name=profile_name)
                self._replace_oids_for_profile(db, pid, key_map)

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

    def delete_device(
        self, db: Session, ups_id: str, *, delete_profile: bool = True
    ) -> Dict[str, Union[str, int, bool]]:
        prof_row = db.execute(
            text("SELECT profile_id FROM ups_device_profile WHERE ups_id=:uid LIMIT 1"),
            {"uid": ups_id},
        ).first()
        profile_id: Optional[int] = (
            int(prof_row[0]) if prof_row and prof_row[0] is not None else None
        )

        profile_name: Optional[str] = None
        if profile_id is not None:
            r2 = db.execute(
                text("SELECT name FROM snmp_profile WHERE id=:pid"), {"pid": profile_id}
            ).first()
            profile_name = r2[0] if r2 else None

        # ลบตารางลูก (สำคัญ: รวม ups_status)
        db.execute(text("DELETE FROM ups_reading        WHERE ups_id=:uid"), {"uid": ups_id})
        db.execute(text("DELETE FROM ups_events         WHERE ups_id=:uid"), {"uid": ups_id})
        db.execute(text("DELETE FROM ups_status_event   WHERE ups_id=:uid"), {"uid": ups_id})
        db.execute(text("DELETE FROM ups_history        WHERE ups_id=:uid"), {"uid": ups_id})
        db.execute(text("DELETE FROM ups_status         WHERE ups_id=:uid"), {"uid": ups_id})
        db.execute(text("DELETE FROM ups_device_profile WHERE ups_id=:uid"), {"uid": ups_id})

        # ลบ parent
        res = db.execute(text("DELETE FROM ups_devices WHERE id=:uid"), {"uid": ups_id})
        deleted = res.rowcount or 0

        # ลบโปรไฟล์ถ้า CUSTOM_ และไม่ถูกใช้อยู่
        profile_deleted = False
        if delete_profile and profile_id is not None:
            cnt = db.execute(
                text("SELECT COUNT(*) FROM ups_device_profile WHERE profile_id=:pid"),
                {"pid": profile_id},
            ).scalar() or 0
            if cnt == 0 and profile_name and profile_name.startswith("CUSTOM_"):
                db.execute(text("DELETE FROM snmp_profile WHERE id=:pid"), {"pid": profile_id})
                profile_deleted = True

        return {"ups_id": ups_id, "deleted": deleted, "profile_deleted": profile_deleted}

    # ---------- read: OIDs by IP (optionally auto-create profile binding) ----------
    def get_oids_for_device_by_ip(
        self,
        db: Session,
        ip: str,
        *,
        auto_create_profile: bool = False,
    ) -> dict:
        """
        คืน {ip, ups_id, profile_id, oids:{...}}
        - ถ้า auto_create_profile=True และยังไม่ผูกโปรไฟล์ -> จะสร้าง/ผูกให้ทันที (แต่ยังไม่ใส่ OIDs)
        """
        # หาอุปกรณ์ตาม IP
        dev = db.query(UPSDevice).filter(UPSDevice.ip_address == ip).first()
        if not dev:
            raise LookupError(f"ไม่พบ UPS ip={ip}")

        # หาโปรไฟล์ที่ผูกอยู่
        row = db.execute(
            text("SELECT profile_id FROM ups_device_profile WHERE ups_id=:uid LIMIT 1"),
            {"uid": dev.id},
        ).first()

        # ยังไม่มีโปรไฟล์
        if not row:
            if auto_create_profile:
                pid = self._ensure_profile_for_device(db, dev.id, profile_name=None)
                return {"ip": ip, "ups_id": dev.id, "profile_id": pid, "oids": {}}
            return {"ip": ip, "ups_id": dev.id, "profile_id": None, "oids": {}}

        # มีโปรไฟล์แล้ว -> ดึง OIDs ทั้งหมดเรียงตาม priority
        pid = int(row[0])
        rows = db.execute(
            text(
                """
                SELECT oid_key, oid, priority
                FROM snmp_profile_oid
                WHERE profile_id=:pid
                ORDER BY oid_key ASC, priority ASC
                """
            ),
            {"pid": pid},
        ).mappings().all()

        oids: Dict[str, List[str]] = {}
        for r in rows:
            oids.setdefault(r["oid_key"], []).append(r["oid"])

        return {"ip": ip, "ups_id": dev.id, "profile_id": pid, "oids": oids}

    # ---------- merged config: STANDARD + โปรไฟล์เครื่อง (หรือ override/guess) ----------
    def get_device_config_map(
        self,
        db: Session,
        *,
        ips: Optional[List[str]] = None,
        base_profile_name: str = "STANDARD",
        override_profile_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        คืน mapping: { ip: {brand, model, location, oids: merged} }
        merged = STANDARD (base) + โปรไฟล์ของเครื่อง (ทับ base)
        ถ้าเครื่องยังไม่ผูกโปรไฟล์ -> จะลอง override_profile_name ก่อน, ไม่งั้นเดาจาก brand/model
        """
        # base OIDs (STANDARD)
        base_pid = self._profile_id_by_name(db, base_profile_name)
        base_map: Dict[str, str] = (
            self._oids_map_for_profile(db, base_pid) if base_pid else {}
        )

        # รายการเครื่อง
        q = db.query(UPSDevice)
        if ips:
            q = q.filter(UPSDevice.ip_address.in_(ips))
        devs = q.all()

        out: Dict[str, Any] = {}
        for d in devs:
            # โปรไฟล์ที่ผูกไว้จริง
            row = db.execute(
                text("SELECT profile_id FROM ups_device_profile WHERE ups_id=:uid LIMIT 1"),
                {"uid": d.id},
            ).first()

            prof_map: Dict[str, str] = {}
            pid: Optional[int] = int(row[0]) if row and row[0] is not None else None

            if pid:
                prof_map = self._oids_map_for_profile(db, pid)
            else:
                # ถ้ายังไม่ผูก: ลอง override ชื่อโปรไฟล์ก่อน, ไม่งั้นเดาตาม brand/model
                if override_profile_name:
                    pid = self._profile_id_by_name(db, override_profile_name)
                if not pid:
                    pid = self._guess_profile_id(db, d.brand, d.model)
                if pid:
                    prof_map = self._oids_map_for_profile(db, pid)

            merged = {**base_map, **prof_map}  # โปรไฟล์เครื่องทับ STANDARD

            out[d.ip_address] = {
                "brand": d.brand,
                "model": d.model,
                "location": d.location,
                "oids": merged,
            }
        return out

    def get_single_device_config(
        self,
        db: Session,
        *,
        ip: str,
        base_profile_name: str = "STANDARD",
        override_profile_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """ดึง config สำหรับ IP เดียว"""
        m = self.get_device_config_map(
            db,
            ips=[ip],
            base_profile_name=base_profile_name,
            override_profile_name=override_profile_name,
        )
        if ip not in m:
            raise LookupError(f"ไม่พบอุปกรณ์ IP {ip}")
        return m[ip]


snmp_service = SNMPService()

# app/services/ups_service.py
from __future__ import annotations

from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, Future, TimeoutError as FuturesTimeout
import time
import random
import os
import re

from app.services.snmp_client import snmp_client
from app.api.routes.data_utils import OIDResolver, DataProcessor
from app.services.ups_cache import ups_cache
from app.services.ups_repo import UPSRepository


# ---------- helpers ----------
def _derive_id(ip: str) -> str:
    """ให้รูปแบบ id แบบตัวอย่าง: UPS_10_40_1_10"""
    return f"UPS_{ip.replace('.', '_')}"

def _ip_key(ip: str) -> Tuple[int, int, int, int]:
    """ช่วยเรียง IP เป็นตัวเลขจริง"""
    try:
        a, b, c, d = ip.split(".")
        return (int(a), int(b), int(c), int(d))
    except Exception:
        return (999, 999, 999, 999)

def _human_status(payload: Dict[str, Any]) -> str:
    """
    นิยามสถานะให้มนุษย์อ่าน:
      - Offline    : output รวมเป็น 0
      - Powerfail  : output > 0 แต่ input รวมเป็น 0 (ไฟขาเข้าไม่มี แต่ยังจ่ายจากแบต/บายพาส)
      - Online     : input > 0 และ output > 0
    """
    try:
        i = payload.get("input", {}) or {}
        o = payload.get("output", {}) or {}
        in_sum = int(i.get("L1V") or 0) + int(i.get("L2V") or 0) + int(i.get("L3V") or 0)
        out_sum = int(o.get("L1V") or 0) + int(o.get("L2V") or 0) + int(o.get("L3V") or 0)
        if out_sum <= 0:
            return "Offline"
        if in_sum <= 0 and out_sum > 0:
            return "Powerfail"
        return "Online"
    except Exception:
        # ถ้าคำนวณไม่ได้ ให้ถือว่า Online เพื่อไม่เตะระบบ
        return "Online"

def _blank_identity_fields(rec: Dict[str, Any]) -> None:
    """บังคับให้ brand/model/location เป็น string ว่าง"""
    rec["brand"] = ""
    rec["model"] = ""
    rec["location"] = ""


# ---------- frequency normalizer (Hz) ----------
_ARITH_SAFE = re.compile(r"^[\d\.\s\+\-\*\/\(\)]+$")

def _eval_number_string(s: str) -> Optional[float]:
    """
    รองรับสตริงตัวเลขง่าย ๆ ที่มีเครื่องหมายคำนวณ เช่น '500/10', '50.1'
    ป้องกันด้วย whitelist ของอักขระที่ยอมรับ
    """
    s = s.strip()
    if not _ARITH_SAFE.match(s):
        return None
    try:
        return float(eval(s, {"__builtins__": {}}, {}))
    except Exception:
        return None

def _to_number(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and v.strip() != "":
        try:
            return float(v.strip())
        except Exception:
            return _eval_number_string(v)
    return None

def _norm_freq_hz(v: Any) -> Optional[float]:
    """
    แปลงความถี่ให้เป็นเฮิร์ตซ์ (Hz) เสมอ:
    - ถ้าได้ deci-Hz (ค่าประมาณ >= 100) ให้หาร 10
    - ถ้าได้ Hz อยู่แล้ว (ช่วง ~45–65) คืนตามเดิม
    - รองรับสตริงแบบ '500/10'
    - 0 หรือติดลบ -> None
    """
    x = _to_number(v)
    if x is None:
        return None
    if x <= 0:
        return None
    hz = x / 10.0 if x >= 100 else x
    if hz > 1000:  # กันค่าผิดปกติ
        return None
    return round(hz, 2)


class UPSService:
    """
    Service สำหรับดึง/ประมวลผลข้อมูล UPS ผ่าน SNMP และรวมผลแบบขนาน
      - get_ups_data(ip, ...)         : ดึงเครื่องเดียว (มี cache)
      - get_all_ups_data(...)         : ดึงทุกเครื่องแบบ ThreadPool + per-host timeout
      - get_device_list()             : รายชื่อเครื่อง (จาก DB)
      - clear_cache() / remove_from_cache(ip)
    """

    def __init__(self, repo: Optional[UPSRepository] = None, max_workers: int = 10):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.repo = repo or UPSRepository()

        # ค่าเริ่มต้นจาก .env (ถ้าไม่มี ให้ใช้ค่าภายใน)
        env_defaults = {
            "timeout": float(os.getenv("UPS_TIMEOUT", "2.0")),
            "retries": int(os.getenv("UPS_RETRIES", "1")),
            "cache_ttl": float(os.getenv("UPS_CACHE_TTL", "5.0")),
            "community": os.getenv("UPS_SNMP_COMMUNITY", "public"),
            "snmp_version": os.getenv("UPS_SNMP_VERSION", "2c"),
        }

        # ถ้า repo มี method สำหรับ defaults ก็อนุญาตให้ override
        repo_defaults: Dict[str, Any] = {}
        if hasattr(self.repo, "get_system_defaults"):
            try:
                repo_defaults = self.repo.get_system_defaults() or {}
            except Exception:
                repo_defaults = {}

        # repo ทับ env ถ้าซ้ำ key
        self.defaults = {**env_defaults, **repo_defaults}

    # -------- public --------
    def get_ups_data(
        self,
        ip: str,
        timeout: Optional[float] = None,
        retries: Optional[int] = None,
        use_cache: bool = True,
        cache_ttl: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        ดึงค่า SNMP + ประมวลผลเป็น payload พร้อมใช้งาน
        คืนโครงสร้างทรงเดียวกับตัวอย่างในโจทย์
        """
        # 1) ตรวจอุปกรณ์จาก DB
        dev = self.repo.get_device_by_ip(ip)
        if not dev:
            resp = {
                "id": _derive_id(ip),
                "ip": ip,
                "status": "error",
                "error": f"No device found for ip={ip}",
            }
            _blank_identity_fields(resp)
            return resp
        ups_db_id: str = dev["id"]
        if not dev.get("is_active", 1):
            resp = {
                "id": _derive_id(ip),
                "ip": ip,
                "status": "error",
                "error": "Device is not active",
            }
            _blank_identity_fields(resp)
            return resp

        # 2) ตั้งค่าพื้นฐาน
        timeout = float(timeout if timeout is not None else self.defaults["timeout"])
        retries = int(retries if retries is not None else self.defaults["retries"])
        cache_ttl = float(cache_ttl if cache_ttl is not None else self.defaults["cache_ttl"])
        community = self.defaults["community"]
        snmp_version = self.defaults["snmp_version"]

        # 3) cache (ต่อเครื่อง ตาม TTL)
        if use_cache:
            cached = ups_cache.get(ip, cache_ttl)
            if cached:
                return cached

        # 4) สร้าง OID config จาก profile ของเครื่อง
        profile_id = self.repo.get_profile_id_for_ups(ups_db_id)
        if not profile_id:
            resp = {
                "id": _derive_id(ip),
                "ip": ip,
                "status": "error",
                "error": f"No SNMP profile mapped for ups_id={ups_db_id}",
            }
            _blank_identity_fields(resp)
            return resp

        primary_oids, fallbacks, scale_key_map = self.repo.get_oids_for_profile(profile_id)
        oid_config = self._build_oid_config(primary_oids, fallbacks)

        # เตรียม OIDs ทั้งหมด
        resolver = OIDResolver(oid_config)
        all_oids = resolver.get_all_oids()

        # 4.5) กัน thundering herd เล็กน้อยเมื่อยิงพร้อมกันหลายตัว
        if retries > 0:
            time.sleep(random.uniform(0.0, 0.06))

        # 5) ยิง SNMP
        try:
            oid_values = snmp_client.get_multiple(
                ip=ip,
                community=community,
                oids=all_oids,
                timeout=timeout,
                retries=retries,
                version=snmp_version,
            )
        except Exception as e:
            resp = {
                "id": _derive_id(ip),
                "ip": ip,
                "status": "error",
                "error": f"SNMP error: {e}",
            }
            _blank_identity_fields(resp)
            return resp

        # 6) ประมวลผลผลลัพธ์
        device_config = {
            "id": ups_db_id,               # รหัสใน DB (ไม่แสดงออก UI ถ้าไม่ต้องการ)
            "ip": ip,
            # ค่าจาก DB อาจใช้ใน DataProcessor
            "brand": dev.get("brand"),
            "model": dev.get("model"),
            "location": dev.get("location"),
            "oids": oid_config,
            "scale_key_map": scale_key_map,  # สำหรับ DataProcessor ถ้ารองรับ scale
            "community": community,
            "snmp_version": snmp_version,
        }

        processor = DataProcessor(resolver)
        data = processor.process_ups_data(ip, oid_values, device_config)

        # --- ปรับความถี่ให้เป็น Hz เสมอ (รองรับค่า deci-Hz และนิพจน์) ---
        try:
            if isinstance(data.get("input"), dict):
                data["input"]["freqHz"] = _norm_freq_hz(data["input"].get("freqHz"))
            if isinstance(data.get("output"), dict):
                data["output"]["freqHz"] = _norm_freq_hz(data["output"].get("freqHz"))
        except Exception:
            # ไม่ให้กระทบข้อมูลอื่น ๆ ถ้า normalize พลาด
            pass

        # สร้าง payload ตามฟอร์แมตตัวอย่าง
        data["id"] = _derive_id(ip)         # ให้เป็น UPS_<ip>
        data["ip"] = ip
        data["brand"] = dev.get("brand")
        data["model"] = dev.get("model")
        data["location"] = dev.get("location")
        data["status"] = _human_status(data)
        data["collected_at"] = time.time()

        # 7) เก็บ cache
        if use_cache:
            ups_cache.set(ip, data)

        return data

    def get_all_ups_data(
        self,
        timeout: Optional[float] = None,
        retries: Optional[int] = None,
        use_cache: bool = True,
        cache_ttl: Optional[float] = None,
        per_host_timeout: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        ดึงทุกเครื่องแบบขนาน:
          - per_host_timeout (ถ้าไม่ส่ง) = (timeout หรือ default) * 1.5 + 2 วินาที
          - เรียงผลลัพธ์ตามค่า IP จริง
        """
        ips = self.repo.get_all_ips()
        if not ips:
            return []

        base_timeout = float(timeout if timeout is not None else self.defaults["timeout"])
        per_host_timeout = float(per_host_timeout if per_host_timeout is not None else base_timeout * 1.5 + 2.0)

        ips_to_poll = list(ips)
        random.shuffle(ips_to_poll)

        futures: List[Tuple[str, Future]] = []
        for ip in ips_to_poll:
            fut = self.executor.submit(self.get_ups_data, ip, timeout, retries, use_cache, cache_ttl)
            futures.append((ip, fut))

        out: List[Dict[str, Any]] = []
        for ip, fut in futures:
            try:
                out.append(fut.result(timeout=per_host_timeout))
            except FuturesTimeout:
                resp = {
                    "id": _derive_id(ip),
                    "ip": ip,
                    "status": "error",
                    "error": f"Future timeout (> {per_host_timeout:.2f}s)",
                }
                _blank_identity_fields(resp)
                out.append(resp)
            except Exception as e:
                resp = {
                    "id": _derive_id(ip),
                    "ip": ip,
                    "status": "error",
                    "error": f"Future error: {e}",
                }
                _blank_identity_fields(resp)
                out.append(resp)

        # เรียงตาม IP จริง
        out.sort(key=lambda r: _ip_key(r.get("ip", "")))
        return out

    def get_device_list(self) -> List[Dict[str, str]]:
        """รายชื่อเครื่อง (ip/brand/model/location) สำหรับแสดง dropdown/ตาราง"""
        ips = self.repo.get_all_ips()
        devices: List[Dict[str, str]] = []
        for ip in ips:
            dev = self.repo.get_device_by_ip(ip)
            if dev:
                devices.append({
                    "ip": dev["ip_address"],
                    "brand": dev.get("brand") or "Unknown",
                    "model": dev.get("model") or "Unknown",
                    "location": dev.get("location") or "Unknown",
                })
        devices.sort(key=lambda d: _ip_key(d["ip"]))
        return devices

    def clear_cache(self) -> None:
        ups_cache.clear()

    def remove_from_cache(self, ip: str) -> None:
        ups_cache.remove(ip)

    # -------- private --------
    def _build_oid_config(
        self,
        primary_oids: Dict[str, str],
        fallbacks: Dict[str, List[str]],
    ) -> Dict[str, Any]:
        """
        คืน dict สำหรับ OIDResolver:
          - ถ้ามี fallback -> เป็น list[str] โดย primary จะอยู่ตัวแรกเสมอ
          - ถ้าไม่มี -> เป็น str เดี่ยว
        """
        cfg: Dict[str, Any] = {}
        for k, primary in primary_oids.items():
            fb = list(fallbacks.get(k, [])) if fallbacks and k in fallbacks else []
            merged = [primary] + [x for x in fb if x != primary]
            cfg[k] = merged if len(merged) > 1 else primary
        return cfg


# singleton
ups_service = UPSService()

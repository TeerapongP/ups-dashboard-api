# app/api/routes/data_utils.py
from __future__ import annotations
from typing import Any, Dict, List, Union, Optional
import time

Number = Union[int, float]
OIDConfig = Dict[str, Union[str, List[str]]]

class OIDResolver:
    def __init__(self, oid_config: Optional[OIDConfig] = None):
        self.oid_config: OIDConfig = oid_config or {}

    def get_all_oids(self) -> List[str]:
        out: List[str] = []
        seen = set()
        for v in self.oid_config.values():
            if isinstance(v, str):
                if v and v not in seen:
                    seen.add(v); out.append(v)
            else:
                for oid in v:
                    if oid and oid not in seen:
                        seen.add(oid); out.append(oid)
        return out

    def pick_value(self, key: str, raw: Dict[str, Any]) -> Any:
        mapping = self.oid_config.get(key)
        if not mapping:
            return None
        if isinstance(mapping, str):
            return raw.get(mapping)
        for oid in mapping:
            val = raw.get(oid)
            if val not in (None, "", "NULL"):
                return val
        return None


class DataProcessor:
    def __init__(self, resolver: OIDResolver,
                 scale_map: Optional[Dict[str, str]] = None,
                 scale_factors: Optional[Dict[str, Number]] = None):
        self.resolver = resolver
        self.scale_key_map = scale_map or {}
        self.scale_factors = scale_factors or {}

    def _scale(self, key: str, value: Any) -> Any:
        if value is None:
            return None
        skey = self.scale_key_map.get(key)
        factor = float(self.scale_factors.get(skey, 1.0)) if skey else 1.0
        try:
            return float(value) * factor
        except Exception:
            return value

    @staticmethod
    def _as_int(v: Any) -> Optional[int]:
        if v is None or v == "":
            return None
        try:
            return int(round(float(v)))
        except Exception:
            return None

    def process_ups_data(self, ip: str, raw: Dict[str, Any], device_config: Dict[str, Any]) -> Dict[str, Any]:
        # ดึงค่าที่ต้องใช้ตามตัวอย่าง
        bp   = self._as_int(self._scale("battery_percent",     self.resolver.pick_value("battery_percent",     raw)))
        bvdc = self._as_int(self._scale("battery_vdc",         self.resolver.pick_value("battery_vdc",         raw)))
        brtm = self._as_int(self._scale("battery_runtime_min", self.resolver.pick_value("battery_runtime_min", raw)))
        temp = self._as_int(self._scale("temperature_C",       self.resolver.pick_value("temperature_C",       raw)))

        in_l1v = self._as_int(self._scale("input_L1_V",  self.resolver.pick_value("input_L1_V",  raw)))
        in_l2v = self._as_int(self._scale("input_L2_V",  self.resolver.pick_value("input_L2_V",  raw)))
        in_l3v = self._as_int(self._scale("input_L3_V",  self.resolver.pick_value("input_L3_V",  raw)))
        in_l1a = self._as_int(self._scale("input_L1_A",  self.resolver.pick_value("input_L1_A",  raw)))
        in_l2a = self._as_int(self._scale("input_L2_A",  self.resolver.pick_value("input_L2_A",  raw)))
        in_l3a = self._as_int(self._scale("input_L3_A",  self.resolver.pick_value("input_L3_A",  raw)))
        in_f   = self._as_int(self._scale("input_freq_Hz", self.resolver.pick_value("input_freq_Hz", raw)))

        out_l1v = self._as_int(self._scale("output_L1_V", self.resolver.pick_value("output_L1_V", raw)))
        out_l2v = self._as_int(self._scale("output_L2_V", self.resolver.pick_value("output_L2_V", raw)))
        out_l3v = self._as_int(self._scale("output_L3_V", self.resolver.pick_value("output_L3_V", raw)))
        out_l1a = self._as_int(self._scale("output_L1_A", self.resolver.pick_value("output_L1_A", raw)))
        out_l2a = self._as_int(self._scale("output_L2_A", self.resolver.pick_value("output_L2_A", raw)))
        out_l3a = self._as_int(self._scale("output_L3_A", self.resolver.pick_value("output_L3_A", raw)))
        out_f   = self._as_int(self._scale("output_freq_Hz", self.resolver.pick_value("output_freq_Hz", raw)))

        load_va = self._as_int(self._scale("load_VA", self.resolver.pick_value("load_VA", raw)))
        load_w  = self._as_int(self._scale("load_W",  self.resolver.pick_value("load_W",  raw)))

        # คืนรูปแบบตรงตัวอย่าง (status จะให้ UPSService คำนวน)
        return {
            "ip": ip,
            "brand":    device_config.get("brand"),
            "model":    device_config.get("model"),
            "location": device_config.get("location"),
            "batteryPercent":  bp if bp is not None else 0,
            "batteryVDC":      bvdc if bvdc is not None else 0,
            "backupTimeMin":   brtm if brtm is not None else 0,
            "temperatureC":    temp if temp is not None else 0,
            "input": {
                "L1V": in_l1v or 0, "L2V": in_l2v or 0, "L3V": in_l3v or 0,
                "L1A": in_l1a or 0, "L2A": in_l2a or 0, "L3A": in_l3a or 0,
                "freqHz": in_f or 0,
            },
            "output": {
                "L1V": out_l1v or 0, "L2V": out_l2v or 0, "L3V": out_l3v or 0,
                "L1A": out_l1a or 0, "L2A": out_l2a or 0, "L3A": out_l3a or 0,
                "freqHz": out_f or 0,
            },
            "loadVA": load_va or 0,
            "loadW":  load_w or 0,
            "collected_at": time.time(),
        }

# main.py
from fastapi import FastAPI, HTTPException, Query
from typing import Dict, Any, Optional, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from pysnmp.hlapi import (
    getCmd,
    nextCmd,
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
)
import datetime, time, asyncio

app = FastAPI(title="UPS Monitor API", version="1.0.0")

# -------------------- UPS-MIB Identification & Ratings --------------------
UPS_MIB_IDENT: Dict[str, str] = {
    "ident_manufacturer": "1.3.6.1.2.1.33.1.1.1.0",  # upsIdentManufacturer
    "ident_model":        "1.3.6.1.2.1.33.1.1.2.0",  # upsIdentModel
    "ident_fw":           "1.3.6.1.2.1.33.1.1.3.0",  # upsIdentUPSSoftwareVersion
}

UPS_MIB_RATING: Dict[str, str] = {
    # มาตรฐาน UPS-MIB (พบได้ในหลายรุ่น)
    "rating_frequency_hz":      "1.3.6.1.2.1.33.1.9.1.0",  # upsConfigInputFrequency
    "rating_voltage_v":         "1.3.6.1.2.1.33.1.9.2.0",  # upsConfigInputVoltage
    "rating_battery_voltage_v": "1.3.6.1.2.1.33.1.2.5.0",  # upsBatteryVoltage (ใช้เป็นแบตรวม/เรทแบต)
}

# Enterprise placeholders (แก้เป็น OID จริงของรุ่น/ยี่ห้อคุณภายหลัง หากมีคู่มือ)
APC_ENTERPRISE: Dict[str, str] = {
    # PowerNet-MIB ตัวอย่าง (อาจต่างตามรุ่น/เฟิร์มแวร์)
    "battery_last_replace_date": "1.3.6.1.4.1.318.1.1.1.2.2.1.0",
    "battery_count":             "1.3.6.1.4.1.318.1.1.1.2.2.2.0",
    "battery_charge_voltage_v":  "1.3.6.1.4.1.318.1.1.1.2.2.3.0",
}

GAMATRONIC_ENTERPRISE: Dict[str, str] = {
    "battery_last_replace_date": "1.3.6.1.4.1.6050.0",
    "battery_count":             "1.3.6.1.4.1.6050.0",
    "battery_charge_voltage_v":  "1.3.6.1.4.1.6050.0",
}

# -------------------- OID Templates (ใช้ UPS-MIB เป็น “ค่าเริ่มต้น”) --------------------
# หมายเหตุ: จากไฟล์ walk ที่คุณอัปโหลด พบว่า UPS-MIB มีข้อมูลครบกว่าฝั่ง enterprise
# จึงสลับมาใช้ UPS-MIB เป็น primary แล้วค่อย fallback ไป enterprise
OID_TEMPLATE: Dict[str, str] = {
    # Battery
    "battery_percent":      "1.3.6.1.2.1.33.1.2.4.0",   # upsBatteryCharge %
    "battery_vdc":          "1.3.6.1.2.1.33.1.2.5.0",   # upsBatteryVoltage (V)
    "battery_runtime_min":  "1.3.6.1.2.1.33.1.2.3.0",   # upsEstimatedMinutesRemaining
    "temperature_C":        "1.3.6.1.2.1.33.1.2.7.0",   # upsBatteryTemperature (ถัด fallback ไป enterprise หากไม่มี)

    # Input (per phase) – UPS-MIB: upsInputLineTable
    "input_L1_V":           "1.3.6.1.2.1.33.1.3.3.1.3.1",  # upsInputVoltage.1
    "input_L2_V":           "1.3.6.1.2.1.33.1.3.3.1.3.2",
    "input_L3_V":           "1.3.6.1.2.1.33.1.3.3.1.3.3",
    "input_L1_A":           "1.3.6.1.2.1.33.1.3.3.1.4.1",  # upsInputCurrent.1 (tenths A)
    "input_L2_A":           "1.3.6.1.2.1.33.1.3.3.1.4.2",
    "input_L3_A":           "1.3.6.1.2.1.33.1.3.3.1.4.3",
    "input_freq_Hz":        "1.3.6.1.2.1.33.1.3.3.1.2.1",  # upsInputFrequency.1 (tenths Hz)

    # Output (per phase) – UPS-MIB: upsOutputTable
    "output_L1_V":          "1.3.6.1.2.1.33.1.4.4.1.2.1",  # upsOutputVoltage.1
    "output_L2_V":          "1.3.6.1.2.1.33.1.4.4.1.2.2",
    "output_L3_V":          "1.3.6.1.2.1.33.1.4.4.1.2.3",
    "output_L1_A":          "1.3.6.1.2.1.33.1.4.4.1.3.1",  # upsOutputCurrent.1 (tenths A)
    "output_L2_A":          "1.3.6.1.2.1.33.1.4.4.1.3.2",
    "output_L3_A":          "1.3.6.1.2.1.33.1.4.4.1.3.3",
    "output_freq_Hz":       "1.3.6.1.2.1.33.1.4.2.0",      # upsOutputFrequency (Hz)

    # Load (ถ้ามี)
    "load_W":               "1.3.6.1.2.1.33.1.4.4.1.5.1",  # upsOutputPower.1 (W)
    "load_VA":              "",                             # ส่วนมากไม่มีใน UPS-MIB -> คำนวณ VA = V*A

    # Max/Min Input (ส่วนใหญ่เป็น enterprise 935)
    "input_max_V":          "1.3.6.1.4.1.935.1.1.1.6.1.6.1",
    "input_min_V":          "1.3.6.1.4.1.935.1.1.1.6.1.7.1",

    # รวม UPS-MIB การระบุตัวตน/เรทติ้ง
    **UPS_MIB_IDENT,
    **UPS_MIB_RATING,
}

# -------------------- Brand constants --------------------
SMART_POWER_BRAND = "Smart power "
GAMATRONIC_BRAND = "Gamatronic"
UNKNOWN_BRAND = "ไม่ระบุ"

# -------------------- UPS-MIB template (ตัวอย่าง Gamatronic) --------------------
GAMATRONIC_OIDS: Dict[str, str] = {
    "sysDescr":    "1.3.6.1.2.1.1.1.0",
    "sysObjectID": "1.3.6.1.2.1.1.2.0",
    "sysName":     "1.3.6.1.2.1.1.5.0",
    "sysLocation": "1.3.6.1.2.1.1.6.0",

    # ใช้ UPS-MIB มาตรฐานเป็นหลัก (เหมือน OID_TEMPLATE)
    **{k: v for k, v in OID_TEMPLATE.items() if isinstance(v, str)},
    # เติม enterprise ของ Gamatronic หากทราบ (placeholder)
    **UPS_MIB_IDENT,
    **UPS_MIB_RATING,
}

# -------------------- IP -> OIDs --------------------
UPS_OID_MAP: Dict[str, Dict[str, Any]] = {
    # กลุ่ม Smart power (HE-1K-IoT / NMC)
    "10.50.11.64": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "คณะสัตวแพทย์",
                    "community":"public", "snmp_ver":"1"},
    "10.50.11.66": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "คณะสัตวแพทย์",
                    "community":"public", "snmp_ver":"1"},

    "10.40.1.10":  {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "แฟลตบุคลากร 1"},
    "10.50.11.21": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "แฟลตบุคลากร 2"},
    "10.50.11.23": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "แฟลตบุคลากร 3"},
    "10.50.11.25": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "แฟลตบุคลากร 4"},
    "10.50.11.27": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "แฟลตบุคลากร 5"},
    "10.50.11.29": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "แฟลตบุคลากร 6"},
    "10.50.11.31": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "แฟลตบุคลากร 7"},
    "10.50.11.33": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "แฟลตบุคลากร 8"},
    "10.50.11.35": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "แฟลตบุคลากร 9 main"},
    "10.50.11.37": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "แฟลตบุคลากร 9 ชั้น 1"},
    "10.50.11.39": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "แฟลตบุคลากร 9 ชั้น 2"},
    "10.50.11.41": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "แฟลตบุคลากร 9 ชั้น 3"},
    "10.50.11.43": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "แฟลตบุคลากร 10 main"},
    "10.50.11.45": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "แฟลตบุคลากร 10 ชั้น 1"},
    "10.50.11.47": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "แฟลตบุคลากร 10 ชั้น 2"},
    "10.50.11.49": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "แฟลตบุคลากร 10 ชั้น 3"},
    "10.50.11.51": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "แฟลตบุคลากร 11 main"},
    "10.50.11.53": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "แฟลตบุคลากร 11 ชั้น 1"},
    "10.50.11.55": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "แฟลตบุคลากร 11 ชั้น 2"},
    "10.50.11.57": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "แฟลตบุคลากร 11 ชั้น 3"},

    # Gamatronic
    "10.50.8.100": {**GAMATRONIC_OIDS, **GAMATRONIC_ENTERPRISE, "brand": GAMATRONIC_BRAND, "model": "Gamatronic", "location": "ศูนย์มหาลัย"},
    "10.50.11.11": {**GAMATRONIC_OIDS, **GAMATRONIC_ENTERPRISE, "brand": GAMATRONIC_BRAND, "model": "Gamatronic", "location": "ห้องสมุด"},

    # Smart Power / Unknown
    "10.50.11.12": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": UNKNOWN_BRAND, "model": "HE-1K-IoT", "location": "ห้องสมุด"},

    # หอพัก 25–31
    "10.50.11.73": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "หอพัก 25 ชั้น 4"},
    "10.50.11.75": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "หอพัก 26 ชั้น 1"},
    "10.50.11.77": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "หอพัก 26 ชั้น 2"},
    "10.50.11.79": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "หอพัก 26 ชั้น 3"},
    "10.50.11.81": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "หอพัก 26 ชั้น 4"},
    "10.50.11.83": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "หอพัก 27 ชั้น 1"},
    "10.50.11.85": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "หอพัก 27 ชั้น 2"},
    "10.50.11.87": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "หอพัก 27 ชั้น 3"},
    "10.50.11.89": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "หอพัก 27 ชั้น 4"},
    "10.50.11.91": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "หอพัก 28 ชั้น 1"},
    "10.50.11.93": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "หอพัก 28 ชั้น 2"},
    "10.50.11.97": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "หอพัก 28 ชั้น 4"},
    "10.50.11.99": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "หอพัก 29 ชั้น 1"},
    "10.50.11.101": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "หอพัก 29 ชั้น 2"},
    "10.50.11.103": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "หอพัก 29 ชั้น 3"},
    "10.50.11.105": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "หอพัก 29 ชั้น 4"},
    "10.50.11.109": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "หอพัก 30 ชั้น 2"},
    "10.50.11.111": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "หอพัก 30 ชั้น 3"},
    "10.50.11.115": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "หอพัก 31 ชั้น 1"},
    "10.50.11.121": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "หอพัก 31 ชั้น 4"},
    "10.50.11.123": {**OID_TEMPLATE, **APC_ENTERPRISE, "brand": SMART_POWER_BRAND, "location": "หอพัก 17"},
}


# -------------------- Scale & Fallbacks --------------------
SCALE_MAP = {
    "freqHz": 0.1,        # UPS-MIB inputFrequency/current เป็น "หน่วย 0.1"
    "output_L1_A": 0.1, "output_L2_A": 0.1, "output_L3_A": 0.1,
    "input_L1_A": 0.1,  "input_L2_A": 0.1,  "input_L3_A": 0.1,
    # batteryVDC จาก UPS-MIB ปกติเป็นโวลต์ "จริง" (ถ้ารุ่นคุณให้เป็น 10x ให้ตั้งเป็น 0.1)
    "batteryVDC": 1.0,
}

OID_FALLBACKS = {
    # Battery
    "battery_percent": ["1.3.6.1.2.1.33.1.2.4.0"],
    "battery_vdc":     ["1.3.6.1.2.1.33.1.2.5.0"],
    "battery_runtime_min": ["1.3.6.1.2.1.33.1.2.3.0"],
    "temperature_C":   ["1.3.6.1.4.1.935.1.1.1.15.0"],  # enterprise 935 เป็น fallback

    # Input (UPS-MIB fallback)
    "input_L1_V": ["1.3.6.1.2.1.33.1.3.3.1.3.1"],
    "input_L2_V": ["1.3.6.1.2.1.33.1.3.3.1.3.2"],
    "input_L3_V": ["1.3.6.1.2.1.33.1.3.3.1.3.3"],
    "input_freq_Hz": ["1.3.6.1.2.1.33.1.3.3.1.2.1"],
    "input_L1_A": ["1.3.6.1.2.1.33.1.3.3.1.4.1"],
    "input_L2_A": ["1.3.6.1.2.1.33.1.3.3.1.4.2"],
    "input_L3_A": ["1.3.6.1.2.1.33.1.3.3.1.4.3"],

    # Output (UPS-MIB fallback)
    "output_L1_V": ["1.3.6.1.2.1.33.1.4.4.1.2.1"],
    "output_L2_V": ["1.3.6.1.2.1.33.1.4.4.1.2.2"],
    "output_L3_V": ["1.3.6.1.2.1.33.1.4.4.1.2.3"],
    "output_freq_Hz": ["1.3.6.1.2.1.33.1.4.2.0"],
    "output_L1_A": ["1.3.6.1.2.1.33.1.4.4.1.3.1"],
    "output_L2_A": ["1.3.6.1.2.1.33.1.4.4.1.3.2"],
    "output_L3_A": ["1.3.6.1.2.1.33.1.4.4.1.3.3"],

    # Load
    "load_VA": [],
    "load_W":  ["1.3.6.1.2.1.33.1.4.4.1.5.1"],

    # Identification & Ratings fallbacks (UPS-MIB เอง)
    "ident_manufacturer": ["1.3.6.1.2.1.33.1.1.1.0"],
    "ident_model":        ["1.3.6.1.2.1.33.1.1.2.0"],
    "ident_fw":           ["1.3.6.1.2.1.33.1.1.3.0"],
    "rating_voltage_v":         ["1.3.6.1.2.1.33.1.9.2.0"],
    "rating_frequency_hz":      ["1.3.6.1.2.1.33.1.9.1.0"],
    "rating_battery_voltage_v": ["1.3.6.1.2.1.33.1.2.5.0"],

    # Battery info (enterprise)
    "battery_last_replace_date": [
        "1.3.6.1.4.1.318.1.1.1.2.2.1.0",
        "1.3.6.1.4.1.6050.0",
    ],
    "battery_count": [
        "1.3.6.1.4.1.318.1.1.1.2.2.2.0",
        "1.3.6.1.4.1.6050.0",
    ],
    "battery_charge_voltage_v": [
        "1.3.6.1.4.1.318.1.1.1.2.2.3.0",
        "1.3.6.1.4.1.6050.0",
    ],
}

# -------------------- Utils --------------------
def __ensure_event_loop():
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

def _target(ip: str, timeout: float, retries: int) -> UdpTransportTarget:
    return UdpTransportTarget((ip, 161), timeout=timeout, retries=retries)

def snmp_get_many(ip: str, community: str, oids: List[str], timeout=1.2, retries=0, comm_obj=None) -> Dict[str, Optional[str]]:
    __ensure_event_loop()
    if not oids:
        return {}
    try:
        it = getCmd(
            SnmpEngine(),
            comm_obj or CommunityData(community, mpModel=1),
            _target(ip, timeout, retries),
            ContextData(),
            *[ObjectType(ObjectIdentity(oid)) for oid in oids]
        )
        err, status, index, varBinds = next(it)
        if err or status:
            return {oid: None for oid in oids}
        out = {}
        for vb in varBinds:
            raw = vb[1].prettyPrint() if hasattr(vb[1], "prettyPrint") else str(vb[1])
            out[str(vb[0])] = None if raw.lower().startswith(("no such", "nosuch")) else raw
        return out
    except Exception:
        return {oid: None for oid in oids}

def snmp_get(ip: str, community: str, oid: Optional[str], timeout=1.2, retries=0, comm_obj=None) -> Optional[str]:
    __ensure_event_loop()
    if not oid:
        return None
    try:
        it = getCmd(
            SnmpEngine(),
            comm_obj or CommunityData(community, mpModel=1),
            _target(ip, timeout, retries),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        )
        err, status, index, varBinds = next(it)
        if err or status:
            return None
        v = varBinds[0][1]
        raw = v.prettyPrint() if hasattr(v, "prettyPrint") else str(v)
        return None if raw.lower().startswith(("no such", "nosuch")) else raw
    except Exception:
        return None


def to_float(v: Optional[str], scale: float = 1.0) -> float:
    try:
        return float(v) * scale if v is not None else 0.0
    except Exception:
        return 0.0

def to_int(v: Optional[str]) -> int:
    try:
        return int(float(v)) if v is not None else 0
    except Exception:
        return 0

def to_str(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip().strip('"')
    return s if s else None

def parse_last_replace_date(v: Optional[str]) -> Optional[str]:
    s = to_str(v)
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%Y", "%Y/%m", "%d-%m-%Y", "%m-%Y", "%Y.%m.%d"):
        try:
            dt = datetime.datetime.strptime(s, fmt)
            if fmt in ("%m/%Y", "%Y/%m", "%m-%Y"):
                dt = dt.replace(day=1)
            return dt.date().isoformat()
        except Exception:
            continue
    return s  # คืนค่าตามที่ได้มาถ้า parse ไม่ได้

def _resolve_oids_and_meta(config: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, Any]]:
    oids: Dict[str, str] = config["oids"] if "oids" in config else {k: v for k, v in config.items() if isinstance(v, str)}
    meta = {
        "community": config.get("community", "public"),
        "brand": config.get("brand"),
        "model": config.get("model"),
        "location": config.get("location"),
        "pf": float(config.get("pf", 0.8)),
    }
    return oids, meta

# -------------------- Batch planning (primary + fallbacks) --------------------
KEY_SCALE = {
    "battery_vdc": "batteryVDC",
    "input_freq_Hz": "freqHz",
    "output_freq_Hz": "freqHz",
    "output_L1_A": "output_L1_A",
    "output_L2_A": "output_L2_A",
    "output_L3_A": "output_L3_A",
    "input_L1_A":  "input_L1_A",
    "input_L2_A":  "input_L2_A",
    "input_L3_A":  "input_L3_A",
}

def _build_key_oids(oids: Dict[str, str]) -> Dict[str, List[str]]:
    key_oids: Dict[str, List[str]] = {}
    keys = [
        # battery
        "battery_percent","battery_vdc","battery_runtime_min","temperature_C",
        # input/output basics
        "input_L1_V","input_L2_V","input_L3_V","input_L1_A","input_L2_A","input_L3_A","input_freq_Hz",
        "output_L1_V","output_L2_V","output_L3_V","output_L1_A","output_L2_A","output_L3_A","output_freq_Hz",
        # load
        "load_VA","load_W",
        # max/min
        "input_max_V","input_min_V",
        # identification & ratings
        "ident_manufacturer","ident_model","ident_fw",
        "rating_voltage_v","rating_frequency_hz","rating_battery_voltage_v",
        # enterprise battery info
        "battery_last_replace_date","battery_count","battery_charge_voltage_v",
    ]
    for k in keys:
        lst = []
        if k in oids and isinstance(oids[k], str) and oids[k]:
            lst.append(oids[k])
        lst.extend(OID_FALLBACKS.get(k, []))
        seen = set(); merged = []
        for oid in lst:
            if oid and oid not in seen:
                merged.append(oid); seen.add(oid)
        key_oids[k] = merged
    return key_oids

def _pick_first(key: str, key_oids: Dict[str, List[str]], oid2val: Dict[str, Optional[str]]) -> Optional[str]:
    for oid in key_oids.get(key, []):
        v = oid2val.get(oid)
        if v not in (None, "0"):
            return v
    return None

# -------------------- Cache (TTL) --------------------
_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
DEFAULT_TTL = 2.0  # วินาที

# -------------------- Collector --------------------
def get_ups_data(ip: str, config: Dict[str, Any], timeout: float = 1.2, retries: int = 0) -> Dict[str, Any]:
    oids, meta = _resolve_oids_and_meta(config)
    comm_obj = _comm_obj(config, meta["community"])

    key_oids = _build_key_oids(oids)
    all_oids: List[str] = []
    for arr in key_oids.values():
        all_oids.extend(arr)
    all_oids = list(dict.fromkeys(all_oids))

    oid2val = snmp_get_many(ip, meta["community"], all_oids, timeout=timeout, retries=retries, comm_obj=comm_obj)

    # ดึงค่า + scale
    def _g(key: str) -> float:
        raw = _pick_first(key, key_oids, oid2val)
        scale_key = KEY_SCALE.get(key)
        scale = SCALE_MAP.get(scale_key, 1.0) if scale_key else 1.0
        return to_float(raw, scale)

    def _gi(key: str) -> int:
        raw = _pick_first(key, key_oids, oid2val)
        return to_int(raw)

    def _gs(key: str) -> Optional[str]:
        raw = _pick_first(key, key_oids, oid2val)
        return to_str(raw)

    # Battery
    batt_pct = _gi("battery_percent")
    batt_vdc = _g("battery_vdc")
    batt_min = _gi("battery_runtime_min")
    temp_c   = _g("temperature_C")

    # Input
    in_L1V = _g("input_L1_V"); in_L2V = _g("input_L2_V"); in_L3V = _g("input_L3_V")
    in_L1A = _g("input_L1_A"); in_L2A = _g("input_L2_A"); in_L3A = _g("input_L3_A")
    in_freq = _g("input_freq_Hz")
    in_max  = _g("input_max_V")
    in_min  = _g("input_min_V")

    # Output
    out_L1V = _g("output_L1_V"); out_L2V = _g("output_L2_V"); out_L3V = _g("output_L3_V")
    out_L1A = _g("output_L1_A"); out_L2A = _g("output_L2_A"); out_L3A = _g("output_L3_A")
    out_freq = _g("output_freq_Hz")

    # Load
    load_va = _gi("load_VA")
    load_w  = _gi("load_W")
    # ไม่มี OID VA -> คำนวณจาก L1 เป็นอย่างน้อย (หรือจะรวมทุกเฟสก็ได้)
    if (not load_va) and out_L1V and out_L1A:
        load_va = round(out_L1V * out_L1A)
    if (not load_w) and out_L1V and out_L1A:
        load_w = round(out_L1V * out_L1A * meta["pf"])

    # Identification & rating (เติมถ้ามี)
    ident_manufacturer = _gs("ident_manufacturer")
    ident_model        = _gs("ident_model")
    ident_fw           = _gs("ident_fw")
    rating_v           = _g("rating_voltage_v")
    rating_hz          = _g("rating_frequency_hz")
    rating_batt_v      = _g("rating_battery_voltage_v")
    batt_charge_v      = _g("battery_charge_voltage_v")
    batt_count         = _gi("battery_count")
    batt_last_date     = parse_last_replace_date(_pick_first("battery_last_replace_date", key_oids, oid2val))

    # ให้ brand/model จาก meta ก่อน ถ้าไม่มีค่อยใช้จาก UPS-MIB
    brand = meta.get("brand") or ident_manufacturer
    model = meta.get("model") or ident_model

    return {
        # --- รูปแบบหลักตามที่ขอ ---
        "id": f"UPS_{ip.replace('.', '_')}",
        "status": "Online",
        "ip": ip,
        "brand": brand,
        "model": model,
        "location": meta.get("location"),
        "batteryPercent": batt_pct,
        "batteryVDC": batt_vdc,
        "backupTimeMin": batt_min,
        "temperatureC": temp_c,
        "input": {
            "L1V": in_L1V, "L2V": in_L2V, "L3V": in_L3V,
            "L1A": in_L1A, "L2A": in_L2A, "L3A": in_L3A,
            "freqHz": in_freq
        },
        "output": {
            "L1V": out_L1V, "L2V": out_L2V, "L3V": out_L3V,
            "L1A": out_L1A, "L2A": out_L2A, "L3A": out_L3A,
            "freqHz": out_freq
        },
        "loadVA": load_va,
        "loadW":  load_w,
        "inputMax": in_max,
        "inputMin": in_min,

        # --- ฟิลด์เสริม (ถ้ามี) ---
        "manufacturer": ident_manufacturer,
        "firmwareVersion": ident_fw,
        "ratingVoltageV": rating_v,
        "ratingFrequencyHz": rating_hz,
        "ratingBatteryVoltageV": rating_batt_v,
        "batteryChargeVoltageV": batt_charge_v,
        "batteryCount": batt_count,
        "lastBatteryReplaceDate": batt_last_date,
    }

def _comm_obj(cfg: Dict[str, Any], default_comm: str):
    ver = str(cfg.get("snmp_ver", "2c")).lower()
    comm = cfg.get("community", default_comm)
    # v1 => mpModel=0, v2c => mpModel=1
    return CommunityData(comm, mpModel=0 if ver in ("1", "v1") else 1)

# -------------------- Cache (TTL) --------------------
_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
DEFAULT_TTL = 2.0  # วินาที

def get_ups_data_cached(ip: str, cfg: Dict[str, Any], timeout: float, retries: int, ttl: float) -> Dict[str, Any]:
    now = time.time()
    ent = _CACHE.get(ip)
    if ent and (now - ent[0] < ttl):
        return ent[1]
    data = get_ups_data(ip, cfg, timeout=timeout, retries=retries)
    _CACHE[ip] = (now, data)
    return data

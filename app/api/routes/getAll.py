from fastapi import FastAPI
from typing import Dict, Any
from pysnmp.hlapi import *
import datetime

app = FastAPI(title="UPS Monitor API", version="1.0.0")

# ---------- UPS OID MAP ----------
UPS_OID_MAP: Dict[str, Dict[str, str]] = {
    "10.40.1.10": {  # ตัวอย่าง
        "brand": "APC",
        "model": "Smart-UPS 3000",
        "location": "Server Room A",
        "oids": {
            "battery_percent": "1.3.6.1.2.1.33.1.2.4.0",
            "battery_vdc": "1.3.6.1.2.1.33.1.2.5.0",
            "battery_runtime_min": "1.3.6.1.2.1.33.1.2.3.0",
            "input_L1_V": "1.3.6.1.4.1.935.1.1.1.6.1.2.1",
            "input_freq_Hz": "1.3.6.1.4.1.935.1.1.1.6.1.4.1",
            "output_L1_V": "1.3.6.1.4.1.935.1.1.1.8.1.2.1",
            "output_freq_Hz": "1.3.6.1.4.1.935.1.1.1.8.1.4.1",
            "load_VA": "1.3.6.1.4.1.935.1.1.1.8.1.5.1",
            "load_W": "1.3.6.1.4.1.935.1.1.1.8.1.6.1",
        }
    },
    # เพิ่ม IP อื่น ๆ ได้
}

# ---------- SNMP GET ----------
def snmp_get(ip: str, community: str, oid: str):
    iterator = getCmd(
        SnmpEngine(),
        CommunityData(community, mpModel=1),
        UdpTransportTarget((ip, 161), timeout=2, retries=1),
        ContextData(),
        ObjectType(ObjectIdentity(oid)),
    )
    errorIndication, errorStatus, errorIndex, varBinds = next(iterator)
    if errorIndication:
        return None
    if errorStatus:
        return None
    return str(varBinds[0][1])

# ---------- ดึงข้อมูลทั้งหมดของ UPS ----------
def get_ups_data(ip: str, config: Dict[str, Any], community="public"):
    oids = config["oids"]

    return {
        "status": "Online",
        "ip": ip,
        "brand": config["brand"],
        "model": config["model"],
        "location": config["location"],
        "batteryPercent": float(snmp_get(ip, community, oids["battery_percent"]) or 0),
        "batteryVDC": float(snmp_get(ip, community, oids["battery_vdc"]) or 0),
        "backupTimeMin": int(snmp_get(ip, community, oids["battery_runtime_min"]) or 0),
        "temperatureC": None,  # เพิ่มได้ถ้ามี OID
        "input": {
            "L1V": float(snmp_get(ip, community, oids.get("input_L1_V", "")) or 0),
            "freqHz": float(snmp_get(ip, community, oids.get("input_freq_Hz", "")) or 0)
        },
        "output": {
            "L1V": float(snmp_get(ip, community, oids.get("output_L1_V", "")) or 0),
            "freqHz": float(snmp_get(ip, community, oids.get("output_freq_Hz", "")) or 0)
        },
        "loadVA": int(snmp_get(ip, community, oids.get("load_VA", "")) or 0),
        "loadW": int(snmp_get(ip, community, oids.get("load_W", "")) or 0),
        "timestamp": datetime.datetime.now().isoformat()
    }

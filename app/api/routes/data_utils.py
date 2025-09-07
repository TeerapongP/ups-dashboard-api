import datetime
from typing import Optional, Dict, List, Any
from app.services.ups_config import SCALE_FACTORS, KEY_TO_SCALE, OID_FALLBACKS

def to_float(value: Optional[str], scale: float = 1.0) -> float:
    try:
        return float(value) * scale if value is not None else 0.0
    except (ValueError, TypeError):
        return 0.0

def to_int(value: Optional[str]) -> int:
    try:
        return int(float(value)) if value is not None else 0
    except (ValueError, TypeError):
        return 0

def to_str(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = str(value).strip().strip('"')
    return cleaned if cleaned else None

def format_decimal(value: Optional[float], decimals: int = 2) -> Optional[float]:
    try:
        if value is None:
            return None
        return round(float(value), decimals)
    except (ValueError, TypeError):
        return None

def parse_date(value: Optional[str]) -> Optional[str]:
    cleaned_value = to_str(value)
    if not cleaned_value:
        return None
    
    date_formats = [
        "%Y-%m-%d", "%d/%m/%Y", "%m/%Y", "%Y/%m", 
        "%d-%m-%Y", "%m-%Y", "%Y.%m.%d"
    ]
    
    for fmt in date_formats:
        try:
            dt = datetime.datetime.strptime(cleaned_value, fmt)
            if fmt in ("%m/%Y", "%Y/%m", "%m-%Y"):
                dt = dt.replace(day=1)
            return dt.date().isoformat()
        except ValueError:
            continue
    
    return cleaned_value

class OIDResolver:
    
    def __init__(self, oid_config: Dict[str, str]):
        self.oid_config = oid_config
        self.key_oids = self._build_key_oids()
    
    def _build_key_oids(self) -> Dict[str, List[str]]:
        key_oids = {}
        
        data_keys = [
            "battery_percent", "battery_vdc", "battery_runtime_min", "temperature_C",
            "input_L1_V", "input_L2_V", "input_L3_V", 
            "input_L1_A", "input_L2_A", "input_L3_A", "input_freq_Hz",
            "output_L1_V", "output_L2_V", "output_L3_V",
            "output_L1_A", "output_L2_A", "output_L3_A", "output_freq_Hz",
            "load_VA", "load_W",
            "ident_manufacturer", "ident_model", "ident_fw",
            "rating_voltage_v", "rating_frequency_hz", "rating_battery_voltage_v",
        ]
        
        for key in data_keys:
            oid_list = []
            
            if key in self.oid_config and self.oid_config[key]:
                oid_list.append(self.oid_config[key])
            
            oid_list.extend(OID_FALLBACKS.get(key, []))
            
            unique_oids = []
            seen = set()
            for oid in oid_list:
                if oid and oid not in seen:
                    unique_oids.append(oid)
                    seen.add(oid)
            
            key_oids[key] = unique_oids
        
        return key_oids
    
    def get_all_oids(self) -> List[str]:
        all_oids = []
        for oid_list in self.key_oids.values():
            all_oids.extend(oid_list)
        return list(dict.fromkeys(all_oids))
    
    def resolve_value(self, key: str, oid_values: Dict[str, Optional[str]]) -> Optional[str]:
        for oid in self.key_oids.get(key, []):
            value = oid_values.get(oid)
            if value is not None and value != "0":
                return value
        return None

class DataProcessor:
    
    def __init__(self, resolver: OIDResolver, voltage_threshold: float = 180.0):
        self.resolver = resolver
        self.voltage_threshold = voltage_threshold

    @staticmethod
    def _is_zero(x: Optional[float]) -> bool:
        if x is None:
            return False
        return abs(float(x)) < 1e-6

    def _is_offline(
        self,
        in_v: List[Optional[float]],
        battery_percent: int,
        battery_vdc: float,
        battery_runtime: int,
        temperature: float,
        load_va: int,
        load_w: int,
    ) -> bool:
        return all([
            self._is_zero(in_v[0]), self._is_zero(in_v[1]), self._is_zero(in_v[2]),
            battery_percent == 0,
            self._is_zero(battery_vdc),
            battery_runtime == 0,
            self._is_zero(temperature),
            load_va == 0,
            load_w == 0,
        ])

    def _is_power_fail(self, in_v: List[Optional[float]]) -> bool:
        v1 = in_v[0]
        return v1 is not None and v1 < self.voltage_threshold

    def _get_scaled_float(self, key: str, oid_values: Dict[str, Optional[str]]) -> float:
        raw_value = self.resolver.resolve_value(key, oid_values)
        scale_key = KEY_TO_SCALE.get(key)
        scale = SCALE_FACTORS.get(scale_key, 1.0) if scale_key else 1.0
        return to_float(raw_value, scale)

    def _get_int(self, key: str, oid_values: Dict[str, Optional[str]]) -> int:
        raw_value = self.resolver.resolve_value(key, oid_values)
        return to_int(raw_value)

    def _get_string(self, key: str, oid_values: Dict[str, Optional[str]]) -> Optional[str]:
        raw_value = self.resolver.resolve_value(key, oid_values)
        return to_str(raw_value)

    def process_ups_data(
        self, 
        ip: str, 
        oid_values: Dict[str, Optional[str]], 
        device_config: Dict[str, Any]
    ) -> Dict[str, Any]:

        battery_percent = self._get_int("battery_percent", oid_values)
        battery_vdc_raw = self._get_scaled_float("battery_vdc", oid_values)
        battery_runtime = self._get_int("battery_runtime_min", oid_values)
        temperature_raw = self._get_scaled_float("temperature_C", oid_values)

        in_L1_raw = self._get_scaled_float("input_L1_V", oid_values)
        in_L2_raw = self._get_scaled_float("input_L2_V", oid_values)
        in_L3_raw = self._get_scaled_float("input_L3_V", oid_values)
        in_L1 = format_decimal(in_L1_raw)
        in_L2 = format_decimal(in_L2_raw)
        in_L3 = format_decimal(in_L3_raw)

        in_A1 = format_decimal(self._get_scaled_float("input_L1_A", oid_values))
        in_A2 = format_decimal(self._get_scaled_float("input_L2_A", oid_values))
        in_A3 = format_decimal(self._get_scaled_float("input_L3_A", oid_values))
        in_f  = format_decimal(self._get_scaled_float("input_freq_Hz", oid_values))

        input_data = {
            "L1V": in_L1, "L2V": in_L2, "L3V": in_L3,
            "L1A": in_A1, "L2A": in_A2, "L3A": in_A3,
            "freqHz": in_f,
        }

        out_L1 = format_decimal(self._get_scaled_float("output_L1_V", oid_values))
        out_L2 = format_decimal(self._get_scaled_float("output_L2_V", oid_values))
        out_L3 = format_decimal(self._get_scaled_float("output_L3_V", oid_values))
        out_A1 = format_decimal(self._get_scaled_float("output_L1_A", oid_values))
        out_A2 = format_decimal(self._get_scaled_float("output_L2_A", oid_values))
        out_A3 = format_decimal(self._get_scaled_float("output_L3_A", oid_values))
        out_f  = format_decimal(self._get_scaled_float("output_freq_Hz", oid_values))

        output_data = {
            "L1V": out_L1, "L2V": out_L2, "L3V": out_L3,
            "L1A": out_A1, "L2A": out_A2, "L3A": out_A3,
            "freqHz": out_f,
        }

        load_va = self._get_int("load_VA", oid_values)
        load_w  = self._get_int("load_W", oid_values)

        if not load_va and output_data["L1V"] and output_data["L1A"]:
            load_va = round(output_data["L1V"] * output_data["L1A"])
        if not load_w and output_data["L1V"] and output_data["L1A"]:
            pf = device_config.get("power_factor", 0.8)
            load_w = round(output_data["L1V"] * output_data["L1A"] * pf)

        brand = device_config.get("brand") or self._get_string("ident_manufacturer", oid_values)
        model = device_config.get("model") or self._get_string("ident_model", oid_values)

        in_volt_list = [in_L1_raw, in_L2_raw, in_L3_raw]

        if self._is_offline(
            in_volt_list,
            battery_percent=battery_percent,
            battery_vdc=battery_vdc_raw,
            battery_runtime=battery_runtime,
            temperature=temperature_raw,
            load_va=load_va,
            load_w=load_w,
        ):
            status = "Offline"
        elif self._is_power_fail(in_volt_list):
            status = "PowerFail"
        else:
            status = "Online"

        return {
            "id": f"UPS_{ip.replace('.', '_')}",
            "status": status,
            "ip": ip,
            "brand": brand,
            "model": model,
            "location": device_config.get("location"),
            "batteryPercent": battery_percent,
            "batteryVDC": format_decimal(battery_vdc_raw/10),
            "backupTimeMin": battery_runtime,
            "temperatureC": format_decimal(temperature_raw),
            "input": input_data,
            "output": output_data,
            "loadVA": load_va,
            "loadW": load_w,
        }

# Data Processing Utilities
import datetime
from typing import Optional, Dict, List, Any
from app.services.ups_config import SCALE_FACTORS, KEY_TO_SCALE, OID_FALLBACKS


def to_float(value: Optional[str], scale: float = 1.0) -> float:
    """Convert string value to float with scaling"""
    try:
        return float(value) * scale if value is not None else 0.0
    except (ValueError, TypeError):
        return 0.0


def to_int(value: Optional[str]) -> int:
    """Convert string value to integer"""
    try:
        return int(float(value)) if value is not None else 0
    except (ValueError, TypeError):
        return 0


def to_str(value: Optional[str]) -> Optional[str]:
    """Clean and normalize string value"""
    if value is None:
        return None
    cleaned = str(value).strip().strip('"')
    return cleaned if cleaned else None


def format_decimal(value: Optional[float], decimals: int = 2) -> Optional[float]:
    """Format float to specified decimal places"""
    try:
        if value is None:
            return None
        return round(float(value), decimals)
    except (ValueError, TypeError):
        return None


def parse_date(value: Optional[str]) -> Optional[str]:
    """Parse various date formats to ISO format"""
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
    
    return cleaned_value  # Return original if parsing fails


class OIDResolver:
    """Resolves OID values with fallback support"""
    
    def __init__(self, oid_config: Dict[str, str]):
        self.oid_config = oid_config
        self.key_oids = self._build_key_oids()
    
    def _build_key_oids(self) -> Dict[str, List[str]]:
        """Build mapping of data keys to OID lists (primary + fallbacks)"""
        key_oids = {}
        
        data_keys = [
            # Battery
            "battery_percent", "battery_vdc", "battery_runtime_min", "temperature_C",
            # Input/Output
            "input_L1_V", "input_L2_V", "input_L3_V", 
            "input_L1_A", "input_L2_A", "input_L3_A", "input_freq_Hz",
            "output_L1_V", "output_L2_V", "output_L3_V",
            "output_L1_A", "output_L2_A", "output_L3_A", "output_freq_Hz",
            # Load
            "load_VA", "load_W",
            # Identification & ratings
            "ident_manufacturer", "ident_model", "ident_fw",
            "rating_voltage_v", "rating_frequency_hz", "rating_battery_voltage_v",
        ]
        
        for key in data_keys:
            oid_list = []
            
            # Add primary OID if exists
            if key in self.oid_config and self.oid_config[key]:
                oid_list.append(self.oid_config[key])
            
            # Add fallback OIDs
            oid_list.extend(OID_FALLBACKS.get(key, []))
            
            # Remove duplicates while preserving order
            unique_oids = []
            seen = set()
            for oid in oid_list:
                if oid and oid not in seen:
                    unique_oids.append(oid)
                    seen.add(oid)
            
            key_oids[key] = unique_oids
        
        return key_oids
    
    def get_all_oids(self) -> List[str]:
        """Get all unique OIDs needed for data collection"""
        all_oids = []
        for oid_list in self.key_oids.values():
            all_oids.extend(oid_list)
        return list(dict.fromkeys(all_oids))  # Remove duplicates
    
    def resolve_value(self, key: str, oid_values: Dict[str, Optional[str]]) -> Optional[str]:
        """Resolve value for a key using primary OID and fallbacks"""
        for oid in self.key_oids.get(key, []):
            value = oid_values.get(oid)
            if value is not None and value != "0":
                return value
        return None


class DataProcessor:
    """Processes raw SNMP data into structured UPS data"""
    
    def __init__(self, resolver: OIDResolver):
        self.resolver = resolver
    
    def _get_scaled_float(self, key: str, oid_values: Dict[str, Optional[str]]) -> float:
        """Get float value with appropriate scaling"""
        raw_value = self.resolver.resolve_value(key, oid_values)
        scale_key = KEY_TO_SCALE.get(key)
        scale = SCALE_FACTORS.get(scale_key, 1.0) if scale_key else 1.0
        return to_float(raw_value, scale)
    
    def _get_int(self, key: str, oid_values: Dict[str, Optional[str]]) -> int:
        """Get integer value"""
        raw_value = self.resolver.resolve_value(key, oid_values)
        return to_int(raw_value)
    
    def _get_string(self, key: str, oid_values: Dict[str, Optional[str]]) -> Optional[str]:
        """Get string value"""
        raw_value = self.resolver.resolve_value(key, oid_values)
        return to_str(raw_value)
    
    def process_ups_data(
        self, 
        ip: str, 
        oid_values: Dict[str, Optional[str]], 
        device_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process raw OID values into structured UPS data"""
        
        # Battery data
        battery_percent = self._get_int("battery_percent", oid_values)
        battery_vdc = self._get_scaled_float("battery_vdc", oid_values)
        battery_runtime = self._get_int("battery_runtime_min", oid_values)
        temperature = self._get_scaled_float("temperature_C", oid_values)
        
        # Input data
        input_data = {
            "L1V": format_decimal(self._get_scaled_float("input_L1_V", oid_values)),
            "L2V": format_decimal(self._get_scaled_float("input_L2_V", oid_values)),
            "L3V": format_decimal(self._get_scaled_float("input_L3_V", oid_values)),
            "L1A": format_decimal(self._get_scaled_float("input_L1_A", oid_values)),
            "L2A": format_decimal(self._get_scaled_float("input_L2_A", oid_values)),
            "L3A": format_decimal(self._get_scaled_float("input_L3_A", oid_values)),
            "freqHz": format_decimal(self._get_scaled_float("input_freq_Hz", oid_values))
        }
        
        # Output data
        output_data = {
            "L1V": format_decimal(self._get_scaled_float("output_L1_V", oid_values)),
            "L2V": format_decimal(self._get_scaled_float("output_L2_V", oid_values)),
            "L3V": format_decimal(self._get_scaled_float("output_L3_V", oid_values)),
            "L1A": format_decimal(self._get_scaled_float("output_L1_A", oid_values)),
            "L2A": format_decimal(self._get_scaled_float("output_L2_A", oid_values)),
            "L3A": format_decimal(self._get_scaled_float("output_L3_A", oid_values)),
            "freqHz": format_decimal(self._get_scaled_float("output_freq_Hz", oid_values))
        }
        
        # Load data
        load_va = self._get_int("load_VA", oid_values)
        load_w = self._get_int("load_W", oid_values)
        
        # Calculate load if not available from SNMP
        if not load_va and output_data["L1V"] and output_data["L1A"]:
            load_va = round(output_data["L1V"] * output_data["L1A"])
        
        if not load_w and output_data["L1V"] and output_data["L1A"]:
            power_factor = device_config.get("power_factor", 0.8)
            load_w = round(output_data["L1V"] * output_data["L1A"] * power_factor)
        
        # Device identification
        brand = device_config.get("brand") or self._get_string("ident_manufacturer", oid_values)
        model = device_config.get("model") or self._get_string("ident_model", oid_values)
        
        # Status determination
        if input_data["L1V"] == 0 and input_data["L2V"] == 0 and input_data["L3V"] == 0:
            status = "Offline"
        elif input_data["L1V"] is not None and input_data["L1V"] < 180:
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
            "batteryVDC": format_decimal(battery_vdc/10),
            "backupTimeMin": battery_runtime,
            "temperatureC": temperature,
            "input": input_data,
            "output": output_data,
            "loadVA": load_va,
            "loadW": load_w,
        }
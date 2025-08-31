# UPS Configuration and Constants
from typing import Dict, List, Any

# Brand Constants
UNKNOWN_BRAND = "Unknown"
SMART_POWER_BRAND = "Smart Power"
GAMATRONIC_BRAND = "Gamatronic"

# UPS-MIB (RFC1628) Base OIDs
UPS_MIB_IDENTS = {
    "ident_manufacturer": "1.3.6.1.2.1.33.1.1.1.0",
    "ident_model": "1.3.6.1.2.1.33.1.1.2.0",
    "ident_fw": "1.3.6.1.2.1.33.1.1.3.0",
}

UPS_MIB_RATINGS = {
    "rating_frequency_hz": "1.3.6.1.2.1.33.1.9.1.0",
    "rating_voltage_v": "1.3.6.1.2.1.33.1.9.2.0",
    "rating_battery_voltage_v": "1.3.6.1.2.1.33.1.2.5.0",
}

# Standard UPS-MIB OIDs
STANDARD_OIDS = {
    # Battery
    "battery_percent": "1.3.6.1.2.1.33.1.2.4.0",
    "battery_vdc": "1.3.6.1.2.1.33.1.2.5.0",
    "battery_runtime_min": "1.3.6.1.2.1.33.1.2.3.0",
    "temperature_C": "1.3.6.1.2.1.33.1.2.7.0",
    
    # Input
    "input_L1_V": "1.3.6.1.2.1.33.1.3.3.1.3.1",
    "input_L2_V": "1.3.6.1.2.1.33.1.3.3.1.3.2",
    "input_L3_V": "1.3.6.1.2.1.33.1.3.3.1.3.3",
    "input_L1_A": "1.3.6.1.2.1.33.1.3.3.1.4.1",
    "input_L2_A": "1.3.6.1.2.1.33.1.3.3.1.4.2",
    "input_L3_A": "1.3.6.1.2.1.33.1.3.3.1.4.3",
    "input_freq_Hz": "1.3.6.1.2.1.33.1.3.3.1.2.1",
    
    # Output
    "output_L1_V": "1.3.6.1.2.1.33.1.4.4.1.2.1",
    "output_L2_V": "1.3.6.1.2.1.33.1.4.4.1.2.2",
    "output_L3_V": "1.3.6.1.2.1.33.1.4.4.1.2.3",
    "output_L1_A": "1.3.6.1.2.1.33.1.4.4.1.3.1",
    "output_L2_A": "1.3.6.1.2.1.33.1.4.4.1.3.2",
    "output_L3_A": "1.3.6.1.2.1.33.1.4.4.1.3.3",
    "output_freq_Hz": "1.3.6.1.2.1.33.1.4.2.0",
    
    # Load
    "load_W": "1.3.6.1.2.1.33.1.4.4.1.5.1",
    "load_VA": "",
    
    **UPS_MIB_IDENTS,
    **UPS_MIB_RATINGS,
}

# EPPC Enterprise OIDs (935)
EPPC_935_OIDS = {
    "ident_manufacturer": "1.3.6.1.4.1.935.10.1.1.1.1.0",
    "ident_model": "1.3.6.1.4.1.935.10.1.1.1.2.0",
    "ident_fw": "1.3.6.1.4.1.935.10.1.1.1.3.0",
    "input_L2_V": "1.3.6.1.4.1.935.10.1.1.2.16.1.3.2",
    "input_L3_V": "1.3.6.1.4.1.935.10.1.1.2.16.1.3.3",
    "input_L1_A": "1.3.6.1.4.1.935.10.1.1.2.16.1.4.1",
    "input_L2_A": "1.3.6.1.4.1.935.10.1.1.2.16.1.4.2",
    "input_L3_A": "1.3.6.1.4.1.935.10.1.1.2.16.1.4.3",
    "output_L2_V": "1.3.6.1.4.1.935.10.1.1.2.18.1.3.2",
    "output_L3_V": "1.3.6.1.4.1.935.10.1.1.2.18.1.3.3",
    "output_L1_A": "1.3.6.1.4.1.935.10.1.1.2.18.1.4.1",
    "output_L2_A": "1.3.6.1.4.1.935.10.1.1.2.18.1.4.2",
    "output_L3_A": "1.3.6.1.4.1.935.10.1.1.2.18.1.4.3",
    "load_W": "1.3.6.1.4.1.935.10.1.1.2.18.1.5.1",
    "load_VA": "1.3.6.1.4.1.935.10.1.1.2.18.1.6.1",
    "battery_percent": "1.3.6.1.4.1.935.10.1.1.3.4.0",
    "battery_runtime_min": "1.3.6.1.4.1.935.10.1.1.3.3.0",
}

# Scale factors for different measurements
SCALE_FACTORS = {
    "freqHz": 0.1,
    "output_L1_A": 0.1,
    "output_L2_A": 0.1,
    "output_L3_A": 0.1,
    "input_L1_A": 0.1,
    "input_L2_A": 0.1,
    "input_L3_A": 0.1,
    "batteryVDC": 1.0,
}

# Mapping of data keys to scale factor keys
KEY_TO_SCALE = {
    "battery_vdc": "batteryVDC",
    "input_freq_Hz": "freqHz",
    "output_freq_Hz": "freqHz",
    "output_L1_A": "output_L1_A",
    "output_L2_A": "output_L2_A",
    "output_L3_A": "output_L3_A",
    "input_L1_A": "input_L1_A",
    "input_L2_A": "input_L2_A",
    "input_L3_A": "input_L3_A",
}

# OID fallback chains
OID_FALLBACKS: Dict[str, List[str]] = {
    # Battery
    "battery_percent": ["1.3.6.1.2.1.33.1.2.4.0"],
    "battery_vdc": ["1.3.6.1.2.1.33.1.2.5.0"],
    "battery_runtime_min": ["1.3.6.1.2.1.33.1.2.3.0"],
    "temperature_C": ["1.3.6.1.2.1.33.1.2.7.0"],
    
    # Input
    "input_L1_V": ["1.3.6.1.2.1.33.1.3.3.1.3.1", "1.3.6.1.4.1.935.10.1.1.2.16.1.3.1"],
    "input_L2_V": ["1.3.6.1.2.1.33.1.3.3.1.3.2", "1.3.6.1.4.1.935.10.1.1.2.16.1.3.2"],
    "input_L3_V": ["1.3.6.1.2.1.33.1.3.3.1.3.3", "1.3.6.1.4.1.935.10.1.1.2.16.1.3.3"],
    "input_L1_A": ["1.3.6.1.2.1.33.1.3.3.1.4.1", "1.3.6.1.4.1.935.10.1.1.2.16.1.4.1"],
    "input_L2_A": ["1.3.6.1.2.1.33.1.3.3.1.4.2", "1.3.6.1.4.1.935.10.1.1.2.16.1.4.2"],
    "input_L3_A": ["1.3.6.1.2.1.33.1.3.3.1.4.3", "1.3.6.1.4.1.935.10.1.1.2.16.1.4.3"],
    "input_freq_Hz": ["1.3.6.1.2.1.33.1.3.3.1.2.1", "1.3.6.1.4.1.935.10.1.1.2.16.1.2.1"],
    
    # Output
    "output_L1_V": ["1.3.6.1.2.1.33.1.4.4.1.2.1", "1.3.6.1.4.1.935.10.1.1.2.18.1.3.1"],
    "output_L2_V": ["1.3.6.1.2.1.33.1.4.4.1.2.2", "1.3.6.1.4.1.935.10.1.1.2.18.1.3.2"],
    "output_L3_V": ["1.3.6.1.2.1.33.1.4.4.1.2.3", "1.3.6.1.4.1.935.10.1.1.2.18.1.3.3"],
    "output_L1_A": ["1.3.6.1.2.1.33.1.4.4.1.3.1", "1.3.6.1.4.1.935.10.1.1.2.18.1.4.1"],
    "output_L2_A": ["1.3.6.1.2.1.33.1.4.4.1.3.2", "1.3.6.1.4.1.935.10.1.1.2.18.1.4.2"],
    "output_L3_A": ["1.3.6.1.2.1.33.1.4.4.1.3.3", "1.3.6.1.4.1.935.10.1.1.2.18.1.4.3"],
    "output_freq_Hz": ["1.3.6.1.2.1.33.1.4.2.0", "1.3.6.1.4.1.935.10.1.1.2.18.1.2.1"],
    
    # Load
    "load_W": ["1.3.6.1.2.1.33.1.4.4.1.5.1", "1.3.6.1.4.1.935.10.1.1.2.18.1.5.1"],
    "load_VA": ["1.3.6.1.4.1.935.10.1.1.2.18.1.6.1"],
    
    # Identification & ratings
    "ident_manufacturer": ["1.3.6.1.2.1.33.1.1.1.0", "1.3.6.1.4.1.935.10.1.1.1.1.0"],
    "ident_model": ["1.3.6.1.2.1.33.1.1.2.0", "1.3.6.1.4.1.935.10.1.1.1.2.0"],
    "ident_fw": ["1.3.6.1.2.1.33.1.1.3.0", "1.3.6.1.4.1.935.10.1.1.1.3.0"],
    "rating_voltage_v": [
        "1.3.6.1.2.1.33.1.9.2.0",
        "1.3.6.1.4.1.935.10.1.1.2.7.0",
        "1.3.6.1.4.1.935.10.1.1.2.5.0"
    ],
    "rating_frequency_hz": [
        "1.3.6.1.2.1.33.1.9.1.0",
        "1.3.6.1.4.1.935.10.1.1.2.8.0",
        "1.3.6.1.4.1.935.10.1.1.2.6.0"
    ],
    "rating_battery_voltage_v": ["1.3.6.1.2.1.33.1.2.5.0"],
}

# UPS Device Configuration
UPS_DEVICES: Dict[str, Dict[str, Any]] = {
    "10.40.1.10": {
        "brand": SMART_POWER_BRAND,
        "model": "HE-1K-IoT",
        "location": "แฟลตบุคลากร 1",
        "oids": {**STANDARD_OIDS, **EPPC_935_OIDS}
    },
    "10.50.11.11": {
        "brand": SMART_POWER_BRAND,
        "model": "HE-1K-IoT",
        "location": "สำนักส่งเสริม",
        "oids": {**STANDARD_OIDS, **EPPC_935_OIDS}
    },
    "10.50.11.12": {
        "brand": SMART_POWER_BRAND,
        "model": "HE-1K-IoT",
        "location": "ห้องสมุด",
        "oids": {**STANDARD_OIDS, **EPPC_935_OIDS}
    },
    "10.50.11.13": {
        "brand": SMART_POWER_BRAND,
        "model": "HE-1K-IoT",
        "location": "ห้องสมุด",
        "oids": {**STANDARD_OIDS, **EPPC_935_OIDS}
    },
    "10.50.11.64": {
        "brand": SMART_POWER_BRAND,
        "model": "HE-1K-IoT",
        "location": "คณะสัตวแพทย์",
        "oids": {**STANDARD_OIDS, **EPPC_935_OIDS}
    },
    "10.50.11.67": {
        "brand": SMART_POWER_BRAND,
        "model": "HE-1K-IoT",
        "location": "หอพัก 25 ชั้น 1",
        "oids": {**STANDARD_OIDS, **EPPC_935_OIDS}
    },
    "10.50.11.73": {
        "brand": SMART_POWER_BRAND,
        "model": "HE-1K-IoT",
        "location": "หอพัก 25 ชั้น 4",
        "oids": {**STANDARD_OIDS, **EPPC_935_OIDS}
    },
    "10.50.11.75": {
        "brand": SMART_POWER_BRAND,
        "model": "HE-1K-IoT",
        "location": "หอพัก 26 ชั้น 1",
        "oids": {**STANDARD_OIDS, **EPPC_935_OIDS}
    },
    "10.50.11.77": {
        "brand": SMART_POWER_BRAND,
        "model": "HE-1K-IoT",
        "location": "หอพัก 26 ชั้น 2",
        "oids": {**STANDARD_OIDS, **EPPC_935_OIDS}
    },
    "10.50.11.79": {
        "brand": SMART_POWER_BRAND,
        "model": "HE-1K-IoT",
        "location": "หอพัก 26 ชั้น 3",
        "oids": {**STANDARD_OIDS, **EPPC_935_OIDS}
    },
    "10.50.11.81": {
        "brand": SMART_POWER_BRAND,
        "model": "HE-1K-IoT",
        "location": "หอพัก 26 ชั้น 4",
        "oids": {**STANDARD_OIDS, **EPPC_935_OIDS}
    },
    "10.50.11.83": {
        "brand": SMART_POWER_BRAND,
        "model": "HE-1K-IoT",
        "location": "หอพัก 27 ชั้น 1",
        "oids": {**STANDARD_OIDS, **EPPC_935_OIDS}
    },
    "10.50.11.85": {
        "brand": SMART_POWER_BRAND,
        "model": "HE-1K-IoT",
        "location": "หอพัก 27 ชั้น 2",
        "oids": {**STANDARD_OIDS, **EPPC_935_OIDS}
    },
    "10.50.11.87": {
        "brand": SMART_POWER_BRAND,
        "model": "HE-1K-IoT",
        "location": "หอพัก 27 ชั้น 3",
        "oids": {**STANDARD_OIDS, **EPPC_935_OIDS}
    },
    "10.50.11.89": {
        "brand": SMART_POWER_BRAND,
        "model": "HE-1K-IoT",
        "location": "หอพัก 27 ชั้น 4",
        "oids": {**STANDARD_OIDS, **EPPC_935_OIDS}
    },
    "10.50.11.91": {
        "brand": SMART_POWER_BRAND,
        "model": "HE-1K-IoT",
        "location": "หอพัก 28 ชั้น 1",
        "oids": {**STANDARD_OIDS, **EPPC_935_OIDS}
    },
    "10.50.11.93": {
        "brand": SMART_POWER_BRAND,
        "model": "HE-1K-IoT",
        "location": "หอพัก 28 ชั้น 2",
        "oids": {**STANDARD_OIDS, **EPPC_935_OIDS}
    },
    "10.50.8.100": {
        "brand": SMART_POWER_BRAND,
        "model": "HE-1K-IoT",
        "location": "ศูนย์มหาลัย",
        "oids": {**STANDARD_OIDS, **EPPC_935_OIDS}
    },
    "10.50.11.111": {
        "brand": SMART_POWER_BRAND,
        "model": "HE-1K-IoT",
        "location": "หอพัก 30 ชั้น 3",
        "oids": {**STANDARD_OIDS, **EPPC_935_OIDS}
    },
}

# Default configuration values
DEFAULT_CONFIG = {
    "community": "public",
    "snmp_version": "2c",
    "timeout": 1.2,
    "retries": 0,
    "power_factor": 0.8,
    "cache_ttl": 2.0,
}
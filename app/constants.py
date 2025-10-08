"""Application constants."""

# UPS Status Constants
class UPSStatus:
    ONLINE = "Online"
    OFFLINE = "Offline"
    POWERFAIL = "Powerfail"
    WARNING = "warning"
    CRITICAL = "critical"
    ERROR = "error"

# Temperature Thresholds (Celsius)
class TemperatureThresholds:
    WARN = 50
    CRITICAL = 60
    CLEAR = 45

# Battery Thresholds (Percentage)
class BatteryThresholds:
    WARN = 20
    CRITICAL = 10
    CLEAR = 25

# Voltage Thresholds (Volts)
class VoltageThresholds:
    POWER_FAIL = 180.0          # แรงดันต่ำกว่านี้ถือว่าไฟตก
    NOMINAL_MIN = 200.0         # แรงดันปกติขั้นต่ำ
    NOMINAL_MAX = 250.0         # แรงดันปกติสูงสุด
    CRITICAL_LOW = 160.0        # แรงดันต่ำมาก (อันตราย)
    WARNING_LOW = 190.0         # แรงดันต่ำ (เตือน)

# Event Types
class EventTypes:
    POWER_OFFLINE = "power_offline"
    POWER_RECOVERED = "power_recovered"
    TEMP_HIGH = "temp_high"
    BATTERY_LOW = "battery_low"
    VOLTAGE_LOW = "voltage_low"

# Event Severities
class EventSeverities:
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

# SNMP Constants
class SNMPDefaults:
    COMMUNITY = "public"
    VERSION = "2c"
    PORT = 161
    TIMEOUT = 1.2
    RETRIES = 0
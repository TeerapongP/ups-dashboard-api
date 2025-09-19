from sqlalchemy import (
    Column, Integer, BigInteger, String, Float, DateTime,
    Boolean, Enum, ForeignKey, JSON, func, TIMESTAMP, DECIMAL, Text
)
from sqlalchemy.orm import relationship
from datetime import datetime
from db.database import Base


# -------------------------
# Users (คงเดิม)
# -------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password = Column(String(100), nullable=False)


# -------------------------
# UPS Devices (ปรับ id เป็น VARCHAR(50) ให้ตรง DDL)
# DDL: id VARCHAR(50) PRIMARY KEY
# -------------------------
class UPSDevice(Base):
    __tablename__ = "ups_devices"

    id = Column(String(50), primary_key=True)  # <<< เปลี่ยนจาก BigInteger เป็น String(50)
    ip_address = Column(String(15), unique=True, nullable=False)
    brand = Column(String(50), nullable=False)
    model = Column(String(100), nullable=False)
    location = Column(String(100), nullable=False)
    capacity_va = Column(Integer, nullable=False)
    capacity_w = Column(Integer, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    is_active = Column(Boolean, default=True)

    statuses = relationship("UPSStatus", back_populates="device")


# -------------------------
# UPS Status (snapshot ล่าสุดของเครื่อง)
# (ตารางนี้ใน DDL เดิมไม่ได้ให้มา แต่คุณมีใช้อยู่—คงไว้ได้)
# -------------------------
class UPSStatus(Base):
    __tablename__ = "ups_status"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    ups_id = Column(String(50), ForeignKey("ups_devices.id"), nullable=False)  # FK -> VARCHAR(50)
    timestamp = Column(TIMESTAMP, default=datetime.utcnow)

    status = Column(Enum("online", "warning", "critical", "offline"), nullable=False)
    battery_percentage = Column(DECIMAL(5, 2))
    battery_voltage = Column(DECIMAL(6, 2))
    backup_time_minutes = Column(Integer)
    temperature = Column(DECIMAL(4, 1))

    input_voltage_l1 = Column(DECIMAL(6, 2))
    input_voltage_l2 = Column(DECIMAL(6, 2))
    input_voltage_l3 = Column(DECIMAL(6, 2))
    input_current_l1 = Column(DECIMAL(8, 3))
    input_current_l2 = Column(DECIMAL(8, 3))
    input_current_l3 = Column(DECIMAL(8, 3))
    input_frequency = Column(DECIMAL(4, 1))

    input_max_voltage = Column(DECIMAL(6, 2))
    input_min_voltage = Column(DECIMAL(6, 2))

    output_voltage_l1 = Column(DECIMAL(6, 2))
    output_voltage_l2 = Column(DECIMAL(6, 2))
    output_voltage_l3 = Column(DECIMAL(6, 2))
    output_current_l1 = Column(DECIMAL(8, 3))
    output_current_l2 = Column(DECIMAL(8, 3))
    output_current_l3 = Column(DECIMAL(8, 3))
    output_frequency = Column(DECIMAL(4, 1))

    output_load_va = Column(Integer)
    output_load_w = Column(Integer)
    load_percentage = Column(DECIMAL(5, 2))

    device = relationship("UPSDevice", back_populates="statuses")


# -------------------------
# UPS Events (ตาม DDL #7)
# -------------------------
class UPSEvent(Base):
    __tablename__ = "ups_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ups_id = Column(String(50), ForeignKey("ups_devices.id"), nullable=False)

    event_type = Column(String(50), nullable=False)
    severity = Column(Enum("info", "warning", "critical"), nullable=False)
    event_code = Column(String(20))
    message = Column(Text)
    event_data = Column(JSON)

    start_time = Column(TIMESTAMP, server_default=func.now())
    end_time = Column(TIMESTAMP)  # nullable
    duration_seconds = Column(Integer)

    is_resolved = Column(Boolean, default=False)
    resolved_by = Column(String(50))
    created_at = Column(TIMESTAMP, server_default=func.now())

    device = relationship("UPSDevice", backref="events")


# -------------------------
# UPS History (ตาม DDL #8)
# -------------------------
class UPSHistory(Base):
    __tablename__ = "ups_history"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ups_id = Column(String(50), ForeignKey("ups_devices.id"), nullable=False)

    date_hour = Column(DateTime, nullable=False)  # DATETIME NOT NULL
    avg_battery_percent = Column(DECIMAL(5, 2))
    avg_temperature = Column(DECIMAL(4, 1))
    avg_load_percent = Column(DECIMAL(5, 2))
    avg_input_voltage = Column(DECIMAL(6, 2))
    avg_output_voltage = Column(DECIMAL(6, 2))
    min_battery_percent = Column(DECIMAL(5, 2))
    max_battery_percent = Column(DECIMAL(5, 2))
    min_temperature = Column(DECIMAL(4, 1))
    max_temperature = Column(DECIMAL(4, 1))
    total_samples = Column(Integer)

    online_minutes = Column(Integer)
    warning_minutes = Column(Integer)
    critical_minutes = Column(Integer)
    offline_minutes = Column(Integer)

    created_at = Column(TIMESTAMP, server_default=func.now())

    device = relationship("UPSDevice", backref="histories")


# -------------------------
# UPS Status Event (ตาม DDL #9)
# -------------------------
class UPSStatusEvent(Base):
    __tablename__ = "ups_status_event"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ups_id = Column(String(50), ForeignKey("ups_devices.id"), nullable=False)

    old_status = Column(Enum("online", "warning", "critical", "offline"))
    new_status = Column(Enum("online", "warning", "critical", "offline"), nullable=False)

    changed_at = Column(TIMESTAMP, nullable=False)         # WHEN status becomes new_status
    next_changed_at = Column(TIMESTAMP)                    # WHEN status changes again
    duration_sec = Column(Integer)
    note = Column(Text)

    device = relationship("UPSDevice", backref="status_events")

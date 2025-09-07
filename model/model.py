from sqlalchemy import (
    Column, Integer, BigInteger, String, Float, DateTime,
    Boolean, Enum, ForeignKey, JSON, func, TIMESTAMP, DECIMAL
)
from sqlalchemy.orm import relationship
from datetime import datetime

from db.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password = Column(String(100), nullable=False)

class UPSDevice(Base):
    __tablename__ = "ups_devices"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
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

class UPSStatus(Base):
    __tablename__ = "ups_status"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    ups_id = Column(BigInteger, ForeignKey("ups_devices.id"), nullable=False)
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
    
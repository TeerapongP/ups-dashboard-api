# db/ups_db.py
from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    create_engine, Column, String, Integer, Enum, Text, JSON, DateTime,
    Boolean, ForeignKey, DECIMAL
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Mapped, mapped_column, relationship
from db.config import SQLALCHEMY_DATABASE_URL

DB_URL = SQLALCHEMY_DATABASE_URL

engine = create_engine(
    DB_URL,
    pool_pre_ping=True,
    pool_recycle=280,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

class Base(DeclarativeBase):
    pass

class UPSDevice(Base):
    __tablename__ = "ups_devices"
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    ip_address: Mapped[str] = mapped_column(String(15), unique=True, nullable=False)
    brand: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    location: Mapped[str] = mapped_column(String(100), nullable=False)
    capacity_va: Mapped[int] = mapped_column(Integer, nullable=False)
    capacity_w: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, default=True)

class UPSStatus(Base):
    __tablename__ = "ups_status"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ups_id: Mapped[str] = mapped_column(String(50), ForeignKey("ups_devices.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    status: Mapped[str] = mapped_column(Enum("online","warning","critical","offline", name="status_enum"), nullable=False)

    battery_percentage: Mapped[Optional[float]] = mapped_column(DECIMAL(5,2))
    battery_voltage:    Mapped[Optional[float]] = mapped_column(DECIMAL(6,2))
    backup_time_minutes:Mapped[Optional[int]]   = mapped_column(Integer)
    temperature:        Mapped[Optional[float]] = mapped_column(DECIMAL(4,1))

    input_voltage_l1:   Mapped[Optional[float]] = mapped_column(DECIMAL(6,2))
    input_voltage_l2:   Mapped[Optional[float]] = mapped_column(DECIMAL(6,2))
    input_voltage_l3:   Mapped[Optional[float]] = mapped_column(DECIMAL(6,2))
    input_current_l1:   Mapped[Optional[float]] = mapped_column(DECIMAL(8,3))
    input_current_l2:   Mapped[Optional[float]] = mapped_column(DECIMAL(8,3))
    input_current_l3:   Mapped[Optional[float]] = mapped_column(DECIMAL(8,3))
    input_frequency:    Mapped[Optional[float]] = mapped_column(DECIMAL(4,1))

    output_voltage_l1:  Mapped[Optional[float]] = mapped_column(DECIMAL(6,2))
    output_voltage_l2:  Mapped[Optional[float]] = mapped_column(DECIMAL(6,2))
    output_voltage_l3:  Mapped[Optional[float]] = mapped_column(DECIMAL(6,2))
    output_current_l1:  Mapped[Optional[float]] = mapped_column(DECIMAL(8,3))
    output_current_l2:  Mapped[Optional[float]] = mapped_column(DECIMAL(8,3))
    output_current_l3:  Mapped[Optional[float]] = mapped_column(DECIMAL(8,3))
    output_frequency:   Mapped[Optional[float]] = mapped_column(DECIMAL(4,1))

    output_load_va:     Mapped[Optional[int]]   = mapped_column(Integer)
    output_load_w:      Mapped[Optional[int]]   = mapped_column(Integer)
    load_percentage:    Mapped[Optional[float]] = mapped_column(DECIMAL(5,2))

class UPSEvent(Base):
    __tablename__ = "ups_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ups_id: Mapped[str] = mapped_column(String(50), ForeignKey("ups_devices.id"), nullable=False)

    event_type: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. power_offline, temp_high, battery_low
    severity:   Mapped[str] = mapped_column(Enum("info","warning","critical", name="severity_enum"), nullable=False)
    event_code: Mapped[Optional[str]] = mapped_column(String(20))
    message:    Mapped[Optional[str]] = mapped_column(Text)
    event_data: Mapped[Optional[dict]] = mapped_column(JSON)

    start_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    end_time:   Mapped[Optional[datetime]] = mapped_column(DateTime)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(50))

def init_db():
    Base.metadata.create_all(engine)

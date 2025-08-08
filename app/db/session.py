import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

load_dotenv()  # โหลดไฟล์ .env

SQLALCHEMY_DATABASE_URL = os.getenv("SQLALCHEMY_DATABASE_URL")

if not SQLALCHEMY_DATABASE_URL:
    raise ValueError("Missing SQLALCHEMY_DATABASE_URL environment variable")

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=True,           # เปิดดู SQL log (ปิดได้ถ้าไม่ต้องการ)
    pool_pre_ping=True   # ป้องกัน connection หลุด
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

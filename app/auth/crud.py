from db.database import SessionLocal
from model.model import User
from app.auth.schemas import UserCreate
from passlib.context import CryptContext

from app.auth.schemas import UserCreate, UserUpdate  # ตัวอย่าง import ที่ใช้จริง (แก้ตามจริง)

def get_user(username: str):
    db = SessionLocal()
    user = db.query(User).filter(User.username == username).first()
    db.close()
    return user

def create_user(user_in: UserCreate):
    db = SessionLocal()
    hashed_password = pwd_context.hash(user_in.password)
    db_user = User(username=user_in.username, password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    db.close()
    return db_user

def authenticate_user(username: str, password: str):
    user = get_user(username)
    if not user:
        return False
    if not pwd_context.verify(password, user.password):
        return False
    return user

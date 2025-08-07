# ลบ import ไม่ใช้ออก
# from app.auth.schemas import User  <- ลบออก

from app.auth.schemas import UserCreate, UserUpdate  # ตัวอย่าง import ที่ใช้จริง (แก้ตามจริง)

# เว้นบรรทัด 2 บรรทัด ก่อนฟังก์ชัน/คลาส

def get_user():
    pass


def create_user():
    raise NotImplementedError()


def update_user():
   raise NotImplementedError()

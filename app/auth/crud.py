from passlib.context import CryptContext
from app.auth.schemas import UserInDB, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ตัวอย่าง fake DB
fake_users_db = {
    "alice": {
        "username": "alice",
        "hashed_password": pwd_context.hash("secret"),
        "disabled": False,
    }
}

def get_user(username: str) -> UserInDB | None:
    user = fake_users_db.get(username)
    if user:
        return UserInDB(**user)
    return None

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def authenticate_user(username: str, password: str) -> UserInDB | None:
    user = get_user(username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user

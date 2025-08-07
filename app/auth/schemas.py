from pydantic import BaseModel


class UserBase(BaseModel):
    email: str
    is_active: bool


class UserCreate(UserBase):
    password: str


class UserUpdate(UserBase):
    password: str | None = None

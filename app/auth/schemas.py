from pydantic import BaseModel
<<<<<<< HEAD

class UserBase(BaseModel):
    username: str

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int

    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str
=======


class UserBase(BaseModel):
    email: str
    is_active: bool


class UserCreate(UserBase):
    password: str


class UserUpdate(UserBase):
    password: str | None = None
>>>>>>> 166c063 (Refactor authentication and schema handling; improve JWT token creation)

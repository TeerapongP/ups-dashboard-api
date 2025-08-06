from pydantic import BaseModel
from typing import Optional

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenPayload(BaseModel):
    sub: Optional[str] = None

class User(BaseModel):
    username: str
    disabled: Optional[bool] = False

class UserInDB(User):
    hashed_password: str

from pydantic import BaseModel
from typing import Optional

class UserBase(BaseModel):
    id: int
    username: str
    disabled: Optional[bool] = False

class UserInDB(UserBase):
    hashed_password: str
    
class User(UserBase):
    pass 

class Token(BaseModel):
    access_token: str
    token_type: str

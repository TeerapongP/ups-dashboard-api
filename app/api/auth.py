from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from app.auth import crud, schemas 
from app.auth.deps import get_current_user
from core import security as jwt_handler 
from fastapi import Response
from model.response_model import MessageResponse
import os

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login") 
IS_DEV = os.getenv("ENV", "dev") == "dev"

@router.post("/register", response_model=schemas.User)
async def register(user_in: schemas.UserCreate):
    existing_user = crud.get_user(user_in.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    user = crud.create_user(user_in)
    return user

@router.post("/login", response_model=MessageResponse)
async def login(response: Response, form_data: OAuth2PasswordRequestForm = Depends()):
    user = crud.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    access_token = jwt_handler.create_access_token(subject=user.username)

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=not IS_DEV,                   
        samesite="lax" if IS_DEV else "none",
        max_age=7 * 24 * 60 * 60,
        path="/",                            
    )

    return {"message": "login success"}

@router.get("/me")
def read_users_me(current_user: schemas.User = Depends(get_current_user)):
    return {"user": current_user}


@router.post("/logout", response_model=MessageResponse)
async def logout(response: Response):
    # ลบ cookie โดยการ set max_age = 0
    response.delete_cookie(
        key="access_token",
        path="/",
        samesite="lax" if IS_DEV else "none",
        secure=not IS_DEV,
    )

    return {"message": "logout success"}
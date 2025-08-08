from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from app.auth import crud, schemas
from core import security as jwt_handler 
from fastapi import Response



router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")  # ตรงกับ path login

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

@router.post("/login", response_model=schemas.Token)
async def login(response: Response, form_data: OAuth2PasswordRequestForm = Depends()):
    user = crud.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    access_token = jwt_handler.create_access_token(subject=user.username)
    
    # เซ็ต cookie HttpOnly, Secure (ใน dev ใช้ secure=False)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,  # ใน production ต้องเป็น True (https)
        samesite="lax",
        max_age=7 * 24 * 60 * 60,  # 7 วัน
    )
    
    return {"access_token": access_token, "token_type": "bearer"}


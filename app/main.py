from fastapi import FastAPI,Depends
from fastapi.middleware.cors import CORSMiddleware
from app.api.auth import router as auth_router
from app.api.endpoints.endpoints import router as endpoints_router
from app.auth.deps import get_current_user

from db.database import Base, engine
from model.model import User

app = FastAPI()
Base.metadata.create_all(bind=engine)

origins = [
    "http://localhost:3000",
    "http://158.108.196.162:3000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(
    endpoints_router,
    prefix="/api",
    tags=["ups"],
)  
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])

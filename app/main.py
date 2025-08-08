from fastapi import FastAPI
from app.api.auth import router as auth_router
from app.api.endpoints.endpoints import router as status_router
from db.database import Base, engine
from model.model import User

app = FastAPI()
Base.metadata.create_all(bind=engine)

app.include_router(status_router, prefix="/api")
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])

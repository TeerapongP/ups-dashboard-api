from fastapi import FastAPI
from app.api.endpoints import status
from app.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION
)

app.include_router(status.router, prefix="/api")

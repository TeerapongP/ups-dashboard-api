from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import router as auth_router
from app.api.endpoints.endpoints import router as endpoints_router
from app.api.endpoints.snmp_endpoints import router as snmp_router
from db.database import Base, engine
from app.scheduler import start_scheduler
from core.security import require_token

# ✅ นำเข้า util ที่ sanitize error
from app.utils.errors import sanitize_db_error

app = FastAPI()
Base.metadata.create_all(bind=engine)

origins = [
    "http://localhost:3000",
    "http://158.108.196.162:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Global Exception Handlers ----------
@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    http_status, safe_msg = sanitize_db_error(exc)
    # TODO: logger.exception("SQLAlchemy error", exc_info=exc)  # (แนะนำ log ภายใน)
    return JSONResponse(status_code=http_status, content={"detail": safe_msg})

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    http_status, safe_msg = sanitize_db_error(exc)
    # TODO: logger.exception("Unhandled error", exc_info=exc)
    return JSONResponse(status_code=http_status, content={"detail": safe_msg})

# ---------- Routers ----------
app.include_router(endpoints_router, prefix="/api", tags=["ups"])
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(
    snmp_router,
    prefix="/api",
    dependencies=[Depends(require_token)],  # ใช้ token กับทุกเส้น /api/snmp/*
    tags=["SNMP / OID"],
)

@app.on_event("startup")
def startup_event():
    start_scheduler()

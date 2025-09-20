from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.endpoints.endpoints import router as endpoints_router
from app.api.endpoints.snmp_endpoints import router as snmp_router  
from db.database import Base, engine
from app.scheduler import start_scheduler
from core.security import require_token  

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

# รวมทุก router ไว้ที่นี่
app.include_router(endpoints_router, prefix="/api", tags=["ups"])
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(
    snmp_router,
    prefix="/api",
    dependencies=[Depends(require_token)],
    tags=["SNMP / OID"],
)

@app.on_event("startup")
def startup_event():
    start_scheduler()

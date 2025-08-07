from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/status")
def read_status() -> dict:
    return {"status": "UPS System OK"}

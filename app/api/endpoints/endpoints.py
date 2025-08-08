from fastapi import APIRouter

router = APIRouter()

# กำหนด routes ที่นี่ เช่น
@router.get("/status")
async def status():
    return {"status": "OK"}

from app.api.routes.getAll import UPS_OID_MAP, get_ups_data
from fastapi import APIRouter

router = APIRouter()

# กำหนด routes ที่นี่ เช่น
@router.get("/status")
async def status():
    return {"status": "OK"}


@router.get("/get_all")
def get_all_ups():
    results = []
    for ip, config in UPS_OID_MAP.items():
        data = get_ups_data(ip, config)
        results.append(data)
    return results

from fastapi import APIRouter

router = APIRouter(prefix="/billing", tags=["Billing"])


@router.get("/ping")
def ping():
    return {"module": "billing", "status": "ok"}
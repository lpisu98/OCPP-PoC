from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from charge_point import ChargePoint

router = APIRouter()

# Initialize the ChargePoint instance
charge_point = ChargePoint('CP_1', None)  # Replace None with actual websocket connection if needed

class StartTransactionRequest(BaseModel):
    id_tag: str

class StopTransactionRequest(BaseModel):
    reason: str = "Local"

@router.post("/start_transaction")
async def start_transaction(request: StartTransactionRequest):
    try:
        transaction_id = await charge_point._start_transaction(id_tag=request.id_tag)
        return {"transaction_id": transaction_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stop_transaction")
async def stop_transaction(request: StopTransactionRequest):
    try:
        await charge_point._stop_transaction(reason=request.reason)
        return {"detail": "Transaction stopped successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/boot_notification")
async def boot_notification():
    try:
        await charge_point.send_boot_notification()
        return {"detail": "Boot notification sent successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/status_notification")
async def status_notification(status: str):
    try:
        await charge_point.send_status(status)
        return {"detail": f"Status notification sent: {status}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
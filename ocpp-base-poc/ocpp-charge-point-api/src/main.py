from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router as api_router
from charge_point import ChargePoint
import websockets
import asyncio

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

charge_point = ChargePoint('CP_1', None)  # Replace None with actual websocket connection if needed

@app.on_event("startup")
async def startup_event():
    await charge_point.send_boot_notification()
    await charge_point.start_background_tasks()

@app.on_event("shutdown")
async def shutdown_event():
    await charge_point.stop_background_tasks()

app.include_router(api_router)
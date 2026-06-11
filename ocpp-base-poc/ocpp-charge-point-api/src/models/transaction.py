from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class Transaction(BaseModel):
    id: str
    id_tag: str
    meter_start: int
    meter_stop: Optional[int] = None
    timestamp_start: datetime
    timestamp_stop: Optional[datetime] = None
    status: str  # e.g., "Charging", "Stopped"

class TransactionCreate(BaseModel):
    id_tag: str
    meter_start: int

class TransactionUpdate(BaseModel):
    meter_stop: int
    timestamp_stop: datetime
    status: str  # e.g., "Stopped"
from pydantic import BaseModel
from typing import Optional

class StartTransactionRequest(BaseModel):
    id_tag: str
    meter_start_wh: Optional[int] = 0

class StartTransactionResponse(BaseModel):
    transaction_id: str

class StopTransactionRequest(BaseModel):
    reason: Optional[str] = "Local"

class StopTransactionResponse(BaseModel):
    status: str

class StatusNotificationRequest(BaseModel):
    status: str
    error_code: Optional[str] = "NoError"
    vendor_id: Optional[str] = None
    vendor_error_code: Optional[str] = None

class HeartbeatResponse(BaseModel):
    status: str

class ChangeConfigurationRequest(BaseModel):
    key: str
    value: str

class ChangeConfigurationResponse(BaseModel):
    status: str

class GetConfigurationRequest(BaseModel):
    key: Optional[list[str]] = [] 

class GetConfigurationResponse(BaseModel):
    configuration_key: Optional[list[dict]] = []
    unknown_key: Optional[list[str]] = []
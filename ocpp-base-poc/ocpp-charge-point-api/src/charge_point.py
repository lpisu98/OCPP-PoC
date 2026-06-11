import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from dataclasses import make_dataclass, field as dc_field

import websockets
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ocpp.v16 import call, ChargePoint as cp
from ocpp.v16.enums import RegistrationStatus, AvailabilityType
from ocpp.routing import on

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("charge_point")


def _dataclassify(payload: Any, name: str = "Response"):
    """Convert a dict payload into a simple dataclass instance.

    python-ocpp expects handler return values to be dataclass instances
    so that it can call ``asdict()``. Wrapping dicts in a lightweight
    dataclass avoids the TypeError seen when returning plain dicts.
    """
    if payload is None:
        return None
    # If already a dataclass-like object, return as-is
    if hasattr(payload, "__dataclass_fields__"):
        return payload
    if isinstance(payload, dict):
        fields = []
        for k in payload.keys():
            fields.append((k, Any, dc_field(default=None)))
        DC = make_dataclass(name, fields)
        return DC(**payload)
    return payload


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup event
    LOG.info("API started. Call POST /connect to connect to Steve.")
    yield
    # Shutdown event
    await charge_point.stop_background_tasks()


app = FastAPI(lifespan=lifespan)

def _call_cls(name: str):
    cls = getattr(call, name, None)
    if cls is None:
        raise RuntimeError(f"OCPP call class not found: {name}")
    return cls


class ChargePoint(cp):
    def __init__(self, *args, connector_id=1, **kwargs):
        super().__init__(*args, **kwargs)
        self.connector_id = connector_id
        self._tasks = set()
        self._transaction = None
        self._running = True
        self._ws = None
        self._connect_lock = asyncio.Lock()
        self._connected_uri: Optional[str] = None
        self._config: Dict[str, str] = {
            "HeartbeatInterval": "14400",
            "MaxChargingProfilesInstalled": "42",
            "GetConfigurationMaxKeys": "100",
            "AllowOfflineTxForUnknownId": "True",
            "AuthorizationCacheEnabled": "True",
            "WebSocketPingInterval": "60",
        }
        self._availability_status = "Operative"  # "Operative" or "Inoperative"
        self._reservations: Dict[int, Dict] = {}

    async def connect(self, ws_uri: str):
        async with self._connect_lock:
            if self._ws is not None and not getattr(self._ws, "closed", False):
                return

            self._ws = await websockets.connect(ws_uri, subprotocols=["ocpp1.6"])
            self._connection = self._ws
            self._connected_uri = ws_uri

            listener = asyncio.create_task(self.start(), name="ocpp-listener")
            self._tasks.add(listener)
            listener.add_done_callback(self._tasks.discard)

            LOG.info("Connected to central system: %s", ws_uri)

    async def disconnect(self):
        async with self._connect_lock:
            if self._ws is not None and not getattr(self._ws, "closed", False):
                try:
                    await self._ws.close()
                except Exception:
                    # Some websocket client implementations may not expose close as an awaitable
                    try:
                        close_m = getattr(self._ws, "close", None)
                        if callable(close_m):
                            maybe = close_m()
                            if asyncio.iscoroutine(maybe):
                                await maybe
                    except Exception:
                        LOG.debug("Failed to close websocket cleanly")

            tasks = list(self._tasks)
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            self._tasks.clear()
            self._ws = None
            self._connection = None
            self._connected_uri = None

    async def stop_background_tasks(self):
        await self.disconnect()

    async def send_boot_notification(self):
        boot_cls = _call_cls("BootNotification")
        request = boot_cls(
            charge_point_model='Wallbox XYZ',
            charge_point_vendor='anewone'
        )
        response = await self.call(request)
        if response.status == RegistrationStatus.accepted:
            LOG.info("BootNotification accepted by central system")
        else:
            LOG.warning("BootNotification not accepted: %s", getattr(response, "status", response))

    async def _start_transaction(self, id_tag="SIMULATED_ID", meter_start_wh=0):
        tx_id = str(uuid.uuid4())
        meter_start = int(meter_start_wh)
        start_cls = _call_cls("StartTransaction")
        payload = start_cls(
            connector_id=self.connector_id,
            id_tag=id_tag,
            meter_start=meter_start,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        try:
            # Wait for central system response, but don't block HTTP forever
            response = await asyncio.wait_for(self.call(payload), timeout=10)
        except asyncio.TimeoutError:
            LOG.error("StartTransaction timed out waiting for central system response")
            return None
        except Exception as exc:
            LOG.exception("StartTransaction failed: %s", exc)
            return None

        # Inspect id tag authorization result (idTagInfo.status)
        LOG.info("StartTransaction response object: %s", response)
        LOG.info("Response type: %s, dir: %s", type(response), dir(response))

        # Support both camelCase and snake_case from different library versions
        id_tag_info = getattr(response, "idTagInfo", None) or getattr(response, "id_tag_info", None)
        # Normalize to dict-like access
        id_tag_status = None
        try:
            if id_tag_info is not None:
                if hasattr(id_tag_info, "status"):
                    id_tag_status = getattr(id_tag_info, "status", None)
                elif isinstance(id_tag_info, dict):
                    id_tag_status = id_tag_info.get("status") or id_tag_info.get("Status")
        except Exception:
            id_tag_status = None

        if id_tag_status and str(id_tag_status).lower() != "accepted":
            LOG.warning("StartTransaction rejected by central system for id_tag=%s: idTagInfo=%s", id_tag, id_tag_info)
            # Store last idTagInfo dict for external inspection (HTTP API)
            try:
                if hasattr(id_tag_info, "status"):
                    expiry = getattr(id_tag_info, "expiryDate", None) or getattr(id_tag_info, "expiry_date", None)
                    self._last_id_tag_info = {"status": getattr(id_tag_info, "status", None), "expiryDate": expiry}
                elif isinstance(id_tag_info, dict):
                    self._last_id_tag_info = {"status": id_tag_info.get("status"), "expiryDate": id_tag_info.get("expiryDate") or id_tag_info.get("expiry_date")}
                else:
                    self._last_id_tag_info = {"status": id_tag_status}
            except Exception:
                self._last_id_tag_info = {"status": id_tag_status}
            # Do not set local transaction if authorization not accepted
            return None

        # Authorization ok — record local transaction state
        # Support both camelCase and snake_case for transaction id
        remote_tx_id = getattr(response, "transactionId", None) or getattr(response, "transaction_id", None)
        LOG.info("Extracted transactionId from response: %s", remote_tx_id)
        self._transaction = {
            "id": tx_id,
            "remote_transaction_id": remote_tx_id,
            "meter_wh": meter_start,
            "meter_start": meter_start,
            "id_tag": id_tag,
        }
        await self.send_status("Charging")
        LOG.info("Started transaction %s (remote id: %s)", tx_id, remote_tx_id)
        return tx_id

    async def _stop_transaction(self, reason="Local"):
        if not self._transaction:
            return
        remote_tx_id = self._transaction.get("remote_transaction_id")
        if remote_tx_id is None:
            LOG.error("Cannot stop transaction: remote_transaction_id is None. Transaction details: %s", self._transaction)
            self._transaction = None
            return
        stop_cls = _call_cls("StopTransaction")
        meter_stop = int(self._transaction["meter_wh"])
        LOG.info("Stopping transaction with remote_id=%s, meter_stop=%d", remote_tx_id, meter_stop)
        payload = stop_cls(
            meter_stop=meter_stop,
            id_tag=self._transaction.get("id_tag"),
            timestamp=datetime.now(timezone.utc).isoformat(),
            transaction_id=remote_tx_id,
            reason=reason
        )
        await self.call(payload)
        LOG.info("Stopped transaction %s", self._transaction.get("id"))
        self._transaction = None

    async def send_status(self, status, error_code="NoError", vendor_id=None, vendor_error_code=None):
        status_cls = _call_cls("StatusNotification")
        payload = status_cls(
            connector_id=self.connector_id,
            error_code=error_code,
            status=status,
            vendor_id=vendor_id,
            vendor_error_code=vendor_error_code
        )
        await self.call(payload)
        LOG.info("StatusNotification sent: %s", status)

    # ============================================================================
    # OCPP Request Handlers (messages from central system to charge point)
    # ============================================================================

    @on("GetConfiguration")
    async def on_get_configuration(self, key, **kwargs):
        """Handle GetConfiguration request from central system."""
        LOG.info("Received GetConfiguration request for keys: %s", key)
        try:
            config_key_value_list = []
            unknown_keys = []

            # Treat empty list the same as no key (return all)
            if not key:
                for k, v in self._config.items():
                    config_key_value_list.append({
                        "key": k,
                        "readonly": False,
                        "value": v
                    })
            else:
                for requested_key in key:
                    if requested_key in self._config:
                        config_key_value_list.append({
                            "key": requested_key,
                            "readonly": False,
                            "value": self._config[requested_key]
                        })
                    else:
                        unknown_keys.append(requested_key)

            return _dataclassify({
                "configurationKey": config_key_value_list,
                "unknownKey": unknown_keys
            }, "GetConfigurationResponse")
        except Exception as exc:
            LOG.exception("Error while handling GetConfiguration: %s", exc)
            # Avoid raising exceptions to the OCPP layer — return empty result instead
            return _dataclassify({"configurationKey": [], "unknownKey": []}, "GetConfigurationResponse")

    @on("ChangeConfiguration")
    async def on_change_configuration(self, key, value, **kwargs):
        """Handle ChangeConfiguration request from central system."""
        LOG.info("Received ChangeConfiguration request: %s = %s", key, value)
        
        # In a real implementation, validate and apply configuration
        self._config[key] = value
        
        LOG.info("Configuration updated: %s = %s", key, value)
        return _dataclassify({"status": "Accepted"}, "ChangeConfigurationResponse")

    @on("ChangeAvailability")
    async def on_change_availability(self, connector_id, type, **kwargs):
        """Handle ChangeAvailability request from central system."""
        LOG.info("Received ChangeAvailability request: connector_id=%s, type=%s", connector_id, type)
        
        if connector_id == 0 or connector_id == self.connector_id:
            self._availability_status = "Operative" if type == AvailabilityType.operative else "Inoperative"
            LOG.info("Availability changed to: %s", self._availability_status)
            return _dataclassify({"status": "Accepted"}, "ChangeAvailabilityResponse")
        else:
            LOG.warning("Invalid connector_id: %s", connector_id)
            return _dataclassify({"status": "Rejected"}, "ChangeAvailabilityResponse")

    @on("RemoteStartTransaction")
    async def on_remote_start_transaction(self, connector_id, id_tag, **kwargs):
        """Handle RemoteStartTransaction request from central system."""
        LOG.info("Received RemoteStartTransaction request: connector_id=%s, id_tag=%s", connector_id, id_tag)
        
        if self._transaction:
            LOG.warning("Transaction already active")
            return _dataclassify({"status": "Rejected"}, "RemoteStartTransactionResponse")
        
        # In a real charge point, this would start the actual charging
        await self._start_transaction(id_tag=id_tag)
        return _dataclassify({"status": "Accepted"}, "RemoteStartTransactionResponse")

    @on("RemoteStopTransaction")
    async def on_remote_stop_transaction(self, transaction_id, **kwargs):
        """Handle RemoteStopTransaction request from central system."""
        LOG.info("Received RemoteStopTransaction request: transaction_id=%s", transaction_id)
        
        if not self._transaction:
            LOG.warning("No active transaction to stop")
            return _dataclassify({"status": "Rejected"}, "RemoteStopTransactionResponse")
        
        await self._stop_transaction(reason="Remote")
        return _dataclassify({"status": "Accepted"}, "RemoteStopTransactionResponse")

    @on("SetChargingProfile")
    async def on_set_charging_profile(self, connector_id, charging_profile, **kwargs):
        """Handle SetChargingProfile request from central system."""
        LOG.info("Received SetChargingProfile request for connector_id=%s", connector_id)
        
        # In a real implementation, validate and store the charging profile
        LOG.info("Charging profile accepted: %s", charging_profile)
        return _dataclassify({"status": "Accepted"}, "SetChargingProfileResponse")

    @on("ReserveNow")
    async def on_reserve_now(self, connector_id, reservation_id, expiry_date, parent_id, id_tag, **kwargs):
        """Handle ReserveNow request from central system."""
        LOG.info("Received ReserveNow request: connector_id=%s, reservation_id=%s, id_tag=%s", 
                 connector_id, reservation_id, id_tag)
        
        if connector_id != 0 and connector_id != self.connector_id:
            LOG.warning("Invalid connector_id: %s", connector_id)
            return _dataclassify({"status": "Unavailable"}, "ReserveNowResponse")
        
        if self._transaction and self._transaction.get("id_tag") != id_tag:
            LOG.warning("Connector already in use")
            return _dataclassify({"status": "Occupied"}, "ReserveNowResponse")
        
        # Store reservation
        self._reservations[reservation_id] = {
            "connector_id": connector_id,
            "expiry_date": expiry_date,
            "id_tag": id_tag,
            "parent_id": parent_id
        }
        LOG.info("Reservation created: %s", reservation_id)
        return _dataclassify({"status": "Accepted"}, "ReserveNowResponse")

    @on("CancelReservation")
    async def on_cancel_reservation(self, reservation_id, **kwargs):
        """Handle CancelReservation request from central system."""
        LOG.info("Received CancelReservation request: reservation_id=%s", reservation_id)
        
        if reservation_id in self._reservations:
            del self._reservations[reservation_id]
            LOG.info("Reservation cancelled: %s", reservation_id)
            return _dataclassify({"status": "Accepted"}, "CancelReservationResponse")
        else:
            LOG.warning("Reservation not found: %s", reservation_id)
            return _dataclassify({"status": "Rejected"}, "CancelReservationResponse")

    @on("UnlockConnector")
    async def on_unlock_connector(self, connector_id, **kwargs):
        """Handle UnlockConnector request from central system."""
        LOG.info("Received UnlockConnector request: connector_id=%s", connector_id)
        
        # In a real charge point, this would physically unlock the connector
        if connector_id == 0 or connector_id == self.connector_id:
            LOG.info("Connector unlocked")
            return _dataclassify({"status": "Unlocked"}, "UnlockConnectorResponse")
        else:
            LOG.warning("Invalid connector_id: %s", connector_id)
            return _dataclassify({"status": "UnlockFailed"}, "UnlockConnectorResponse")

    @on("Authorize")
    async def on_authorize(self, id_tag, **kwargs):
        """Handle Authorize request from central system."""
        LOG.info("Received Authorize request: id_tag=%s", id_tag)
        
        # In a real implementation, check against authorization database
        LOG.info("Authorization accepted for id_tag: %s", id_tag)
        return _dataclassify({
            "idTagInfo": {
                "status": "Accepted",
                "expiryDate": None
            }
        }, "AuthorizeResponse")

    @on("Reset")
    async def on_reset(self, type, **kwargs):
        """Handle Reset request from central system."""
        LOG.info("Received Reset request: type=%s", type)
        
        # In a real charge point, perform appropriate reset (Soft or Hard)
        if self._transaction:
            await self._stop_transaction(reason="Reset")
        
        LOG.info("Charge point reset (type=%s)", type)
        return _dataclassify({"status": "Accepted"}, "ResetResponse")

    @on("ClearCache")
    async def on_clear_cache(self, **kwargs):
        """Handle ClearCache request from central system."""
        LOG.info("Received ClearCache request")
        
        # In a real implementation, clear the authorization cache
        LOG.info("Cache cleared")
        return _dataclassify({"status": "Accepted"}, "ClearCacheResponse")

    @on("StartDiagnostics")
    async def on_start_diagnostics(self, location, **kwargs):
        """Handle StartDiagnostics request from central system."""
        LOG.info("Received StartDiagnostics request: location=%s", location)
        
        # In a real implementation, start diagnostics upload
        LOG.info("Diagnostics started")
        return _dataclassify({"fileName": "diagnostics_dump_001.txt"}, "StartDiagnosticsResponse")

    @on("GetDiagnostics")
    async def on_get_diagnostics(self, location, **kwargs):
        """Handle GetDiagnostics request from central system."""
        LOG.info("Received GetDiagnostics request: location=%s", location)
        
        # In a real implementation, return diagnostics data
        LOG.info("Diagnostics retrieved")
        return _dataclassify({"fileName": "diagnostics_dump_001.txt"}, "GetDiagnosticsResponse")

    @on("UpdateFirmware")
    async def on_update_firmware(self, location, retrieve_date, **kwargs):
        """Handle UpdateFirmware request from central system."""
        LOG.info("Received UpdateFirmware request: location=%s", location)
        
        # In a real implementation, trigger firmware update
        LOG.info("Firmware update initiated")
        return _dataclassify({}, "UpdateFirmwareResponse")

    @on("SendLocalList")
    async def on_send_local_list(self, list_version, local_authorization_list, update_type, **kwargs):
        """Handle SendLocalList request from central system."""
        LOG.info("Received SendLocalList request (v%s, type=%s, %d entries)", 
                 list_version, update_type, len(local_authorization_list))
        
        # In a real implementation, update local authorization list
        LOG.info("Local authorization list updated")
        return _dataclassify({"status": "Accepted"}, "SendLocalListResponse")

    @on("DataTransfer")
    async def on_data_transfer(self, vendor_id, message_id, data, **kwargs):
        """Handle DataTransfer request from central system (vendor-specific)."""
        LOG.info("Received DataTransfer request: vendor_id=%s, message_id=%s", vendor_id, message_id)
        
        # Echo back the data as a simple implementation
        return _dataclassify({
            "status": "Accepted",
            "data": data
        }, "DataTransferResponse")

charge_point = ChargePoint("CP_1", None)


class ConnectRequest(BaseModel):
    websocket_uri: str = Field(..., description="e.g. ws://localhost:8180/steve/websocket/CentralSystemService/CP_1")


class TransactionRequest(BaseModel):
    id_tag: str


class ConfigurationRequest(BaseModel):
    key: str
    value: str


class AvailabilityRequest(BaseModel):
    type: str  # "Inoperative" or "Operative"


class ReservationRequest(BaseModel):
    connector_id: int
    reservation_id: int
    expiry_date: str
    id_tag: str
    parent_id: Optional[int] = None


class ResetRequest(BaseModel):
    type: str  # "Soft" or "Hard"


class DiagnosticsRequest(BaseModel):
    location: str


class UpdateFirmwareRequest(BaseModel):
    location: str


@app.post("/connect")
async def connect_to_central_system(request: ConnectRequest):
    try:
        await charge_point.connect(request.websocket_uri)
        await charge_point.send_boot_notification()
        return {"status": "connected", "websocket_uri": request.websocket_uri}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/start_transaction")
async def start_transaction(request: TransactionRequest):
    try:
        tx_id = await charge_point._start_transaction(id_tag=request.id_tag)
        if tx_id is None:
            # StartTransaction was rejected by the central system (e.g., idTag not authorized)
            id_info = getattr(charge_point, "_last_id_tag_info", None)
            raise HTTPException(status_code=400, detail={"message": "StartTransaction rejected by central system (idTag not accepted)", "idTagInfo": id_info})
        return {"transaction_id": tx_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/stop_transaction")
async def stop_transaction():
    try:
        await charge_point._stop_transaction(reason="Local")
        return {"status": "Transaction stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Configuration and Status Endpoints
# ============================================================================

@app.get("/configuration")
async def get_configuration():
    """Get current charge point configuration."""
    try:
        return {"configuration": charge_point._config}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/configuration")
async def set_configuration(request: ConfigurationRequest):
    """Update charge point configuration."""
    try:
        charge_point._config[request.key] = request.value
        return {"status": "updated", "key": request.key, "value": request.value}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/availability")
async def change_availability(request: AvailabilityRequest):
    """Change charge point availability."""
    try:
        new_status = "Operative" if request.type == "Operative" else "Inoperative"
        charge_point._availability_status = new_status
        return {"status": "changed", "availability": new_status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/availability")
async def get_availability():
    """Get current availability status."""
    try:
        return {"availability": charge_point._availability_status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reserve")
async def create_reservation(request: ReservationRequest):
    """Create a reservation for the charge point."""
    try:
        charge_point._reservations[request.reservation_id] = {
            "connector_id": request.connector_id,
            "expiry_date": request.expiry_date,
            "id_tag": request.id_tag,
            "parent_id": request.parent_id
        }
        return {"status": "created", "reservation_id": request.reservation_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/reservations")
async def get_reservations():
    """Get all active reservations."""
    try:
        return {"reservations": charge_point._reservations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/reservations/{reservation_id}")
async def cancel_reservation(reservation_id: int):
    """Cancel a reservation."""
    try:
        if reservation_id in charge_point._reservations:
            del charge_point._reservations[reservation_id]
            return {"status": "cancelled", "reservation_id": reservation_id}
        else:
            raise HTTPException(status_code=404, detail="Reservation not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/unlock")
async def unlock_connector():
    """Unlock the connector."""
    try:
        LOG.info("Connector unlock requested via HTTP")
        return {"status": "unlocked"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reset")
async def reset_charge_point(request: ResetRequest):
    """Reset the charge point."""
    try:
        LOG.info("Charge point reset requested: type=%s", request.type)
        if charge_point._transaction:
            await charge_point._stop_transaction(reason="Reset")
        return {"status": "reset", "type": request.type}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/clear-cache")
async def clear_cache():
    """Clear the charge point cache."""
    try:
        LOG.info("Cache clear requested")
        return {"status": "cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/diagnostics/start")
async def start_diagnostics(request: DiagnosticsRequest):
    """Start diagnostics collection."""
    try:
        LOG.info("Diagnostics started: location=%s", request.location)
        return {"status": "started", "fileName": "diagnostics_dump_001.txt"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/firmware/update")
async def update_firmware(request: UpdateFirmwareRequest):
    """Initiate firmware update."""
    try:
        LOG.info("Firmware update initiated: location=%s", request.location)
        return {"status": "initiated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status")
async def get_charge_point_status():
    """Get current charge point status."""
    try:
        return {
            "charge_point_id": charge_point.id,
            "connected": charge_point._ws is not None and not charge_point._ws.closed,
            "availability": charge_point._availability_status,
            "transaction_active": charge_point._transaction is not None,
            "transaction_id": charge_point._transaction.get("id") if charge_point._transaction else None,
            "reservations_count": len(charge_point._reservations)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    """Root endpoint with documentation."""
    return {
        "message": "OCPP Charge Point API",
        "endpoints": {
            "connection": {
                "POST /connect": "Connect to Steve OCPP server"
            },
            "transactions": {
                "POST /start_transaction": "Start charging transaction",
                "POST /stop_transaction": "Stop active transaction"
            },
            "configuration": {
                "GET /configuration": "Get charge point configuration",
                "POST /configuration": "Update configuration",
                "GET /": "List all available operations"
            },
            "availability": {
                "GET /availability": "Get availability status",
                "POST /availability": "Change availability"
            },
            "reservations": {
                "POST /reserve": "Create a reservation",
                "GET /reservations": "List all reservations",
                "DELETE /reservations/{id}": "Cancel a reservation"
            },
            "control": {
                "POST /unlock": "Unlock connector",
                "POST /reset": "Reset charge point",
                "POST /clear-cache": "Clear authorization cache"
            },
            "diagnostics": {
                "POST /diagnostics/start": "Start diagnostics collection",
                "POST /firmware/update": "Initiate firmware update"
            },
            "status": {
                "GET /status": "Get current charge point status"
            }
        }
    }
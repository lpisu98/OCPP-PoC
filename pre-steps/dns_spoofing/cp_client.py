#!/usr/bin/env python3
"""Minimal charge point client used by the DNS spoofing pre-step.

This client intentionally resolves the WebSocket URL through the malicious DNS
server and then performs a short OCPP 1.6 boot/heartbeat handshake with the
impersonating CSMS.
"""

import asyncio
import json
import logging
import os
import time

import websockets

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("cp_client")

CP_ID = os.getenv("CP_ID", "CP_BENIGN_001")
WS_URL = os.getenv("WS_URL", "ws://csms.lab:9002/")
LOOP_SECONDS = float(os.getenv("LOOP_SECONDS", "30"))


def pack_message(msg_type: str, unique_id: str, action: str, payload: dict) -> str:
    return json.dumps([2, unique_id, action, payload])


async def connect_once() -> None:
    logger.info("Connecting CP %s to %s", CP_ID, WS_URL)
    async with websockets.connect(WS_URL, subprotocols=["ocpp1.6"]) as websocket:
        logger.info("WebSocket connected to fake CSMS")

        await websocket.send(json.dumps([2, "1", "BootNotification", {
            "chargePointVendor": "TestVendor",
            "chargePointModel": "TestModel",
            "chargePointSerialNumber": CP_ID,
            "firmwareVersion": "1.0.0",
            "iccid": "",
            "imsi": "",
            "meterType": "",
            "meterSerialNumber": "",
        }]))
        boot_reply = json.loads(await websocket.recv())
        logger.info("BootNotification reply: %s", boot_reply)

        await websocket.send(json.dumps([2, "2", "StatusNotification", {
            "connectorId": 1,
            "errorCode": "NoError",
            "status": "Available",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }]))
        status_reply = json.loads(await websocket.recv())
        logger.info("StatusNotification reply: %s", status_reply)

        await websocket.send(json.dumps([2, "3", "Heartbeat", {}]))
        heartbeat_reply = json.loads(await websocket.recv())
        logger.info("Heartbeat reply: %s", heartbeat_reply)

        await asyncio.sleep(2)


async def main() -> None:
    deadline = time.time() + LOOP_SECONDS
    while time.time() < deadline:
        try:
            await connect_once()
        except Exception as exc:
            logger.warning("Connection failed: %s", exc)
            await asyncio.sleep(2)
        else:
            break

    logger.info("Charge point DNS spoofing client finished")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("CP client interrupted by user")

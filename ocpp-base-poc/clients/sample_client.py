#!/usr/bin/env python3
"""
Simple example of using the charge point HTTP API
Run this script to simulate a quick charging session.
"""

import asyncio
from realistic_charge_point_client import RealisticChargePointClient


async def main():
    # Create a client that connects to your local setup
    client = RealisticChargePointClient(
        charge_point_api_url="http://localhost:9000",
        steve_ws_uri="ws://app:8180/steve/websocket/CentralSystemService/CP_1",
        charge_point_id="CP_1",
        simulation_duration_seconds=30,  # 30 second charging session
        id_tag="USER_1234"
    )

    # Run the complete session
    await client.run_complete_session()


if __name__ == "__main__":
    asyncio.run(main())

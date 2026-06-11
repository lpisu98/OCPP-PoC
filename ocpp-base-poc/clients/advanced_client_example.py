#!/usr/bin/env python3
"""
Advanced OCPP Charge Point Client Example
Demonstrates all supported OCPP operations including:
- Configuration management
- Availability control
- Reservation management
- Diagnostics and firmware updates
"""

import asyncio
from datetime import datetime, timedelta
from realistic_charge_point_client import RealisticChargePointClient


async def main():
    # Create client
    client = RealisticChargePointClient(
        charge_point_api_url="http://localhost:9000",
        steve_ws_uri="ws://localhost:8180/steve/websocket/CentralSystemService/CP_1",
        charge_point_id="CP_1",
        simulation_duration_seconds=30,
        id_tag="ADVANCED_USER"
    )

    print("\n" + "=" * 70)
    print("ADVANCED OCPP OPERATIONS DEMO")
    print("=" * 70 + "\n")

    # Step 1: Connect to Steve
    print("[1] Connecting to Steve OCPP server...")
    if not await client.connect_to_steve():
        print("Failed to connect. Aborting.")
        return
    await asyncio.sleep(2)

    # Step 2: Check initial status
    print("\n[2] Getting charge point status...")
    status = await client.get_charge_point_status()
    print(f"   Status: {status}")

    # Step 3: Configuration management
    print("\n[3] Configuration management:")
    print("   3a. Get current configuration...")
    config = await client.get_configuration()
    print(f"       HeartbeatInterval: {config.get('HeartbeatInterval')}")
    
    print("   3b. Update configuration...")
    await client.set_configuration("HeartbeatInterval", "3600")
    
    print("   3c. Verify update...")
    config = await client.get_configuration()
    print(f"       HeartbeatInterval: {config.get('HeartbeatInterval')}")

    # Step 4: Availability management
    print("\n[4] Availability management:")
    print("   4a. Get current availability...")
    availability = await client.get_availability()
    print(f"       Availability: {availability}")
    
    print("   4b. Set to Operative...")
    await client.set_availability("Operative")

    # Step 5: Reservation management
    print("\n[5] Reservation management:")
    expiry = (datetime.utcnow() + timedelta(hours=1)).isoformat()
    
    print("   5a. Create reservation...")
    await client.create_reservation(
        reservation_id=1,
        connector_id=1,
        id_tag="RESERVED_USER_001",
        expiry_date=expiry
    )
    
    print("   5b. List reservations...")
    reservations = await client.get_reservations()
    print(f"       Total reservations: {len(reservations)}")
    
    print("   5c. Cancel reservation...")
    await client.cancel_reservation(1)

    # Step 6: Start charging transaction
    print("\n[6] Starting charging transaction...")
    if not await client.start_charging_transaction():
        print("Failed to start transaction. Aborting.")
        return
    await asyncio.sleep(1)

    # Step 7: Simulate charging
    print("\n[7] Simulating charging for 30 seconds...")
    await client.simulate_charging()

    # Step 8: Connector operations
    print("\n[8] Connector operations:")
    print("   8a. Locking/Unlocking connector...")
    await client.unlock_connector()
    await asyncio.sleep(1)

    # Step 9: Stop transaction
    print("\n[9] Stopping transaction...")
    await client.stop_charging_transaction()
    await asyncio.sleep(1)

    # Step 10: Diagnostics and maintenance
    print("\n[10] Diagnostics and maintenance:")
    print("   10a. Clear cache...")
    await client.clear_cache()
    
    print("   10b. Start diagnostics...")
    await client.start_diagnostics("http://localhost:8180/diagnostics")
    
    print("   10c. Initiate firmware update...")
    await client.update_firmware("http://localhost:8180/firmware/latest")

    # Step 11: Reset (soft)
    print("\n[11] Resetting charge point (Soft)...")
    await client.reset_charge_point("Soft")
    await asyncio.sleep(2)

    # Step 12: Final status
    print("\n[12] Final charge point status...")
    status = await client.get_charge_point_status()
    print(f"    Connected: {status.get('connected')}")
    print(f"    Availability: {status.get('availability')}")
    print(f"    Transaction Active: {status.get('transaction_active')}")

    print("\n" + "=" * 70)
    print("DEMO COMPLETED SUCCESSFULLY")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())

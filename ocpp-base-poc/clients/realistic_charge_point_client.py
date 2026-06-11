#!/usr/bin/env python3
"""
Realistic OCPP Charge Point Client
Simulates a charge point connecting to Steve OCPP server and conducting a charging session.
"""

import asyncio
import logging
import time
import requests
from typing import Optional
from datetime import datetime
import argparse

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ChargePointClient")


class RealisticChargePointClient:
    """
    Simulates a realistic charge point that:
    - Connects to Steve OCPP server
    - Performs boot notification
    - Starts a charging transaction
    - Simulates energy consumption
    - Stops the transaction
    """

    def __init__(
        self,
        charge_point_api_url: str = "http://localhost:9000",
        steve_ws_uri: str = "ws://localhost:8180/steve/websocket/CentralSystemService/CP_1",
        charge_point_id: str = "CP_1",
        simulation_duration_seconds: int = 60,
        id_tag: str = "SIMULATED_ID"
    ):
        """
        Initialize the charge point client.

        Args:
            charge_point_api_url: URL of the FastAPI charge point server
            steve_ws_uri: WebSocket URI of the Steve OCPP server
            charge_point_id: Charge point identifier
            simulation_duration_seconds: How long to simulate charging
            id_tag: ID tag for the charging session
        """
        self.charge_point_api_url = charge_point_api_url
        self.steve_ws_uri = steve_ws_uri
        self.charge_point_id = charge_point_id
        self.simulation_duration_seconds = simulation_duration_seconds
        self.id_tag = id_tag
        self.transaction_id: Optional[str] = None
        self.start_time: Optional[float] = None
        self.session_active = False

    def _make_request(self, method: str, endpoint: str, json_data=None, timeout: int = 10):
        """
        Make HTTP request to the charge point API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            json_data: JSON body for POST requests
            timeout: Request timeout in seconds

        Returns:
            Response data or raises exception
        """
        url = f"{self.charge_point_api_url}{endpoint}"
        try:
            if method == "POST":
                response = requests.post(url, json=json_data, timeout=timeout)
            elif method == "GET":
                response = requests.get(url, timeout=timeout)
            elif method == "DELETE":
                response = requests.delete(url, timeout=timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            try:
                response.raise_for_status()
                return response.json()
            except requests.exceptions.HTTPError:
                # If the server returned a JSON error body, return it for higher-level handling
                try:
                    return response.json()
                except Exception:
                    logger.error("Request failed with status %s and no JSON body", response.status_code)
                    raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise

    async def connect_to_steve(self) -> bool:
        """
        Connect the charge point to Steve OCPP central system.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            logger.info(f"Connecting to Steve: {self.steve_ws_uri}")
            result = self._make_request(
                "POST",
                "/connect",
                {
                    "websocket_uri": self.steve_ws_uri
                }
            )
            logger.info(f"Connection successful: {result}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Steve: {e}")
            return False

    async def start_charging_transaction(self) -> bool:
        """
        Start a charging transaction.

        Returns:
            True if transaction started successfully, False otherwise
        """
        try:
            logger.info(f"Starting charging transaction with ID tag: {self.id_tag}")
            result = self._make_request(
                "POST",
                "/start_transaction",
                {
                    "id_tag": self.id_tag
                }
            )

            # Server returns successful JSON with transaction_id, or an error body with 'detail'
            if isinstance(result, dict) and result.get("transaction_id"):
                self.transaction_id = result.get("transaction_id")
                logger.info(f"Transaction started: {self.transaction_id}")
                self.session_active = True
                self.start_time = time.time()
                return True

            # If server returned an error body, inspect details
            detail = None
            if isinstance(result, dict):
                detail = result.get("detail") or result
            if isinstance(detail, dict) and detail.get("idTagInfo"):
                id_info = detail.get("idTagInfo")
                logger.warning("StartTransaction rejected by central system: idTagInfo=%s", id_info)
                return False

            logger.error("Failed to start transaction: unexpected response: %s", result)
            return False
        except Exception as e:
            logger.error(f"Failed to start transaction: {e}")
            return False

    async def stop_charging_transaction(self) -> bool:
        """
        Stop the active charging transaction.

        Returns:
            True if transaction stopped successfully, False otherwise
        """
        try:
            if not self.session_active:
                logger.warning("No active transaction to stop")
                return False

            logger.info(f"Stopping transaction: {self.transaction_id}")
            result = self._make_request("POST", "/stop_transaction")
            logger.info(f"Transaction stopped: {result}")
            self.session_active = False
            return True
        except Exception as e:
            logger.error(f"Failed to stop transaction: {e}")
            return False

    # ============================================================================
    # Advanced OCPP Operations (exposed via HTTP API)
    # ============================================================================

    async def get_configuration(self, keys: list = None) -> dict:
        """
        Get charge point configuration.

        Args:
            keys: List of configuration keys to retrieve (None = all)

        Returns:
            Configuration dictionary
        """
        try:
            logger.info("Retrieving configuration")
            result = self._make_request("GET", "/configuration")
            return result.get("configuration", {})
        except Exception as e:
            logger.error(f"Failed to get configuration: {e}")
            return {}

    async def set_configuration(self, key: str, value: str) -> bool:
        """
        Set a configuration parameter.

        Args:
            key: Configuration key
            value: Configuration value

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Setting configuration: {key} = {value}")
            result = self._make_request("POST", "/configuration", {"key": key, "value": value})
            logger.info(f"Configuration updated: {result}")
            return result.get("status") == "updated"
        except Exception as e:
            logger.error(f"Failed to set configuration: {e}")
            return False

    async def get_availability(self) -> str:
        """
        Get current availability status.

        Returns:
            Availability status string
        """
        try:
            result = self._make_request("GET", "/availability")
            status = result.get("availability", "Unknown")
            logger.info(f"Current availability: {status}")
            return status
        except Exception as e:
            logger.error(f"Failed to get availability: {e}")
            return "Unknown"

    async def set_availability(self, availability_type: str) -> bool:
        """
        Change charge point availability.

        Args:
            availability_type: "Operative" or "Inoperative"

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Setting availability to: {availability_type}")
            result = self._make_request("POST", "/availability", {"type": availability_type})
            logger.info(f"Availability changed: {result}")
            return result.get("status") == "changed"
        except Exception as e:
            logger.error(f"Failed to set availability: {e}")
            return False

    async def create_reservation(
        self,
        reservation_id: int,
        connector_id: int,
        id_tag: str,
        expiry_date: str,
        parent_id: int = None
    ) -> bool:
        """
        Create a reservation for the charge point.

        Args:
            reservation_id: Unique reservation identifier
            connector_id: Connector to reserve
            id_tag: ID tag for reservation
            expiry_date: Reservation expiry date (ISO format)
            parent_id: Optional parent reservation ID

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Creating reservation {reservation_id} for {id_tag}")
            data = {
                "connector_id": connector_id,
                "reservation_id": reservation_id,
                "expiry_date": expiry_date,
                "id_tag": id_tag
            }
            if parent_id:
                data["parent_id"] = parent_id
            result = self._make_request("POST", "/reserve", data)
            logger.info(f"Reservation created: {result}")
            return result.get("status") == "created"
        except Exception as e:
            logger.error(f"Failed to create reservation: {e}")
            return False

    async def cancel_reservation(self, reservation_id: int) -> bool:
        """
        Cancel an active reservation.

        Args:
            reservation_id: ID of reservation to cancel

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Cancelling reservation {reservation_id}")
            result = self._make_request("DELETE", f"/reservations/{reservation_id}")
            logger.info(f"Reservation cancelled: {result}")
            return result.get("status") == "cancelled"
        except Exception as e:
            logger.error(f"Failed to cancel reservation: {e}")
            return False

    async def get_reservations(self) -> dict:
        """
        Get all active reservations.

        Returns:
            Dictionary of active reservations
        """
        try:
            result = self._make_request("GET", "/reservations")
            reservations = result.get("reservations", {})
            logger.info(f"Active reservations: {len(reservations)}")
            return reservations
        except Exception as e:
            logger.error(f"Failed to get reservations: {e}")
            return {}

    async def unlock_connector(self) -> bool:
        """
        Unlock the connector.

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("Unlocking connector")
            result = self._make_request("POST", "/unlock")
            logger.info(f"Connector unlock result: {result}")
            return result.get("status") == "unlocked"
        except Exception as e:
            logger.error(f"Failed to unlock connector: {e}")
            return False

    async def reset_charge_point(self, reset_type: str = "Soft") -> bool:
        """
        Reset the charge point.

        Args:
            reset_type: "Soft" or "Hard" reset

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Resetting charge point ({reset_type})")
            result = self._make_request("POST", "/reset", {"type": reset_type})
            logger.info(f"Reset result: {result}")
            return result.get("status") == "reset"
        except Exception as e:
            logger.error(f"Failed to reset: {e}")
            return False

    async def clear_cache(self) -> bool:
        """
        Clear the authorization cache.

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("Clearing cache")
            result = self._make_request("POST", "/clear-cache")
            logger.info(f"Cache clear result: {result}")
            return result.get("status") == "cleared"
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return False

    async def start_diagnostics(self, location: str) -> bool:
        """
        Start diagnostics collection.

        Args:
            location: Location/URL for diagnostics upload

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Starting diagnostics to {location}")
            result = self._make_request("POST", "/diagnostics/start", {"location": location})
            logger.info(f"Diagnostics started: {result}")
            return "fileName" in result
        except Exception as e:
            logger.error(f"Failed to start diagnostics: {e}")
            return False

    async def update_firmware(self, location: str) -> bool:
        """
        Initiate firmware update.

        Args:
            location: Location/URL for firmware download

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Initiating firmware update from {location}")
            result = self._make_request("POST", "/firmware/update", {"location": location})
            logger.info(f"Firmware update initiated: {result}")
            return result.get("status") == "initiated"
        except Exception as e:
            logger.error(f"Failed to initiate firmware update: {e}")
            return False

    async def get_charge_point_status(self) -> dict:
        """
        Get comprehensive charge point status.

        Returns:
            Status dictionary
        """
        try:
            result = self._make_request("GET", "/status")
            logger.info(f"Charge point status: {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to get status: {e}")
            return {}

    async def simulate_charging(self):
        """
        Simulate realistic charging behavior for the specified duration.
        In a real scenario, this would simulate energy transfer and status updates.
        """
        logger.info(f"Simulating charging for {self.simulation_duration_seconds} seconds")
        elapsed = 0
        update_interval = max(5, self.simulation_duration_seconds // 10)  # Update roughly 10 times

        while elapsed < self.simulation_duration_seconds and self.session_active:
            elapsed = int(time.time() - self.start_time)
            remaining = self.simulation_duration_seconds - elapsed
            energy_simulated_wh = int((elapsed / self.simulation_duration_seconds) * 5000)  # Simulate 5 kWh

            logger.info(
                f"Charging in progress: {elapsed}/{self.simulation_duration_seconds}s, "
                f"Energy: {energy_simulated_wh} Wh, Remaining: {remaining}s"
            )

            await asyncio.sleep(min(update_interval, remaining if remaining > 0 else 1))

        logger.info("Charging simulation complete")

    async def run_complete_session(self):
        """
        Execute a complete charging session:
        1. Connect to Steve
        2. Start transaction
        3. Simulate charging
        4. Stop transaction
        """
        try:
            logger.info("=" * 60)
            logger.info("Starting realistic charge point session")
            logger.info("=" * 60)

            # Step 1: Connect to Steve
            if not await self.connect_to_steve():
                logger.error("Failed to connect to Steve. Aborting session.")
                return False

            await asyncio.sleep(2)  # Wait for connection to stabilize

            # Step 2: Start transaction
            if not await self.start_charging_transaction():
                logger.error("Failed to start transaction. Aborting session.")
                return False

            await asyncio.sleep(1)

            # Step 3: Simulate charging
            await self.simulate_charging()

            # Step 4: Stop transaction
            if not await self.stop_charging_transaction():
                logger.error("Failed to stop transaction")
                return False

            logger.info("=" * 60)
            logger.info("Charging session completed successfully")
            logger.info("=" * 60)
            return True

        except Exception as e:
            logger.error(f"Session error: {e}")
            if self.session_active:
                await self.stop_charging_transaction()
            return False


async def main():
    """Main entry point for the charge point client."""
    parser = argparse.ArgumentParser(
        description="Realistic OCPP Charge Point Client"
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:9000",
        help="Charge point API URL (default: http://localhost:9000)"
    )
    parser.add_argument(
        "--steve-uri",
        default="ws://localhost:8180/steve/websocket/CentralSystemService/CP_1",
        help="Steve WebSocket URI"
    )
    parser.add_argument(
        "--charge-point-id",
        default="CP_1",
        help="Charge point identifier (default: CP_1)"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Charging simulation duration in seconds (default: 60)"
    )
    parser.add_argument(
        "--id-tag",
        default="SIMULATED_ID",
        help="ID tag for the transaction (default: SIMULATED_ID)"
    )

    args = parser.parse_args()

    client = RealisticChargePointClient(
        charge_point_api_url=args.api_url,
        steve_ws_uri=args.steve_uri,
        charge_point_id=args.charge_point_id,
        simulation_duration_seconds=args.duration,
        id_tag=args.id_tag
    )

    success = await client.run_complete_session()
    exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())

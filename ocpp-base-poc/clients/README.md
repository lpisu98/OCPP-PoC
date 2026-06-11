# OCPP Charge Point Client

This directory contains clients for interacting with the OCPP charge point FastAPI server and simulating realistic charging scenarios.

## Files

- **realistic_charge_point_client.py**: Full-featured client that simulates a complete charging session
- **sample_client.py**: Simple example showing basic usage
- **requirements.txt**: Python dependencies

## How It Works

The client interacts with the charge point HTTP API to:

1. **Connect to Steve** (OCPP Central System)
   - Establishes a WebSocket connection to the Steve backend server
   - Sends BootNotification to register the charge point

2. **Start a Transaction**
   - Initiates a charging session with an ID tag
   - Receives confirmation from the central system

3. **Simulate Charging**
   - Runs for a configurable duration (default: 60 seconds)
   - Logs simulated energy consumption

4. **Stop the Transaction**
   - Terminates the charging session gracefully
   - Reports final meter readings

## Prerequisites

### System Requirements

Ensure the following services are running:
- **Steve OCPP Server** running on `localhost:8180`
- **Charge Point FastAPI** running on `localhost:9000`
- **Database** (MariaDB) for Steve

### Starting Services with Docker

From the `ocpp-base-poc` directory:

```bash
docker-compose up
```

This starts:
- Steve on port 8180
- Charge Point API on port 9000
- MariaDB on port 3306
- Network traffic capture (tcpdump)

### Python Dependencies

Install required packages:

```bash
pip install -r requirements.txt
```

## Usage

### Quick Start (Simple Example)

```bash
python sample_client.py
```

This runs a basic 30-second charging session with default parameters.

### Full Usage (with Options)

```bash
python realistic_charge_point_client.py \
  --api-url http://localhost:9000 \
  --steve-uri ws://localhost:8180/steve/websocket/CentralSystemService/CP_1 \
  --charge-point-id CP_1 \
  --duration 120 \
  --id-tag USER_1234
```

### Options

- **--api-url**: URL of the charge point API (default: `http://localhost:9000`)
- **--steve-uri**: WebSocket URI for Steve OCPP server (default: `ws://localhost:8180/steve/websocket/CentralSystemService/CP_1`)
- **--charge-point-id**: Identifier for the charge point (default: `CP_1`)
- **--duration**: Charging simulation duration in seconds (default: `60`)
- **--id-tag**: ID tag for the transaction (default: `SIMULATED_ID`)

## Example Output

```
2024-05-14 10:30:15,123 - ChargePointClient - INFO - ============================================================
2024-05-14 10:30:15,124 - ChargePointClient - INFO - Starting realistic charge point session
2024-05-14 10:30:15,125 - ChargePointClient - INFO - ============================================================
2024-05-14 10:30:15,126 - ChargePointClient - INFO - Connecting to Steve: ws://localhost:8180/steve/websocket/CentralSystemService/CP_1
2024-05-14 10:30:15,500 - ChargePointClient - INFO - Connection successful: {'status': 'connected', ...}
2024-05-14 10:30:17,600 - ChargePointClient - INFO - Starting charging transaction with ID tag: USER_1234
2024-05-14 10:30:18,100 - ChargePointClient - INFO - Transaction started: abc123...
2024-05-14 10:30:19,200 - ChargePointClient - INFO - Simulating charging for 60 seconds
2024-05-14 10:30:25,300 - ChargePointClient - INFO - Charging in progress: 6/60s, Energy: 500 Wh, Remaining: 54s
...
2024-05-14 10:31:19,500 - ChargePointClient - INFO - Charging simulation complete
2024-05-14 10:31:20,600 - ChargePointClient - INFO - Stopping transaction: abc123...
2024-05-14 10:31:21,100 - ChargePointClient - INFO - ============================================================
2024-05-14 10:31:21,100 - ChargePointClient - INFO - Charging session completed successfully
2024-05-14 10:31:21,100 - ChargePointClient - INFO - ============================================================
```

## Architecture

```
┌─────────────────────────┐
│  Charge Point Client    │  (This client)
│  (Python Script)        │
└────────────┬────────────┘
             │ HTTP requests
             ▼
┌─────────────────────────┐
│  Charge Point API       │  (FastAPI, port 9000)
│  (HTTP Interface)       │
└────────────┬────────────┘
             │ WebSocket
             ▼
┌─────────────────────────┐
│  Steve OCPP Server      │  (OCPP 1.6, port 8180)
│  (Central System)       │
└────────────┬────────────┘
             │ SQL
             ▼
┌─────────────────────────┐
│  MariaDB                │  (port 3306)
└─────────────────────────┘
```

## Features

### RealisticChargePointClient

- **Async/Await**: Fully asynchronous for concurrent operations
- **Error Handling**: Comprehensive error handling and logging
- **Configurable**: All parameters can be customized
- **Logging**: Detailed logs for monitoring session progress
- **Simulation**: Realistic energy consumption simulation
- **Graceful Shutdown**: Properly stops transactions on failure

## Troubleshooting

### Connection Refused
- Ensure Docker containers are running: `docker-compose ps`
- Check that ports are correct (8180, 9000, 3306)
- Verify network connectivity: `docker-compose logs app`

### Transaction Fails to Start
- Check that the charge point is properly registered with Steve
- Verify the ID tag format (default: `SIMULATED_ID`)
- Check logs in the FastAPI server: `docker-compose logs charge_point`

### Timeout Errors
- Increase connection timeout in the client code
- Check Steve logs for OCPP-level errors
- Verify the WebSocket URI is correct

## Extending the Client

You can extend the client to:
- Send periodic status updates
- Simulate meter readings
- Handle remote commands from the server
- Test different charging scenarios
- Integrate with other testing frameworks

Example extension:
```python
class AdvancedClient(RealisticChargePointClient):
    async def send_periodic_status(self):
        # Send status updates every N seconds
        pass

    async def simulate_meter_readings(self):
        # More realistic meter value progression
        pass
```

## References

- [OCPP 1.6 Specification](https://www.ocpp-info.org/)
- [Steve GitHub Repository](https://github.com/steve-community/steve)
- [Python-OCPP Library](https://github.com/mobilityhouse/python-ocpp)

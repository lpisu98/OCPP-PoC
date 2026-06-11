# OCPP Charge Point API - Complete Reference

This document describes all available OCPP operations supported by the FastAPI charge point server.

## Base URL
```
http://localhost:9000
```

## Overview of Operations

The charge point implements OCPP 1.6 client functionality with the following operation groups:

1. **Connection Management** - Connect/disconnect from central system
2. **Transaction Management** - Start/stop charging sessions
3. **Configuration** - Get/set charge point configuration
4. **Availability** - Control and monitor availability status
5. **Reservations** - Reserve connectors for future use
6. **Control Operations** - Remote control (unlock, reset, etc.)
7. **Diagnostics** - Diagnostics collection and monitoring
8. **Support** - API documentation and status

---

## 1. Connection Management

### POST /connect
**Connect to Steve OCPP Central System**

Establish WebSocket connection to Steve and perform boot notification.

**Request:**
```json
{
  "websocket_uri": "ws://localhost:8180/steve/websocket/CentralSystemService/CP_1"
}
```

**Response:**
```json
{
  "status": "connected",
  "websocket_uri": "ws://localhost:8180/steve/websocket/CentralSystemService/CP_1"
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:9000/connect \
  -H "Content-Type: application/json" \
  -d '{"websocket_uri":"ws://localhost:8180/steve/websocket/CentralSystemService/CP_1"}'
```

---

## 2. Transaction Management

### POST /start_transaction
**Start a Charging Transaction**

Initiate a new charging session with an ID tag.

**Request:**
```json
{
  "id_tag": "USER_1234"
}
```

**Response:**
```json
{
  "transaction_id": "abc123def456"
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:9000/start_transaction \
  -H "Content-Type: application/json" \
  -d '{"id_tag":"USER_1234"}'
```

### POST /stop_transaction
**Stop Active Charging Transaction**

Terminate the current charging session.

**Request Body:** (None - POST with no body)

**Response:**
```json
{
  "status": "Transaction stopped"
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:9000/stop_transaction \
  -H "Content-Type: application/json"
```

---

## 3. Configuration Management

### GET /configuration
**Retrieve Charge Point Configuration**

Get all configuration parameters and their values.

**Response:**
```json
{
  "configuration": {
    "HeartbeatInterval": "14400",
    "MaxChargingProfilesInstalled": "42",
    "GetConfigurationMaxKeys": "100",
    "AllowOfflineTxForUnknownId": "True",
    "AuthorizationCacheEnabled": "True",
    "WebSocketPingInterval": "60"
  }
}
```

**cURL Example:**
```bash
curl http://localhost:9000/configuration
```

### POST /configuration
**Update Configuration Parameter**

Set or modify a configuration parameter.

**Request:**
```json
{
  "key": "HeartbeatInterval",
  "value": "3600"
}
```

**Response:**
```json
{
  "status": "updated",
  "key": "HeartbeatInterval",
  "value": "3600"
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:9000/configuration \
  -H "Content-Type: application/json" \
  -d '{"key":"HeartbeatInterval","value":"3600"}'
```

---

## 4. Availability Management

### GET /availability
**Get Current Availability Status**

Query the current availability status of the charge point.

**Response:**
```json
{
  "availability": "Operative"
}
```

**cURL Example:**
```bash
curl http://localhost:9000/availability
```

### POST /availability
**Change Availability Status**

Set the charge point to operational or inoperative.

**Request:**
```json
{
  "type": "Operative"
}
```

Valid values for `type`:
- `"Operative"` - Enable charging
- `"Inoperative"` - Disable charging

**Response:**
```json
{
  "status": "changed",
  "availability": "Operative"
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:9000/availability \
  -H "Content-Type: application/json" \
  -d '{"type":"Operative"}'
```

---

## 5. Reservation Management

### POST /reserve
**Create a Reservation**

Reserve the charge point connector for a specific user.

**Request:**
```json
{
  "connector_id": 1,
  "reservation_id": 100,
  "expiry_date": "2026-05-15T18:00:00Z",
  "id_tag": "USER_5678",
  "parent_id": null
}
```

**Response:**
```json
{
  "status": "created",
  "reservation_id": 100
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:9000/reserve \
  -H "Content-Type: application/json" \
  -d '{
    "connector_id": 1,
    "reservation_id": 100,
    "expiry_date": "2026-05-15T18:00:00Z",
    "id_tag": "USER_5678"
  }'
```

### GET /reservations
**List All Active Reservations**

Retrieve all active reservations.

**Response:**
```json
{
  "reservations": {
    "100": {
      "connector_id": 1,
      "expiry_date": "2026-05-15T18:00:00Z",
      "id_tag": "USER_5678",
      "parent_id": null
    }
  }
}
```

**cURL Example:**
```bash
curl http://localhost:9000/reservations
```

### DELETE /reservations/{reservation_id}
**Cancel a Reservation**

Remove an active reservation.

**Response:**
```json
{
  "status": "cancelled",
  "reservation_id": 100
}
```

**cURL Example:**
```bash
curl -X DELETE http://localhost:9000/reservations/100
```

---

## 6. Connector Control Operations

### POST /unlock
**Unlock Connector**

Physically unlock the connector (if applicable).

**Request Body:** (None - POST with no body)

**Response:**
```json
{
  "status": "unlocked"
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:9000/unlock
```

### POST /reset
**Reset Charge Point**

Perform a soft or hard reset of the charge point.

**Request:**
```json
{
  "type": "Soft"
}
```

Valid values for `type`:
- `"Soft"` - Graceful restart
- `"Hard"` - Force restart

**Response:**
```json
{
  "status": "reset",
  "type": "Soft"
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:9000/reset \
  -H "Content-Type: application/json" \
  -d '{"type":"Soft"}'
```

### POST /clear-cache
**Clear Authorization Cache**

Clear the local authorization cache.

**Request Body:** (None - POST with no body)

**Response:**
```json
{
  "status": "cleared"
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:9000/clear-cache
```

---

## 7. Diagnostics and Maintenance

### POST /diagnostics/start
**Start Diagnostics Collection**

Initiate collection of diagnostic data.

**Request:**
```json
{
  "location": "http://localhost:8180/diagnostics"
}
```

**Response:**
```json
{
  "status": "started",
  "fileName": "diagnostics_dump_001.txt"
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:9000/diagnostics/start \
  -H "Content-Type: application/json" \
  -d '{"location":"http://localhost:8180/diagnostics"}'
```

### POST /firmware/update
**Initiate Firmware Update**

Start firmware update process.

**Request:**
```json
{
  "location": "http://localhost:8180/firmware/latest"
}
```

**Response:**
```json
{
  "status": "initiated"
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:9000/firmware/update \
  -H "Content-Type: application/json" \
  -d '{"location":"http://localhost:8180/firmware/latest"}'
```

---

## 8. Status and Monitoring

### GET /status
**Get Comprehensive Charge Point Status**

Retrieve the complete current status of the charge point.

**Response:**
```json
{
  "charge_point_id": "CP_1",
  "connected": true,
  "availability": "Operative",
  "transaction_active": true,
  "transaction_id": "abc123def456",
  "reservations_count": 1
}
```

**cURL Example:**
```bash
curl http://localhost:9000/status
```

### GET /
**API Documentation**

Get a list of all available endpoints.

**Response:**
```json
{
  "message": "OCPP Charge Point API",
  "endpoints": {
    "connection": { "POST /connect": "Connect to Steve OCPP server" },
    "transactions": { "POST /start_transaction": "Start charging transaction" },
    ...
  }
}
```

**cURL Example:**
```bash
curl http://localhost:9000/
```

---

## OCPP Operations Handled by Server

The charge point responds to these OCPP messages from the central system:

| Operation | Direction | Purpose |
|-----------|-----------|---------|
| **GetConfiguration** | ← | Central system queries charge point configuration |
| **ChangeConfiguration** | ← | Central system updates configuration |
| **ChangeAvailability** | ← | Central system changes availability status |
| **RemoteStartTransaction** | ← | Central system starts remote transaction |
| **RemoteStopTransaction** | ← | Central system stops active transaction |
| **SetChargingProfile** | ← | Central system sets charging profile |
| **ReserveNow** | ← | Central system creates reservation |
| **CancelReservation** | ← | Central system cancels reservation |
| **UnlockConnector** | ← | Central system unlocks connector |
| **Authorize** | ← | Central system authorizes ID tag |
| **Reset** | ← | Central system resets charge point |
| **ClearCache** | ← | Central system clears cache |
| **StartDiagnostics** | ← | Central system starts diagnostics |
| **UpdateFirmware** | ← | Central system initiates firmware update |
| **SendLocalList** | ← | Central system sends auth list |
| **DataTransfer** | ← | Central system vendor-specific data |
| **BootNotification** | → | Charge point announces boot |
| **StatusNotification** | → | Charge point reports status |
| **StartTransaction** | → | Charge point reports transaction start |
| **StopTransaction** | → | Charge point reports transaction stop |
| **MeterValues** | → | Charge point reports meter values |

---

## Error Handling

All endpoints return HTTP status codes:

- `200` - Success
- `404` - Not found (e.g., reservation doesn't exist)
- `500` - Internal server error (e.g., connection failed)

Error response format:
```json
{
  "detail": "Error message describing what went wrong"
}
```

---

## Authentication and Security

The current implementation has **no authentication**. In a production environment:
- Implement API key or OAuth2 authentication
- Use HTTPS for all connections
- Validate all input parameters
- Implement rate limiting

---

## Integration with Client Library

The Python client (`realistic_charge_point_client.py`) provides methods for all operations:

```python
client = RealisticChargePointClient()

# Features available:
await client.connect_to_steve()              # Connect
await client.start_charging_transaction()    # Transaction
await client.get_configuration()             # Config
await client.set_availability("Operative")   # Availability
await client.create_reservation(...)         # Reservations
await client.unlock_connector()              # Control
await client.start_diagnostics(...)          # Diagnostics
```

See `advanced_client_example.py` for a complete working example.

---

## Example Workflow

```bash
# 1. Connect to central system
curl -X POST http://localhost:9000/connect \
  -H "Content-Type: application/json" \
  -d '{"websocket_uri":"ws://localhost:8180/steve/websocket/CentralSystemService/CP_1"}'

# 2. Get status
curl http://localhost:9000/status

# 3. Start transaction
curl -X POST http://localhost:9000/start_transaction \
  -H "Content-Type: application/json" \
  -d '{"id_tag":"USER_1234"}'

# 4. Wait for charging...
sleep 30

# 5. Stop transaction
curl -X POST http://localhost:9000/stop_transaction

# 6. Check final status
curl http://localhost:9000/status
```

---

## Performance and Limits

- **Connection timeout**: 10 seconds
- **Request timeout**: 10 seconds
- **Max configuration keys**: 100
- **Max reservations**: Limited by memory
- **Concurrent transactions**: 1 per charge point

---

## Future Enhancements

- [ ] WebSocket real-time status streaming
- [ ] Metrics and monitoring endpoints
- [ ] Centralized logging/audit trail
- [ ] Multi-connector support
- [ ] Advanced charging profile management
- [ ] Load testing suite
- [ ] Performance metrics collection

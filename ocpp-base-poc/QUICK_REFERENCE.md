# OCPP Charge Point Quick Reference Guide

## Quick Setup

```bash
# 1. Start services
docker-compose up

# 2. In another terminal, run a client
python clients/sample_client.py
```

## Common Operations

### 1. STATUS CHECK

**Python:**
```python
client = RealisticChargePointClient()
status = await client.get_charge_point_status()
print(f"Connected: {status['connected']}")
print(f"Transaction: {status['transaction_active']}")
```

**cURL:**
```bash
curl http://localhost:9000/status
```

**Response:**
```json
{
  "charge_point_id": "CP_1",
  "connected": true,
  "availability": "Operative",
  "transaction_active": false,
  "reservations_count": 0
}
```

---

### 2. START CHARGING

**Python:**
```python
await client.connect_to_steve()
await client.start_charging_transaction()
```

**cURL:**
```bash
# Connect first
curl -X POST http://localhost:9000/connect \
  -H "Content-Type: application/json" \
  -d '{"websocket_uri":"ws://localhost:8180/steve/websocket/CentralSystemService/CP_1"}'

# Then start transaction
curl -X POST http://localhost:9000/start_transaction \
  -H "Content-Type: application/json" \
  -d '{"id_tag":"USER_001"}'
```

---

### 3. STOP CHARGING

**Python:**
```python
await client.stop_charging_transaction()
```

**cURL:**
```bash
curl -X POST http://localhost:9000/stop_transaction \
  -H "Content-Type: application/json"
```

---

### 4. CONFIGURATION

**Get Configuration:**
```python
config = await client.get_configuration()
```

```bash
curl http://localhost:9000/configuration | jq
```

**Update Configuration:**
```python
await client.set_configuration("HeartbeatInterval", "3600")
```

```bash
curl -X POST http://localhost:9000/configuration \
  -H "Content-Type: application/json" \
  -d '{"key":"HeartbeatInterval","value":"3600"}'
```

---

### 5. AVAILABILITY

**Check Availability:**
```python
status = await client.get_availability()  # "Operative" or "Inoperative"
```

```bash
curl http://localhost:9000/availability
```

**Set Unavailable (Stop Accepting Charges):**
```python
await client.set_availability("Inoperative")
```

```bash
curl -X POST http://localhost:9000/availability \
  -H "Content-Type: application/json" \
  -d '{"type":"Inoperative"}'
```

---

### 6. RESERVATIONS

**Create Reservation:**
```python
from datetime import datetime, timedelta

expiry = (datetime.utcnow() + timedelta(hours=1)).isoformat()
await client.create_reservation(
    reservation_id=1,
    connector_id=1,
    id_tag="VIP_USER",
    expiry_date=expiry
)
```

```bash
curl -X POST http://localhost:9000/reserve \
  -H "Content-Type: application/json" \
  -d '{
    "connector_id": 1,
    "reservation_id": 1,
    "expiry_date": "2026-05-15T18:00:00Z",
    "id_tag": "VIP_USER"
  }'
```

**List Reservations:**
```python
reservations = await client.get_reservations()
```

```bash
curl http://localhost:9000/reservations | jq
```

**Cancel Reservation:**
```python
await client.cancel_reservation(1)
```

```bash
curl -X DELETE http://localhost:9000/reservations/1
```

---

### 7. CONNECTOR CONTROL

**Unlock Connector:**
```python
await client.unlock_connector()
```

```bash
curl -X POST http://localhost:9000/unlock
```

---

### 8. MAINTENANCE

**Clear Cache:**
```python
await client.clear_cache()
```

```bash
curl -X POST http://localhost:9000/clear-cache
```

**Start Diagnostics:**
```python
await client.start_diagnostics("http://server:8180/diagnostics")
```

```bash
curl -X POST http://localhost:9000/diagnostics/start \
  -H "Content-Type: application/json" \
  -d '{"location":"http://server:8180/diagnostics"}'
```

**Update Firmware:**
```python
await client.update_firmware("http://server:8180/firmware/latest")
```

```bash
curl -X POST http://localhost:9000/firmware/update \
  -H "Content-Type: application/json" \
  -d '{"location":"http://server:8180/firmware/latest"}'
```

**Soft Reset:**
```python
await client.reset_charge_point("Soft")
```

```bash
curl -X POST http://localhost:9000/reset \
  -H "Content-Type: application/json" \
  -d '{"type":"Soft"}'
```

---

## Common Scenarios

### Scenario 1: Full Charging Session

```python
client = RealisticChargePointClient(simulation_duration_seconds=60)

# Connect
await client.connect_to_steve()
print("✓ Connected to Steve")

# Get status
status = await client.get_charge_point_status()
print(f"✓ Status: {status['availability']}")

# Start
tx_id = await client.start_charging_transaction()
print(f"✓ Transaction started: {tx_id}")

# Charge
await client.simulate_charging()
print("✓ Charging complete")

# Stop
await client.stop_charging_transaction()
print("✓ Transaction stopped")
```

### Scenario 2: Scheduled Reservation

```python
from datetime import datetime, timedelta

# Create reservation 1 hour from now
client = RealisticChargePointClient()
now = datetime.utcnow()
expiry = (now + timedelta(hours=1)).isoformat()

await client.create_reservation(
    reservation_id=100,
    connector_id=1,
    id_tag="SCHEDULED_USER",
    expiry_date=expiry
)

# Check active reservations
reservations = await client.get_reservations()
print(f"Reservations: {len(reservations)}")

# Later, cancel it
await client.cancel_reservation(100)
```

### Scenario 3: Configuration Update

```python
client = RealisticChargePointClient()

# Get current
config = await client.get_configuration()
hb = config.get('HeartbeatInterval')
print(f"Current HeartbeatInterval: {hb}")

# Update
await client.set_configuration("HeartbeatInterval", "1800")
print("Updated to 1800 seconds (30 minutes)")

# Verify
config = await client.get_configuration()
hb = config.get('HeartbeatInterval')
print(f"New HeartbeatInterval: {hb}")
```

---

## Useful API Patterns

### Check Connection Status

```bash
curl http://localhost:9000/status | jq '.connected'
```

### Monitor Active Transactions

```bash
while true; do
  curl -s http://localhost:9000/status | jq '.transaction_active'
  sleep 5
done
```

### Batch Configuration Check

```bash
curl http://localhost:9000/configuration | jq '.configuration | keys[]'
```

### Create Multiple Reservations

```bash
for i in {1..5}; do
  expiry=$(date -d "+1 hour" -u +%Y-%m-%dT%H:%M:%SZ)
  curl -X POST http://localhost:9000/reserve \
    -H "Content-Type: application/json" \
    -d "{
      \"connector_id\": 1,
      \"reservation_id\": $i,
      \"expiry_date\": \"$expiry\",
      \"id_tag\": \"USER_$i\"
    }"
  echo "Reservation $i created"
done
```

---

## Error Handling

### Connection Error
```python
try:
    await client.connect_to_steve()
except Exception as e:
    logger.error(f"Connection failed: {e}")
    # Retry logic
```

```bash
curl -i http://localhost:9000/connect 2>&1 | head -20
# HTTP/1.1 500 Internal Server Error
# {"detail":"Connection refused"}
```

### Missing Resource
```bash
curl -X DELETE http://localhost:9000/reservations/999
# {"detail":"Reservation not found"}
```

---

## Debugging

### Enable Verbose Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check Server Logs

```bash
docker-compose logs -f charge_point
```

### Monitor Network Traffic

```bash
# From another terminal
docker-compose exec app tcpdump -i eth0 port 8180
```

### Test Server Connectivity

```bash
docker-compose exec charge_point ping app
```

---

## Performance Tips

1. **Batch Operations**: Group multiple queries
2. **Async/Await**: Use async for concurrency
3. **Timeouts**: Set reasonable request timeouts
4. **Connection Pooling**: Reuse client connections
5. **Caching**: Store frequently accessed config

---

## Security Notes

⚠️ **Current Implementation**: No authentication required

For production:
- Add API key authentication
- Use HTTPS/WSS
- Validate all inputs
- Implement rate limiting
- Add audit logging
- Use environment variables for configuration

---

## Integration Examples

### With Dashboard
```javascript
fetch('http://localhost:9000/status')
  .then(r => r.json())
  .then(data => {
    document.getElementById('status').textContent = 
      data.connected ? '✓ Connected' : '✗ Disconnected'
  })
```

### With Monitoring
```python
import prometheus_client

# Export metrics
gauge = prometheus_client.Gauge('cp_connected', 'Connected status')
gauge.set(1 if status['connected'] else 0)
```

### With Logging
```python
import structlog

logger.info("transaction_started", 
  transaction_id=tx_id, 
  id_tag=id_tag,
  timestamp=datetime.utcnow().isoformat()
)
```

---

## Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| Connection refused | Ensure Steve is running: `docker-compose up app` |
| No handler for X | Handler not implemented for that OCPP operation |
| Transaction failed | Check charge point is registered and available |
| Invalid ID tag | Verify ID tag format with central system |
| Timeout | Increase client timeout or check network |
| High latency | Check WebSocket connection stability |

---

## Testing Checklist

- [ ] Connection established
- [ ] Boot notification received
- [ ] Transaction started
- [ ] Charging simulated
- [ ] Transaction stopped  
- [ ] Configuration retrieved
- [ ] Configuration updated
- [ ] Availability changed
- [ ] Reservation created
- [ ] Reservation cancelled
- [ ] Diagnostics started
- [ ] Firmware update initiated
- [ ] Reset performed
- [ ] Status endpoint working
- [ ] All endpoints respond with proper JSON

---

## Next Steps

1. Try the simple example: `python clients/sample_client.py`
2. Explore advanced features: `python clients/advanced_client_example.py`
3. Review API docs: [API_REFERENCE.md](ocpp-charge-point-api/API_REFERENCE.md)
4. Read implementation summary: [OCPP_OPERATIONS_SUMMARY.md](OCPP_OPERATIONS_SUMMARY.md)
5. Integrate with your system

## Support Resources

- OCPP Spec: https://www.ocpp-info.org/
- Python-OCPP: https://github.com/mobilityhouse/python-ocpp
- Steve Docs: https://github.com/steve-community/steve/wiki
- FastAPI: https://fastapi.tiangolo.com/docs

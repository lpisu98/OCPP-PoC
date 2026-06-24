# OCPP-PoC

Repository for OCPP attack proof-of-concept scenarios built around Steve and a CP simulator written in NodeJS.

## Repository Structure

- `ocpp-base-poc/` - Base OCPP stack used by scenarios 01, 02, and 04.
- `attack_scenarios/01-Heartbeat Flood/` - Heartbeat flood attack script.
- `attack_scenarios/02-CP Flood/` - Multiple charge point flood attack script.
- `attack_scenarios/03-CSMS-Impersonation/` - CSMS impersonation attack stack.
- `attack_scenarios/04-CP-Impersonation/` - Charge point impersonation attack script.
- `attack_scenarios/05-MITM/` - MITM attack stack.
- `run_attack_scenario.sh` - Single launcher for running one or more scenarios with a duration flag.

## How To Run

Use the launcher from the repository root:

```bash
./run_attack_scenario.sh --scenario cp-flood --duration 60
```

You can pass multiple `--scenario` flags if you want to run several scenarios sequentially:

```bash
./run_attack_scenario.sh --scenario heartbeat-flood --scenario cp-impersonation --duration 45
```

Supported scenario values:

- `heartbeat-flood`
- `cp-flood`
- `cp-impersonation`
- `csms-impersonation`
- `mitm`
- `all`

### Performance Flags

| Flag | Effect |
|------|--------|
| `--clean` | Destroy DB/anonymous volumes on teardown (full reset). By default, volumes are preserved so SteVe starts faster on re-runs. |
| `--no-build` | Skip `docker compose build` — use cached images for faster startup when code hasn't changed. |
| `--keep-stack` | Leave the Docker stack running after the scenario finishes. Useful for manual inspection. Tear down manually with `docker compose down`. |

Examples:

```bash
# Fast re-runs (no rebuild, keep DB across restarts):
./run_attack_scenario.sh --scenario cp-flood --no-build

# Full clean reset (destroy DB, equivalent to old behaviour):
./run_attack_scenario.sh --scenario all --clean

# Leave stack running for debugging:
./run_attack_scenario.sh --scenario heartbeat-flood --keep-stack
```

When running `--scenario all`, the three host-based scenarios (heartbeat-flood, cp-flood, cp-impersonation) share a single base stack startup, avoiding the SteVe build cost multiple times.

### What the launcher does

- Scenarios 01, 02, and 04 start the main stack from `ocpp-base-poc/docker-compose.yml`, then execute the matching Python script.
- Scenarios 03 and 05 start their own local `docker-compose.yml` inside the scenario directory.
- `--duration` is expressed in seconds.
- By default, DB volumes are **preserved** between runs (no `-v` on teardown) for faster restarts. Use `--clean` to wipe them.
- When running `all`, host-based scenarios (01, 02, 04) share a single stack start; standalone scenarios (03, 05) each spin up their own.

## PCAP Output

Packet captures are written by the `tcpdump` container in each stack and saved into the local `data/` folder mounted by the compose file.

- Base stack: `ocpp-base-poc/data/poc-ocpp.pcap`
- CSMS impersonation: `attack_scenarios/03-CSMS-Impersonation/data/csms_impersonation_capture.pcap`
- MITM stack: `attack_scenarios/05-MITM/data/mitm_capture.pcap`

The MITM stack also writes proxy logs to `attack_scenarios/05-MITM/logs/captures.jsonl`.
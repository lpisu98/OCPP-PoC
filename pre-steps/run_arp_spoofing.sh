#!/usr/bin/env bash
#
# run_arp_spoofing.sh
#
# Launches the ARP spoofing pre-step lab.
# Starts the real SteVe CSMS + MariaDB + CP simulator + attacker + tcpdump stack,
# lets the attacker poison the ARP caches of the CP and CSMS so traffic flows
# through the attacker, captures the intercepted OCPP traffic, then tears down.
#
# Usage:
#   ./run_arp_spoofing.sh [--duration <seconds>]
#
#   --duration   How long to keep the stack running (default: 60).
#                The tcpdump captures all traffic during this period.
#

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCENARIO_DIR="$ROOT_DIR/arp_spoofing"

DEFAULT_DURATION=60
duration="$DEFAULT_DURATION"

usage() {
  cat <<'EOF'
Usage:
  run_arp_spoofing.sh [--duration <seconds>]

Options:
  --duration   How long (seconds) to keep the stack running so the attacker
               can poison ARP caches and the CP can exchange OCPP messages.
               Default: 60
EOF
}

die() {
  echo "Error: $*" >&2
  exit 1
}

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --duration)
      [[ $# -ge 2 ]] || die "--duration requires a value"
      duration="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

[[ "$duration" =~ ^[0-9]+$ ]] || die "--duration must be a non-negative integer"

# Determine docker compose command
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  DOCKER_COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DOCKER_COMPOSE=(docker-compose)
else
  die "docker compose or docker-compose is required"
fi

cleanup() {
  echo ""
  echo "[INFO] Tearing down ARP spoofing stack..."
  (cd "$SCENARIO_DIR" && "${DOCKER_COMPOSE[@]}" down --remove-orphans) || true
  echo "[INFO] Stack teardown complete."
}

trap cleanup EXIT INT TERM

echo "============================================"
echo " ARP Spoofing MITM — Pre-Step Lab"
echo "============================================"
echo "Duration: ${duration}s"
echo ""

# Build and start the stack
echo "[INFO] Building and starting stack..."
(cd "$SCENARIO_DIR" && "${DOCKER_COMPOSE[@]}" up --build -d)

# Fail fast instead of sleeping for the full capture duration when the attack
# process could not initialize.
sleep 3
attacker_id="$(cd "$SCENARIO_DIR" && "${DOCKER_COMPOSE[@]}" ps --status running -q attacker)"
if [[ -z "$attacker_id" ]]; then
  echo "[ERROR] Attacker exited during startup. Logs:" >&2
  (cd "$SCENARIO_DIR" && "${DOCKER_COMPOSE[@]}" logs attacker) >&2 || true
  exit 1
fi

# Show initial attacker logs
echo ""
echo "--- Attacker logs (initial) ---"
(cd "$SCENARIO_DIR" && "${DOCKER_COMPOSE[@]}" logs attacker) || true
echo "--- End of attacker logs (initial) ---"
echo ""

echo "[INFO] Stack is running. The attacker will poison ARP caches of the CP and CSMS."
echo "[INFO] Capturing traffic for ${duration}s..."
echo ""

# Wait for the specified duration
sleep "$duration"

# Show final logs
echo ""
echo "--- Attacker logs (final) ---"
(cd "$SCENARIO_DIR" && "${DOCKER_COMPOSE[@]}" logs attacker) || true
echo "--- End of attacker logs (final) ---"
echo ""

echo "[INFO] PCAP saved to: $SCENARIO_DIR/data/arp_spoofing_capture.pcap"
echo "[INFO] Done."

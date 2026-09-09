#!/usr/bin/env bash
#
# run_dns_spoofing.sh
#
# Launches the DNS spoofing pre-step lab.
# Starts the malicious DNS server + fake CSMS + CP simulator + tcpdump stack,
# lets the CP connect and exchange OCPP messages, then tears down.
#
# Usage:
#   ./run_dns_spoofing.sh [--duration <seconds>]
#
#   --duration   How long to keep the stack running (default: 30).
#                The tcpdump captures all traffic during this period.
#

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCENARIO_DIR="$ROOT_DIR/dns_spoofing"

DEFAULT_DURATION=30
duration="$DEFAULT_DURATION"

usage() {
  cat <<'EOF'
Usage:
  run_dns_spoofing.sh [--duration <seconds>]

Options:
  --duration   How long (seconds) to keep the stack running so the CP
               can connect and exchange OCPP messages. Default: 30
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
  echo "[INFO] Tearing down DNS spoofing stack..."
  (cd "$SCENARIO_DIR" && "${DOCKER_COMPOSE[@]}" down --remove-orphans) || true
  echo "[INFO] Stack teardown complete."
}

trap cleanup EXIT INT TERM

echo "============================================"
echo " DNS Spoofing — Pre-Step Lab"
echo "============================================"
echo "Duration: ${duration}s"
echo ""

# Build and start the stack
echo "[INFO] Building and starting stack..."
(cd "$SCENARIO_DIR" && "${DOCKER_COMPOSE[@]}" up --build -d)

# Show initial logs from the DNS attacker and fake CSMS
echo ""
echo "--- DNS attacker logs ---"
(cd "$SCENARIO_DIR" && "${DOCKER_COMPOSE[@]}" logs dns_attacker) || true
echo "--- End of DNS attacker logs ---"
echo ""

echo "[INFO] Stack is running. CP simulator will resolve csms.lab via the"
echo "[INFO] malicious DNS and connect to the fake CSMS."
echo "[INFO] Capturing traffic for ${duration}s..."
echo ""

# Wait for the specified duration
sleep "$duration"

# Show final logs
echo ""
echo "--- DNS attacker logs (final) ---"
(cd "$SCENARIO_DIR" && "${DOCKER_COMPOSE[@]}" logs dns_attacker) || true
echo "--- End of DNS attacker logs ---"
echo ""

echo "--- Fake CSMS logs (final) ---"
(cd "$SCENARIO_DIR" && "${DOCKER_COMPOSE[@]}" logs impersonating_csms) || true
echo "--- End of Fake CSMS logs ---"
echo ""

echo "[INFO] PCAP saved to: $SCENARIO_DIR/data/dns_spoofing_capture.pcap"
echo "[INFO] Done."

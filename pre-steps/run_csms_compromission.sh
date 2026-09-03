#!/usr/bin/env bash
#
# run_csms_compromission.sh
#
# Launches the CSMS compromission pre-step lab.
# Starts the SteVe + MariaDB + attacker + tcpdump stack, waits for the
# attacker to finish, then tears down.
#
# Usage:
#   ./run_csms_compromission.sh [--duration <seconds>]
#
#   --duration   How long to keep the stack running after the attacker
#                finishes (default: 10). The tcpdump continues capturing
#                during this extra time.
#

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCENARIO_DIR="$ROOT_DIR/CSMS compromission"

DEFAULT_DURATION=10
duration="$DEFAULT_DURATION"

usage() {
  cat <<'EOF'
Usage:
  run_csms_compromission.sh [--duration <seconds>]

Options:
  --duration   Extra time (seconds) to keep the stack running after the
               attacker finishes, so tcpdump can capture additional traffic.
               Default: 10
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
  echo "[INFO] Tearing down CSMS compromission stack..."
  (cd "$SCENARIO_DIR" && "${DOCKER_COMPOSE[@]}" down --remove-orphans) || true
  echo "[INFO] Stack teardown complete."
}

trap cleanup EXIT INT TERM

echo "============================================"
echo " CSMS Compromission — Pre-Step Lab"
echo "============================================"
echo "Duration (extra capture time): ${duration}s"
echo ""

# Build and start the stack
echo "[INFO] Building and starting stack..."
(cd "$SCENARIO_DIR" && "${DOCKER_COMPOSE[@]}" up --build -d)

# Wait for the attacker container to finish
echo "[INFO] Waiting for attacker container to complete..."
attacker_exit_code=0
(cd "$SCENARIO_DIR" && "${DOCKER_COMPOSE[@]}" wait attacker) || attacker_exit_code=$?

echo "[INFO] Attacker finished (exit code: $attacker_exit_code)."

# Show attacker logs
echo ""
echo "--- Attacker logs ---"
(cd "$SCENARIO_DIR" && "${DOCKER_COMPOSE[@]}" logs attacker) || true
echo "--- End of attacker logs ---"
echo ""

# Keep stack running for the specified duration so tcpdump captures more
if [[ "$duration" -gt 0 ]]; then
  echo "[INFO] Keeping stack alive for ${duration}s to capture additional traffic..."
  sleep "$duration"
fi

echo "[INFO] PCAP saved to: $SCENARIO_DIR/data/csms_compromission_capture.pcap"
echo "[INFO] Done."

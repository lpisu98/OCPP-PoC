#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_DURATION=30

duration="$DEFAULT_DURATION"
declare -a scenarios=()
clean_volumes=false
no_build=false
keep_stack=false

usage() {
  cat <<'EOF'
Usage:
  run_attack_scenario.sh --scenario <name> [--scenario <name> ...] [--duration <seconds>]
                         [--clean] [--no-build] [--keep-stack]

Options:
  --clean          Destroy DB/anonymous volumes on teardown (default: keep them for faster restarts)
  --no-build       Skip "docker compose build" (use cached images for faster startup)
  --keep-stack     Leave the Docker stack running after the scenario finishes (skips teardown)

Scenarios:
  heartbeat-flood | cp-flood | cp-impersonation | csms-impersonation | mitm | all

Examples:
  ./run_attack_scenario.sh --scenario cp-flood --duration 60
  ./run_attack_scenario.sh --scenario mitm
  ./run_attack_scenario.sh --scenario all --duration 120
  ./run_attack_scenario.sh --scenario all --clean          # full reset, destroy DB volumes
  ./run_attack_scenario.sh --scenario cp-flood --no-build  # skip rebuild for speed
  ./run_attack_scenario.sh --scenario heartbeat-flood --keep-stack  # leave stack running
EOF
}

die() {
  echo "Error: $*" >&2
  exit 1
}

if command -v docker >/dev/null 2>&1; then
  DOCKER_COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DOCKER_COMPOSE=(docker-compose)
else
  die "docker compose or docker-compose is required"
fi

python_cmd=""
if command -v python3 >/dev/null 2>&1; then
  python_cmd="python3"
elif command -v python >/dev/null 2>&1; then
  python_cmd="python"
fi

# ---------------------------------------------------------------------------
# cleanup_compose_stack
#   First argument (optional): "-v" to also destroy anonymous volumes.
#   By default volumes are preserved so SteVe startup is faster on re-runs.
# ---------------------------------------------------------------------------
cleanup_compose_stack() {
  local extra_flags="${1:-}"
  if [[ -n "${STACK_DIR:-}" && -n "${STACK_FILE:-}" ]]; then
    (cd "$STACK_DIR" && "${DOCKER_COMPOSE[@]}" -f "$STACK_FILE" down ${extra_flags:+"$extra_flags"} --remove-orphans) || true
  fi
}

# ---------------------------------------------------------------------------
# build_flags
#   Returns "--build" unless --no-build was requested.
# ---------------------------------------------------------------------------
build_flags() {
  if [[ "$no_build" == "true" ]]; then
    echo ""
  else
    echo "--build"
  fi
}

# ---------------------------------------------------------------------------
# setup_cleanup_trap
#   Installs the EXIT trap.  If --keep-stack is set the trap is a no-op.
#   If --clean is set, volumes are destroyed on teardown.
# ---------------------------------------------------------------------------
setup_cleanup_trap() {
  if [[ "$keep_stack" == "true" ]]; then
    echo "[INFO] --keep-stack is set: stack will NOT be torn down automatically."
    trap '' EXIT INT TERM
  elif [[ "$clean_volumes" == "true" ]]; then
    trap 'cleanup_compose_stack "-v"' EXIT INT TERM
  else
    trap 'cleanup_compose_stack' EXIT INT TERM
  fi
}

# ---------------------------------------------------------------------------
# run_host_python_scenario
# ---------------------------------------------------------------------------
run_host_python_scenario() {
  local scenario_dir="$1"
  local script_name="$2"

  [[ -n "$python_cmd" ]] || die "python3 or python is required for host-run scenarios"

  echo "Starting host scenario: $script_name ($duration s)"
  (cd "$scenario_dir" && DURATION_S="$duration" "$python_cmd" "$script_name")
}

# ---------------------------------------------------------------------------
# run_compose_scenario
# ---------------------------------------------------------------------------
run_compose_scenario() {
  local scenario_dir="$1"
  local compose_file="$2"

  echo "Starting compose scenario: $(basename "$scenario_dir") ($duration s)"
  (
    STACK_DIR="$scenario_dir"
    STACK_FILE="$compose_file"
    setup_cleanup_trap
    cd "$scenario_dir"
    "${DOCKER_COMPOSE[@]}" -f "$compose_file" up -d $(build_flags)
    sleep "$duration"
  )
}

# ---------------------------------------------------------------------------
# run_host_python_with_compose
# ---------------------------------------------------------------------------
run_host_python_with_compose() {
  local compose_dir="$1"
  local compose_file="$2"
  local scenario_dir="$3"
  local script_name="$4"

  [[ -n "$python_cmd" ]] || die "python3 or python is required for host-run scenarios"

  echo "Starting host scenario with base compose: $script_name ($duration s)"
  (
    STACK_DIR="$compose_dir"
    STACK_FILE="$compose_file"
    setup_cleanup_trap
    cd "$compose_dir"
    "${DOCKER_COMPOSE[@]}" -f "$compose_file" up -d $(build_flags)
    cd "$scenario_dir"
    DURATION_S="$duration" "$python_cmd" "$script_name"
  )
}

# ---------------------------------------------------------------------------
# run_base_stack_host_scenarios  (optimisation for "all")
#   Starts the base ocpp-base-poc stack ONCE, then runs every host-based
#   python scenario against it sequentially.  This avoids paying the SteVe
#   startup cost multiple times.
# ---------------------------------------------------------------------------
run_base_stack_host_scenarios() {
  local compose_dir="$ROOT_DIR/ocpp-base-poc"
  local compose_file="docker-compose.yml"

  echo "=== Starting base stack ONCE for all host-based scenarios ==="

  (
    STACK_DIR="$compose_dir"
    STACK_FILE="$compose_file"
    setup_cleanup_trap

    cd "$compose_dir"
    "${DOCKER_COMPOSE[@]}" -f "$compose_file" up -d $(build_flags)

    # --- Scenario 01: Heartbeat Flood ---
    echo ""
    echo "--- Running: heartbeat-flood ($duration s) ---"
    DURATION_S="$duration" "$python_cmd" "$ROOT_DIR/attack_scenarios/01-Heartbeat Flood/heartbeat_flood.py"

    # --- Scenario 02: CP Flood ---
    echo ""
    echo "--- Running: cp-flood ($duration s) ---"
    DURATION_S="$duration" "$python_cmd" "$ROOT_DIR/attack_scenarios/02-CP Flood/CP_flood.py"

    # --- Scenario 04: CP Impersonation ---
    echo ""
    echo "--- Running: cp-impersonation ($duration s) ---"
    DURATION_S="$duration" "$python_cmd" "$ROOT_DIR/attack_scenarios/04-CP-Impersonation/cp_impersonation.py"

    echo ""
    echo "=== All host-based scenarios finished ==="
    # trap fires here on subshell exit → cleanup
  )
}

# ---------------------------------------------------------------------------
# run_scenario (dispatch)
# ---------------------------------------------------------------------------
run_scenario() {
  local scenario="$1"

  case "$scenario" in
    heartbeat-flood)
      run_host_python_with_compose "$ROOT_DIR/ocpp-base-poc" "docker-compose.yml" "$ROOT_DIR/attack_scenarios/01-Heartbeat Flood" "heartbeat_flood.py"
      ;;
    cp-flood)
      run_host_python_with_compose "$ROOT_DIR/ocpp-base-poc" "docker-compose.yml" "$ROOT_DIR/attack_scenarios/02-CP Flood" "CP_flood.py"
      ;;
    cp-impersonation)
      run_host_python_with_compose "$ROOT_DIR/ocpp-base-poc" "docker-compose.yml" "$ROOT_DIR/attack_scenarios/04-CP-Impersonation" "cp_impersonation.py"
      ;;
    csms-impersonation)
      run_compose_scenario "$ROOT_DIR/attack_scenarios/03-CSMS-Impersonation" "docker-compose.yml"
      ;;
    mitm)
      run_compose_scenario "$ROOT_DIR/attack_scenarios/05-MITM" "docker-compose.yml"
      ;;
    all)
      # Optimised path: start base stack once, run 3 host scenarios, then
      # run the 2 standalone-compose scenarios (each with its own stack).
      run_base_stack_host_scenarios

      echo ""
      echo "=== Running standalone-compose scenarios ==="
      echo ""

      run_scenario csms-impersonation
      run_scenario mitm

      echo ""
      echo "=== All scenarios complete ==="
      ;;
    *)
      die "Unknown scenario: $scenario"
      ;;
  esac
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --scenario)
      [[ $# -ge 2 ]] || die "--scenario requires a value"
      scenarios+=("${2,,}")
      shift 2
      ;;
    --duration)
      [[ $# -ge 2 ]] || die "--duration requires a value"
      duration="$2"
      shift 2
      ;;
    --clean)
      clean_volumes=true
      shift
      ;;
    --no-build)
      no_build=true
      shift
      ;;
    --keep-stack)
      keep_stack=true
      shift
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

[[ ${#scenarios[@]} -gt 0 ]] || die "Provide at least one --scenario"

for scenario in "${scenarios[@]}"; do
  run_scenario "$scenario"
done
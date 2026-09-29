# Local service ports, shared by the FaultLab start scripts (source this file; it runs nothing).
# One environment setting per service; unset or empty means the documented default:
#   FAULTLAB_SIMULATOR_PORT  8001    FAULTLAB_BACKEND_PORT  8000    FAULTLAB_DASHBOARD_PORT  5173
# backend/app/ports.py and frontend/local-ports.ts apply the same rule.

# faultlab_port NAME DEFAULT: print the port, or explain the problem and return 2.
faultlab_port() {
  local name="$1" default="$2" value
  value="${!1:-}"
  if [[ -z "$value" ]]; then
    printf '%s\n' "$default"
    return 0
  fi
  if [[ ! "$value" =~ ^[1-9][0-9]{0,4}$ ]] || (( value > 65535 )); then
    printf '%s must be a whole port number from 1 to 65535 (got %s).\n' "$name" "$value" >&2
    return 2
  fi
  printf '%s\n' "$value"
}

# When only FAULTLAB_SIMULATOR_PORT is given, point the backend at that simulator port.
# An explicit FAULTLAB_SIMULATOR_URL in the process environment still wins; with neither
# set nothing is exported, so the backend keeps its .env or default simulator URL.
faultlab_export_simulator_url() {
  local port
  if [[ -n "${FAULTLAB_SIMULATOR_PORT:-}" && -z "${FAULTLAB_SIMULATOR_URL:-}" ]]; then
    port="$(faultlab_port FAULTLAB_SIMULATOR_PORT 8001)" || return 2
    FAULTLAB_SIMULATOR_URL="http://127.0.0.1:${port}"
    export FAULTLAB_SIMULATOR_URL
  fi
}

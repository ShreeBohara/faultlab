#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# Port: FAULTLAB_SIMULATOR_PORT (default 8001). See scripts/lib/ports.sh.
source "$ROOT/scripts/lib/ports.sh"
listen_port="$(faultlab_port FAULTLAB_SIMULATOR_PORT 8001)"
cd "$ROOT/backend"
# --timeout-keep-alive 75: defence in depth against the Phase 13/14 failure. uvicorn's
# default is 5s, and its keep-alive handler closes the transport without draining the
# socket, so on macOS a request that lands just before the deadline is answered with
# RST and discarded before the app runs. WorldClient already retires its connections
# at KEEPALIVE_EXPIRY=2.0s so the client always closes first; this makes the server
# the slower side too, for any client that does not. It changes only TCP connection
# lifetime - no handler, response, fixture, fault schedule or referee input.
exec "$ROOT/.venv/bin/python" -m uvicorn app.simulator.main:app --host 127.0.0.1 --port "$listen_port" --timeout-keep-alive 75

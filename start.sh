#!/usr/bin/env bash
# Starts Stud Finder Plus in one terminal: checks the Pro Micro's port,
# optionally uploads the firmware, then runs the web app on that port.
#
#   ./start.sh              check the port, run the app
#   ./start.sh --flash      upload the stud finder firmware first
#   ./start.sh --camera 1   anything else is passed on to host/web.py
#
# Stud events (S1/S0) show up in this terminal and on the page, so there's no
# need for `pio device monitor` (it can't share the port with the app anyway).
set -eo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python
FLASH=0
ARGS=()
for a in "$@"; do
  if [[ $a == --flash ]]; then FLASH=1; else ARGS+=("$a"); fi
done

if [[ ! -x $PY ]]; then
  echo "No .venv yet. Run the Setup steps in README.md first." >&2
  exit 1
fi
if [[ ! -f host/web/dist/index.html ]]; then
  echo "note: the web page isn't built (cd host/web && npm install && npm run build)" >&2
fi

echo "== checking the stud finder port"
PORT=$($PY host/serial_link.py) || exit 1
echo "   $PORT"

if [[ $FLASH == 1 ]]; then
  echo "== uploading firmware"
  pio run -t upload --upload-port "$PORT"
  # The Pro Micro resets after an upload and its port comes back a moment later.
  echo "== waiting for the board to come back"
  for _ in $(seq 20); do
    sleep 0.5
    if PORT=$($PY host/serial_link.py 2>/dev/null); then break; fi
  done
  PORT=$($PY host/serial_link.py) || exit 1
  echo "   $PORT"
fi

# The port check above also finds the laser station when it's plugged in.
if [[ " ${ARGS[*]-} " != *" --laser-"* ]] && $PY -c '
import os, sys
sys.path.insert(0, "host")
from serial_link import configured_port
p = configured_port("laser")
sys.exit(0 if p and os.path.exists(p) else 1)'; then
  echo "== laser station found, using it"
  ARGS+=(--laser-serial)
fi

echo "== starting the web app (Ctrl+C to stop)"
exec "$PY" host/web.py --tape --serial --port "$PORT" ${ARGS[@]+"${ARGS[@]}"}

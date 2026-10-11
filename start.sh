#!/bin/sh
set -eu

cd "$(dirname "$0")"

PYTHON_BIN=python
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Startup error: python (3.10+) is required on PATH" >&2
  exit 2
fi

# Validate every setting before creating any listener process.
"$PYTHON_BIN" -m hearth.launch validate
if [ -z "${HEARTH_SESSION_KEY+x}" ]; then
  HEARTH_SESSION_KEY=$("$PYTHON_BIN" -c 'import secrets; print(secrets.token_urlsafe(48))')
  export HEARTH_SESSION_KEY
fi

"$PYTHON_BIN" -m hearth.launch prepare

pids=""
stopping=0
cleanup() {
  if [ "$stopping" -eq 1 ]; then return; fi
  stopping=1
  trap - TERM INT EXIT
  for pid in $pids; do kill -TERM "$pid" 2>/dev/null || true; done
  for pid in $pids; do wait "$pid" 2>/dev/null || true; done
}
terminate() {
  cleanup
  exit 0
}
trap cleanup EXIT
trap terminate TERM INT

"$PYTHON_BIN" -m hearth.launch ai & pids="$pids $!"
"$PYTHON_BIN" -m hearth.launch adapter & pids="$pids $!"
"$PYTHON_BIN" -m hearth.launch dashboard & pids="$pids $!"
if [ "${HEARTH_SIMULATE:-0}" = "1" ]; then
  "$PYTHON_BIN" -m hearth.launch simulator & pids="$pids $!"
fi

# Poll child liveness so this remains portable to the system shells on macOS/Linux.
exit_code=0
while :; do
  for pid in $pids; do
    if ! kill -0 "$pid" 2>/dev/null; then
      wait "$pid" || exit_code=$?
      cleanup
      exit "$exit_code"
    fi
  done
  sleep 0.2
done

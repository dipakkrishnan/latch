#!/usr/bin/env bash
set -euo pipefail

if [[ $# -eq 0 ]]; then
  set -- node openclaw.mjs gateway --allow-unconfigured
fi

LATCH_HOST="${LATCH_HOST:-0.0.0.0}"
LATCH_PORT="${LATCH_PORT:-18890}"
LATCH_CHAT_ROUTE_NONBLOCKING="${LATCH_CHAT_ROUTE_NONBLOCKING:-0}"
LATCH_PLUGIN_PATH="${LATCH_PLUGIN_PATH:-/opt/latch-openclaw-plugin}"
export LATCH_CHAT_ROUTE_NONBLOCKING

playwright_chrome="$(find /home/node/.cache/ms-playwright -maxdepth 3 -type f -path '*/chrome-linux/chrome' 2>/dev/null | head -n 1 || true)"
if [[ -n "${playwright_chrome}" ]]; then
  if [[ ! -f /home/node/.openclaw/openclaw.json ]] || ! grep -q '"executablePath"' /home/node/.openclaw/openclaw.json; then
    node dist/index.js config set browser.executablePath "${playwright_chrome}" >/dev/null 2>&1 || true
  fi
fi

# Clear stale singleton locks from unclean browser shutdowns in persisted profiles.
rm -f \
  /home/node/.openclaw/browser/openclaw/user-data/SingletonLock \
  /home/node/.openclaw/browser/openclaw/user-data/SingletonCookie \
  /home/node/.openclaw/browser/openclaw/user-data/SingletonSocket || true

if [[ -d "${LATCH_PLUGIN_PATH}" ]]; then
  node dist/index.js plugins install --link "${LATCH_PLUGIN_PATH}" >/dev/null 2>&1 || true
  node dist/index.js plugins enable latch-approval-gate >/dev/null 2>&1 || true
fi

node dist/index.js config set hooks.allowRequestSessionKey true >/dev/null 2>&1 || true

/opt/latch-venv/bin/python -m latch.server --host "$LATCH_HOST" --port "$LATCH_PORT" &
latch_pid=$!

"$@" &
main_pid=$!

cleanup() {
  kill "$main_pid" "$latch_pid" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

wait -n "$main_pid" "$latch_pid"
exit_code=$?

cleanup
wait "$main_pid" 2>/dev/null || true
wait "$latch_pid" 2>/dev/null || true

exit "$exit_code"

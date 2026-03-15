#!/usr/bin/env sh
set -eu

echo "[latch] Installing latch-agent..."

has() {
  command -v "$1" >/dev/null 2>&1
}

if has pipx; then
  if pipx list 2>/dev/null | grep -q "latch-agent"; then
    echo "[latch] Upgrading existing install via pipx..."
    pipx upgrade latch-agent >/dev/null 2>&1 || pipx install --force latch-agent
  else
    pipx install latch-agent
  fi
elif has uv; then
  echo "[latch] pipx not found; using uv tool install..."
  uv tool install --upgrade latch-agent
else
  echo "[latch] Error: install pipx or uv first." >&2
  echo "[latch] pipx: https://pypa.github.io/pipx/" >&2
  echo "[latch] uv: https://docs.astral.sh/uv/" >&2
  exit 1
fi

if has latch; then
  echo "[latch] Installed: $(latch --version)"
  echo "[latch] Next: latch init"
else
  echo "[latch] Installed, but 'latch' is not on PATH in this shell." >&2
  echo "[latch] Open a new shell, then run: latch init" >&2
fi

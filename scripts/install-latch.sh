#!/usr/bin/env sh
set -eu

echo "[latch] Installing latch-agent CLI..."

has() {
  command -v "$1" >/dev/null 2>&1
}

install_with_pipx() {
  if pipx list 2>/dev/null | grep -q "latch-agent"; then
    echo "[latch] Upgrading existing pipx install..."
    pipx upgrade latch-agent >/dev/null 2>&1 || pipx install --force latch-agent
  else
    pipx install latch-agent
  fi
}

if has pipx; then
  install_with_pipx
elif has uv; then
  echo "[latch] pipx not found; using uv tool install..."
  uv tool install --upgrade latch-agent
else
  echo "[latch] pipx/uv not found; bootstrapping pipx with python..."
  if has python3; then
    PY=python3
  elif has python; then
    PY=python
  else
    echo "[latch] Error: python is required (3.10+)." >&2
    exit 1
  fi
  "$PY" -m pip install --user --upgrade pipx
  "$PY" -m pipx ensurepath >/dev/null 2>&1 || true
  PIPX_BIN="$HOME/.local/bin/pipx"
  if [ -x "$PIPX_BIN" ]; then
    "$PIPX_BIN" install --force latch-agent
  elif has pipx; then
    pipx install --force latch-agent
  else
    echo "[latch] pipx installed but not on PATH yet." >&2
    echo "[latch] Re-open your shell, then run: pipx install latch-agent" >&2
    exit 1
  fi
fi

if has latch; then
  echo "[latch] Installed: $(latch --version)"
  echo "[latch] Next: latch setup"
else
  echo "[latch] Installed, but 'latch' is not on PATH yet." >&2
  echo "[latch] Try opening a new shell, then run: latch setup" >&2
fi

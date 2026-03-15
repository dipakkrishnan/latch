#!/bin/sh
# Run this inside the OpenClaw container to register latch as an MCP server via mcporter.
# Usage: sh setup-openclaw-mcporter.sh [latch_url]
#
# Default URL assumes latch is reachable at host.docker.internal:8100
# (latch container with port 8100 mapped to the host).

set -e

LATCH_URL="${1:-http://host.docker.internal:8100/mcp}"
CONFIG_DIR="${HOME}/.mcporter"
CONFIG_FILE="${CONFIG_DIR}/mcporter.json"

# Ensure mcporter is available
if ! command -v mcporter >/dev/null 2>&1; then
  echo "[latch] Installing mcporter..."
  npm install -g mcporter 2>/dev/null || npm install --prefix "${HOME}/.local" mcporter
fi

# Write config
mkdir -p "${CONFIG_DIR}"

if [ -f "${CONFIG_FILE}" ]; then
  # Merge latch into existing config (using node since jq may not be available)
  node -e "
    const fs = require('fs');
    const cfg = JSON.parse(fs.readFileSync('${CONFIG_FILE}', 'utf8'));
    cfg.mcpServers = cfg.mcpServers || {};
    cfg.mcpServers.latch = { url: '${LATCH_URL}', allowHttp: true };
    fs.writeFileSync('${CONFIG_FILE}', JSON.stringify(cfg, null, 2));
  "
  echo "[latch] Updated ${CONFIG_FILE} with latch server."
else
  cat > "${CONFIG_FILE}" <<EOF
{
  "mcpServers": {
    "latch": {
      "url": "${LATCH_URL}",
      "allowHttp": true
    }
  }
}
EOF
  echo "[latch] Created ${CONFIG_FILE} with latch server."
fi

# Verify
echo "[latch] Verifying connection..."
npx mcporter list --http-url "${LATCH_URL}" --name latch --allow-http 2>&1 || echo "[latch] Warning: could not reach latch at ${LATCH_URL}. Is the latch container running?"

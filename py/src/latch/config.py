import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("AGENT_2FA_DIR", Path.home() / ".agent-2fa"))

LATCH_APPROVAL_PORT = int(os.environ.get("LATCH_APPROVAL_PORT", "0"))
LATCH_RP_ID = os.environ.get("LATCH_RP_ID", "localhost")
LATCH_ORIGIN = os.environ.get("LATCH_ORIGIN", "")
LATCH_MCP_TRANSPORT = os.environ.get("LATCH_MCP_TRANSPORT", "stdio")
LATCH_MCP_HOST = os.environ.get("LATCH_MCP_HOST", "127.0.0.1")
LATCH_MCP_PORT = int(os.environ.get("LATCH_MCP_PORT", "8000"))
LATCH_MCP_PATH = os.environ.get("LATCH_MCP_PATH", "/mcp")

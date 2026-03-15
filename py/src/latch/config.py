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
LATCH_APPROVAL_REDIRECT_URL = os.environ.get("LATCH_APPROVAL_REDIRECT_URL", "")

# OpenClaw webhook callback — pushes approval results into the chat session
OPENCLAW_HOOKS_URL = os.environ.get("OPENCLAW_HOOKS_URL", "")  # e.g. http://openclaw:18789/hooks/agent
OPENCLAW_HOOKS_TOKEN = os.environ.get("OPENCLAW_HOOKS_TOKEN", "")
OPENCLAW_SESSION_KEY = os.environ.get("OPENCLAW_SESSION_KEY", "")  # e.g. agent:main:whatsapp:direct:number
OPENCLAW_CHANNEL = os.environ.get("OPENCLAW_CHANNEL", "")  # e.g. whatsapp
OPENCLAW_CHANNEL_TO = os.environ.get("OPENCLAW_CHANNEL_TO", "") 
OPENCLAW_SESSION_KEY = os.environ.get("OPENCLAW_SESSION_KEY", "")  # e.g. agent:main:whatsapp:direct:+14124679849
OPENCLAW_CHANNEL = os.environ.get("OPENCLAW_CHANNEL", "")  # e.g. whatsapp
OPENCLAW_CHANNEL_TO = os.environ.get("OPENCLAW_CHANNEL_TO", "")  # e.g. +14124679849

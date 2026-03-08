import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("AGENT_2FA_DIR", Path.home() / ".agent-2fa"))

LATCH_APPROVAL_PORT = int(os.environ.get("LATCH_APPROVAL_PORT", "0"))
LATCH_RP_ID = os.environ.get("LATCH_RP_ID", "localhost")
LATCH_ORIGIN = os.environ.get("LATCH_ORIGIN", "")

import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("AGENT_2FA_DIR", Path.home() / ".agent-2fa"))

import json
from datetime import datetime, timezone

from .config import config_dir


def _path():
    return config_dir() / "audit.jsonl"


def append(tool_name: str, action: str, decision: str, reason: str) -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "tool": tool_name,
        "action": action,
        "decision": decision,
        "reason": reason,
    }
    with _path().open("a") as f:
        f.write(json.dumps(entry) + "\n")


def read(limit: int = 20) -> list[dict]:
    p = _path()
    if not p.exists():
        return []
    entries = []
    for line in p.read_text().splitlines():
        try:
            entries.append(json.loads(line))
        except Exception:
            pass
    return entries[-limit:]

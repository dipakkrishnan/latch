import json, os, uuid
from datetime import datetime, timezone
from pathlib import Path

_DIR = Path(os.environ.get("AGENT_2FA_DIR", Path.home() / ".agent-2fa"))
_PATH = _DIR / "audit.jsonl"


def append(tool_name, tool_input, action, decision, reason, method, mode):
    _DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "toolName": tool_name,
        "toolInput": tool_input,
        "action": action,
        "decision": decision,
        "reason": reason,
        "method": method,
        "mode": mode,
    }
    with _PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def read(limit=50, offset=0):
    if not _PATH.exists():
        return []
    lines = [l for l in _PATH.read_text().splitlines() if l.strip()]
    entries = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except Exception:
            pass
    return list(reversed(entries))[offset : offset + limit]


def stats():
    all_entries = read(limit=10**9)
    by_tool: dict = {}
    approvals = denials = asks = 0
    for e in all_entries:
        d = e.get("decision")
        if d == "allow": approvals += 1
        elif d == "deny": denials += 1
        elif d == "ask": asks += 1
        t = e.get("toolName", "unknown")
        by_tool[t] = by_tool.get(t, 0) + 1
    return {"total": len(all_entries), "approvals": approvals, "denials": denials, "asks": asks, "byTool": by_tool}

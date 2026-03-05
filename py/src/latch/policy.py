import os, re
from pathlib import Path
import yaml

_DIR = Path(os.environ.get("AGENT_2FA_DIR", Path.home() / ".agent-2fa"))
_PATH = _DIR / "policy.yaml"
_DEFAULT = """\
defaultAction: allow
rules:
  - match: {tool: Bash}
    action: ask
  - match: {tool: 'Edit|Write|NotebookEdit'}
    action: ask
  - match: {tool: 'Read|Glob|Grep'}
    action: allow
"""
_cache = None


def load_policy(force=False):
    global _cache
    if _cache and not force:
        return _cache
    if not _PATH.exists():
        _DIR.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(_DEFAULT)
    _cache = yaml.safe_load(_PATH.read_text())
    return _cache


def evaluate(tool_name: str, policy: dict) -> tuple[str, str]:
    for rule in policy.get("rules", []):
        pattern = rule["match"]["tool"]
        if re.fullmatch(pattern, tool_name):
            action = rule["action"]
            return action, f'Policy rule: "{pattern}" → {action}'
    default = policy.get("defaultAction", "allow")
    return default, f"Default policy action: {default}"

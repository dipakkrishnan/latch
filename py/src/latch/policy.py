import re
import yaml

from .config import CONFIG_DIR

_PATH = CONFIG_DIR / "policy.yaml"
DEFAULT_POLICY = """\
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
_cache_mtime = 0.0


def load_policy(force=False):
    global _cache, _cache_mtime
    if not _PATH.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(DEFAULT_POLICY)
    mtime = _PATH.stat().st_mtime
    if _cache and not force and mtime == _cache_mtime:
        return _cache
    _cache = yaml.safe_load(_PATH.read_text())
    _cache_mtime = mtime
    return _cache


def evaluate(tool_name: str, policy: dict) -> tuple[str, str]:
    for rule in policy.get("rules", []):
        pattern = rule["match"]["tool"]
        if re.fullmatch(pattern, tool_name):
            action = rule["action"]
            return action, f'Policy rule: "{pattern}" → {action}'
    default = policy.get("defaultAction", "allow")
    return default, f"Default policy action: {default}"

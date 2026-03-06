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


def load_policy(force=False):
    global _cache
    if _cache and not force:
        return _cache
    if not _PATH.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(DEFAULT_POLICY)
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

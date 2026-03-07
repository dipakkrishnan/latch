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

MCP_ONBOARD_POLICY = """\
defaultAction: allow
rules:
  - match: {tool: '.*__(write|edit|delete|execute|run|bash|shell).*'}
    action: webauthn
  - match: {tool: '.*__(create|update|commit|push|deploy).*'}
    action: webauthn
  - match: {tool: '.*__(read|get|list|search).*'}
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


def save_policy(config):
    global _cache
    if not isinstance(config, dict):
        raise ValueError("policy config must be a mapping")
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(yaml.safe_dump(config, sort_keys=False))
    _cache = config


def apply_mcp_onboard_policy():
    config = yaml.safe_load(MCP_ONBOARD_POLICY)
    save_policy(config)
    return config


def evaluate(tool_name: str, policy: dict) -> tuple[str, str]:
    for rule in policy.get("rules", []):
        pattern = rule["match"]["tool"]
        if re.fullmatch(pattern, tool_name):
            action = rule["action"]
            return action, f'Policy rule: "{pattern}" → {action}'
    default = policy.get("defaultAction", "allow")
    return default, f"Default policy action: {default}"


def policy_uses_ask(policy: dict) -> bool:
    if policy.get("defaultAction") == "ask":
        return True
    for rule in policy.get("rules", []):
        if isinstance(rule, dict) and rule.get("action") == "ask":
            return True
    return False

import re

import yaml

from .config import config_dir

_DEFAULT = """\
defaultAction: approve
rules:
  - match: {tool: '(ls|pwd|whoami|cat|head|tail|echo|date|env)'}
    action: allow
  - match: {tool: '(rm|chmod|chown|kill|shutdown|reboot)'}
    action: deny
"""


def load() -> dict:
    p = config_dir() / "policy.yaml"
    if not p.exists():
        config_dir().mkdir(parents=True, exist_ok=True)
        p.write_text(_DEFAULT)
    return yaml.safe_load(p.read_text()) or {}


def save(policy: dict) -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    (config_dir() / "policy.yaml").write_text(yaml.dump(policy, default_flow_style=False))


def evaluate(tool_name: str, policy: dict) -> tuple[str, str]:
    for rule in policy.get("rules", []):
        pattern = rule["match"]["tool"]
        if re.fullmatch(pattern, tool_name):
            action = rule["action"]
            return action, f'Rule: "{pattern}" → {action}'
    default = policy.get("defaultAction", "allow")
    return default, f"Default: {default}"

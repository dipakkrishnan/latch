from __future__ import annotations

import yaml


PRESETS: dict[str, dict] = {
    "Permissive": {
        "defaultAction": "allow",
        "rules": [
            {"match": {"tool": "Bash"}, "action": "ask"},
        ],
    },
    "Balanced": {
        "defaultAction": "allow",
        "rules": [
            {"match": {"tool": "Bash"}, "action": "ask"},
            {"match": {"tool": "Edit|Write|NotebookEdit"}, "action": "ask"},
            {"match": {"tool": "Read|Glob|Grep"}, "action": "allow"},
        ],
    },
    "Strict": {
        "defaultAction": "deny",
        "rules": [
            {"match": {"tool": "Read|Glob|Grep"}, "action": "allow"},
            {"match": {"tool": ".*"}, "action": "webauthn"},
        ],
    },
}


def preset_names() -> list[str]:
    return list(PRESETS.keys())


def preset_choice_labels() -> dict[str, str]:
    return {
        "Permissive": "Permissive (allow most, ask Bash)",
        "Balanced": "Balanced (allow reads, ask writes/shell)",
        "Strict": "Strict (read-only allowlist, passkey for actions)",
    }


def get_preset(name: str) -> dict:
    if name not in PRESETS:
        raise KeyError(f"Unknown preset: {name}")
    # Safe deep copy via serialization; preset shape is YAML-safe dict/list scalars.
    return yaml.safe_load(yaml.safe_dump(PRESETS[name]))


def to_yaml(policy: dict) -> str:
    return yaml.safe_dump(policy, sort_keys=False)


def rules_rows(policy: dict) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for rule in policy.get("rules", []):
        rows.append((str(rule.get("match", {}).get("tool", "")), str(rule.get("action", ""))))
    return rows

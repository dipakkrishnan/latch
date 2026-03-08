import os
from pathlib import Path

import json

import yaml

_DIR = Path(os.environ.get("LATCH_DIR", Path.home() / ".latch"))


def config_dir() -> Path:
    return _DIR


def _path(name: str) -> Path:
    return _DIR / name


def load() -> dict:
    p = _path("config.yaml")
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text()) or {}


def save(cfg: dict) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    _path("config.yaml").write_text(yaml.dump(cfg, default_flow_style=False))


def load_totp_secret() -> str | None:
    p = _path("totp_secret.key")
    return p.read_text().strip() if p.exists() else None


def save_totp_secret(secret: str) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    p = _path("totp_secret.key")
    p.write_text(secret)
    p.chmod(0o600)


def auto_detect_gateway() -> tuple[str, str]:
    """Auto-detect OpenClaw gateway URL and token."""
    cfg = load()
    default_url = "http://127.0.0.1:18789/hooks/agent"
    url = str(cfg.get("openclaw_webhook_url", "")).strip()

    token = os.environ.get("OPENCLAW_HOOKS_TOKEN", "").strip()
    if not token:
        token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "").strip()

    oc_json = Path.home() / ".openclaw" / "openclaw.json"
    if oc_json.exists():
        try:
            oc = json.loads(oc_json.read_text())
            hooks_cfg = oc.get("hooks", {}) if isinstance(oc, dict) else {}
            hooks_enabled = bool(hooks_cfg.get("enabled")) if isinstance(hooks_cfg, dict) else False
            hooks_token = str(hooks_cfg.get("token", "")).strip() if isinstance(hooks_cfg, dict) else ""
            hooks_path = str(hooks_cfg.get("path", "/hooks")).strip() if isinstance(hooks_cfg, dict) else "/hooks"

            if not url and hooks_enabled:
                base_path = hooks_path if hooks_path.startswith("/") else f"/{hooks_path}"
                base_path = base_path.rstrip("/") or "/hooks"
                url = f"http://127.0.0.1:18789{base_path}/agent"

            # Prefer dedicated hooks token when available.
            if hooks_enabled and hooks_token:
                token = hooks_token
            elif not token:
                token = str(oc.get("gateway", {}).get("auth", {}).get("token", "")).strip()
        except Exception:
            pass

    if not url:
        url = default_url
    if not token:
        token = str(cfg.get("openclaw_webhook_token", "")).strip()

    return url, token

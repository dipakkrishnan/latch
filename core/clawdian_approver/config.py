from __future__ import annotations

import os
import platform
from dataclasses import dataclass


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    gateway_ws_url: str
    gateway_token: str
    latch_base_url: str
    latch_token: str
    allow_decision: str
    poll_interval_seconds: float
    poll_timeout_seconds: float
    strict_deny_on_error: bool
    debug_frames: bool
    client_id: str
    client_mode: str
    client_version: str
    client_platform: str
    scopes: list[str]
    device_key_path: str

    @classmethod
    def from_env(cls) -> Config:
        required = {
            "OPENCLAW_GATEWAY_WS_URL": os.getenv("OPENCLAW_GATEWAY_WS_URL", "").strip(),
            "OPENCLAW_GATEWAY_TOKEN": os.getenv("OPENCLAW_GATEWAY_TOKEN", "").strip(),
            "LATCH_BASE_URL": os.getenv("LATCH_BASE_URL", "").strip(),
            "LATCH_TOKEN": os.getenv("LATCH_TOKEN", "").strip(),
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"Missing required environment variable(s): {', '.join(missing)}")

        allow_decision = os.getenv("CLAWDIAN_ALLOW_DECISION", "allow-once").strip()
        if allow_decision not in {"allow-once", "allow-always"}:
            raise ValueError("CLAWDIAN_ALLOW_DECISION must be one of: allow-once, allow-always")

        scopes_raw = os.getenv("CLAWDIAN_SCOPES", "operator.read,operator.write,operator.approvals").strip()
        scopes = [s.strip() for s in scopes_raw.split(",") if s.strip()]
        if not scopes:
            raise ValueError("CLAWDIAN_SCOPES must contain at least one scope")

        return cls(
            gateway_ws_url=required["OPENCLAW_GATEWAY_WS_URL"],
            gateway_token=required["OPENCLAW_GATEWAY_TOKEN"],
            latch_base_url=required["LATCH_BASE_URL"].rstrip("/"),
            latch_token=required["LATCH_TOKEN"],
            allow_decision=allow_decision,
            poll_interval_seconds=float(os.getenv("CLAWDIAN_POLL_INTERVAL_SECONDS", "2")),
            poll_timeout_seconds=float(os.getenv("CLAWDIAN_POLL_TIMEOUT_SECONDS", "300")),
            strict_deny_on_error=_bool_env("CLAWDIAN_STRICT_DENY_ON_ERROR", True),
            debug_frames=_bool_env("CLAWDIAN_DEBUG_FRAMES", False),
            client_id=os.getenv("CLAWDIAN_CLIENT_ID", "cli").strip(),
            client_mode=os.getenv("CLAWDIAN_CLIENT_MODE", "cli").strip(),
            client_version=os.getenv("CLAWDIAN_CLIENT_VERSION", "0.1.0").strip(),
            client_platform=os.getenv("CLAWDIAN_CLIENT_PLATFORM", platform.system().lower()).strip(),
            scopes=scopes,
            device_key_path=os.getenv("CLAWDIAN_DEVICE_KEY_PATH", "~/.clawdian-approver/device_ed25519.pem").strip(),
        )

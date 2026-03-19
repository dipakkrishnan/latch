from __future__ import annotations

import os
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

    @classmethod
    def from_env(cls) -> "Config":
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

        return cls(
            gateway_ws_url=required["OPENCLAW_GATEWAY_WS_URL"],
            gateway_token=required["OPENCLAW_GATEWAY_TOKEN"],
            latch_base_url=required["LATCH_BASE_URL"].rstrip("/"),
            latch_token=required["LATCH_TOKEN"],
            allow_decision=allow_decision,
            poll_interval_seconds=float(os.getenv("CLAWDIAN_POLL_INTERVAL_SECONDS", "2")),
            poll_timeout_seconds=float(os.getenv("CLAWDIAN_POLL_TIMEOUT_SECONDS", "300")),
            strict_deny_on_error=_bool_env("CLAWDIAN_STRICT_DENY_ON_ERROR", True),
        )


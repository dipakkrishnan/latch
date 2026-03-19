from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ApprovalRequest:
    approval_id: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class LatchDecision:
    state: str
    approval_id: str | None = None
    approval_url: str | None = None
    raw: dict[str, Any] | None = None


from __future__ import annotations

import asyncio
import time
from typing import Any

import aiohttp

from .models import LatchDecision


class LatchClient:
    def __init__(self, base_url: str, token: str, timeout_seconds: float = 10) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async def authorize_native(self, request: dict[str, Any]) -> LatchDecision:
        url = f"{self._base_url}/v1/gate/native"
        async with aiohttp.ClientSession(timeout=self._timeout, headers=self._headers) as session:
            async with session.post(url, json=request) as resp:
                body = await resp.json()
                if resp.status >= 400:
                    raise RuntimeError(f"Latch authorize failed ({resp.status}): {body}")
                return self._to_decision(body)

    async def poll_native(self, approval_id: str, *, interval_seconds: float, timeout_seconds: float) -> LatchDecision:
        url = f"{self._base_url}/v1/gate/native/{approval_id}"
        deadline = time.monotonic() + timeout_seconds
        async with aiohttp.ClientSession(timeout=self._timeout, headers=self._headers) as session:
            while time.monotonic() < deadline:
                async with session.get(url) as resp:
                    body = await resp.json()
                    if resp.status >= 400:
                        raise RuntimeError(f"Latch poll failed ({resp.status}): {body}")
                    decision = self._to_decision(body)
                    if decision.state in {"allow", "deny"}:
                        return decision
                await asyncio.sleep(interval_seconds)
        return LatchDecision(state="timeout", approval_id=approval_id)

    @staticmethod
    def _to_decision(body: dict[str, Any]) -> LatchDecision:
        state = str(body.get("state") or body.get("decision") or body.get("result") or "").strip().lower()
        if state not in {"allow", "deny", "pending"}:
            raise RuntimeError(f"Unexpected latch decision payload: {body}")
        return LatchDecision(
            state=state,
            approval_id=body.get("approvalId") or body.get("approval_id"),
            approval_url=body.get("approvalUrl") or body.get("approval_url"),
            raw=body,
        )


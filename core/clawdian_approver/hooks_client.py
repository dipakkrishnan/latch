from __future__ import annotations

import logging

import aiohttp

_LOG = logging.getLogger(__name__)


class HooksClient:
    def __init__(self, hooks_url: str, hooks_token: str, timeout_seconds: float = 10) -> None:
        self._hooks_url = hooks_url.strip()
        self._hooks_token = hooks_token.strip()
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    @property
    def enabled(self) -> bool:
        return bool(self._hooks_url and self._hooks_token)

    async def send_pending_approval(
        self,
        *,
        approval_id: str,
        approval_url: str,
        session_key: str | None,
        channel: str | None,
        to: str | None,
    ) -> None:
        if not self.enabled:
            return

        payload: dict[str, object] = {
            "message": (
                "Approval required for an exec request.\n\n"
                f"Approval ID: {approval_id}\n"
                f"Open to approve or deny: {approval_url}"
            ),
            "name": "clawdian-approver",
            "deliver": True,
            "wakeMode": "now",
        }
        if session_key:
            payload["sessionKey"] = session_key
        if channel:
            payload["channel"] = channel
        if to:
            payload["to"] = to

        headers = {
            "Authorization": f"Bearer {self._hooks_token}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            async with session.post(self._hooks_url, json=payload, headers=headers) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    raise RuntimeError(f"OpenClaw hooks push failed ({resp.status}): {body}")
                _LOG.info("Pushed pending approval URL for approval_id=%s", approval_id)

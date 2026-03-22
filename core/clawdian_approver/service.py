from __future__ import annotations

import asyncio
import logging
from typing import Any

from .config import Config
from .gateway_client import GatewayClient
from .hooks_client import HooksClient
from .latch_client import LatchClient
from .models import ApprovalRequest

_LOG = logging.getLogger(__name__)


class ClawdianApproverService:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._gateway = GatewayClient(
            config.gateway_ws_url,
            config.gateway_token,
            device_key_path=config.device_key_path,
            client_id=config.client_id,
            client_mode=config.client_mode,
            client_version=config.client_version,
            client_platform=config.client_platform,
            scopes=config.scopes,
            debug_frames=config.debug_frames,
        )
        self._latch = LatchClient(config.latch_base_url, config.latch_token)
        self._hooks = HooksClient(config.openclaw_hooks_url, config.openclaw_hooks_token)
        self._seen_approval_ids: set[str] = set()
        self._lock = asyncio.Lock()

    async def run(self) -> None:
        _LOG.info("Starting clawdian-approver (debug_frames=%s)", self._config.debug_frames)
        await self._gateway.run_with_reconnect(self._handle_request)

    async def _handle_request(self, req: ApprovalRequest) -> None:
        async with self._lock:
            if req.approval_id in self._seen_approval_ids:
                _LOG.info("Skipping duplicate approval request: %s", req.approval_id)
                return
            self._seen_approval_ids.add(req.approval_id)

        _LOG.info("Processing approval request: %s", req.approval_id)
        try:
            session = self._extract_session(req.payload)
            native_req = self._to_latch_request(req)
            decision = await self._latch.authorize_native(native_req)

            if decision.state == "pending":
                if decision.approval_url:
                    _LOG.info("Latch pending approval_id=%s approval_url=%s", decision.approval_id, decision.approval_url)
                    if self._config.notify_pending and self._hooks.enabled:
                        try:
                            await self._hooks.send_pending_approval(
                                approval_id=decision.approval_id or req.approval_id,
                                approval_url=decision.approval_url,
                                session_key=session.get("sessionKey") or session.get("session_key"),
                                channel=session.get("channel"),
                                to=session.get("to"),
                            )
                        except Exception as exc:
                            _LOG.warning("Failed to push pending approval to chat for approval_id=%s: %s", req.approval_id, exc)
                poll_id = decision.approval_id or req.approval_id
                decision = await self._latch.poll_native(
                    poll_id,
                    interval_seconds=self._config.poll_interval_seconds,
                    timeout_seconds=self._config.poll_timeout_seconds,
                )

            if decision.state == "allow":
                await self._gateway.resolve(req.approval_id, self._config.allow_decision, "approved by latch")
                _LOG.info("Resolved allow for approval_id=%s", req.approval_id)
                return

            if decision.state in {"deny", "timeout"}:
                await self._gateway.resolve(req.approval_id, "deny", f"latch decision={decision.state}")
                _LOG.info("Resolved deny for approval_id=%s reason=%s", req.approval_id, decision.state)
                return

            raise RuntimeError(f"Unhandled decision state: {decision.state}")
        except Exception as exc:
            _LOG.exception("Approval flow failed for approval_id=%s: %s", req.approval_id, exc)
            if self._config.strict_deny_on_error:
                await self._gateway.resolve(req.approval_id, "deny", "clawdian-approver error")
                _LOG.warning("Resolved deny due to error for approval_id=%s", req.approval_id)

    @staticmethod
    def _to_latch_request(req: ApprovalRequest) -> dict[str, Any]:
        payload = req.payload
        command = (
            payload.get("command")
            or payload.get("cmd")
            or (payload.get("request") or {}).get("command")
            or ""
        )
        session = ClawdianApproverService._extract_session(payload)
        return {
            "tool": "openclaw.exec",
            "args": {"command": command, "approvalId": req.approval_id, "raw": payload},
            "sessionKey": session.get("sessionKey") or session.get("session_key"),
            "channel": session.get("channel"),
            "to": session.get("to"),
            "agentId": session.get("agentId") or session.get("agent_id"),
        }

    @staticmethod
    def _extract_session(payload: dict[str, Any]) -> dict[str, Any]:
        return payload.get("session") or payload.get("_meta") or {}

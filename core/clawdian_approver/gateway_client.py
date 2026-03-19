from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Any, AsyncIterator

import aiohttp

from .models import ApprovalRequest

_LOG = logging.getLogger(__name__)


class GatewayClient:
    """OpenClaw Gateway WS client skeleton.

    Assumption for skeleton:
    - inbound approval event includes event name `exec.approval.requested`
    - outbound resolver call accepts JSON-RPC-like:
      {"id", "method": "exec.approval.resolve", "params": {...}}
    """

    def __init__(self, ws_url: str, token: str, *, timeout_seconds: float = 30) -> None:
        self._ws_url = ws_url
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._headers = {"Authorization": f"Bearer {token}"}
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None

    async def connect(self) -> None:
        if self._session is not None:
            return
        self._session = aiohttp.ClientSession(timeout=self._timeout, headers=self._headers)
        self._ws = await self._session.ws_connect(self._ws_url, heartbeat=20)
        _LOG.info("Connected to Gateway WS: %s", self._ws_url)

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def iter_approval_requests(self) -> AsyncIterator[ApprovalRequest]:
        if self._ws is None:
            raise RuntimeError("Gateway WS not connected")
        ws = self._ws
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                obj = json.loads(msg.data)
                req = self._parse_exec_approval_event(obj)
                if req is not None:
                    yield req
            elif msg.type == aiohttp.WSMsgType.ERROR:
                raise RuntimeError(f"Gateway WS error: {ws.exception()}")
            elif msg.type in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED}:
                raise RuntimeError("Gateway WS closed")

    async def resolve(self, approval_id: str, decision: str, reason: str) -> dict[str, Any]:
        if self._ws is None:
            raise RuntimeError("Gateway WS not connected")

        request_id = int(time.time() * 1000)
        payload = {
            "id": request_id,
            "method": "exec.approval.resolve",
            "params": {
                "approvalId": approval_id,
                "decision": decision,
                "reason": reason,
            },
        }
        await self._ws.send_json(payload)
        return {"ok": True, "requestId": request_id}

    async def run_with_reconnect(self, handler) -> None:
        backoff = 1.0
        while True:
            try:
                await self.connect()
                async for req in self.iter_approval_requests():
                    await handler(req)
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _LOG.warning("Gateway loop error: %s", exc)
                await self.close()
                sleep_for = min(backoff, 30.0) + random.random()
                await asyncio.sleep(sleep_for)
                backoff = min(backoff * 2, 30.0)

    @staticmethod
    def _parse_exec_approval_event(obj: dict[str, Any]) -> ApprovalRequest | None:
        # Accept common wire shapes.
        event_name = obj.get("event") or obj.get("type") or obj.get("method")
        if event_name != "exec.approval.requested":
            # JSON-RPC notification shape: {"method":"event","params":{"event":"...","data":...}}
            if obj.get("method") == "event":
                params = obj.get("params") or {}
                if params.get("event") != "exec.approval.requested":
                    return None
                payload = params.get("data") or {}
            else:
                return None
        else:
            payload = obj.get("data") or obj.get("params") or {}

        approval_id = payload.get("approvalId") or payload.get("approval_id") or payload.get("id")
        if not approval_id:
            return None
        return ApprovalRequest(approval_id=str(approval_id), payload=payload)


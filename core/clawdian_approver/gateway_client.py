from __future__ import annotations

import asyncio
import json
import logging
import random
import time
import uuid
from typing import Any, AsyncIterator

import aiohttp

from .device_auth import DeviceIdentity, load_or_create_identity
from .models import ApprovalRequest

_LOG = logging.getLogger(__name__)


class GatewayClient:
    def __init__(
        self, ws_url: str, token: str, *,
        device_key_path: str,
        client_id: str = "cli",
        client_mode: str = "cli",
        client_version: str = "0.1.0",
        client_platform: str = "darwin",
        scopes: list[str] | None = None,
        timeout_seconds: float = 30,
        debug_frames: bool = False,
    ) -> None:
        self._ws_url = ws_url
        self._token = token
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._debug_frames = debug_frames

        self._client_id = client_id
        self._client_mode = client_mode
        self._client_version = client_version
        self._client_platform = client_platform
        self._user_agent = f"{client_id}/{client_version}"
        self._scopes = scopes or ["operator.read", "operator.write", "operator.approvals"]

        self._identity: DeviceIdentity = load_or_create_identity(device_key_path)
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None

    # -- lifecycle --

    async def connect(self) -> None:
        await self.close()
        self._session = aiohttp.ClientSession(
            timeout=self._timeout,
            headers={"Authorization": f"Bearer {self._token}"},
        )
        self._ws = await self._session.ws_connect(self._ws_url, heartbeat=20)
        _LOG.info("Connected to Gateway WS: %s", self._ws_url)
        await self._handshake()

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def run_with_reconnect(self, handler) -> None:
        backoff = 1.0
        while True:
            try:
                await self.connect()
                async for req in self._iter_approval_requests():
                    await handler(req)
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _LOG.warning("Gateway loop error: %s", exc)
                await self.close()
                await asyncio.sleep(min(backoff, 30.0) + random.random())
                backoff = min(backoff * 2, 30.0)

    # -- operations --

    async def resolve(self, approval_id: str, decision: str, reason: str) -> None:
        if self._ws is None:
            raise RuntimeError("Gateway WS not connected")
        payload = {
            "id": int(time.time() * 1000),
            "method": "exec.approval.resolve",
            "params": {"approvalId": approval_id, "decision": decision, "reason": reason},
        }
        await self._ws.send_json(payload)
        if self._debug_frames:
            _LOG.info("Gateway resolve sent: %s", _truncate(json.dumps(payload, separators=(",", ":"))))

    # -- internals --

    async def _iter_approval_requests(self) -> AsyncIterator[ApprovalRequest]:
        assert self._ws is not None
        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                if self._debug_frames:
                    _LOG.info("Gateway frame: %s", _truncate(msg.data))
                req = _parse_approval_event(json.loads(msg.data))
                if req is not None:
                    yield req
            elif msg.type == aiohttp.WSMsgType.ERROR:
                raise RuntimeError(f"Gateway WS error: {self._ws.exception()}")
            elif msg.type in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED}:
                raise RuntimeError("Gateway WS closed")

    async def _handshake(self) -> None:
        ws = self._ws
        assert ws is not None

        # 1. receive challenge
        challenge = await ws.receive()
        if challenge.type != aiohttp.WSMsgType.TEXT:
            raise RuntimeError(f"Expected challenge text frame, got {challenge.type}")
        if self._debug_frames:
            _LOG.info("Gateway frame: %s", _truncate(challenge.data))

        msg = json.loads(challenge.data)
        if msg.get("event") != "connect.challenge":
            raise RuntimeError(f"Expected connect.challenge, got {msg.get('event') or msg.get('type')}")
        nonce = (msg.get("payload") or {}).get("nonce")
        if not nonce:
            raise RuntimeError(f"connect.challenge missing nonce: {msg}")

        # 2. sign and send connect
        signed_at = int(time.time() * 1000)
        signature = self._identity.sign_connect(
            client_id=self._client_id, client_mode=self._client_mode,
            role="operator", scopes=self._scopes,
            signed_at_ms=signed_at, token=self._token, nonce=nonce,
        )
        req_id = str(uuid.uuid4())
        connect_req = {
            "id": req_id, "type": "req", "method": "connect",
            "params": {
                "minProtocol": 3, "maxProtocol": 3,
                "client": {
                    "id": self._client_id, "version": self._client_version,
                    "platform": self._client_platform, "mode": self._client_mode,
                },
                "userAgent": self._user_agent, "role": "operator",
                "scopes": self._scopes, "caps": [], "commands": [],
                "permissions": {}, "locale": "en-US",
                "device": {
                    "id": self._identity.device_id,
                    "publicKey": self._identity.public_key_b64,
                    "signature": signature, "signedAt": signed_at, "nonce": nonce,
                },
                "auth": {"token": self._token},
            },
        }
        await ws.send_json(connect_req)
        if self._debug_frames:
            _LOG.info("Gateway connect sent: %s", _truncate(json.dumps(connect_req, separators=(",", ":"))))

        # 3. wait for acceptance
        while True:
            resp = await ws.receive()
            if resp.type in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED}:
                raise RuntimeError("Gateway closed during connect")
            if resp.type == aiohttp.WSMsgType.ERROR:
                raise RuntimeError(f"Gateway error during connect: {ws.exception()}")
            if resp.type != aiohttp.WSMsgType.TEXT:
                continue
            if self._debug_frames:
                _LOG.info("Gateway frame: %s", _truncate(resp.data))
            obj = json.loads(resp.data)
            if obj.get("type") == "event" and obj.get("event") == "hello-ok":
                _LOG.info("Gateway connect accepted (mode=%s)", self._client_mode)
                return
            if obj.get("id") == req_id:
                if obj.get("ok"):
                    _LOG.info("Gateway connect accepted (mode=%s)", self._client_mode)
                    return
                raise RuntimeError(f"Gateway connect rejected: {obj.get('error')}")


def _parse_approval_event(obj: dict[str, Any]) -> ApprovalRequest | None:
    event = obj.get("event") or obj.get("type") or obj.get("method")
    if event == "exec.approval.requested":
        payload = obj.get("data") or obj.get("params") or {}
    elif obj.get("method") == "event":
        params = obj.get("params") or {}
        if params.get("event") != "exec.approval.requested":
            return None
        payload = params.get("data") or {}
    else:
        return None
    approval_id = payload.get("approvalId") or payload.get("approval_id") or payload.get("id")
    if not approval_id:
        return None
    return ApprovalRequest(approval_id=str(approval_id), payload=payload)


def _truncate(s: str, max_len: int = 2000) -> str:
    return s if len(s) <= max_len else s[:max_len] + "...(truncated)"

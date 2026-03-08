import asyncio
import os
import re
import sys
import time
from uuid import uuid4

import aiohttp
import aiohttp.web

from . import audit, policy, totp
from .config import load


_LISTEN_HOST = os.environ.get("LATCH_HOST", "127.0.0.1")
_LISTEN_PORT = int(os.environ.get("LATCH_PORT", "18890"))
_PENDING_APPROVALS: dict[str, asyncio.Future] = {}
_PENDING_ROUTE_APPROVALS: dict[tuple[str, str], str] = {}
_PENDING_APPROVAL_META: dict[str, dict[str, object]] = {}
_ROUTE_TOOL_GRANTS: dict[tuple[str, str, str], float] = {}
_SESSION_CHAT_ROUTE_RE = re.compile(
    r"^agent:[^:]+:(?P<channel>[^:]+):(?P<scope>direct|group):(?P<peer>.+)$"
)
_TOTP_CODE_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")


def _approval_base_url(cfg: dict) -> str:
    configured = str(cfg.get("approval_base_url", "")).strip()
    if configured:
        return configured.rstrip("/")
    env_base = os.environ.get("LATCH_APPROVAL_BASE_URL", "").strip()
    if env_base:
        return env_base.rstrip("/")
    return f"http://127.0.0.1:{_LISTEN_PORT}"


def _route_from_session_key(session_key: str) -> tuple[str, str] | None:
    """Resolve a channel route from an agent session key.

    We route approval prompts to channel+to (same chat) instead of reusing the
    same sessionKey, to avoid lane waits while the original tool call is active.
    """
    m = _SESSION_CHAT_ROUTE_RE.fullmatch(session_key.strip())
    if not m:
        return None
    channel = m.group("channel")
    peer = m.group("peer")
    if not channel or not peer or channel in {"main", "hook"}:
        return None
    return channel, f"{channel}:{peer}"


def _normalize_route(channel: str | None, to: str | None) -> tuple[str, str] | None:
    if not isinstance(channel, str) or not isinstance(to, str):
        return None
    channel_norm = channel.strip().lower()
    to_norm = to.strip()
    if not channel_norm or not to_norm:
        return None
    if ":" not in to_norm:
        to_norm = f"{channel_norm}:{to_norm}"
    return channel_norm, to_norm


def _bool_cfg(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "on"}:
            return True
        if v in {"0", "false", "no", "off"}:
            return False
    return default


def _chat_approve_without_totp_enabled(cfg: dict) -> bool:
    env_value = os.environ.get("LATCH_CHAT_APPROVE_WITHOUT_TOTP")
    if env_value is not None:
        return _bool_cfg(env_value, default=False)
    return _bool_cfg(cfg.get("chat_approve_without_totp"), default=False)


def _chat_route_nonblocking_enabled(cfg: dict) -> bool:
    env_value = os.environ.get("LATCH_CHAT_ROUTE_NONBLOCKING")
    if env_value is not None:
        return _bool_cfg(env_value, default=False)
    return _bool_cfg(cfg.get("chat_route_nonblocking"), default=False)


def _route_grant_ttl_sec(cfg: dict) -> int:
    env_value = os.environ.get("LATCH_ROUTE_GRANT_TTL_SEC")
    if env_value and env_value.strip().isdigit():
        return max(15, int(env_value.strip()))
    raw = cfg.get("route_grant_ttl_sec")
    if isinstance(raw, int):
        return max(15, raw)
    return 180


def _grant_key(route: tuple[str, str], tool_name: str) -> tuple[str, str, str]:
    channel, to = route
    return channel, to, tool_name.strip().lower()


def _clear_pending_approval(approval_id: str) -> None:
    meta = _PENDING_APPROVAL_META.pop(approval_id, None)
    route = meta.get("route") if isinstance(meta, dict) else None
    if isinstance(route, tuple) and len(route) == 2:
        route_key = (str(route[0]), str(route[1]))
        if _PENDING_ROUTE_APPROVALS.get(route_key) == approval_id:
            _PENDING_ROUTE_APPROVALS.pop(route_key, None)
    _PENDING_APPROVALS.pop(approval_id, None)


def _grant_route_tool(route: tuple[str, str], tool_name: str, cfg: dict) -> None:
    ttl_sec = _route_grant_ttl_sec(cfg)
    _ROUTE_TOOL_GRANTS[_grant_key(route, tool_name)] = time.monotonic() + ttl_sec


def _consume_route_tool_grant(route: tuple[str, str], tool_name: str) -> bool:
    key = _grant_key(route, tool_name)
    exp = _ROUTE_TOOL_GRANTS.get(key)
    now = time.monotonic()
    if exp is None:
        return False
    if exp <= now:
        _ROUTE_TOOL_GRANTS.pop(key, None)
        return False
    _ROUTE_TOOL_GRANTS.pop(key, None)
    return True


def _cleanup_expired_state() -> None:
    now = time.monotonic()
    for key, exp in list(_ROUTE_TOOL_GRANTS.items()):
        if exp <= now:
            _ROUTE_TOOL_GRANTS.pop(key, None)
    for approval_id, meta in list(_PENDING_APPROVAL_META.items()):
        expires_at = meta.get("expires_at") if isinstance(meta, dict) else None
        if isinstance(expires_at, (int, float)) and expires_at <= now:
            _clear_pending_approval(approval_id)


def _extract_totp_code(content: str) -> str | None:
    matches = _TOTP_CODE_RE.findall(content)
    if not matches:
        return None
    # Favor the most recent 6-digit token in case metadata/text precedes the code.
    return matches[-1]


async def _handle_callback(request: aiohttp.web.Request) -> aiohttp.web.Response:
    approval_id = request.match_info.get("approval_id", "").strip()
    code_future = _PENDING_APPROVALS.get(approval_id)
    if not code_future:
        return aiohttp.web.Response(status=404, text="Approval request not found or expired.")

    if request.method == "GET":
        html = f"""<!doctype html>
<html>
  <body style="font-family: -apple-system, sans-serif; max-width: 420px; margin: 2rem auto;">
    <h2>Latch Approval</h2>
    <form method="post" action="/callback/{approval_id}">
      <label for="code">Enter 6-digit code (or 'deny')</label><br/>
      <input id="code" name="code" autocomplete="one-time-code" inputmode="numeric" autofocus />
      <button type="submit">Submit</button>
    </form>
  </body>
</html>"""
        return aiohttp.web.Response(text=html, content_type="text/html")

    code = ""
    try:
        if request.content_type == "application/json":
            body = await request.json()
            code = str(body.get("code", "")).strip()
        else:
            form = await request.post()
            code = str(form.get("code", "")).strip()
    except Exception:
        code = ""

    if not code:
        return aiohttp.web.Response(status=400, text="Missing code.")

    meta = _PENDING_APPROVAL_META.get(approval_id) or {}
    cfg = load()
    route = meta.get("route")
    tool_name = str(meta.get("tool_name", "")).strip()
    nonblocking = bool(meta.get("nonblocking")) if isinstance(meta, dict) else False
    if (
        nonblocking
        and isinstance(route, tuple)
        and len(route) == 2
        and tool_name
        and re.fullmatch(r"\d{6}", code)
        and totp.verify(code)
    ):
        _grant_route_tool((str(route[0]), str(route[1])), tool_name, cfg)
        _clear_pending_approval(approval_id)
        return aiohttp.web.Response(text="Approved. Retry the original request in chat.")

    if not code_future.done():
        code_future.set_result(code)
    return aiohttp.web.Response(text="Approval submitted. You can close this page.")


async def _handle_chat_reply(request: aiohttp.web.Request) -> aiohttp.web.Response:
    try:
        data = await request.json()
    except Exception as e:
        return aiohttp.web.json_response({"accepted": False, "reason": f"invalid json: {e}"}, status=400)

    content_raw = data.get("content") if isinstance(data, dict) else None
    if not isinstance(content_raw, str) or not content_raw.strip():
        return aiohttp.web.json_response({"accepted": False, "reason": "content required"})

    route = _normalize_route(
        data.get("channel") if isinstance(data, dict) else None,
        data.get("conversation_id") if isinstance(data, dict) else None,
    )
    if not route:
        return aiohttp.web.json_response({"accepted": False, "reason": "channel/conversation_id required"})

    cfg = load()
    _cleanup_expired_state()

    approval_id = _PENDING_ROUTE_APPROVALS.get(route)
    if not approval_id:
        return aiohttp.web.json_response({"accepted": False, "reason": "no pending approval for route"})

    code_future = _PENDING_APPROVALS.get(approval_id)
    if not code_future or code_future.done():
        return aiohttp.web.json_response({"accepted": False, "reason": "pending approval expired"})

    meta = _PENDING_APPROVAL_META.get(approval_id) or {}
    tool_name = str(meta.get("tool_name", "")).strip()
    nonblocking = bool(meta.get("nonblocking")) if isinstance(meta, dict) else False

    content = content_raw.strip()
    content_lc = content.lower()
    maybe_code = _extract_totp_code(content)

    if maybe_code:
        if not totp.verify(maybe_code):
            return aiohttp.web.json_response({"accepted": False, "reason": "invalid totp code"})
        if nonblocking and tool_name:
            _grant_route_tool(route, tool_name, cfg)
            _clear_pending_approval(approval_id)
            return aiohttp.web.json_response({"accepted": True, "reason": "approved; retry original request"})
        code_future.set_result(maybe_code)
        return aiohttp.web.json_response({"accepted": True, "reason": "submitted code"})

    if content_lc in {"deny", "no", "reject"}:
        if not code_future.done():
            code_future.set_result("deny")
        _clear_pending_approval(approval_id)
        return aiohttp.web.json_response({"accepted": True, "reason": "submitted denial"})

    if content_lc in {"approve", "yes", "ok"} and _chat_approve_without_totp_enabled(cfg):
        if nonblocking and tool_name:
            _grant_route_tool(route, tool_name, cfg)
            _clear_pending_approval(approval_id)
            return aiohttp.web.json_response({"accepted": True, "reason": "approved; retry original request"})
        if not code_future.done():
            code_future.set_result("approve")
        return aiohttp.web.json_response({"accepted": True, "reason": "submitted approval"})

    return aiohttp.web.json_response({"accepted": False, "reason": "no actionable approval reply detected"})


async def _request_approval(tool_name: str, tool_input: dict, session_key: str | None = None) -> tuple[bool, str]:
    cfg = load()
    webhook_url = cfg.get("openclaw_webhook_url", "").strip()
    webhook_token = cfg.get("openclaw_webhook_token", "").strip()

    if not webhook_url:
        return False, "openclaw_webhook_url not configured (run: latch setup)"
    if not totp.is_enrolled():
        return False, "TOTP not enrolled (run: latch setup)"

    timeout = int(cfg.get("approval_timeout_sec", 120))
    _cleanup_expired_state()
    route = _route_from_session_key(session_key) if session_key else None
    if route and _consume_route_tool_grant(route, tool_name):
        return True, "Approved via prior chat code"

    summary = ", ".join(f"{k}={repr(v)[:40]}" for k, v in list(tool_input.items())[:3])
    approval_id = uuid4().hex
    code_future: asyncio.Future = asyncio.get_running_loop().create_future()
    _PENDING_APPROVALS[approval_id] = code_future
    nonblocking_route = bool(route) and _chat_route_nonblocking_enabled(cfg)
    _PENDING_APPROVAL_META[approval_id] = {
        "tool_name": tool_name,
        "route": route,
        "nonblocking": nonblocking_route,
        "expires_at": time.monotonic() + timeout,
    }
    approval_url = f"{_approval_base_url(cfg)}/callback/{approval_id}"

    msg_lines = ["*Latch approval needed*", f"Command: `{tool_name}`"]
    if summary:
        msg_lines.append(f"Input: `{summary}`")
    msg_lines.append(f"\nOpen to approve: {approval_url}")
    if nonblocking_route:
        msg_lines.append("Reply in this chat with your 6-digit code.")
        msg_lines.append("Then retry the original request.")
    else:
        msg_lines.append("Enter the 6-digit code on that page, or submit `deny` there.")

    payload = {
        "message": "\n".join(msg_lines),
        "name": "Latch Approval",
        "_latch_callback": approval_url,
        # Run approval hooks in a dedicated lane to avoid deadlocking the
        # originating chat session while it waits on this decision.
        "sessionKey": f"hook:latch:{approval_id}",
    }
    if route:
        channel, to = route
        payload["channel"] = channel
        payload["to"] = to
        _PENDING_ROUTE_APPROVALS[(channel, to)] = approval_id
    headers = {"Content-Type": "application/json"}
    if webhook_token:
        headers["Authorization"] = f"Bearer {webhook_token}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status >= 300:
                    _clear_pending_approval(approval_id)
                    return False, f"OpenClaw webhook failed: HTTP {resp.status}"
    except Exception as e:
        _clear_pending_approval(approval_id)
        return False, f"OpenClaw webhook error: {e}"

    if nonblocking_route:
        return False, "Approval requested in chat. Reply with code, then retry."

    try:
        code = await asyncio.wait_for(code_future, timeout=timeout)
    except asyncio.TimeoutError:
        return False, "Approval timed out"
    finally:
        _clear_pending_approval(approval_id)

    if re.fullmatch(r"\d{6}", code):
        if totp.verify(code):
            return True, "Approved via TOTP"
        return False, "Invalid TOTP code"
    if code.lower() == "deny":
        return False, "Denied by user"
    if code.lower() == "approve":
        if _chat_approve_without_totp_enabled(cfg):
            return True, "Approved via chat confirmation"
        return False, "Chat approval without TOTP is disabled"
    return False, f"Unrecognized response: {code!r}"


async def _handle_approve(request: aiohttp.web.Request) -> aiohttp.web.Response:
    try:
        data = await request.json()
        tool_name = data.get("command") or data.get("tool_name", "unknown")
        tool_input = data.get("tool_input", {})
        raw_session_key = data.get("session_key") or data.get("sessionKey")
        session_key = raw_session_key.strip() if isinstance(raw_session_key, str) and raw_session_key.strip() else None
    except Exception as e:
        return aiohttp.web.json_response(
            {"decision": "allow-once", "reason": f"Parse error (fail-open): {e}"},
        )

    try:
        pol = policy.load()
        action, reason = policy.evaluate(tool_name, pol)
    except Exception as e:
        return aiohttp.web.json_response(
            {"decision": "allow-once", "reason": f"Policy error (fail-open): {e}"},
        )

    if action == "allow":
        audit.append(tool_name, action, "allow", reason)
        return aiohttp.web.json_response({"decision": "allow-once", "reason": reason})

    elif action == "deny":
        audit.append(tool_name, action, "deny", reason)
        return aiohttp.web.json_response({"decision": "deny", "reason": reason})

    elif action == "approve":
        approved, result_reason = await _request_approval(tool_name, tool_input, session_key=session_key)
        decision = "allow-once" if approved else "deny"
        audit.append(tool_name, action, "allow" if approved else "deny", result_reason)
        return aiohttp.web.json_response({"decision": decision, "reason": result_reason})

    else:
        audit.append(tool_name, action, "allow", f"Unknown action {action!r} (fail-open)")
        return aiohttp.web.json_response({"decision": "allow-once", "reason": reason})


def main(host: str = _LISTEN_HOST, port: int = _LISTEN_PORT) -> None:
    global _LISTEN_HOST
    global _LISTEN_PORT
    _LISTEN_HOST = host
    _LISTEN_PORT = port
    app = aiohttp.web.Application()
    app.router.add_post("/approve", _handle_approve)
    app.router.add_post("/approve/reply", _handle_chat_reply)
    app.router.add_get("/callback/{approval_id}", _handle_callback)
    app.router.add_post("/callback/{approval_id}", _handle_callback)
    print(f"Latch server listening on http://{host}:{port}")
    aiohttp.web.run_app(app, host=host, port=port, print=None)


if __name__ == "__main__":
    args = sys.argv[1:]
    cli_host = _LISTEN_HOST
    cli_port = _LISTEN_PORT

    idx = 0
    while idx < len(args):
        arg = args[idx]
        if arg == "--host" and idx + 1 < len(args):
            cli_host = args[idx + 1]
            idx += 2
            continue
        if arg == "--port" and idx + 1 < len(args):
            try:
                cli_port = int(args[idx + 1])
            except ValueError as exc:
                raise SystemExit(f"Invalid --port value: {args[idx + 1]!r}") from exc
            idx += 2
            continue
        raise SystemExit("Usage: python -m latch.server [--host HOST] [--port PORT]")

    main(host=cli_host, port=cli_port)

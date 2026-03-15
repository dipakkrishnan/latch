import asyncio
import base64
import json
import secrets
import sys
import time
import webbrowser
from datetime import datetime, timezone
import re
from urllib.parse import urlparse

from aiohttp import web
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    UserVerificationRequirement,
    ResidentKeyRequirement,
    AuthenticatorAttachment,
    AttestationConveyancePreference,
)

from . import credentials
from .config import (
    LATCH_APPROVAL_PORT,
    LATCH_APPROVAL_REDIRECT_URL,
    LATCH_RP_ID,
    LATCH_ORIGIN,
    OPENCLAW_HOOKS_URL,
    OPENCLAW_HOOKS_TOKEN,
    OPENCLAW_SESSION_KEY,
    OPENCLAW_CHANNEL,
    OPENCLAW_CHANNEL_TO,
)
from .tunnel import get_tunnel_url

SESSION_TTL = 300  # 5 minutes
MAX_SESSIONS = 100


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _descriptor_json(descriptor) -> dict | None:
    if isinstance(descriptor, dict):
        dtype = descriptor.get("type", "public-key")
        did = descriptor.get("id")
    else:
        dtype = getattr(descriptor, "type", "public-key")
        did = getattr(descriptor, "id", None)
    if did is None:
        return None
    if isinstance(did, (bytes, bytearray, memoryview)):
        did = _b64url(bytes(did))
    return {"type": dtype, "id": str(did)}


def _normalize_credential_id(value: str | None) -> str | None:
    if not value:
        return None
    try:
        decoded = base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))
    except Exception:
        return value
    return _b64url(decoded)


def _is_safe_redirect_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    return parsed.scheme in {"https", "http", "whatsapp"} and bool(parsed.netloc or parsed.scheme == "whatsapp")


def _normalize_phone_digits(value: str) -> str:
    return re.sub(r"\D+", "", value)


class ApprovalServer:
    """Persistent HTTP server for approval and enrollment flows."""

    def __init__(self):
        self._sessions: dict[str, dict] = {}
        self._enroll_challenge: bytes | None = None
        self._enroll_complete: asyncio.Event | None = None
        self._runner: web.AppRunner | None = None
        self._port: int | None = None
        self._cleanup_task: asyncio.Task | None = None

    @property
    def port(self) -> int | None:
        return self._port

    @property
    def has_tunnel(self) -> bool:
        return get_tunnel_url() is not None

    @property
    def _rp_id(self) -> str:
        if LATCH_RP_ID and LATCH_RP_ID != "localhost":
            return LATCH_RP_ID
        tunnel_url = get_tunnel_url()
        if tunnel_url:
            parsed = urlparse(tunnel_url)
            return parsed.hostname or "localhost"
        return "localhost"

    @property
    def _origin(self) -> str:
        if LATCH_ORIGIN:
            return LATCH_ORIGIN
        tunnel_url = get_tunnel_url()
        if tunnel_url:
            parsed = urlparse(tunnel_url)
            return f"https://{parsed.hostname}"
        return ""

    def _base_url(self) -> str:
        tunnel_url = get_tunnel_url()
        if tunnel_url:
            return tunnel_url
        host = "localhost" if self._rp_id == "localhost" else self._rp_id
        return f"http://{host}:{self._port}"

    def _get_expected_origin(self, req: web.Request) -> str:
        if self._origin:
            return self._origin
        port = req.url.port
        return f"http://{self._rp_id}:{port}"

    async def start(self):
        app = web.Application()
        # Approval routes
        app.router.add_get("/approval/{id}", self._get_approval_page)
        app.router.add_get("/approval/{id}/webauthn-options", self._get_webauthn_opts)
        app.router.add_post("/approval/{id}/decide", self._post_decide)
        # Enrollment routes
        app.router.add_get("/enroll", self._get_enroll_page)
        app.router.add_get("/enroll/options", self._get_enroll_options)
        app.router.add_post("/enroll/verify", self._post_enroll_verify)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        port = LATCH_APPROVAL_PORT
        site = web.TCPSite(self._runner, "0.0.0.0", port)
        await site.start()
        self._port = self._runner.addresses[0][1]
        sys.stderr.write(f"Approval server listening on 0.0.0.0:{self._port}\n")

        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        if self._runner:
            await self._runner.cleanup()

    def create_request(self, tool_name: str, tool_input: dict, require_webauthn: bool = False) -> tuple[str, str]:
        """Register a pending approval session. Returns (approval_id, url).

        When a tunnel is active, require_webauthn is automatically set to True
        so remote approvals always require biometric verification.
        """
        if self.has_tunnel:
            require_webauthn = True
        # Evict oldest sessions if at capacity
        while len(self._sessions) >= MAX_SESSIONS:
            oldest_key = min(self._sessions, key=lambda k: self._sessions[k]["created_at"])
            session = self._sessions.pop(oldest_key)
            session["event"].set()
        approval_id = secrets.token_urlsafe(32)
        self._sessions[approval_id] = {
            "tool": tool_name,
            "args": tool_input,
            "require_webauthn": require_webauthn,
            "event": asyncio.Event(),
            "approved": False,
            "challenge": None,
            "created_at": time.time(),
        }
        url = f"{self._base_url()}/approval/{approval_id}"
        return approval_id, url

    async def wait_for_decision(self, approval_id: str, timeout: float = 300) -> bool:
        session = self._sessions.get(approval_id)
        if not session:
            return False
        try:
            await asyncio.wait_for(session["event"].wait(), timeout=timeout)
        except asyncio.TimeoutError:
            self._sessions.pop(approval_id, None)
            return False
        approved = session["approved"]
        self._sessions.pop(approval_id, None)
        return approved

    async def _cleanup_loop(self):
        while True:
            await asyncio.sleep(60)
            now = time.time()
            expired = [k for k, v in self._sessions.items() if now - v["created_at"] > SESSION_TTL]
            for k in expired:
                session = self._sessions.pop(k, None)
                if session:
                    session["event"].set()  # unblock any waiters

    # --- Approval routes ---

    async def _get_approval_page(self, req: web.Request):
        approval_id = req.match_info["id"]
        session = self._sessions.get(approval_id)
        if not session:
            return web.Response(text="Approval session not found or expired.", status=404)
        if time.time() - session["created_at"] > SESSION_TTL:
            self._sessions.pop(approval_id, None)
            return web.Response(text="Approval session expired.", status=410)
        redirect_url = self._resolve_post_decision_redirect_url()
        return web.Response(
            content_type="text/html",
            text=_approval_page(
                approval_id,
                session["tool"],
                session["args"],
                session["require_webauthn"],
                redirect_url,
            ),
        )

    def _resolve_post_decision_redirect_url(self) -> str | None:
        configured = (LATCH_APPROVAL_REDIRECT_URL or "").strip()
        if configured:
            if _is_safe_redirect_url(configured):
                return configured
            sys.stderr.write(f"[latch] Ignoring unsafe LATCH_APPROVAL_REDIRECT_URL: {configured}\n")
            return None

        if (OPENCLAW_CHANNEL or "").strip().lower() == "whatsapp":
            to = (OPENCLAW_CHANNEL_TO or "").strip()
            digits = _normalize_phone_digits(to)
            if digits:
                return f"https://wa.me/{digits}"
        return None

    async def _get_webauthn_opts(self, req: web.Request):
        approval_id = req.match_info["id"]
        session = self._sessions.get(approval_id)
        if not session:
            raise web.HTTPNotFound()
        creds = credentials.load()
        if not creds:
            return web.json_response({"error": "No credentials enrolled. Run: latch enroll"}, status=400)
        try:
            opts = generate_authentication_options(
                rp_id=self._rp_id,
                allow_credentials=[{"type": "public-key", "id": c["credentialID"]} for c in creds],
                user_verification=UserVerificationRequirement.REQUIRED,
            )
            allow_credentials = [d for d in (_descriptor_json(c) for c in (opts.allow_credentials or [])) if d]
        except Exception as e:
            return web.json_response({"error": f"Failed to build WebAuthn options: {e}"}, status=500)
        session["challenge"] = opts.challenge
        return web.json_response({
            "challenge": _b64url(opts.challenge),
            "timeout": opts.timeout,
            "rpId": opts.rp_id,
            "allowCredentials": allow_credentials,
            "userVerification": opts.user_verification.value if opts.user_verification else "preferred",
        })

    async def _post_decide(self, req: web.Request):
        approval_id = req.match_info["id"]
        session = self._sessions.get(approval_id)
        if not session:
            return web.json_response({"error": "Session not found or expired"}, status=404)
        if time.time() - session["created_at"] > SESSION_TTL:
            self._sessions.pop(approval_id, None)
            return web.json_response({"error": "Session expired"}, status=410)

        body = await req.json()
        decision = body.get("decision")

        if decision == "approve" and session["require_webauthn"]:
            auth_response = body.get("authResponse")
            if not auth_response or session["challenge"] is None:
                return web.json_response({"error": "WebAuthn assertion required"}, status=400)
            creds = credentials.load()
            received_id = _normalize_credential_id(auth_response.get("id") or auth_response.get("rawId"))
            match = next((c for c in creds if _normalize_credential_id(c.get("credentialID")) == received_id), None)
            if not match:
                return web.json_response({"error": "Unknown credential"}, status=400)
            try:
                expected_origin = self._get_expected_origin(req)
                verification = verify_authentication_response(
                    credential=auth_response,
                    expected_challenge=session["challenge"],
                    expected_rp_id=self._rp_id,
                    expected_origin=expected_origin,
                    credential_public_key=base64.b64decode(match["publicKey"]),
                    credential_current_sign_count=match["counter"],
                    require_user_verification=True,
                )
                credentials.update_counter(match["credentialID"], verification.new_sign_count)
            except Exception as e:
                return web.json_response({"error": f"WebAuthn error: {e}"}, status=400)

        session["approved"] = decision == "approve"
        session["event"].set()

        # Execute downstream tool and push result via webhook
        asyncio.create_task(self._handle_decision(approval_id, session))

        return web.json_response({"ok": True})

    async def _handle_decision(self, approval_id: str, session: dict):
        """After user decides, execute the tool (if approved) and push result to OpenClaw."""
        from .audit import append

        tool_name = session["tool"]
        tool_args = session["args"]
        approved = session["approved"]

        if not approved:
            append(tool_name, tool_args, "browser", "deny", "Denied by user", "browser", "mcp")
            await self._push_to_openclaw(f"Tool call `{tool_name}` was **denied**.")
            return

        append(tool_name, tool_args, "browser", "allow", "Approved by user", "browser", "mcp")

        # Execute the downstream tool
        alias, _, downstream_tool = tool_name.partition("__")
        client = self._clients.get(alias)
        if not client:
            await self._push_to_openclaw(f"Tool `{tool_name}` approved, but downstream server '{alias}' not found.")
            return

        try:
            result = await client.call_tool(downstream_tool, tool_args)
            text_parts = []
            for block in result.content:
                if hasattr(block, "text"):
                    text_parts.append(block.text)
                elif isinstance(block, dict) and "text" in block:
                    text_parts.append(block["text"])
            result_text = "\n".join(text_parts) if text_parts else "(no output)"
            await self._push_to_openclaw(
                f"Tool `{tool_name}` was **approved** and executed.\n\nResult:\n```\n{result_text}\n```"
            )
        except Exception as e:
            await self._push_to_openclaw(f"Tool `{tool_name}` approved but execution failed: {e}")

    async def _push_to_openclaw(self, message: str):
        """Push a message into the OpenClaw session via the hooks/agent endpoint."""
        if not OPENCLAW_HOOKS_URL or not OPENCLAW_HOOKS_TOKEN:
            sys.stderr.write(f"[latch] Webhook not configured, skipping push: {message[:100]}\n")
            return

        import aiohttp

        # /hooks/agent runs an isolated agent turn; it does not directly emit payload.message.
        # Ask the agent to produce a concise user-facing summary of the outcome.
        agent_prompt = (
            "Summarize the following latch approval outcome for the user in 1-2 short sentences. "
            "Include the decision (approved/denied), the tool name, and execution status if applicable. "
            "Keep the response concise and user-facing.\n"
            f"<latch_result>\n{message}\n</latch_result>"
        )

        payload = {
            "message": agent_prompt,
            "name": "latch-approval",
            "deliver": True,
            "wakeMode": "now",
        }
        if OPENCLAW_SESSION_KEY:
            payload["sessionKey"] = OPENCLAW_SESSION_KEY
        if OPENCLAW_CHANNEL:
            payload["channel"] = OPENCLAW_CHANNEL
        if OPENCLAW_CHANNEL_TO:
            payload["to"] = OPENCLAW_CHANNEL_TO

        try:
            async with aiohttp.ClientSession() as http:
                async with http.post(
                    OPENCLAW_HOOKS_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {OPENCLAW_HOOKS_TOKEN}",
                        "Content-Type": "application/json",
                    },
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    body = await resp.text()
                    if resp.status >= 400:
                        sys.stderr.write(f"[latch] Webhook push failed ({resp.status}): {body}\n")
                    else:
                        sys.stderr.write(f"[latch] Webhook push OK ({resp.status}): {body}\n")
                    sys.stderr.write(f"[latch] Webhook payload: {json.dumps(payload)}\n")
        except Exception as e:
            sys.stderr.write(f"[latch] Webhook push error: {e}\n")

    # --- Enrollment routes ---

    async def _get_enroll_page(self, req: web.Request):
        return web.Response(content_type="text/html", text=_ENROLL_HTML)

    async def _get_enroll_options(self, req: web.Request):
        existing = credentials.load()
        opts = generate_registration_options(
            rp_id=self._rp_id,
            rp_name="latch",
            user_name="latch-user",
            attestation=AttestationConveyancePreference.NONE,
            exclude_credentials=[{"type": "public-key", "id": c["credentialID"]} for c in existing],
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.REQUIRED,
                authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            ),
        )
        self._enroll_challenge = opts.challenge
        exclude_credentials = [d for d in (_descriptor_json(c) for c in (opts.exclude_credentials or [])) if d]
        return web.json_response({
            "challenge": _b64url(opts.challenge),
            "rp": {"name": opts.rp.name, "id": opts.rp.id},
            "user": {"id": _b64url(opts.user.id), "name": opts.user.name, "displayName": opts.user.display_name},
            "pubKeyCredParams": [{"type": c.type, "alg": c.alg} for c in opts.pub_key_cred_params],
            "timeout": opts.timeout,
            "excludeCredentials": exclude_credentials,
            "authenticatorSelection": {
                "residentKey": opts.authenticator_selection.resident_key.value if opts.authenticator_selection else None,
                "userVerification": opts.authenticator_selection.user_verification.value if opts.authenticator_selection else None,
                "authenticatorAttachment": opts.authenticator_selection.authenticator_attachment.value if (opts.authenticator_selection and opts.authenticator_selection.authenticator_attachment) else None,
            },
            "attestation": opts.attestation.value if opts.attestation else "none",
        })

    async def _post_enroll_verify(self, req: web.Request):
        if self._enroll_challenge is None:
            return web.json_response({"error": "No challenge"}, status=400)
        body = await req.json()
        try:
            expected_origin = self._get_expected_origin(req)
            verification = verify_registration_response(
                credential=body,
                expected_challenge=self._enroll_challenge,
                expected_rp_id=self._rp_id,
                expected_origin=expected_origin,
            )
            credentials.save({
                "credentialID": _b64url(verification.credential_id),
                "publicKey": base64.b64encode(verification.credential_public_key).decode(),
                "counter": verification.sign_count,
                "transports": body.get("response", {}).get("transports"),
                "createdAt": datetime.now(timezone.utc).isoformat(),
            })
            sys.stderr.write("Passkey enrolled successfully!\n")
            self._enroll_challenge = None
            if self._enroll_complete:
                self._enroll_complete.set()
            return web.json_response({"ok": True})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=400)


# Module-level singleton
_server: ApprovalServer | None = None


async def get_approval_server() -> ApprovalServer:
    """Get or create the shared ApprovalServer singleton."""
    global _server
    if _server is None:
        _server = ApprovalServer()
        await _server.start()
    return _server


async def start_approval_flow(tool_name: str, tool_input: dict, require_webauthn: bool = False) -> bool:
    """Legacy API: creates a request on the persistent server and waits for decision.

    Falls back to opening a local browser if no tunnel is available.
    """
    server = await get_approval_server()
    approval_id, url = server.create_request(tool_name, tool_input, require_webauthn)
    sys.stderr.write(f"Approval URL: {url}\n")
    if not server.has_tunnel:
        webbrowser.open(url)
    return await server.wait_for_decision(approval_id)


# --- HTML templates ---

def _approval_page(approval_id, tool_name, tool_input, require_webauthn, redirect_url):
    escaped = json.dumps(tool_input, indent=2).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    approve_label = "Approve with Passkey" if require_webauthn else "Approve"
    redirect_label = "Return to Chat"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Latch — Approve Tool Call</title>
<style>
  @import url("https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=JetBrains+Mono:wght@400;600&display=swap");
  :root {{
    --bg: #0a111c;
    --bg-2: #101b2b;
    --card: rgba(10, 17, 28, 0.82);
    --line: rgba(126, 159, 204, 0.35);
    --text: #edf3ff;
    --muted: #9cb2cf;
    --approve: #2bc173;
    --deny: #ff5b66;
    --cta: #3f8cff;
    --glow: rgba(63, 140, 255, 0.4);
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: "Space Grotesk", sans-serif;
    color: var(--text);
    min-height: 100vh;
    display: grid;
    place-items: center;
    padding: 1.25rem;
    background:
      radial-gradient(1200px 700px at -10% -20%, #274469 0%, transparent 55%),
      radial-gradient(900px 540px at 110% 120%, #1a5a4a 0%, transparent 60%),
      linear-gradient(155deg, var(--bg) 0%, var(--bg-2) 100%);
  }}
  .card {{
    width: min(780px, 100%);
    border-radius: 20px;
    border: 1px solid var(--line);
    backdrop-filter: blur(10px);
    background: var(--card);
    box-shadow: 0 22px 70px rgba(0, 0, 0, 0.45), 0 0 0 1px rgba(255,255,255,0.03) inset;
    overflow: hidden;
  }}
  .header {{
    padding: 1.5rem 1.5rem 1rem;
    border-bottom: 1px solid rgba(126, 159, 204, 0.2);
    background: linear-gradient(90deg, rgba(63,140,255,0.16), rgba(43,193,115,0.08));
  }}
  .eyebrow {{
    font-size: 0.76rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #7fb7ff;
    margin-bottom: 0.55rem;
    font-weight: 700;
  }}
  h1 {{
    font-size: clamp(1.35rem, 2.4vw, 1.8rem);
    line-height: 1.15;
    margin-bottom: 0.45rem;
  }}
  .subtitle {{
    color: var(--muted);
    font-size: 0.95rem;
  }}
  .content {{
    padding: 1.25rem 1.5rem 1.5rem;
    display: grid;
    gap: 1rem;
  }}
  .meta {{
    display: grid;
    gap: 0.45rem;
  }}
  .label {{
    color: #b9c9e2;
    font-size: 0.82rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    font-weight: 700;
  }}
  .tool-name {{
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    width: fit-content;
    border-radius: 999px;
    border: 1px solid rgba(63, 140, 255, 0.4);
    background: rgba(63, 140, 255, 0.13);
    color: #e3efff;
    font-family: "JetBrains Mono", monospace;
    font-size: 0.95rem;
    font-weight: 600;
    padding: 0.38rem 0.72rem;
  }}
  .args {{
    border-radius: 14px;
    border: 1px solid rgba(126, 159, 204, 0.25);
    background: rgba(5, 11, 20, 0.68);
    padding: 0.95rem;
    font-family: "JetBrains Mono", monospace;
    font-size: 0.83rem;
    line-height: 1.45;
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 260px;
    overflow: auto;
    color: #d8e5fa;
  }}
  .buttons {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.8rem;
  }}
  button {{
    border: none;
    border-radius: 12px;
    padding: 0.84rem 1rem;
    font-family: "Space Grotesk", sans-serif;
    font-size: 0.98rem;
    font-weight: 700;
    cursor: pointer;
    transition: transform 120ms ease, opacity 120ms ease, box-shadow 120ms ease;
  }}
  button:hover {{ transform: translateY(-1px); }}
  button:disabled {{ opacity: 0.55; cursor: not-allowed; transform: none; }}
  .approve {{
    color: #062413;
    background: linear-gradient(135deg, #7ef6b2 0%, var(--approve) 100%);
    box-shadow: 0 7px 20px rgba(43, 193, 115, 0.35);
  }}
  .deny {{
    color: #3a090e;
    background: linear-gradient(135deg, #ffb8be 0%, var(--deny) 100%);
    box-shadow: 0 7px 20px rgba(255, 91, 102, 0.3);
  }}
  #btn-return {{
    display: none;
    color: #eaf2ff;
    background: linear-gradient(135deg, #3f8cff 0%, #2e6ddf 100%);
    box-shadow: 0 7px 20px var(--glow);
  }}
  .status {{
    min-height: 2.25rem;
    border-radius: 10px;
    border: 1px solid rgba(126, 159, 204, 0.25);
    background: rgba(12, 24, 40, 0.55);
    color: #c4d6f1;
    display: grid;
    place-items: center;
    text-align: center;
    font-size: 0.92rem;
    padding: 0.5rem 0.7rem;
  }}
  @media (max-width: 640px) {{
    .header {{ padding: 1.2rem 1rem 0.9rem; }}
    .content {{ padding: 1rem; }}
    .buttons {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <div class="eyebrow">Latch Security Gate</div>
    <h1>Approve This Tool Call</h1>
    <div class="subtitle">Review request details before allowing execution.</div>
  </div>
  <div class="content">
    <div class="meta">
      <div class="label">Tool</div>
      <div class="tool-name">{tool_name}</div>
    </div>
    <div class="meta">
      <div class="label">Arguments</div>
      <div class="args">{escaped}</div>
    </div>
    <div class="buttons">
      <button class="approve" id="btn-approve">{approve_label}</button>
      <button class="deny" id="btn-deny">Deny</button>
      <button id="btn-return">{redirect_label}</button>
    </div>
    <div class="status" id="status">Waiting for your decision.</div>
  </div>
</div>
<script>
  const approvalId = {json.dumps(approval_id)};
  const requireWebAuthn = {"true" if require_webauthn else "false"};
  const redirectUrl = {json.dumps(redirect_url)};
  const statusEl = document.getElementById("status");
  const btnReturn = document.getElementById("btn-return");

  function showReturnButton() {{
    if (!redirectUrl) return;
    btnReturn.style.display = "block";
  }}

  function maybeRedirect() {{
    if (!redirectUrl) return;
    showReturnButton();
    setTimeout(() => {{
      try {{ window.location.href = redirectUrl; }} catch (_e) {{}}
    }}, 700);
  }}

  if (redirectUrl) {{
    btnReturn.addEventListener("click", () => {{
      window.location.href = redirectUrl;
    }});
  }}

  async function decide(decision, authResponse) {{
    statusEl.textContent = decision === "approve" ? "Approving..." : "Denying...";
    document.getElementById("btn-approve").disabled = true;
    document.getElementById("btn-deny").disabled = true;
    const body = {{ decision }};
    if (authResponse) body.authResponse = authResponse;
    const res = await fetch("/approval/" + approvalId + "/decide", {{ method: "POST", headers: {{"Content-Type": "application/json"}}, body: JSON.stringify(body) }});
    if (res.ok) {{
      statusEl.textContent = decision === "approve" ? "Approved \u2713" : "Denied \u2715";
      if (redirectUrl) statusEl.textContent += " Redirecting...";
      maybeRedirect();
    }}
    else {{ const err = await res.json().catch(() => ({{}})); statusEl.textContent = "Error: " + (err.error || res.statusText); document.getElementById("btn-approve").disabled = false; document.getElementById("btn-deny").disabled = false; }}
  }}

  document.getElementById("btn-deny").addEventListener("click", () => decide("deny"));
  document.getElementById("btn-approve").addEventListener("click", async () => {{
    if (!requireWebAuthn) return decide("approve");
    try {{
      statusEl.textContent = "Requesting passkey...";
      document.getElementById("btn-approve").disabled = true;
      const optRes = await fetch("/approval/" + approvalId + "/webauthn-options");
      if (!optRes.ok) {{ const err = await optRes.json().catch(() => ({{}})); throw new Error(err.error || "Failed to get options"); }}
      const options = await optRes.json();
      options.challenge = b64url(options.challenge);
      if (options.allowCredentials) options.allowCredentials = options.allowCredentials.map(c => ({{...c, id: b64url(c.id)}}));
      const assertion = await navigator.credentials.get({{ publicKey: options }});
      const authResponse = {{ id: assertion.id, rawId: buf64(assertion.rawId), type: assertion.type, response: {{ authenticatorData: buf64(assertion.response.authenticatorData), clientDataJSON: buf64(assertion.response.clientDataJSON), signature: buf64(assertion.response.signature), userHandle: assertion.response.userHandle ? buf64(assertion.response.userHandle) : null }}, clientExtensionResults: assertion.getClientExtensionResults(), authenticatorAttachment: assertion.authenticatorAttachment }};
      await decide("approve", authResponse);
    }} catch (err) {{ statusEl.textContent = "WebAuthn error: " + err.message; document.getElementById("btn-approve").disabled = false; }}
  }});

  function b64url(s) {{ const b = s.replace(/-/g,"+").replace(/_/g,"/"); const p = b.length%4; const d = atob(p ? b+"=".repeat(4-p) : b); const a = new Uint8Array(d.length); for (let i=0;i<d.length;i++) a[i]=d.charCodeAt(i); return a.buffer; }}
  function buf64(buf) {{ const a = new Uint8Array(buf); let s=""; for (const b of a) s+=String.fromCharCode(b); return btoa(s).replace(/\\+/g,"-").replace(/\\//g,"_").replace(/=+$/,""); }}
</script>
</body>
</html>"""


_ENROLL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Latch — Enroll Passkey</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0d1117; color: #e6edf3; display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 2rem; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 2rem; max-width: 450px; width: 100%; text-align: center; }
  h1 { font-size: 1.4rem; margin-bottom: 1rem; }
  p { color: #8b949e; margin-bottom: 1.5rem; line-height: 1.5; }
  button { padding: 0.75rem 2rem; border: none; border-radius: 8px; font-size: 1rem; font-weight: 600; cursor: pointer; background: #238636; color: #fff; transition: opacity 0.15s; }
  button:hover { opacity: 0.85; } button:disabled { opacity: 0.5; cursor: not-allowed; }
  .status { margin-top: 1rem; color: #8b949e; min-height: 1.5em; }
</style>
</head>
<body>
<div class="card">
  <h1>Enroll Passkey</h1>
  <p>Register a passkey (Touch ID / Face ID / security key) to approve tool calls from your AI agent.</p>
  <button id="btn-enroll">Register Passkey</button>
  <div class="status" id="status"></div>
</div>
<script>
  const statusEl = document.getElementById("status");
  const btn = document.getElementById("btn-enroll");
  btn.addEventListener("click", async () => {
    try {
      btn.disabled = true;
      statusEl.textContent = "Getting options\\u2026";
      const options = await fetch("/enroll/options").then(r => r.json());
      options.challenge = b64url(options.challenge);
      options.user.id = b64url(options.user.id);
      if (options.excludeCredentials) options.excludeCredentials = options.excludeCredentials.map(c => ({...c, id: b64url(c.id)}));
      statusEl.textContent = "Touch your sensor\\u2026";
      const cred = await navigator.credentials.create({ publicKey: options });
      const reg = { id: cred.id, rawId: buf64(cred.rawId), type: cred.type, response: { attestationObject: buf64(cred.response.attestationObject), clientDataJSON: buf64(cred.response.clientDataJSON), transports: cred.response.getTransports ? cred.response.getTransports() : [] }, clientExtensionResults: cred.getClientExtensionResults(), authenticatorAttachment: cred.authenticatorAttachment };
      statusEl.textContent = "Verifying\\u2026";
      const res = await fetch("/enroll/verify", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(reg) });
      if (res.ok) { statusEl.textContent = "Passkey enrolled! You can close this tab."; statusEl.style.color = "#3fb950"; }
      else { const err = await res.json().catch(() => ({})); throw new Error(err.error || "Verification failed"); }
    } catch (err) { statusEl.textContent = "Error: " + err.message; statusEl.style.color = "#f85149"; btn.disabled = false; }
  });
  function b64url(s) { const b = s.replace(/-/g,"+").replace(/_/g,"/"); const p = b.length%4; const d = atob(p ? b+"=".repeat(4-p) : b); const a = new Uint8Array(d.length); for (let i=0;i<d.length;i++) a[i]=d.charCodeAt(i); return a.buffer; }
  function buf64(buf) { const a = new Uint8Array(buf); let s=""; for (const b of a) s+=String.fromCharCode(b); return btoa(s).replace(/\\+/g,"-").replace(/\\//g,"_").replace(/=+$/,""); }
</script>
</body>
</html>"""

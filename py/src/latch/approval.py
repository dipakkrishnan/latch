import asyncio, base64, json, os, secrets, sys, webbrowser
from aiohttp import web
from webauthn import generate_authentication_options, verify_authentication_response
from webauthn.helpers.structs import UserVerificationRequirement

from . import credentials
from .logging_utils import debug_enabled, init_logger

RP_ID = "localhost"
DEFAULT_APPROVAL_TIMEOUT_SEC = 120.0
_LOGGER = init_logger("latch.approval", debug=debug_enabled())


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


async def start_approval_flow(tool_name: str, tool_input: dict, require_webauthn=False) -> tuple[bool, str]:
    approval_id = secrets.token_urlsafe(16)
    state: dict = {"challenge": None, "approved": False}
    done = asyncio.Event()
    deny_reason = "Denied in browser"
    _LOGGER.debug("starting approval flow tool=%s require_webauthn=%s", tool_name, require_webauthn)

    async def get_page(req):
        if req.match_info["id"] != approval_id:
            raise web.HTTPNotFound()
        return web.Response(content_type="text/html", text=_page(approval_id, tool_name, tool_input, require_webauthn))

    async def get_webauthn_opts(req):
        if req.match_info["id"] != approval_id:
            raise web.HTTPNotFound()
        creds = credentials.load()
        if not creds:
            return web.json_response({"error": "No credentials enrolled. Run: uv run latch-enroll"}, status=400)
        try:
            opts = generate_authentication_options(
                rp_id=RP_ID,
                allow_credentials=[{"type": "public-key", "id": c["credentialID"]} for c in creds],
                user_verification=UserVerificationRequirement.REQUIRED,
            )
            allow_credentials = [d for d in (_descriptor_json(c) for c in (opts.allow_credentials or [])) if d]
        except Exception as e:
            return web.json_response({"error": f"Failed to build WebAuthn options: {e}"}, status=500)
        state["challenge"] = opts.challenge
        return web.json_response({
            "challenge": _b64url(opts.challenge),
            "timeout": opts.timeout,
            "rpId": opts.rp_id,
            "allowCredentials": allow_credentials,
            "userVerification": opts.user_verification.value if opts.user_verification else "preferred",
        })

    async def post_decide(req):
        nonlocal deny_reason
        if req.match_info["id"] != approval_id:
            raise web.HTTPNotFound()
        body = await req.json()
        decision = body.get("decision")

        if decision == "approve" and require_webauthn:
            auth_response = body.get("authResponse")
            if not auth_response or state["challenge"] is None:
                deny_reason = "Denied in browser (webauthn): assertion-or-challenge-missing"
                done.set()
                return web.json_response({"error": "WebAuthn assertion required"}, status=400)
            creds = credentials.load()
            received_id = _normalize_credential_id(auth_response.get("id") or auth_response.get("rawId"))
            match = next((c for c in creds if _normalize_credential_id(c.get("credentialID")) == received_id), None)
            if not match:
                deny_reason = "Denied in browser (webauthn): unknown-credential"
                done.set()
                return web.json_response({"error": "Unknown credential"}, status=400)
            try:
                port = req.url.port
                verification = verify_authentication_response(
                    credential=auth_response,
                    expected_challenge=state["challenge"],
                    expected_rp_id=RP_ID,
                    expected_origin=f"http://{RP_ID}:{port}",
                    credential_public_key=base64.b64decode(match["publicKey"]),
                    credential_current_sign_count=match["counter"],
                    require_user_verification=True,
                )
                credentials.update_counter(match["credentialID"], verification.new_sign_count)
            except Exception as e:
                _LOGGER.warning("WebAuthn verification failed: %s", e)
                deny_reason = "Denied in browser (webauthn): verification-failed"
                done.set()
                return web.json_response({"error": f"WebAuthn error: {e}"}, status=400)

        state["approved"] = decision == "approve"
        if not state["approved"]:
            deny_reason = f"Denied in browser ({'webauthn' if require_webauthn else 'browser'}): user-denied"
        done.set()
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_get("/approval/{id}", get_page)
    app.router.add_get("/approval/{id}/webauthn-options", get_webauthn_opts)
    app.router.add_post("/approval/{id}/decide", post_decide)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]

    url = f"http://{RP_ID}:{port}/approval/{approval_id}"
    sys.stderr.write(f"Opening approval page: {url}\n")
    webbrowser.open(url)

    timeout_sec = _approval_timeout_seconds()
    try:
        await asyncio.wait_for(done.wait(), timeout=timeout_sec)
    except TimeoutError:
        deny_reason = f"Denied in browser ({'webauthn' if require_webauthn else 'browser'}): timeout"
        _LOGGER.warning("Approval timed out after %.2fs for tool=%s", timeout_sec, tool_name)
        await runner.cleanup()
        return False, deny_reason

    await runner.cleanup()
    if state["approved"]:
        _LOGGER.debug("approval flow approved tool=%s", tool_name)
        return True, f"Approved in browser ({'webauthn' if require_webauthn else 'browser'})"
    _LOGGER.debug("approval flow denied tool=%s reason=%s", tool_name, deny_reason)
    return False, deny_reason


def _approval_timeout_seconds() -> float:
    raw = os.environ.get("LATCH_APPROVAL_TIMEOUT_SEC", "").strip()
    if not raw:
        return DEFAULT_APPROVAL_TIMEOUT_SEC
    try:
        parsed = float(raw)
    except ValueError:
        _LOGGER.warning(
            "Invalid LATCH_APPROVAL_TIMEOUT_SEC=%r; using default %.2fs",
            raw,
            DEFAULT_APPROVAL_TIMEOUT_SEC,
        )
        return DEFAULT_APPROVAL_TIMEOUT_SEC
    if parsed <= 0:
        _LOGGER.warning(
            "Non-positive LATCH_APPROVAL_TIMEOUT_SEC=%r; using default %.2fs",
            raw,
            DEFAULT_APPROVAL_TIMEOUT_SEC,
        )
        return DEFAULT_APPROVAL_TIMEOUT_SEC
    return parsed


def _page(approval_id, tool_name, tool_input, require_webauthn):
    escaped = json.dumps(tool_input, indent=2).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    approve_label = "Approve with Passkey" if require_webauthn else "Approve"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>agent-2fa — Approve Tool Call</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0d1117; color: #e6edf3; display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 2rem; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 2rem; max-width: 600px; width: 100%; }}
  h1 {{ font-size: 1.4rem; margin-bottom: 0.5rem; }}
  .tool-name {{ color: #58a6ff; font-family: monospace; font-size: 1.2rem; background: #0d1117; padding: 0.3rem 0.6rem; border-radius: 6px; display: inline-block; margin-bottom: 1rem; }}
  .args {{ background: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 1rem; font-family: monospace; font-size: 0.85rem; white-space: pre-wrap; word-break: break-all; max-height: 300px; overflow-y: auto; margin-bottom: 1.5rem; }}
  .buttons {{ display: flex; gap: 1rem; }}
  button {{ flex: 1; padding: 0.75rem 1.5rem; border: none; border-radius: 8px; font-size: 1rem; font-weight: 600; cursor: pointer; transition: opacity 0.15s; }}
  button:hover {{ opacity: 0.85; }} button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
  .approve {{ background: #238636; color: #fff; }} .deny {{ background: #da3633; color: #fff; }}
  .status {{ margin-top: 1rem; text-align: center; color: #8b949e; min-height: 1.5em; }}
  label {{ font-size: 0.9rem; color: #8b949e; display: block; margin-bottom: 0.3rem; }}
</style>
</head>
<body>
<div class="card">
  <h1>Tool Call Approval</h1>
  <label>Tool</label><div class="tool-name">{tool_name}</div>
  <label>Arguments</label><div class="args">{escaped}</div>
  <div class="buttons">
    <button class="approve" id="btn-approve">{approve_label}</button>
    <button class="deny" id="btn-deny">Deny</button>
  </div>
  <div class="status" id="status"></div>
</div>
<script>
  const approvalId = {json.dumps(approval_id)};
  const requireWebAuthn = {"true" if require_webauthn else "false"};
  const statusEl = document.getElementById("status");

  async function decide(decision, authResponse) {{
    statusEl.textContent = decision === "approve" ? "Approving\u2026" : "Denying\u2026";
    document.getElementById("btn-approve").disabled = true;
    document.getElementById("btn-deny").disabled = true;
    const body = {{ decision }};
    if (authResponse) body.authResponse = authResponse;
    const res = await fetch("/approval/" + approvalId + "/decide", {{ method: "POST", headers: {{"Content-Type": "application/json"}}, body: JSON.stringify(body) }});
    if (res.ok) {{ statusEl.textContent = decision === "approve" ? "Approved \u2713" : "Denied \u2715"; }}
    else {{ const err = await res.json().catch(() => ({{}})); statusEl.textContent = "Error: " + (err.error || res.statusText); document.getElementById("btn-approve").disabled = false; document.getElementById("btn-deny").disabled = false; }}
  }}

  document.getElementById("btn-deny").addEventListener("click", () => decide("deny"));
  document.getElementById("btn-approve").addEventListener("click", async () => {{
    if (!requireWebAuthn) return decide("approve");
    try {{
      statusEl.textContent = "Requesting passkey\u2026";
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

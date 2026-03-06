import asyncio, base64, json, sys, webbrowser
from aiohttp import web
from webauthn import generate_registration_options, verify_registration_response
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    UserVerificationRequirement,
    ResidentKeyRequirement,
    AuthenticatorAttachment,
    AttestationConveyancePreference,
)
from . import credentials

RP_ID = "localhost"
RP_NAME = "agent-2fa"


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


async def _run():
    challenge = None
    port_holder: list = []

    async def get_page(req):
        return web.Response(content_type="text/html", text=_ENROLL_HTML)

    async def get_options(req):
        nonlocal challenge
        existing = credentials.load()
        opts = generate_registration_options(
            rp_id=RP_ID,
            rp_name=RP_NAME,
            user_name="agent-2fa-user",
            attestation=AttestationConveyancePreference.NONE,
            exclude_credentials=[{"type": "public-key", "id": c["credentialID"]} for c in existing],
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.REQUIRED,
                authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            ),
        )
        challenge = opts.challenge
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

    async def post_verify(req):
        if challenge is None:
            return web.json_response({"error": "No challenge"}, status=400)
        body = await req.json()
        try:
            verification = verify_registration_response(
                credential=body,
                expected_challenge=challenge,
                expected_rp_id=RP_ID,
                expected_origin=f"http://{RP_ID}:{port_holder[0]}",
            )
            credentials.save({
                "credentialID": _b64url(verification.credential_id),
                "publicKey": base64.b64encode(verification.credential_public_key).decode(),
                "counter": verification.sign_count,
                "transports": body.get("response", {}).get("transports"),
                "createdAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            })
            sys.stderr.write("Passkey enrolled successfully!\n")
            return web.json_response({"ok": True})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=400)

    app = web.Application()
    app.router.add_get("/enroll", get_page)
    app.router.add_get("/enroll/options", get_options)
    app.router.add_post("/enroll/verify", post_verify)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    port_holder.append(port)

    url = f"http://{RP_ID}:{port}/enroll"
    sys.stderr.write(f"Opening enrollment page: {url}\n")
    webbrowser.open(url)

    # Wait until a credential is saved (poll), then shut down
    initial_count = len(credentials.load())
    while len(credentials.load()) == initial_count:
        await asyncio.sleep(0.5)
    await asyncio.sleep(1)
    await runner.cleanup()


def main():
    asyncio.run(_run())


_ENROLL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>agent-2fa — Enroll Passkey</title>
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
  <p>Register a passkey (Touch ID / security key) to approve tool calls from your AI agent.</p>
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

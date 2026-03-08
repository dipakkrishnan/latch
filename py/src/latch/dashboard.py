import asyncio, base64, datetime, json, secrets, sys, time, webbrowser
from aiohttp import web
from webauthn import generate_registration_options, verify_registration_response
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria, UserVerificationRequirement,
    ResidentKeyRequirement, AttestationConveyancePreference, AuthenticatorAttachment,
)
import yaml

from . import credentials, audit
from .config import CONFIG_DIR
from .policy import load_policy, _PATH as _POLICY_PATH
from .logging_utils import debug_enabled, init_logger

RP_ID = "localhost"
RP_NAME = "agent-2fa"
_VALID_ACTIONS = {"allow", "ask", "deny", "browser", "webauthn"}
ENROLL_CHALLENGE_TTL_SEC = 300
_LOGGER = init_logger("latch.dashboard", debug=debug_enabled())


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


def _validate_policy(config) -> list:
    if not isinstance(config, dict):
        return [f"policy must be a YAML mapping, got {type(config).__name__}"]
    errs = []
    if config.get("defaultAction") not in _VALID_ACTIONS:
        errs.append(f"invalid defaultAction: {config.get('defaultAction')!r}")
    for i, r in enumerate(config.get("rules", [])):
        if not isinstance(r.get("match", {}).get("tool"), str):
            errs.append(f"rule[{i}].match.tool must be a string")
        if r.get("action") not in _VALID_ACTIONS:
            errs.append(f"rule[{i}].action invalid: {r.get('action')!r}")
    return errs


async def create_app(port=2222) -> web.Application:
    app = web.Application()
    challenges: dict = {}

    def prune_challenges():
        now = time.time()
        expired = [cid for cid, rec in challenges.items() if now - rec["t"] > ENROLL_CHALLENGE_TTL_SEC]
        for cid in expired:
            challenges.pop(cid, None)

    async def get_index(req):
        return web.Response(content_type="text/html", text=_HTML)

    # --- Policy (JSON) ---
    async def get_policy_json(req):
        p = load_policy(force=True)
        return web.json_response(p)

    async def put_policy_json(req):
        config = await req.json()
        errs = _validate_policy(config)
        if errs:
            return web.json_response({"error": "Invalid policy", "issues": errs}, status=400)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _POLICY_PATH.write_text(yaml.dump(config, default_flow_style=False))
        load_policy(force=True)
        return web.json_response({"ok": True})

    async def validate_policy_json(req):
        config = await req.json()
        errs = _validate_policy(config)
        return web.json_response({"valid": not errs, "errors": errs})

    # --- Policy (YAML) ---
    async def get_policy_yaml(req):
        if not _POLICY_PATH.exists():
            load_policy(force=True)
        return web.Response(content_type="text/plain", charset="utf-8", text=_POLICY_PATH.read_text())

    async def put_policy_yaml(req):
        raw = await req.text()
        try:
            config = yaml.safe_load(raw)
        except Exception as e:
            return web.json_response({"error": f"YAML parse error: {e}"}, status=400)
        errs = _validate_policy(config)
        if errs:
            return web.json_response({"error": "Invalid policy", "issues": errs}, status=400)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _POLICY_PATH.write_text(raw)
        load_policy(force=True)
        return web.json_response({"ok": True})

    # --- Credentials ---
    async def list_credentials(req):
        return web.json_response([
            {**{k: v for k, v in c.items() if k != "publicKey"}, "publicKey": "[redacted]"}
            for c in credentials.load()
        ])

    async def delete_credential(req):
        if not credentials.delete(req.match_info["id"]):
            return web.json_response({"error": "Not found"}, status=404)
        return web.json_response({"ok": True})

    # --- Enroll ---
    async def enroll_options(req):
        prune_challenges()
        existing = credentials.load()
        opts = generate_registration_options(
            rp_id=RP_ID, rp_name=RP_NAME, user_name="agent-2fa-user",
            attestation=AttestationConveyancePreference.NONE,
            exclude_credentials=[{"type": "public-key", "id": c["credentialID"]} for c in existing],
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.REQUIRED,
                authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            ),
        )
        cid = secrets.token_urlsafe(16)
        challenges[cid] = {"challenge": opts.challenge, "t": time.time()}
        sel = opts.authenticator_selection
        authenticator_selection: dict = {}
        if sel:
            if sel.resident_key:
                authenticator_selection["residentKey"] = sel.resident_key.value
            if sel.user_verification:
                authenticator_selection["userVerification"] = sel.user_verification.value
            if sel.authenticator_attachment:
                authenticator_selection["authenticatorAttachment"] = sel.authenticator_attachment.value
        exclude_credentials = [d for d in (_descriptor_json(c) for c in (opts.exclude_credentials or [])) if d]
        return web.json_response({
            "challengeId": cid,
            "challenge": _b64url(opts.challenge),
            "rp": {"name": opts.rp.name, "id": opts.rp.id},
            "user": {"id": _b64url(opts.user.id), "name": opts.user.name, "displayName": opts.user.display_name},
            "pubKeyCredParams": [{"type": c.type, "alg": c.alg} for c in opts.pub_key_cred_params],
            "timeout": opts.timeout,
            "excludeCredentials": exclude_credentials,
            "authenticatorSelection": authenticator_selection,
            "attestation": opts.attestation.value if opts.attestation else "none",
        })

    async def enroll_verify(req):
        prune_challenges()
        body = await req.json()
        cid = body.get("challengeId")
        if not cid:
            return web.json_response({"error": "Missing challengeId"}, status=400)
        if cid not in challenges:
            return web.json_response({"error": "No challenge"}, status=400)
        rec = challenges.pop(cid)
        if time.time() - rec["t"] > ENROLL_CHALLENGE_TTL_SEC:
            return web.json_response({"error": "Challenge expired"}, status=400)
        response = body.get("response", body)
        if not isinstance(response, dict):
            return web.json_response({"error": "Invalid response payload"}, status=400)
        if response.get("authenticatorAttachment") != "platform":
            return web.json_response(
                {"error": "Platform authenticator required. Use Touch ID / Face ID / Windows Hello on this device."},
                status=400,
            )
        try:
            v = verify_registration_response(
                credential=response,
                expected_challenge=rec["challenge"],
                expected_rp_id=RP_ID,
                expected_origin=f"http://{RP_ID}:{port}",
            )
            credentials.save({
                "credentialID": _b64url(v.credential_id),
                "publicKey": base64.b64encode(v.credential_public_key).decode(),
                "counter": v.sign_count,
                "transports": response.get("response", {}).get("transports") if isinstance(response, dict) else None,
                "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })
            return web.json_response({"ok": True})
        except Exception as e:
            _LOGGER.warning("enroll verify failed: %s", e)
            return web.json_response({"error": str(e)}, status=400)

    # --- Audit ---
    async def get_audit(req):
        limit = int(req.rel_url.query.get("limit", 50))
        offset = int(req.rel_url.query.get("offset", 0))
        return web.json_response(audit.read(limit=limit, offset=offset))

    async def get_audit_stats(req):
        return web.json_response(audit.stats())

    app.router.add_get("/", get_index)
    app.router.add_get("/api/policy", get_policy_json)
    app.router.add_put("/api/policy", put_policy_json)
    app.router.add_post("/api/policy/validate", validate_policy_json)
    app.router.add_get("/api/policy/yaml", get_policy_yaml)
    app.router.add_put("/api/policy/yaml", put_policy_yaml)
    app.router.add_get("/api/credentials", list_credentials)
    app.router.add_delete("/api/credentials/{id}", delete_credential)
    app.router.add_get("/api/enroll/options", enroll_options)
    app.router.add_post("/api/enroll/verify", enroll_verify)
    app.router.add_get("/api/audit-log", get_audit)
    app.router.add_get("/api/audit-log/stats", get_audit_stats)
    return app


async def _run(port=2222, no_open=False):
    app = await create_app(port=port)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", port).start()
    sys.stderr.write(f"Dashboard running at http://localhost:{port}\n")
    if not no_open:
        webbrowser.open(f"http://localhost:{port}")
    await asyncio.Event().wait()


def main(argv=None):
    args = (argv or sys.argv[1:])
    port, no_open, i = 2222, False, 0
    while i < len(args):
        if args[i] == "--no-open": no_open = True
        elif args[i].startswith("--port="): port = int(args[i].split("=", 1)[1])
        elif args[i] == "--port" and i + 1 < len(args): port = int(args[i + 1]); i += 1
        i += 1
    asyncio.run(_run(port=port, no_open=no_open))


_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>agent-2fa dashboard</title>
<style>
  *, *::before, *::after { box-sizing: border-box; }
  :root {
    --bg: #0d1117;
    --card-bg: #161b22;
    --card-soft: #1f2630;
    --border: #30363d;
    --text: #e6edf3;
    --text-muted: #8b949e;
    --blue: #58a6ff;
    --blue-soft: #7bb5ff;
    --green: #238636;
    --green-bright: #3fb950;
    --red: #da3633;
    --red-bright: #f85149;
    --amber: #d29922;
    --purple: #a371f7;
    --font-mono: "SF Mono", "JetBrains Mono", "Fira Code", monospace;
    --font-sans: "Avenir Next", "IBM Plex Sans", "Segoe UI", sans-serif;
    --radius: 14px;
    --transition: 0.15s ease;
  }
  html, body {
    margin: 0;
    min-height: 100%;
  }
  body {
    font-family: var(--font-sans);
    color: var(--text);
    background: var(--bg);
    background-image:
      radial-gradient(circle at 10% -5%, rgba(88, 166, 255, 0.2), transparent 36%),
      radial-gradient(circle at 90% 0%, rgba(35, 134, 54, 0.15), transparent 28%),
      radial-gradient(circle, rgba(255, 255, 255, 0.06) 0.8px, transparent 0.8px);
    background-size: auto, auto, 18px 18px;
  }
  .wrap {
    max-width: 1280px;
    margin: 0 auto;
    padding: 1.2rem 1.2rem 2.2rem;
  }
  header {
    position: sticky;
    top: 0;
    z-index: 10;
    backdrop-filter: blur(8px);
    background: color-mix(in srgb, var(--bg) 82%, transparent);
    border-bottom: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
    border-radius: 12px;
    padding: 0.6rem 0.35rem;
    margin-bottom: 1rem;
  }
  main {
    min-height: 240px;
  }
  .brand-tabs {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    flex-wrap: wrap;
  }
  .brand {
    display: inline-flex;
    align-items: center;
    margin: 0;
    padding: 0;
    border: 0;
    border-radius: 0;
    background: transparent;
    box-shadow: none;
    font-size: 0.95rem;
    font-weight: 700;
    font-family: var(--font-mono);
    color: var(--blue-soft);
    letter-spacing: 0.02em;
  }
  .tabs {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.28rem;
    border-radius: 999px;
    background: color-mix(in srgb, var(--card-bg) 85%, black);
    border: 1px solid var(--border);
  }
  .tabs a {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.35rem;
    min-width: 124px;
    border-radius: 999px;
    padding: 0.5rem 0.85rem;
    text-decoration: none;
    color: var(--text-muted);
    font-size: 0.85rem;
    font-weight: 600;
    transition: color var(--transition), background var(--transition), transform var(--transition);
  }
  .tabs a:hover {
    color: var(--text);
    background: rgba(88, 166, 255, 0.14);
    transform: translateY(-1px);
  }
  .tabs a.active {
    color: #fff;
    background: linear-gradient(120deg, color-mix(in srgb, var(--blue) 76%, #78b7ff), var(--blue));
  }
  .count {
    font-family: var(--font-mono);
    font-size: 0.68rem;
    border: 1px solid color-mix(in srgb, var(--border) 80%, transparent);
    border-radius: 999px;
    min-width: 1.2rem;
    height: 1rem;
    padding: 0 0.3rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
  }
  .lock {
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    margin-right: 0.18rem;
  }
  .tabs a.active .count {
    color: #dceeff;
    border-color: rgba(255, 255, 255, 0.35);
  }

  h1 {
    margin: 0;
    font-size: 1.35rem;
    letter-spacing: 0.01em;
  }
  .subtitle {
    margin-top: 0.35rem;
    color: var(--text-muted);
    font-size: 0.88rem;
  }
  .card {
    border: 1px solid var(--border);
    background: linear-gradient(180deg, color-mix(in srgb, var(--card-bg) 90%, white), var(--card-bg));
    border-radius: var(--radius);
    padding: 0.8rem;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
  }
  .badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 54px;
    padding: 0.18rem 0.52rem;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    border: 1px solid var(--border);
    background: transparent;
  }
  .badge-allow { color: var(--green-bright); border-color: color-mix(in srgb, var(--green) 70%, var(--border)); }
  .badge-ask { color: var(--amber); border-color: color-mix(in srgb, var(--amber) 50%, var(--border)); }
  .badge-deny { color: var(--red-bright); border-color: color-mix(in srgb, var(--red) 70%, var(--border)); }
  .badge-browser { color: var(--blue-soft); border-color: color-mix(in srgb, var(--blue) 55%, var(--border)); }
  .badge-webauthn { color: var(--purple); border-color: color-mix(in srgb, var(--purple) 55%, var(--border)); }

  .btn {
    border-radius: 10px;
    border: 1px solid var(--border);
    padding: 0.43rem 0.74rem;
    font-weight: 600;
    font-size: 0.82rem;
    cursor: pointer;
    transition: all var(--transition);
    font-family: var(--font-sans);
  }
  .btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .btn-primary {
    background: var(--blue);
    border-color: color-mix(in srgb, var(--blue) 70%, #fff);
    color: #071527;
  }
  .btn-save {
    background: linear-gradient(120deg, color-mix(in srgb, var(--green) 82%, #63d67f), var(--green));
    border-color: color-mix(in srgb, var(--green) 70%, #fff);
    color: #031109;
  }
  .btn-save.success { animation: save-pop 220ms ease-out; }
  .btn-ghost { background: transparent; color: var(--text); }
  .btn-ghost:hover {
    background: rgba(88, 166, 255, 0.08);
    border-color: color-mix(in srgb, var(--blue) 40%, var(--border));
  }
  .btn-danger { background: transparent; color: var(--text-muted); }
  .btn-danger:hover {
    background: color-mix(in srgb, var(--red) 40%, transparent);
    border-color: var(--red);
    color: #fff;
  }

  @keyframes save-pop {
    from { transform: scale(0.98); }
    to { transform: scale(1); }
  }

  .status {
    margin-top: 0.62rem;
    font-size: 0.8rem;
  }
  .status.ok { color: var(--green-bright); }
  .status.error { color: var(--red-bright); }
  .errors {
    margin-top: 0.5rem;
    border: 1px solid color-mix(in srgb, var(--red) 55%, var(--border));
    background: rgba(218, 54, 51, 0.08);
    border-radius: 10px;
    padding: 0.55rem 0.65rem;
  }
  .errors div {
    font-family: var(--font-mono);
    font-size: 0.74rem;
    color: #ffd4d2;
  }

  .policy-head { margin-bottom: 0.9rem; }
  .policy-layout {
    display: grid;
    grid-template-columns: minmax(0, 1.25fr) minmax(300px, 0.75fr);
    gap: 0.95rem;
  }
  .policy-layout.collapsed { grid-template-columns: 1fr; }
  .toolbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 0.7rem;
    flex-wrap: wrap;
  }
  .control {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    color: var(--text-muted);
    font-size: 0.82rem;
    flex-wrap: wrap;
  }
  .segmented {
    display: inline-flex;
    gap: 0.28rem;
    padding: 0.22rem;
    border-radius: 12px;
    border: 1px solid var(--border);
    background: color-mix(in srgb, var(--card-bg) 85%, black);
  }
  .segmented button {
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 0.34rem 0.58rem;
    font-size: 0.75rem;
    font-weight: 650;
    letter-spacing: 0.02em;
    text-transform: lowercase;
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    transition: all var(--transition);
  }
  .segmented button:hover {
    color: var(--text);
    border-color: color-mix(in srgb, var(--blue) 35%, var(--border));
    background: rgba(88, 166, 255, 0.08);
  }
  .segmented button.active {
    color: var(--text);
    background: rgba(88, 166, 255, 0.16);
    border-color: color-mix(in srgb, var(--blue) 55%, var(--border));
  }
  .segmented button.action-allow.active {
    color: #d5ffe0;
    background: color-mix(in srgb, var(--green) 35%, transparent);
    border-color: color-mix(in srgb, var(--green) 65%, var(--border));
  }
  .segmented button.action-ask.active {
    color: #ffe9bf;
    background: color-mix(in srgb, var(--amber) 30%, transparent);
    border-color: color-mix(in srgb, var(--amber) 55%, var(--border));
  }
  .segmented button.action-deny.active {
    color: #ffd8d6;
    background: color-mix(in srgb, var(--red) 30%, transparent);
    border-color: color-mix(in srgb, var(--red) 65%, var(--border));
  }
  .segmented button.action-browser.active {
    color: #d8ebff;
    background: color-mix(in srgb, var(--blue) 30%, transparent);
    border-color: color-mix(in srgb, var(--blue) 60%, var(--border));
  }
  .segmented button.action-webauthn.active {
    color: #ecdfff;
    background: color-mix(in srgb, var(--purple) 35%, transparent);
    border-color: color-mix(in srgb, var(--purple) 60%, var(--border));
  }
  .hint {
    color: var(--text-muted);
    font-size: 0.78rem;
    margin-bottom: 0.55rem;
  }
  .rules {
    display: grid;
    gap: 0.5rem;
  }
  .rule-row {
    display: grid;
    grid-template-columns: auto 24px 1fr auto auto;
    gap: 0.7rem;
    align-items: center;
    border: 1px solid var(--border);
    background: color-mix(in srgb, var(--card-bg) 85%, black);
    border-radius: 12px;
    padding: 0.66rem 0.7rem;
    position: relative;
    transition: transform var(--transition), border-color var(--transition), background var(--transition);
  }
  .rule-row::before {
    content: "";
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 2px;
    border-top-left-radius: 12px;
    border-bottom-left-radius: 12px;
    background: var(--border);
  }
  .rule-row:hover {
    transform: translateY(-1px);
    border-color: color-mix(in srgb, var(--blue) 35%, var(--border));
    background: color-mix(in srgb, var(--card-bg) 90%, #1f2d3a);
  }
  .rule-row.action-allow::before { background: var(--green-bright); }
  .rule-row.action-ask::before { background: var(--amber); }
  .rule-row.action-deny::before { background: var(--red-bright); }
  .rule-row.action-browser::before { background: var(--blue-soft); }
  .rule-row.action-webauthn::before { background: var(--purple); }
  .rule-order {
    font-family: var(--font-mono);
    font-size: 0.7rem;
    color: var(--text-muted);
    border: 1px solid var(--border);
    border-radius: 999px;
    min-width: 1.7rem;
    height: 1.2rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  .rule-drag {
    width: 16px;
    height: 16px;
    cursor: grab;
    user-select: none;
    position: relative;
    opacity: 0.8;
  }
  .rule-drag::before {
    content: "";
    position: absolute;
    inset: 0;
    background:
      radial-gradient(circle, var(--text-muted) 1.1px, transparent 1.2px) 0 0 / 8px 8px,
      radial-gradient(circle, var(--text-muted) 1.1px, transparent 1.2px) 4px 4px / 8px 8px;
  }
  .rule-tool {
    font-family: var(--font-mono);
    font-size: 0.9rem;
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .rule-buttons { display: flex; gap: 0.3rem; }
  .rule-icon {
    border: 1px solid var(--border);
    background: transparent;
    color: var(--text-muted);
    border-radius: 999px;
    width: 1.5rem;
    height: 1.5rem;
    padding: 0;
    cursor: pointer;
    font-size: 0.76rem;
    opacity: 0.78;
    transition: all var(--transition);
  }
  .rule-icon:hover {
    color: var(--text);
    border-color: color-mix(in srgb, var(--blue) 55%, var(--border));
    opacity: 1;
  }
  .rule-icon.delete:hover {
    color: #fff;
    border-color: var(--red);
    background: color-mix(in srgb, var(--red) 50%, transparent);
  }
  .empty {
    color: var(--text-muted);
    border: 1px dashed var(--border);
    border-radius: 11px;
    padding: 1rem;
    text-align: left;
    display: grid;
    gap: 0.5rem;
  }
  .empty-title {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    color: var(--text);
    font-weight: 600;
  }
  .empty-icon {
    width: 1.2rem;
    height: 1.2rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--border);
    border-radius: 999px;
    color: var(--blue-soft);
  }

  .yaml-panel {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: linear-gradient(180deg, color-mix(in srgb, var(--card-bg) 92%, white), var(--card-bg));
    overflow: hidden;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
  }
  .yaml-head {
    padding: 0.55rem 0.7rem;
    border-bottom: 1px solid var(--border);
    font-size: 0.76rem;
    color: var(--text-muted);
    display: flex;
    align-items: center;
    justify-content: space-between;
    cursor: pointer;
    user-select: none;
  }
  .yaml-head:hover { color: var(--text); }
  .yaml-toggle {
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 0.14rem 0.45rem;
    font-size: 0.68rem;
    color: var(--text-muted);
  }
  .yaml-body {
    margin: 0;
    padding: 0.8rem;
    max-height: 72vh;
    overflow: auto;
    font-family: var(--font-mono);
    font-size: 0.77rem;
    line-height: 1.5;
    background: #0e141b;
    color: #d9e5f3;
  }
  .yaml-key { color: var(--text-muted); }
  .yaml-dash { color: var(--blue-soft); }
  .yaml-value { color: var(--text); }

  .modal-overlay {
    position: fixed;
    inset: 0;
    display: grid;
    place-items: center;
    background: rgba(6, 10, 15, 0.65);
    backdrop-filter: blur(3px);
    z-index: 40;
  }
  .modal-dialog {
    width: min(560px, calc(100vw - 2rem));
    border-radius: 16px;
    border: 1px solid var(--border);
    background: linear-gradient(180deg, color-mix(in srgb, var(--card-bg) 88%, white), var(--card-bg));
    box-shadow: 0 22px 70px rgba(0, 0, 0, 0.5);
    padding: 1.1rem 1.1rem 1rem;
    animation: dialog-pop 140ms ease-out;
  }
  @keyframes dialog-pop {
    from { opacity: 0; transform: scale(0.97); }
    to { opacity: 1; transform: scale(1); }
  }
  .modal-title { font-size: 1rem; margin: 0 0 0.9rem 0; }
  .field {
    display: grid;
    gap: 0.38rem;
    margin-bottom: 0.8rem;
  }
  .field label {
    color: var(--text-muted);
    font-size: 0.82rem;
  }
  .input, .select {
    width: 100%;
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 0.56rem 0.65rem;
    background: #0f141a;
    color: var(--text);
    font-family: var(--font-mono);
    font-size: 0.83rem;
  }
  .input:focus, .select:focus {
    outline: none;
    border-color: color-mix(in srgb, var(--blue) 82%, var(--border));
    box-shadow: 0 0 0 1px rgba(88, 166, 255, 0.52);
  }
  .regex-check {
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 0.65rem;
    background: rgba(13, 17, 23, 0.74);
  }
  .regex-label {
    color: var(--text-muted);
    font-size: 0.74rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 0.45rem;
    padding-bottom: 0.35rem;
    border-bottom: 1px solid color-mix(in srgb, var(--border) 75%, transparent);
  }
  .regex-match {
    font-size: 0.8rem;
    margin-top: 0.35rem;
  }
  .regex-match.ok { color: var(--green-bright); }
  .regex-match.bad { color: var(--red-bright); }
  .form-error {
    color: var(--red-bright);
    font-size: 0.8rem;
  }
  .modal-buttons {
    display: flex;
    justify-content: flex-end;
    gap: 0.55rem;
    margin-top: 0.9rem;
  }

  .section-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    gap: 1rem;
    margin-bottom: 0.9rem;
    flex-wrap: wrap;
  }
  .sub { margin-top: 0.32rem; color: var(--text-muted); font-size: 0.88rem; }
  .meta { color: var(--text-muted); font-size: 0.8rem; margin-bottom: 0.65rem; }

  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 0.65rem;
  }
  .credential {
    border: 1px solid var(--border);
    border-radius: 13px;
    background: linear-gradient(180deg, color-mix(in srgb, var(--card-bg) 90%, white), var(--card-bg));
    padding: 0.74rem;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
  }
  .cred-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 0.6rem;
  }
  .cred-head-left {
    display: grid;
    gap: 0.38rem;
    min-width: 0;
  }
  .topline {
    display: inline-flex;
    align-items: center;
    gap: 0.42rem;
  }
  .key-icon {
    width: 1.05rem;
    height: 1.05rem;
    border: 1px solid var(--border);
    border-radius: 999px;
    position: relative;
  }
  .key-icon::before {
    content: "";
    position: absolute;
    width: 0.26rem;
    height: 0.26rem;
    border: 1px solid var(--blue-soft);
    border-radius: 999px;
    top: 0.21rem;
    left: 0.21rem;
  }
  .key-icon::after {
    content: "";
    position: absolute;
    width: 0.35rem;
    height: 1px;
    background: var(--blue-soft);
    top: 0.54rem;
    left: 0.49rem;
    box-shadow: 0.15rem 0 0 var(--blue-soft);
  }
  .status-dot {
    width: 0.48rem;
    height: 0.48rem;
    border-radius: 999px;
    display: inline-block;
    background: var(--green-bright);
    box-shadow: 0 0 0 2px rgba(63, 185, 80, 0.18);
  }
  .cred-id {
    font-family: var(--font-mono);
    font-size: 0.79rem;
    color: var(--blue-soft);
    word-break: break-all;
  }
  .cred-meta {
    margin-top: 0.55rem;
    display: grid;
    gap: 0.3rem;
  }
  .cred-row {
    display: flex;
    justify-content: space-between;
    gap: 0.6rem;
    color: var(--text-muted);
    font-size: 0.78rem;
  }
  .cred-row span:last-child {
    color: var(--text);
    font-family: var(--font-mono);
  }
  .date { text-align: right; }
  .date .rel { color: var(--text); }
  .date .abs { font-size: 0.7rem; color: var(--text-muted); }
  .transports {
    display: inline-flex;
    gap: 0.26rem;
    flex-wrap: wrap;
    justify-content: flex-end;
  }
  .transport {
    border-radius: 999px;
    border: 1px solid var(--border);
    padding: 0.1rem 0.35rem;
    font-size: 0.68rem;
    color: var(--text-muted);
  }
  .enroll {
    color: #06170d;
    background: linear-gradient(120deg, color-mix(in srgb, var(--green) 80%, #5fdb7f), var(--green));
    border-color: color-mix(in srgb, var(--green) 65%, #fff);
  }

  .stats {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.6rem;
    margin-bottom: 0.75rem;
  }
  .stat {
    border: 1px solid var(--border);
    border-radius: 12px;
    background: linear-gradient(180deg, color-mix(in srgb, var(--card-bg) 90%, white), var(--card-bg));
    padding: 0.62rem 0.7rem;
    border-top-width: 2px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
  }
  .stat.total { border-top-color: var(--blue-soft); }
  .stat.approvals { border-top-color: var(--green-bright); }
  .stat.denials { border-top-color: var(--red-bright); }
  .stat.asks { border-top-color: var(--amber); }
  .k { color: var(--text-muted); font-size: 0.72rem; }
  .v { margin-top: 0.2rem; font-family: var(--font-mono); font-size: 1rem; }

  .filters {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr 170px;
    gap: 0.5rem;
    margin-bottom: 0.65rem;
  }
  .table-wrap {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: auto;
    background: color-mix(in srgb, var(--card-bg) 95%, black);
  }
  table {
    width: 100%;
    border-collapse: collapse;
    min-width: 1060px;
  }
  thead th {
    text-align: left;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: var(--text-muted);
    padding: 0.5rem 0.55rem;
    border-bottom: 1px solid var(--border);
  }
  tbody td {
    padding: 0.6rem 0.55rem;
    border-top: 1px solid color-mix(in srgb, var(--border) 80%, transparent);
    font-size: 0.8rem;
    vertical-align: top;
  }
  tbody td.striped { background: rgba(255, 255, 255, 0.02); }
  .tool { font-family: var(--font-mono); color: #c8ddf7; font-weight: 600; }
  .method, .action { font-family: var(--font-mono); color: var(--text-muted); }
  .time { color: var(--text); }
  .method-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 0.12rem 0.38rem;
    color: var(--text-muted);
    font-size: 0.7rem;
  }
  .method-icon {
    width: 0.72rem;
    text-align: center;
    opacity: 0.9;
  }
  .reason {
    color: var(--text-muted);
    max-width: 360px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    cursor: pointer;
  }
  .reason.expanded {
    white-space: normal;
    overflow: visible;
  }
  .pagination {
    margin-top: 0.62rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.8rem;
  }
  .page-meta { color: var(--text-muted); font-size: 0.78rem; }
  .pbtns { display: inline-flex; gap: 0.42rem; }
  .pbtns button {
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.3rem 0.55rem;
    background: transparent;
    color: var(--text);
    cursor: pointer;
    font-family: var(--font-sans);
  }

  @media (max-width: 930px) {
    .policy-layout { grid-template-columns: 1fr; }
  }
  @media (max-width: 900px) {
    .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .filters { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<div id="app"></div>
<script>
(() => {
  const ACTIONS = ["allow", "ask", "deny", "browser", "webauthn"];
  const PAGE_SIZE = 20;

  const state = {
    route: "policy",
    loadingPolicy: false,
    savingPolicy: false,
    saveSuccess: false,
    policyMessage: "",
    policyError: "",
    validationErrors: [],
    defaultAction: "allow",
    rules: [],
    yamlCollapsed: false,
    dialogOpen: false,
    editingIndex: null,
    form: {
      title: "Add Rule",
      pattern: "",
      action: "ask",
      regexInput: "",
      error: "",
    },
    draggedIndex: null,

    credentials: [],
    loadingCredentials: false,
    credentialsBusy: false,
    credentialsMessage: "",
    credentialsError: "",

    auditEntries: [],
    auditStats: { total: 0, approvals: 0, denials: 0, asks: 0, byTool: {} },
    loadingAudit: false,
    auditError: "",
    clientFilter: "all",
    agentFilter: "",
    toolFilter: "",
    decisionFilter: "all",
    page: 0,
    expandedReasons: {},
  };

  const root = document.getElementById("app");

  function esc(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function relativeTime(iso) {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return iso;
    const now = Date.now();
    const diff = now - date.getTime();
    const seconds = Math.floor(diff / 1000);
    if (seconds < 60) return "just now";
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d ago`;
    const months = Math.floor(days / 30);
    if (months < 12) return `${months}mo ago`;
    return `${Math.floor(months / 12)}y ago`;
  }

  function formatDate(iso, withSeconds = false) {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return iso;
    return new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: withSeconds ? "2-digit" : undefined,
    }).format(date);
  }

  function truncate(id) {
    if (!id || id.length <= 24) return id || "";
    return `${id.slice(0, 10)}...${id.slice(-10)}`;
  }

  function methodIcon(method) {
    switch (method) {
      case "policy": return "P";
      case "browser": return "B";
      case "webauthn": return "W";
      case "fail-open": return "!";
      default: return "?";
    }
  }

  function makeId() {
    return `rule-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  }

  async function fetchJSON(url, init) {
    const res = await fetch(url, init);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || `Request failed: ${res.status}`);
    }
    return res.json();
  }

  const api = {
    getPolicy: () => fetchJSON("/api/policy"),
    savePolicy: (config) => fetchJSON("/api/policy", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    }),
    validatePolicy: (config) => fetchJSON("/api/policy/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    }),
    getCredentials: () => fetchJSON("/api/credentials"),
    deleteCredential: (id) => fetchJSON(`/api/credentials/${encodeURIComponent(id)}`, { method: "DELETE" }),
    getEnrollOptions: () => fetchJSON("/api/enroll/options"),
    verifyEnrollment: (challengeId, response) => fetchJSON("/api/enroll/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ challengeId, response }),
    }),
    getAuditLog: (limit = 500) => fetchJSON(`/api/audit-log?limit=${limit}`),
    getAuditStats: () => fetchJSON("/api/audit-log/stats"),
  };

  function routeFromHash() {
    const route = location.hash.slice(2) || "policy";
    if (route === "policy" || route === "credentials" || route === "audit") return route;
    return "policy";
  }

  function toPolicyConfig() {
    return {
      defaultAction: state.defaultAction,
      rules: state.rules.map((rule) => ({ match: { tool: rule.match.tool }, action: rule.action })),
    };
  }

  function yamlEscape(value) {
    return JSON.stringify(String(value ?? ""));
  }

  function toYaml(config) {
    const lines = [`defaultAction: ${config.defaultAction}`, "rules:"];
    for (const rule of config.rules || []) {
      lines.push("  - match:");
      lines.push(`      tool: ${yamlEscape(rule.match?.tool ?? "")}`);
      lines.push(`    action: ${rule.action}`);
    }
    return lines.join("\\n");
  }

  function highlightYaml(yamlText) {
    return yamlText
      .split("\\n")
      .map((line) => {
        const safe = esc(line);
        const match = line.match(/^(\\s*)(-\\s*)?([^:#\\n][^:\\n]*):(.*)$/);
        if (!match) return safe;
        const indent = esc(match[1] || "");
        const dash = match[2] ? `<span class=\"yaml-dash\">${esc(match[2])}</span>` : "";
        const key = esc(match[3]);
        const value = esc(match[4] || "");
        return `${indent}${dash}<span class=\"yaml-key\">${key}:</span><span class=\"yaml-value\">${value}</span>`;
      })
      .join("\\n");
  }

  function filteredAuditEntries() {
    const client = state.clientFilter;
    const agent = state.agentFilter.trim().toLowerCase();
    const tool = state.toolFilter.trim().toLowerCase();
    const decision = state.decisionFilter;
    return state.auditEntries.filter((entry) => {
      const entryClient = (entry.agentClient || "unknown").toLowerCase();
      if (client !== "all" && entryClient !== client) return false;
      const agentId = String(entry.agentId || "unknown").toLowerCase();
      if (agent && !agentId.includes(agent)) return false;
      const toolName = String(entry.toolName || "").toLowerCase();
      if (tool && !toolName.includes(tool)) return false;
      if (decision !== "all" && entry.decision !== decision) return false;
      return true;
    });
  }

  function renderNav() {
    const links = [
      { route: "policy", label: "Policy Rules", extra: "" },
      { route: "credentials", label: "Credentials", extra: `<span class=\"count\"><span class=\"lock\">L</span>${state.credentials.length}</span>` },
      { route: "audit", label: "Audit Log", extra: `<span class=\"count\">${state.auditStats.total || 0}</span>` },
    ];
    return `
      <header>
        <div class=\"brand-tabs\">
          <div class=\"brand\">agent-2fa / dashboard</div>
          <nav class=\"tabs\">
            ${links.map((l) => `<a href=\"#/${l.route}\" class=\"${state.route === l.route ? "active" : ""}\">${l.label}${l.extra}</a>`).join("")}
          </nav>
        </div>
      </header>
    `;
  }

  function renderPolicy() {
    const yaml = toYaml(toPolicyConfig());
    const regex = testRegex(state.form.pattern, state.form.regexInput);

    return `
      <section>
        <div class=\"policy-head\">
          <h1>Policy Rules</h1>
          <div class=\"subtitle\">Define match rules in order. First matching rule wins.</div>
        </div>
        <div class=\"policy-layout ${state.yamlCollapsed ? "collapsed" : ""}\">
          <div class=\"card\">
            <div class=\"toolbar\">
              <div class=\"control\">
                <span>Default Action</span>
                <div class=\"segmented\" role=\"radiogroup\" aria-label=\"Default action\">
                  ${ACTIONS.map((action) => `<button type=\"button\" data-action=\"pick-default\" data-value=\"${action}\" class=\"action-${action} ${state.defaultAction === action ? "active" : ""}\">${action}</button>`).join("")}
                </div>
              </div>
              <div class=\"control\">
                ${state.yamlCollapsed ? '<button type="button" class="btn btn-ghost" data-action="expand-yaml">Show YAML</button>' : ""}
                <button type=\"button\" class=\"btn btn-primary\" data-action=\"add-rule\">Add Rule</button>
                <button type=\"button\" class=\"btn btn-save ${state.saveSuccess ? "success" : ""}\" data-action=\"save-policy\" ${state.savingPolicy ? "disabled" : ""}>${state.savingPolicy ? "Saving..." : state.saveSuccess ? "✓ Saved" : "Save Policy"}</button>
              </div>
            </div>
            <div class=\"hint\">Drag rows by handle to reorder rules.</div>
            <div class=\"rules\">
              ${state.rules.length === 0 ? `
                <div class=\"empty\">
                  <div class=\"empty-title\"><span class=\"empty-icon\">+</span><span>No rules configured yet</span></div>
                  <div>Create your first match rule to control tool access order.</div>
                  <div><button type=\"button\" class=\"btn btn-primary\" data-action=\"add-rule\">Add Rule</button></div>
                </div>
              ` : state.rules.map((rule, index) => `
                <div class=\"rule-row action-${esc(rule.action)}\" draggable=\"true\" data-index=\"${index}\">
                  <div class=\"rule-order\">#${index + 1}</div>
                  <div class=\"rule-drag\" aria-hidden=\"true\"></div>
                  <div class=\"rule-tool\" title=\"${esc(rule.match.tool)}\">${esc(rule.match.tool)}</div>
                  <span class=\"badge badge-${esc(rule.action)}\">${esc(rule.action)}</span>
                  <div class=\"rule-buttons\">
                    <button type=\"button\" class=\"rule-icon\" data-action=\"edit-rule\" data-index=\"${index}\" title=\"Edit rule\" aria-label=\"Edit rule\">✎</button>
                    <button type=\"button\" class=\"rule-icon delete\" data-action=\"delete-rule\" data-index=\"${index}\" title=\"Delete rule\" aria-label=\"Delete rule\">×</button>
                  </div>
                </div>
              `).join("")}
            </div>
            ${state.policyMessage ? `<div class=\"status ok\">${esc(state.policyMessage)}</div>` : ""}
            ${state.policyError ? `<div class=\"status error\">${esc(state.policyError)}</div>` : ""}
            ${state.validationErrors.length ? `<div class=\"errors\">${state.validationErrors.map((e) => `<div>${esc(e)}</div>`).join("")}</div>` : ""}
          </div>
          ${state.yamlCollapsed ? "" : `
            <aside class=\"yaml-panel\">
              <div class=\"yaml-head\" data-action=\"toggle-yaml\">
                <span>Live YAML Preview</span>
                <span class=\"yaml-toggle\">Collapse</span>
              </div>
              <pre class=\"yaml-body\">${highlightYaml(yaml)}</pre>
            </aside>
          `}
        </div>
        ${state.dialogOpen ? `
          <div class=\"modal-overlay\" data-action=\"close-dialog\">
            <div class=\"modal-dialog\" data-stop-click=\"true\">
              <h3 class=\"modal-title\">${esc(state.form.title)}</h3>
              <form data-action=\"save-rule-form\">
                <div class=\"field\">
                  <label>Tool Pattern (regex)</label>
                  <input class=\"input\" id=\"rule-pattern\" value=\"${esc(state.form.pattern)}\" data-action=\"form-pattern\" placeholder=\"Bash|Edit|Write\"/>
                </div>
                <div class=\"field\">
                  <label>Action</label>
                  <select class=\"select\" id=\"rule-action\" data-action=\"form-action\">
                    ${ACTIONS.map((a) => `<option value=\"${a}\" ${state.form.action === a ? "selected" : ""}>${a}</option>`).join("")}
                  </select>
                </div>
                <div class=\"field\">
                  <label>Regex Tester (tool name)</label>
                  <div class=\"regex-check\">
                    <div class=\"regex-label\">Match Preview</div>
                    <input class=\"input\" value=\"${esc(state.form.regexInput)}\" data-action=\"form-regex-input\" placeholder=\"Try: Bash or Read\"/>
                    <div class=\"regex-match ${regex.ok ? "ok" : "bad"}\">${esc(regex.message)}</div>
                  </div>
                </div>
                ${state.form.error ? `<div class=\"form-error\">${esc(state.form.error)}</div>` : ""}
                <div class=\"modal-buttons\">
                  <button type=\"button\" class=\"btn btn-ghost\" data-action=\"close-dialog\">Cancel</button>
                  <button type=\"submit\" class=\"btn btn-primary\">Save Rule</button>
                </div>
              </form>
            </div>
          </div>
        ` : ""}
      </section>
    `;
  }

  function renderCredentials() {
    return `
      <section>
        <div class=\"section-head\">
          <div>
            <h1>Credentials</h1>
            <div class=\"sub\">Manage enrolled passkeys for tool-call approvals.</div>
          </div>
          <div>
            <button type=\"button\" class=\"btn btn-ghost\" data-action=\"refresh-credentials\" ${state.loadingCredentials || state.credentialsBusy ? "disabled" : ""}>Refresh</button>
            <button type=\"button\" class=\"btn enroll\" data-action=\"enroll\" ${state.credentialsBusy ? "disabled" : ""}>${state.credentialsBusy ? "Working..." : "Enroll Passkey"}</button>
          </div>
        </div>
        <div class=\"meta\">${state.credentials.length} credential(s)</div>
        ${state.credentialsMessage ? `<div class=\"status ok\">${esc(state.credentialsMessage)}</div>` : ""}
        ${state.credentialsError ? `<div class=\"status error\">${esc(state.credentialsError)}</div>` : ""}
        ${state.credentials.length === 0 ? `
          <div class=\"empty\">
            <div class=\"empty-title\"><span class=\"empty-icon\">K</span><span>No passkeys enrolled yet</span></div>
            <div>Enroll a credential to require biometric approval for protected actions.</div>
            <div><button type=\"button\" class=\"btn enroll\" data-action=\"enroll\" ${state.credentialsBusy ? "disabled" : ""}>${state.credentialsBusy ? "Working..." : "Enroll Passkey"}</button></div>
          </div>
        ` : `
          <div class=\"cards\">
            ${state.credentials.map((cred) => `
              <article class=\"credential\">
                <div class=\"cred-head\">
                  <div class=\"cred-head-left\">
                    <div class=\"topline\"><span class=\"key-icon\"></span><span class=\"status-dot\" title=\"Active credential\"></span></div>
                    <div class=\"cred-id\" title=\"${esc(cred.credentialID)}\">${esc(truncate(cred.credentialID))}</div>
                  </div>
                  <button type=\"button\" class=\"btn btn-danger\" data-action=\"delete-credential\" data-id=\"${esc(cred.credentialID)}\">Delete</button>
                </div>
                <div class=\"cred-meta\">
                  <div class=\"cred-row\"><span>Counter</span><span>${Number(cred.counter || 0)}</span></div>
                  <div class=\"cred-row\"><span>Created</span><span class=\"date\" title=\"${esc(formatDate(cred.createdAt))}\"><div class=\"rel\">enrolled ${esc(relativeTime(cred.createdAt))}</div><div class=\"abs\">${esc(formatDate(cred.createdAt))}</div></span></div>
                  <div class=\"cred-row\"><span>Transports</span><span class=\"transports\">${(cred.transports || []).length ? cred.transports.map((t) => `<span class=\"transport\">${esc(t)}</span>`).join("") : '<span class="transport">-</span>'}</span></div>
                </div>
              </article>
            `).join("")}
          </div>
        `}
      </section>
    `;
  }

  function renderAudit() {
    const filtered = filteredAuditEntries();
    const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
    const safePage = Math.min(state.page, pageCount - 1);
    const start = safePage * PAGE_SIZE;
    const visible = filtered.slice(start, start + PAGE_SIZE);

    return `
      <section>
        <div class=\"section-head\">
          <div>
            <h1>Audit Log</h1>
            <div class=\"sub\">Review approval decisions by tool, action, and method.</div>
          </div>
          <button type=\"button\" class=\"btn btn-ghost\" data-action=\"refresh-audit\" ${state.loadingAudit ? "disabled" : ""}>${state.loadingAudit ? "Refreshing..." : "Refresh"}</button>
        </div>

        <div class=\"stats\">
          <div class=\"stat total\"><div class=\"k\">Total</div><div class=\"v\">${Number(state.auditStats.total || 0)}</div></div>
          <div class=\"stat approvals\"><div class=\"k\">Approvals</div><div class=\"v\">${Number(state.auditStats.approvals || 0)}</div></div>
          <div class=\"stat denials\"><div class=\"k\">Denials</div><div class=\"v\">${Number(state.auditStats.denials || 0)}</div></div>
          <div class=\"stat asks\"><div class=\"k\">Asks</div><div class=\"v\">${Number(state.auditStats.asks || 0)}</div></div>
        </div>

        <div class=\"filters\">
          <select class=\"select\" data-action=\"filter-client\">
            <option value=\"all\" ${state.clientFilter === "all" ? "selected" : ""}>All clients</option>
            <option value=\"claude-code\" ${state.clientFilter === "claude-code" ? "selected" : ""}>claude-code</option>
            <option value=\"codex\" ${state.clientFilter === "codex" ? "selected" : ""}>codex</option>
            <option value=\"openclaw\" ${state.clientFilter === "openclaw" ? "selected" : ""}>openclaw</option>
            <option value=\"unknown\" ${state.clientFilter === "unknown" ? "selected" : ""}>unknown</option>
          </select>
          <input class=\"input\" data-action=\"filter-agent\" value=\"${esc(state.agentFilter)}\" placeholder=\"Filter by agent id\"/>
          <input class=\"input\" data-action=\"filter-tool\" value=\"${esc(state.toolFilter)}\" placeholder=\"Filter by tool name\"/>
          <select class=\"select\" data-action=\"filter-decision\">
            <option value=\"all\" ${state.decisionFilter === "all" ? "selected" : ""}>All decisions</option>
            <option value=\"allow\" ${state.decisionFilter === "allow" ? "selected" : ""}>allow</option>
            <option value=\"ask\" ${state.decisionFilter === "ask" ? "selected" : ""}>ask</option>
            <option value=\"deny\" ${state.decisionFilter === "deny" ? "selected" : ""}>deny</option>
          </select>
        </div>

        ${state.auditError ? `<div class=\"status error\">${esc(state.auditError)}</div>` : ""}

        ${visible.length === 0 ? `<div class=\"empty\">No log entries match these filters.</div>` : `
          <div class=\"table-wrap\">
            <table>
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Client</th>
                  <th>Agent</th>
                  <th>Tool</th>
                  <th>Action</th>
                  <th>Decision</th>
                  <th>Method</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                ${visible.map((entry, index) => {
                  const striped = index % 2 === 1 ? "striped" : "";
                  const id = entry.id || `${entry.timestamp}-${entry.toolName}-${index}`;
                  const expanded = !!state.expandedReasons[id];
                  return `
                    <tr>
                      <td class=\"time ${striped}\" title=\"${esc(formatDate(entry.timestamp, true))}\">${esc(relativeTime(entry.timestamp))}</td>
                      <td class=\"method ${striped}\">${esc(entry.agentClient || "unknown")}</td>
                      <td class=\"method ${striped}\">${esc(entry.agentId || "unknown")}</td>
                      <td class=\"tool ${striped}\">${esc(entry.toolName)}</td>
                      <td class=\"action ${striped}\">${esc(entry.action)}</td>
                      <td class=\"${striped}\"><span class=\"badge badge-${esc(entry.decision)}\">${esc(entry.decision)}</span></td>
                      <td class=\"method ${striped}\"><span class=\"method-badge\"><span class=\"method-icon\">${esc(methodIcon(entry.method))}</span><span>${esc(entry.method)}</span></span></td>
                      <td class=\"reason ${striped} ${expanded ? "expanded" : ""}\" data-action=\"toggle-reason\" data-id=\"${esc(id)}\" title=\"${esc(entry.reason)}\">${esc(entry.reason)}</td>
                    </tr>
                  `;
                }).join("")}
              </tbody>
            </table>
          </div>
          <div class=\"pagination\">
            <div class=\"page-meta\">Showing ${visible.length} of ${filtered.length} filtered entries</div>
            <div class=\"pbtns\">
              <button type=\"button\" data-action=\"prev-page\" ${safePage <= 0 ? "disabled" : ""}>Prev</button>
              <button type=\"button\" data-action=\"next-page\" ${safePage >= pageCount - 1 ? "disabled" : ""}>Next</button>
            </div>
          </div>
        `}
      </section>
    `;
  }

  function renderPage() {
    if (state.route === "credentials") return renderCredentials();
    if (state.route === "audit") return renderAudit();
    return renderPolicy();
  }

  function render() {
    root.innerHTML = `
      <div class=\"wrap\">
        ${renderNav()}
        <main>${renderPage()}</main>
      </div>
    `;
  }

  function testRegex(pattern, input) {
    const trimmed = String(pattern || "").trim();
    if (!trimmed) {
      return { validRegex: true, ok: false, message: "Enter a pattern to test." };
    }
    try {
      const regex = new RegExp(`^(?:${trimmed})$`);
      if (!input) {
        return { validRegex: true, ok: false, message: "Type a tool name to preview match behavior." };
      }
      const matched = regex.test(input);
      return {
        validRegex: true,
        ok: matched,
        message: matched ? "Matches this tool name." : "Does not match this tool name.",
      };
    } catch {
      return { validRegex: false, ok: false, message: "Pattern is not valid regex." };
    }
  }

  async function loadPolicy() {
    state.loadingPolicy = true;
    state.policyError = "";
    state.policyMessage = "";
    state.validationErrors = [];
    render();
    try {
      const config = await api.getPolicy();
      state.defaultAction = ACTIONS.includes(config.defaultAction) ? config.defaultAction : "allow";
      state.rules = (config.rules || []).map((rule) => ({
        id: makeId(),
        match: { tool: String(rule.match?.tool || "") },
        action: ACTIONS.includes(rule.action) ? rule.action : "ask",
      }));
    } catch (err) {
      state.policyError = `Failed to load policy: ${String(err)}`;
    } finally {
      state.loadingPolicy = false;
      render();
    }
  }

  async function savePolicy() {
    state.savingPolicy = true;
    state.policyMessage = "";
    state.policyError = "";
    state.validationErrors = [];
    render();

    const config = toPolicyConfig();
    try {
      const validation = await api.validatePolicy(config);
      if (!validation.valid) {
        state.validationErrors = (validation.errors || []).map((item) => {
          if (typeof item === "string") return item;
          const path = Array.isArray(item.path) ? `${item.path.join(".")}: ` : "";
          return `${path}${item.message || "Invalid value"}`;
        });
        state.policyError = "Policy validation failed.";
        return;
      }

      await api.savePolicy(config);
      state.policyMessage = "Policy saved.";
      state.saveSuccess = true;
      setTimeout(() => {
        state.saveSuccess = false;
        render();
      }, 1100);
      await loadPolicy();
    } catch (err) {
      state.policyError = `Failed to save policy: ${String(err)}`;
    } finally {
      state.savingPolicy = false;
      render();
    }
  }

  function openRuleForm(index = null) {
    state.editingIndex = index;
    const existing = index === null ? null : state.rules[index];
    state.form.title = index === null ? "Add Rule" : "Edit Rule";
    state.form.pattern = existing ? existing.match.tool : "";
    state.form.action = existing ? existing.action : "ask";
    state.form.regexInput = "";
    state.form.error = "";
    state.dialogOpen = true;
    render();
  }

  function closeRuleForm() {
    state.dialogOpen = false;
    state.editingIndex = null;
    state.form.error = "";
    render();
  }

  function saveRuleForm() {
    const pattern = state.form.pattern.trim();
    if (!pattern) {
      state.form.error = "Tool pattern is required.";
      render();
      return;
    }
    const test = testRegex(pattern, state.form.regexInput);
    if (!test.validRegex) {
      state.form.error = "Invalid regex pattern.";
      render();
      return;
    }

    const incoming = { id: makeId(), match: { tool: pattern }, action: state.form.action };
    if (state.editingIndex === null) {
      state.rules = [...state.rules, incoming];
    } else {
      const existingId = state.rules[state.editingIndex]?.id || incoming.id;
      state.rules = state.rules.map((rule, idx) =>
        idx === state.editingIndex ? { ...incoming, id: existingId } : rule
      );
    }

    state.dialogOpen = false;
    state.editingIndex = null;
    state.policyMessage = "";
    state.policyError = "";
    render();
  }

  function deleteRule(index) {
    state.rules = state.rules.filter((_, idx) => idx !== index);
    state.policyMessage = "";
    state.policyError = "";
    render();
  }

  function reorderRules(from, to) {
    if (from === to || from < 0 || to < 0) return;
    const next = [...state.rules];
    const moved = next.splice(from, 1)[0];
    if (!moved) return;
    next.splice(to, 0, moved);
    state.rules = next;
    render();
  }

  async function loadCredentials() {
    state.loadingCredentials = true;
    state.credentialsError = "";
    state.credentialsMessage = "";
    render();
    try {
      state.credentials = await api.getCredentials();
    } catch (err) {
      state.credentialsError = `Failed to load credentials: ${String(err)}`;
    } finally {
      state.loadingCredentials = false;
      render();
    }
  }

  async function deleteCredential(id) {
    if (!window.confirm("Delete this credential?")) return;
    state.credentialsBusy = true;
    state.credentialsError = "";
    state.credentialsMessage = "";
    render();
    try {
      await api.deleteCredential(id);
      state.credentialsMessage = "Credential deleted.";
      await loadCredentials();
      await refreshCounts();
    } catch (err) {
      state.credentialsError = `Failed to delete credential: ${String(err)}`;
    } finally {
      state.credentialsBusy = false;
      render();
    }
  }

  function fromBase64Url(input) {
    const base64 = input.replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64 + "===".slice((base64.length + 3) % 4);
    const binary = atob(padded);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
  }

  function toBase64Url(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (const byte of bytes) {
      binary += String.fromCharCode(byte);
    }
    return btoa(binary).replace(/\\+/g, "-").replace(/\\//g, "_").replace(/=+$/, "");
  }

  function formatEnrollmentError(err) {
    if (err instanceof DOMException && (err.name === "AbortError" || err.name === "NotAllowedError")) {
      return "Enrollment was cancelled or timed out.";
    }
    if (err instanceof DOMException && err.name === "InvalidStateError") {
      return "This authenticator is already registered.";
    }
    if (err instanceof DOMException && err.name === "SecurityError") {
      return "Invalid origin. Open dashboard on http://localhost and retry.";
    }
    if (err instanceof DOMException && err.name === "NotSupportedError") {
      return "No supported platform authenticator is available.";
    }
    if (err instanceof Error) return err.message;
    return String(err);
  }

  async function enrollPasskey() {
    state.credentialsBusy = true;
    state.credentialsError = "";
    state.credentialsMessage = "";
    render();

    try {
      if (window.location.hostname !== "localhost") {
        throw new Error("Open the dashboard on http://localhost (not 127.0.0.1) for passkey enrollment.");
      }
      if (!("credentials" in navigator) || !window.PublicKeyCredential) {
        throw new Error("WebAuthn is not supported in this browser.");
      }

      const options = await api.getEnrollOptions();
      if (!options.challengeId || typeof options.challengeId !== "string") {
        throw new Error("Missing enrollment challenge id.");
      }

      const challengeId = options.challengeId;
      const publicKey = structuredClone(options);
      publicKey.challenge = fromBase64Url(publicKey.challenge);
      if (publicKey.user && publicKey.user.id) {
        publicKey.user.id = fromBase64Url(publicKey.user.id);
      }
      if (Array.isArray(publicKey.excludeCredentials)) {
        publicKey.excludeCredentials = publicKey.excludeCredentials.map((item) => ({
          ...item,
          id: fromBase64Url(String(item.id || "")),
        }));
      }
      if (publicKey.authenticatorSelection && typeof publicKey.authenticatorSelection === "object") {
        for (const key of Object.keys(publicKey.authenticatorSelection)) {
          if (publicKey.authenticatorSelection[key] == null) {
            delete publicKey.authenticatorSelection[key];
          }
        }
        if (Object.keys(publicKey.authenticatorSelection).length === 0) {
          delete publicKey.authenticatorSelection;
        }
      }
      if (publicKey.attestation == null) {
        delete publicKey.attestation;
      }
      delete publicKey.challengeId;

      const credential = await navigator.credentials.create({ publicKey });
      if (!credential) {
        throw new Error("Passkey enrollment was cancelled.");
      }

      const response = credential.response;
      const registrationResponse = {
        id: credential.id,
        rawId: toBase64Url(credential.rawId),
        type: credential.type,
        response: {
          attestationObject: toBase64Url(response.attestationObject),
          clientDataJSON: toBase64Url(response.clientDataJSON),
          transports: response.getTransports ? response.getTransports() : [],
        },
        clientExtensionResults: credential.getClientExtensionResults(),
        authenticatorAttachment: credential.authenticatorAttachment,
      };

      await api.verifyEnrollment(challengeId, registrationResponse);
      state.credentialsMessage = "Passkey enrolled.";
      await loadCredentials();
      await refreshCounts();
    } catch (err) {
      state.credentialsError = `Enrollment failed: ${formatEnrollmentError(err)}`;
    } finally {
      state.credentialsBusy = false;
      render();
    }
  }

  async function loadAudit() {
    state.loadingAudit = true;
    state.auditError = "";
    render();
    try {
      const [entries, stats] = await Promise.all([api.getAuditLog(500), api.getAuditStats()]);
      state.auditEntries = Array.isArray(entries) ? entries : [];
      state.auditStats = stats || { total: 0, approvals: 0, denials: 0, asks: 0, byTool: {} };
      state.page = 0;
    } catch (err) {
      state.auditError = `Failed to load audit data: ${String(err)}`;
    } finally {
      state.loadingAudit = false;
      render();
    }
  }

  async function refreshCounts() {
    try {
      const [stats, credentials] = await Promise.all([api.getAuditStats(), api.getCredentials()]);
      state.auditStats = stats || state.auditStats;
      state.credentials = Array.isArray(credentials) ? credentials : [];
    } catch {
      // Keep nav resilient if one endpoint fails.
    }
    render();
  }

  function onClick(event) {
    const stop = event.target.closest("[data-stop-click='true']");
    if (stop) return;

    const actionTarget = event.target.closest("[data-action]");
    if (!actionTarget) return;
    const action = actionTarget.getAttribute("data-action");

    if (action === "toggle-yaml") {
      state.yamlCollapsed = !state.yamlCollapsed;
      render();
      return;
    }
    if (action === "expand-yaml") {
      state.yamlCollapsed = false;
      render();
      return;
    }
    if (action === "pick-default") {
      const value = actionTarget.getAttribute("data-value");
      if (ACTIONS.includes(value)) {
        state.defaultAction = value;
        state.policyMessage = "";
        state.policyError = "";
      }
      render();
      return;
    }
    if (action === "add-rule") {
      openRuleForm(null);
      return;
    }
    if (action === "edit-rule") {
      openRuleForm(Number(actionTarget.getAttribute("data-index")));
      return;
    }
    if (action === "delete-rule") {
      deleteRule(Number(actionTarget.getAttribute("data-index")));
      return;
    }
    if (action === "close-dialog") {
      closeRuleForm();
      return;
    }
    if (action === "save-policy") {
      void savePolicy();
      return;
    }
    if (action === "refresh-credentials") {
      void loadCredentials();
      return;
    }
    if (action === "enroll") {
      void enrollPasskey();
      return;
    }
    if (action === "delete-credential") {
      void deleteCredential(actionTarget.getAttribute("data-id") || "");
      return;
    }
    if (action === "refresh-audit") {
      void loadAudit();
      return;
    }
    if (action === "filter-client") {
      state.clientFilter = actionTarget.value;
      state.page = 0;
      render();
      return;
    }
    if (action === "filter-agent") {
      state.agentFilter = actionTarget.value;
      state.page = 0;
      render();
      return;
    }
    if (action === "filter-tool") {
      state.toolFilter = actionTarget.value;
      state.page = 0;
      render();
      return;
    }
    if (action === "filter-decision") {
      state.decisionFilter = actionTarget.value;
      state.page = 0;
      render();
      return;
    }
    if (action === "prev-page") {
      state.page = Math.max(0, state.page - 1);
      render();
      return;
    }
    if (action === "next-page") {
      const maxPage = Math.max(0, Math.ceil(filteredAuditEntries().length / PAGE_SIZE) - 1);
      state.page = Math.min(maxPage, state.page + 1);
      render();
      return;
    }
    if (action === "toggle-reason") {
      const id = actionTarget.getAttribute("data-id");
      state.expandedReasons[id] = !state.expandedReasons[id];
      render();
      return;
    }
  }

  function onInput(event) {
    const target = event.target;
    const action = target.getAttribute("data-action");
    if (action === "form-pattern") {
      state.form.pattern = target.value;
      state.form.error = "";
      render();
    } else if (action === "form-regex-input") {
      state.form.regexInput = target.value;
      render();
    } else if (action === "filter-agent") {
      state.agentFilter = target.value;
      state.page = 0;
      render();
    } else if (action === "filter-tool") {
      state.toolFilter = target.value;
      state.page = 0;
      render();
    }
  }

  function onChange(event) {
    const target = event.target;
    const action = target.getAttribute("data-action");
    if (action === "form-action") {
      const val = target.value;
      state.form.action = ACTIONS.includes(val) ? val : "ask";
      render();
    } else if (action === "filter-client") {
      state.clientFilter = target.value;
      state.page = 0;
      render();
    } else if (action === "filter-decision") {
      state.decisionFilter = target.value;
      state.page = 0;
      render();
    }
  }

  function onSubmit(event) {
    const form = event.target.closest("form[data-action='save-rule-form']");
    if (!form) return;
    event.preventDefault();
    saveRuleForm();
  }

  function onDragStart(event) {
    const row = event.target.closest(".rule-row");
    if (!row) return;
    state.draggedIndex = Number(row.getAttribute("data-index"));
  }

  function onDragEnd() {
    state.draggedIndex = null;
  }

  function onDrop(event) {
    const row = event.target.closest(".rule-row");
    if (!row) return;
    event.preventDefault();
    const to = Number(row.getAttribute("data-index"));
    if (state.draggedIndex !== null) reorderRules(state.draggedIndex, to);
    state.draggedIndex = null;
  }

  function onDragOver(event) {
    const row = event.target.closest(".rule-row");
    if (!row) return;
    event.preventDefault();
  }

  async function onRouteChange() {
    state.route = routeFromHash();
    render();
    if (state.route === "credentials") {
      await loadCredentials();
    } else if (state.route === "audit") {
      await loadAudit();
    }
  }

  root.addEventListener("click", onClick);
  root.addEventListener("input", onInput);
  root.addEventListener("change", onChange);
  root.addEventListener("submit", onSubmit);
  root.addEventListener("dragstart", onDragStart);
  root.addEventListener("dragend", onDragEnd);
  root.addEventListener("drop", onDrop);
  root.addEventListener("dragover", onDragOver);
  window.addEventListener("hashchange", () => { void onRouteChange(); });

  async function bootstrap() {
    state.route = routeFromHash();
    render();
    await Promise.all([loadPolicy(), refreshCounts()]);
    if (state.route === "credentials") {
      await loadCredentials();
    } else if (state.route === "audit") {
      await loadAudit();
    }
    render();
  }

  void bootstrap();
})();
</script>
</body>
</html>"""

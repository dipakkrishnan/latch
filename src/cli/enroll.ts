import Fastify from "fastify";
import open from "open";
import { nanoid } from "nanoid";
import {
  generateRegistrationOptions,
  verifyRegistrationResponse,
} from "@simplewebauthn/server";
import { saveCredential, loadCredentials } from "../auth/credential-store.js";

const RP_ID = "localhost";
const RP_NAME = "agent-2fa";

async function main() {
  const app = Fastify({ logger: false });
  const userId = nanoid();

  let challenge: string | undefined;

  app.get("/enroll", async (_req, reply) => {
    return reply.type("text/html").send(ENROLL_HTML);
  });

  app.get("/enroll/options", async (_req, reply) => {
    const existing = loadCredentials();
    const opts = await generateRegistrationOptions({
      rpName: RP_NAME,
      rpID: RP_ID,
      userName: "agent-2fa-user",
      attestationType: "none",
      excludeCredentials: existing.map((c) => ({
        id: c.credentialID,
        type: "public-key" as const,
      })),
      authenticatorSelection: {
        residentKey: "preferred",
        userVerification: "required",
        authenticatorAttachment: "platform",
      },
    });
    challenge = opts.challenge;
    return reply.send(opts);
  });

  app.post("/enroll/verify", async (req, reply) => {
    if (!challenge) {
      return reply.status(400).send({ error: "No challenge" });
    }

    const body = req.body as any;

    try {
      const verification = await verifyRegistrationResponse({
        response: body,
        expectedChallenge: challenge,
        expectedOrigin: `http://${RP_ID}:${serverPort}`,
        expectedRPID: RP_ID,
      });

      if (!verification.verified || !verification.registrationInfo) {
        return reply.status(400).send({ error: "Verification failed" });
      }

      const { credential } = verification.registrationInfo;

      saveCredential({
        credentialID: credential.id,
        publicKey: Buffer.from(credential.publicKey).toString("base64"),
        counter: credential.counter,
        transports: body.response?.transports,
        createdAt: new Date().toISOString(),
      });

      process.stderr.write("Passkey enrolled successfully!\n");
      await reply.send({ ok: true });

      // Give browser time to show success, then shut down
      setTimeout(async () => {
        await app.close();
        process.exit(0);
      }, 1000);
    } catch (err) {
      return reply.status(400).send({ error: `${err}` });
    }
  });

  const address = await app.listen({ port: 0, host: "127.0.0.1" });
  const serverPort = (app.server.address() as { port: number }).port;

  const url = `http://127.0.0.1:${serverPort}/enroll`;
  process.stderr.write(`Opening enrollment page: ${url}\n`);
  await open(url);
}

const ENROLL_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>agent-2fa — Enroll Passkey</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0d1117;
    color: #e6edf3;
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    padding: 2rem;
  }
  .card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 2rem;
    max-width: 450px;
    width: 100%;
    text-align: center;
  }
  h1 { font-size: 1.4rem; margin-bottom: 1rem; }
  p { color: #8b949e; margin-bottom: 1.5rem; line-height: 1.5; }
  button {
    padding: 0.75rem 2rem;
    border: none;
    border-radius: 8px;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    background: #238636;
    color: #fff;
    transition: opacity 0.15s;
  }
  button:hover { opacity: 0.85; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
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
      statusEl.textContent = "Getting options…";

      const optRes = await fetch("/enroll/options");
      const options = await optRes.json();

      // Convert challenge
      options.challenge = base64urlToBuffer(options.challenge);
      options.user.id = base64urlToBuffer(options.user.id);
      if (options.excludeCredentials) {
        options.excludeCredentials = options.excludeCredentials.map(c => ({
          ...c,
          id: base64urlToBuffer(c.id),
        }));
      }

      statusEl.textContent = "Touch your sensor…";
      const credential = await navigator.credentials.create({ publicKey: options });

      // Convert to JSON
      const regResponse = {
        id: credential.id,
        rawId: bufferToBase64url(credential.rawId),
        type: credential.type,
        response: {
          attestationObject: bufferToBase64url(credential.response.attestationObject),
          clientDataJSON: bufferToBase64url(credential.response.clientDataJSON),
          transports: credential.response.getTransports ? credential.response.getTransports() : [],
        },
        clientExtensionResults: credential.getClientExtensionResults(),
        authenticatorAttachment: credential.authenticatorAttachment,
      };

      statusEl.textContent = "Verifying…";
      const verifyRes = await fetch("/enroll/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(regResponse),
      });

      if (verifyRes.ok) {
        statusEl.textContent = "Passkey enrolled! You can close this tab.";
        statusEl.style.color = "#3fb950";
      } else {
        const err = await verifyRes.json().catch(() => ({}));
        throw new Error(err.error || "Verification failed");
      }
    } catch (err) {
      statusEl.textContent = "Error: " + err.message;
      statusEl.style.color = "#f85149";
      btn.disabled = false;
    }
  });

  function base64urlToBuffer(base64url) {
    const base64 = base64url.replace(/-/g, "+").replace(/_/g, "/");
    const pad = base64.length % 4;
    const padded = pad ? base64 + "=".repeat(4 - pad) : base64;
    const binary = atob(padded);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes.buffer;
  }

  function bufferToBase64url(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (const b of bytes) binary += String.fromCharCode(b);
    return btoa(binary).replace(/\\+/g, "-").replace(/\\//g, "_").replace(/=+$/, "");
  }
</script>
</body>
</html>`;

main().catch((err) => {
  process.stderr.write(`Enrollment error: ${err}\n`);
  process.exit(1);
});

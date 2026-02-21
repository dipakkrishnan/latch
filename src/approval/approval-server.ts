import Fastify from "fastify";
import fastifyStatic from "@fastify/static";
import path from "node:path";
import { fileURLToPath } from "node:url";
import open from "open";
import { nanoid } from "nanoid";
import {
  generateAuthenticationOptions,
  verifyAuthenticationResponse,
} from "@simplewebauthn/server";
import {
  loadCredentials,
  updateCredentialCounter,
} from "../auth/credential-store.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const UI_DIR = path.resolve(__dirname, "../ui");

interface PendingApproval {
  id: string;
  toolName: string;
  toolInput: Record<string, unknown>;
  requireWebAuthn: boolean;
  challenge?: string;
  resolve: (approved: boolean) => void;
}

const RP_ID = "localhost";
const RP_NAME = "agent-2fa";

/**
 * Start a temporary Fastify server, open the browser, and block until
 * the user approves or denies the tool call.
 */
export async function startApprovalFlow(
  toolName: string,
  toolInput: Record<string, unknown>,
  requireWebAuthn: boolean,
): Promise<boolean> {
  const approvalId = nanoid();

  return new Promise<boolean>(async (resolveApproval) => {
    const pending: PendingApproval = {
      id: approvalId,
      toolName,
      toolInput,
      requireWebAuthn,
      resolve: resolveApproval,
    };

    const app = Fastify({ logger: false });

    // Serve static UI files
    await app.register(fastifyStatic, {
      root: UI_DIR,
      prefix: "/static/",
    });

    // GET /approval/:id — serve the approval page
    app.get<{ Params: { id: string } }>("/approval/:id", async (req, reply) => {
      if (req.params.id !== pending.id) {
        return reply.status(404).send("Not found");
      }
      return reply.type("text/html").send(buildApprovalPage(pending));
    });

    // GET /approval/:id/info — return tool info as JSON
    app.get<{ Params: { id: string } }>("/approval/:id/info", async (req, reply) => {
      if (req.params.id !== pending.id) {
        return reply.status(404).send("Not found");
      }
      return reply.send({
        toolName: pending.toolName,
        toolInput: pending.toolInput,
        requireWebAuthn: pending.requireWebAuthn,
      });
    });

    // GET /approval/:id/webauthn-options — generate WebAuthn authentication options
    app.get<{ Params: { id: string } }>("/approval/:id/webauthn-options", async (req, reply) => {
      if (req.params.id !== pending.id) {
        return reply.status(404).send("Not found");
      }

      const credentials = loadCredentials();
      if (credentials.length === 0) {
        return reply.status(400).send({ error: "No credentials enrolled. Run: npx tsx src/cli/enroll.ts" });
      }

      const options = await generateAuthenticationOptions({
        rpID: RP_ID,
        allowCredentials: credentials.map((c) => ({
          id: c.credentialID,
          type: "public-key" as const,
        })),
        userVerification: "required",
      });

      pending.challenge = options.challenge;
      return reply.send(options);
    });

    // POST /approval/:id/decide — user clicked approve or deny
    app.post<{
      Params: { id: string };
      Body: { decision: "approve" | "deny"; authResponse?: unknown };
    }>("/approval/:id/decide", async (req, reply) => {
      if (req.params.id !== pending.id) {
        return reply.status(404).send("Not found");
      }

      const { decision, authResponse } = req.body as {
        decision: "approve" | "deny";
        authResponse?: any;
      };

      if (decision === "approve" && pending.requireWebAuthn) {
        // Verify WebAuthn assertion
        if (!authResponse || !pending.challenge) {
          return reply.status(400).send({ error: "WebAuthn assertion required" });
        }

        const credentials = loadCredentials();
        const matchingCred = credentials.find(
          (c) => c.credentialID === authResponse.id,
        );
        if (!matchingCred) {
          return reply.status(400).send({ error: "Unknown credential" });
        }

        try {
          const verification = await verifyAuthenticationResponse({
            response: authResponse,
            expectedChallenge: pending.challenge,
            expectedOrigin: `http://${RP_ID}:${serverPort}`,
            expectedRPID: RP_ID,
            credential: {
              id: matchingCred.credentialID,
              publicKey: new Uint8Array(Buffer.from(matchingCred.publicKey, "base64")),
              counter: matchingCred.counter,
            },
          });

          if (!verification.verified) {
            return reply.status(400).send({ error: "Verification failed" });
          }

          // Persist signature counter to prevent replay attacks.
          const updated = updateCredentialCounter(
            matchingCred.credentialID,
            verification.authenticationInfo.newCounter,
          );
          if (!updated) {
            return reply.status(500).send({ error: "Failed to persist credential counter" });
          }
        } catch (err) {
          return reply.status(400).send({ error: `WebAuthn verification error: ${err}` });
        }
      }

      await reply.send({ ok: true });

      // Resolve the promise and shut down
      pending.resolve(decision === "approve");
      await app.close();
    });

    // Start on a random port
    const address = await app.listen({ port: 0, host: "127.0.0.1" });
    const serverPort = (app.server.address() as { port: number }).port;

    const url = `http://127.0.0.1:${serverPort}/approval/${approvalId}`;
    process.stderr.write(`Opening approval page: ${url}\n`);
    await open(url);
  });
}

function buildApprovalPage(pending: PendingApproval): string {
  const toolInputJson = JSON.stringify(pending.toolInput, null, 2);
  const escapedJson = toolInputJson
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>agent-2fa — Approve Tool Call</title>
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
    max-width: 600px;
    width: 100%;
  }
  h1 { font-size: 1.4rem; margin-bottom: 0.5rem; }
  .tool-name {
    color: #58a6ff;
    font-family: monospace;
    font-size: 1.2rem;
    background: #0d1117;
    padding: 0.3rem 0.6rem;
    border-radius: 6px;
    display: inline-block;
    margin-bottom: 1rem;
  }
  .args {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 1rem;
    font-family: monospace;
    font-size: 0.85rem;
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 300px;
    overflow-y: auto;
    margin-bottom: 1.5rem;
  }
  .buttons { display: flex; gap: 1rem; }
  button {
    flex: 1;
    padding: 0.75rem 1.5rem;
    border: none;
    border-radius: 8px;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.15s;
  }
  button:hover { opacity: 0.85; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .approve { background: #238636; color: #fff; }
  .deny { background: #da3633; color: #fff; }
  .status { margin-top: 1rem; text-align: center; color: #8b949e; min-height: 1.5em; }
  label { font-size: 0.9rem; color: #8b949e; display: block; margin-bottom: 0.3rem; }
</style>
</head>
<body>
<div class="card">
  <h1>Tool Call Approval</h1>
  <label>Tool</label>
  <div class="tool-name">${pending.toolName}</div>
  <label>Arguments</label>
  <div class="args">${escapedJson}</div>
  <div class="buttons">
    <button class="approve" id="btn-approve">
      ${pending.requireWebAuthn ? "Approve with Passkey" : "Approve"}
    </button>
    <button class="deny" id="btn-deny">Deny</button>
  </div>
  <div class="status" id="status"></div>
</div>
<script>
  const approvalId = ${JSON.stringify(pending.id)};
  const requireWebAuthn = ${pending.requireWebAuthn};
  const statusEl = document.getElementById("status");

  async function decide(decision, authResponse) {
    statusEl.textContent = decision === "approve" ? "Approving…" : "Denying…";
    document.getElementById("btn-approve").disabled = true;
    document.getElementById("btn-deny").disabled = true;

    const body = { decision };
    if (authResponse) body.authResponse = authResponse;

    const res = await fetch("/approval/" + approvalId + "/decide", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (res.ok) {
      statusEl.textContent = decision === "approve" ? "Approved ✓" : "Denied ✕";
    } else {
      const err = await res.json().catch(() => ({}));
      statusEl.textContent = "Error: " + (err.error || res.statusText);
      document.getElementById("btn-approve").disabled = false;
      document.getElementById("btn-deny").disabled = false;
    }
  }

  document.getElementById("btn-deny").addEventListener("click", () => decide("deny"));

  document.getElementById("btn-approve").addEventListener("click", async () => {
    if (!requireWebAuthn) {
      return decide("approve");
    }

    try {
      statusEl.textContent = "Requesting passkey…";
      document.getElementById("btn-approve").disabled = true;

      // Get WebAuthn options from server
      const optRes = await fetch("/approval/" + approvalId + "/webauthn-options");
      if (!optRes.ok) {
        const err = await optRes.json().catch(() => ({}));
        throw new Error(err.error || "Failed to get options");
      }
      const options = await optRes.json();

      // Convert base64url challenge to ArrayBuffer
      options.challenge = base64urlToBuffer(options.challenge);
      if (options.allowCredentials) {
        options.allowCredentials = options.allowCredentials.map(c => ({
          ...c,
          id: base64urlToBuffer(c.id),
        }));
      }

      // Call WebAuthn API
      const assertion = await navigator.credentials.get({ publicKey: options });

      // Convert assertion to JSON-friendly format
      const authResponse = {
        id: assertion.id,
        rawId: bufferToBase64url(assertion.rawId),
        type: assertion.type,
        response: {
          authenticatorData: bufferToBase64url(assertion.response.authenticatorData),
          clientDataJSON: bufferToBase64url(assertion.response.clientDataJSON),
          signature: bufferToBase64url(assertion.response.signature),
          userHandle: assertion.response.userHandle
            ? bufferToBase64url(assertion.response.userHandle)
            : null,
        },
        clientExtensionResults: assertion.getClientExtensionResults(),
        authenticatorAttachment: assertion.authenticatorAttachment,
      };

      await decide("approve", authResponse);
    } catch (err) {
      statusEl.textContent = "WebAuthn error: " + err.message;
      document.getElementById("btn-approve").disabled = false;
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
}

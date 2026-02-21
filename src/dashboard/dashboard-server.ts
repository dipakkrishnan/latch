import Fastify, { type FastifyInstance } from "fastify";
import fastifyStatic from "@fastify/static";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { nanoid } from "nanoid";
import {
  generateRegistrationOptions,
  verifyRegistrationResponse,
} from "@simplewebauthn/server";
import {
  loadCredentials,
  saveCredential,
  deleteCredential,
} from "../auth/credential-store.js";
import {
  loadPolicy,
  savePolicy,
  clearCache,
} from "../policy/policy-loader.js";
import { PolicyConfigSchema } from "../policy/policy-types.js";
import { readAuditLog, getAuditStats } from "../audit/audit-log.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const RP_ID = "localhost";
const RP_NAME = "agent-2fa";

export interface DashboardServerOptions {
  port?: number;
}

export async function createDashboardServer(
  options?: DashboardServerOptions,
): Promise<FastifyInstance> {
  const port = options?.port ?? 2222;
  const app = Fastify({ logger: false });

  // Serve built UI from dist/ui/ (only if directory exists)
  const uiDir = path.resolve(__dirname, "../../dist/ui");
  if (fs.existsSync(uiDir)) {
    await app.register(fastifyStatic, {
      root: uiDir,
      prefix: "/",
    });
  }

  // --- Policy routes ---
  await app.register(
    async (fastify) => {
      fastify.get("/", async (_req, reply) => {
        const config = loadPolicy(true);
        return reply.send(config);
      });

      fastify.put("/", async (req, reply) => {
        const result = PolicyConfigSchema.safeParse(req.body);
        if (!result.success) {
          return reply.status(400).send({
            error: "Invalid policy",
            issues: result.error.issues,
          });
        }
        savePolicy(result.data);
        clearCache();
        return reply.send({ ok: true });
      });

      fastify.get("/yaml", async (_req, reply) => {
        const policyDir =
          process.env.AGENT_2FA_DIR ??
          path.join(
            process.env.HOME ?? process.env.USERPROFILE ?? "~",
            ".agent-2fa",
          );
        const policyPath = path.join(policyDir, "policy.yaml");
        if (!fs.existsSync(policyPath)) {
          // Trigger creation of default policy
          loadPolicy(true);
        }
        const yaml = fs.readFileSync(policyPath, "utf-8");
        return reply.type("text/plain; charset=utf-8").send(yaml);
      });

      fastify.post("/validate", async (req, reply) => {
        const result = PolicyConfigSchema.safeParse(req.body);
        if (result.success) {
          return reply.send({ valid: true });
        }
        return reply.send({ valid: false, errors: result.error.issues });
      });
    },
    { prefix: "/api/policy" },
  );

  // --- Credential routes ---
  await app.register(
    async (fastify) => {
      fastify.get("/", async (_req, reply) => {
        const credentials = loadCredentials();
        const redacted = credentials.map(({ publicKey: _, ...rest }) => ({
          ...rest,
          publicKey: "[redacted]",
        }));
        return reply.send(redacted);
      });

      fastify.delete<{ Params: { id: string } }>(
        "/:id",
        async (req, reply) => {
          const credentialID = decodeURIComponent(req.params.id);
          const deleted = deleteCredential(credentialID);
          if (!deleted) {
            return reply.status(404).send({ error: "Credential not found" });
          }
          return reply.send({ ok: true });
        },
      );
    },
    { prefix: "/api/credentials" },
  );

  // --- Enroll routes ---
  await app.register(
    async (fastify) => {
      const challenges = new Map<string, string>();

      fastify.get("/options", async (_req, reply) => {
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
        const challengeId = nanoid();
        challenges.set(challengeId, opts.challenge);
        return reply.send({
          ...opts,
          challengeId,
        });
      });

      fastify.post("/verify", async (req, reply) => {
        const body = (req.body ?? {}) as {
          challengeId?: unknown;
          response?: unknown;
        };
        const challengeId =
          typeof body.challengeId === "string" ? body.challengeId : undefined;
        const responsePayload =
          body.response !== undefined ? body.response : req.body;

        if (!challengeId) {
          return reply.status(400).send({ error: "Missing challengeId" });
        }

        const challenge = challenges.get(challengeId);
        if (!challenge) {
          return reply.status(400).send({ error: "No challenge" });
        }

        try {
          const verification = await verifyRegistrationResponse({
            response: responsePayload as any,
            expectedChallenge: challenge,
            expectedOrigin: `http://${RP_ID}:${port}`,
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
            transports: (responsePayload as any)?.response?.transports,
            createdAt: new Date().toISOString(),
          });

          challenges.delete(challengeId);
          return reply.send({ ok: true });
        } catch (err) {
          return reply.status(400).send({ error: `${err}` });
        }
      });
    },
    { prefix: "/api/enroll" },
  );

  // --- Audit routes ---
  await app.register(
    async (fastify) => {
      fastify.get<{
        Querystring: { limit?: string; offset?: string };
      }>("/", async (req, reply) => {
        const limit = parseNonNegativeInt(req.query.limit, 50);
        const offset = parseNonNegativeInt(req.query.offset, 0);
        if (limit === null || offset === null) {
          return reply.status(400).send({
            error: "limit and offset must be non-negative integers",
          });
        }
        const entries = readAuditLog({ limit, offset });
        return reply.send(entries);
      });

      fastify.get("/stats", async (_req, reply) => {
        const stats = getAuditStats();
        return reply.send(stats);
      });
    },
    { prefix: "/api/audit-log" },
  );

  return app;
}

function parseNonNegativeInt(
  input: string | undefined,
  defaultValue: number,
): number | null {
  if (input === undefined) return defaultValue;
  if (!/^\d+$/.test(input)) return null;
  const value = Number.parseInt(input, 10);
  return Number.isFinite(value) ? value : null;
}

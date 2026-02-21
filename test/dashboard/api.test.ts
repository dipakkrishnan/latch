import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

type DashboardModule = typeof import("../../src/dashboard/dashboard-server.js");

describe("dashboard API", () => {
  const originalDataDir = process.env.AGENT_2FA_DIR;
  let tempHome = "";
  let tempDataDir = "";
  let dashboard: DashboardModule;

  beforeEach(async () => {
    tempHome = fs.mkdtempSync(
      path.join(os.tmpdir(), "agent-2fa-dashboard-"),
    );
    tempDataDir = path.join(tempHome, ".agent-2fa");
    process.env.AGENT_2FA_DIR = tempDataDir;
    vi.resetModules();
    dashboard = await import("../../src/dashboard/dashboard-server.js");
  });

  afterEach(() => {
    process.env.AGENT_2FA_DIR = originalDataDir;
    fs.rmSync(tempHome, { recursive: true, force: true });
  });

  describe("policy endpoints", () => {
    it("GET /api/policy returns current policy", async () => {
      const app = await dashboard.createDashboardServer();
      const res = await app.inject({ method: "GET", url: "/api/policy" });
      expect(res.statusCode).toBe(200);
      const body = res.json();
      expect(body).toHaveProperty("defaultAction");
      expect(body).toHaveProperty("rules");
    });

    it("PUT /api/policy saves and round-trips policy", async () => {
      const app = await dashboard.createDashboardServer();

      const putRes = await app.inject({
        method: "PUT",
        url: "/api/policy",
        payload: { defaultAction: "deny", rules: [] },
      });
      expect(putRes.statusCode).toBe(200);
      expect(putRes.json()).toEqual({ ok: true });

      const getRes = await app.inject({ method: "GET", url: "/api/policy" });
      expect(getRes.json().defaultAction).toBe("deny");
      expect(getRes.json().rules).toEqual([]);
    });

    it("PUT /api/policy rejects invalid policy", async () => {
      const app = await dashboard.createDashboardServer();

      const res = await app.inject({
        method: "PUT",
        url: "/api/policy",
        payload: { defaultAction: "invalid", rules: [] },
      });
      expect(res.statusCode).toBe(400);
      const body = res.json();
      expect(body).toHaveProperty("error");
      expect(body).toHaveProperty("issues");
    });

    it("GET /api/policy/yaml returns raw YAML", async () => {
      const app = await dashboard.createDashboardServer();

      // Trigger default policy creation
      await app.inject({ method: "GET", url: "/api/policy" });

      const res = await app.inject({ method: "GET", url: "/api/policy/yaml" });
      expect(res.statusCode).toBe(200);
      const body = res.json();
      expect(body).toHaveProperty("yaml");
      expect(typeof body.yaml).toBe("string");
      expect(body.yaml).toContain("defaultAction");
    });

    it("POST /api/policy/validate returns valid for good policy", async () => {
      const app = await dashboard.createDashboardServer();

      const res = await app.inject({
        method: "POST",
        url: "/api/policy/validate",
        payload: {
          defaultAction: "allow",
          rules: [{ match: { tool: "Bash" }, action: "deny" }],
        },
      });
      expect(res.statusCode).toBe(200);
      expect(res.json()).toEqual({ valid: true });
    });

    it("POST /api/policy/validate returns errors for bad policy", async () => {
      const app = await dashboard.createDashboardServer();

      const res = await app.inject({
        method: "POST",
        url: "/api/policy/validate",
        payload: { defaultAction: "nope" },
      });
      expect(res.statusCode).toBe(200);
      const body = res.json();
      expect(body.valid).toBe(false);
      expect(body.errors).toBeDefined();
      expect(body.errors.length).toBeGreaterThan(0);
    });
  });

  describe("credential endpoints", () => {
    it("GET /api/credentials returns array with redacted publicKey", async () => {
      const app = await dashboard.createDashboardServer();

      // Seed a credential
      fs.mkdirSync(tempDataDir, { recursive: true });
      fs.writeFileSync(
        path.join(tempDataDir, "credentials.json"),
        JSON.stringify([
          {
            credentialID: "test-cred-id",
            publicKey: "secretKeyData",
            counter: 0,
            transports: ["internal"],
            createdAt: "2026-01-01T00:00:00.000Z",
          },
        ]),
      );

      const res = await app.inject({
        method: "GET",
        url: "/api/credentials",
      });
      expect(res.statusCode).toBe(200);
      const body = res.json();
      expect(Array.isArray(body)).toBe(true);
      expect(body).toHaveLength(1);
      expect(body[0].publicKey).toBe("[redacted]");
      expect(body[0].credentialID).toBe("test-cred-id");
    });

    it("GET /api/credentials returns empty array when none exist", async () => {
      const app = await dashboard.createDashboardServer();

      const res = await app.inject({
        method: "GET",
        url: "/api/credentials",
      });
      expect(res.statusCode).toBe(200);
      expect(res.json()).toEqual([]);
    });

    it("DELETE /api/credentials/:id returns 404 for nonexistent", async () => {
      const app = await dashboard.createDashboardServer();

      const res = await app.inject({
        method: "DELETE",
        url: "/api/credentials/nonexistent",
      });
      expect(res.statusCode).toBe(404);
    });

    it("DELETE /api/credentials/:id deletes existing credential", async () => {
      const app = await dashboard.createDashboardServer();

      fs.mkdirSync(tempDataDir, { recursive: true });
      fs.writeFileSync(
        path.join(tempDataDir, "credentials.json"),
        JSON.stringify([
          {
            credentialID: "delete-me",
            publicKey: "key",
            counter: 0,
            createdAt: "2026-01-01T00:00:00.000Z",
          },
        ]),
      );

      const delRes = await app.inject({
        method: "DELETE",
        url: "/api/credentials/delete-me",
      });
      expect(delRes.statusCode).toBe(200);
      expect(delRes.json()).toEqual({ ok: true });

      // Verify it's gone
      const getRes = await app.inject({
        method: "GET",
        url: "/api/credentials",
      });
      expect(getRes.json()).toEqual([]);
    });
  });

  describe("audit endpoints", () => {
    it("GET /api/audit-log returns entries array", async () => {
      const app = await dashboard.createDashboardServer();

      const res = await app.inject({
        method: "GET",
        url: "/api/audit-log?limit=10&offset=0",
      });
      expect(res.statusCode).toBe(200);
      expect(Array.isArray(res.json())).toBe(true);
    });

    it("GET /api/audit-log respects limit and offset", async () => {
      const app = await dashboard.createDashboardServer();

      // Seed audit entries
      fs.mkdirSync(tempDataDir, { recursive: true });
      const entries = [
        {
          id: "1",
          timestamp: "2026-01-01T00:00:00.000Z",
          toolName: "Read",
          action: "allow",
          decision: "allow",
          reason: "allowed",
          method: "policy",
        },
        {
          id: "2",
          timestamp: "2026-01-02T00:00:00.000Z",
          toolName: "Write",
          action: "ask",
          decision: "ask",
          reason: "ask first",
          method: "policy",
        },
        {
          id: "3",
          timestamp: "2026-01-03T00:00:00.000Z",
          toolName: "Bash",
          action: "deny",
          decision: "deny",
          reason: "denied",
          method: "policy",
        },
      ];
      fs.writeFileSync(
        path.join(tempDataDir, "audit.jsonl"),
        entries.map((e) => JSON.stringify(e)).join("\n") + "\n",
      );

      const res = await app.inject({
        method: "GET",
        url: "/api/audit-log?limit=2&offset=0",
      });
      const body = res.json();
      expect(body).toHaveLength(2);
      // Newest first
      expect(body[0].id).toBe("3");
      expect(body[1].id).toBe("2");
    });

    it("GET /api/audit-log/stats returns stats object", async () => {
      const app = await dashboard.createDashboardServer();

      // Seed audit entries
      fs.mkdirSync(tempDataDir, { recursive: true });
      const entries = [
        {
          id: "1",
          timestamp: "2026-01-01T00:00:00.000Z",
          toolName: "Bash",
          action: "ask",
          decision: "allow",
          reason: "approved",
          method: "browser",
        },
        {
          id: "2",
          timestamp: "2026-01-02T00:00:00.000Z",
          toolName: "Bash",
          action: "ask",
          decision: "deny",
          reason: "denied",
          method: "browser",
        },
      ];
      fs.writeFileSync(
        path.join(tempDataDir, "audit.jsonl"),
        entries.map((e) => JSON.stringify(e)).join("\n") + "\n",
      );

      const res = await app.inject({
        method: "GET",
        url: "/api/audit-log/stats",
      });
      expect(res.statusCode).toBe(200);
      const body = res.json();
      expect(body).toHaveProperty("total", 2);
      expect(body).toHaveProperty("approvals", 1);
      expect(body).toHaveProperty("denials", 1);
      expect(body).toHaveProperty("asks", 0);
      expect(body).toHaveProperty("byTool");
      expect(body.byTool.Bash).toBe(2);
    });
  });

  describe("enroll endpoints", () => {
    it("GET /api/enroll/options returns registration options", async () => {
      const app = await dashboard.createDashboardServer();

      const res = await app.inject({
        method: "GET",
        url: "/api/enroll/options",
      });
      expect(res.statusCode).toBe(200);
      const body = res.json();
      expect(body).toHaveProperty("challenge");
      expect(body).toHaveProperty("rp");
      expect(body.rp.name).toBe("agent-2fa");
      expect(body.rp.id).toBe("localhost");
    });

    it("POST /api/enroll/verify returns 400 with no challenge", async () => {
      // Create a fresh server (no prior /options call)
      vi.resetModules();
      const freshDashboard = await import(
        "../../src/dashboard/dashboard-server.js"
      );
      const app = await freshDashboard.createDashboardServer();

      const res = await app.inject({
        method: "POST",
        url: "/api/enroll/verify",
        payload: {},
      });
      expect(res.statusCode).toBe(400);
    });
  });
});

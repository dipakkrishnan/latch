import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

type AuditLogModule = typeof import("../../src/audit/audit-log.js");

describe("audit-log", () => {
  const originalDataDir = process.env.AGENT_2FA_DIR;
  let tempHome = "";
  let tempDataDir = "";
  let auditLog: AuditLogModule;

  beforeEach(async () => {
    tempHome = fs.mkdtempSync(path.join(os.tmpdir(), "agent-2fa-audit-"));
    tempDataDir = path.join(tempHome, ".agent-2fa");
    process.env.AGENT_2FA_DIR = tempDataDir;
    vi.resetModules();
    auditLog = await import("../../src/audit/audit-log.js");
  });

  afterEach(() => {
    process.env.AGENT_2FA_DIR = originalDataDir;
    fs.rmSync(tempHome, { recursive: true, force: true });
  });

  it("appends and reads audit entries with newest-first pagination", () => {
    auditLog.appendAuditEntry({
      id: "oldest",
      timestamp: "2026-01-01T00:00:00.000Z",
      toolName: "Read",
      toolInput: { file_path: "/tmp/a" },
      action: "allow",
      decision: "allow",
      reason: "allowed",
      method: "policy",
    });
    auditLog.appendAuditEntry({
      id: "newest",
      timestamp: "2026-01-02T00:00:00.000Z",
      toolName: "Write",
      action: "ask",
      decision: "ask",
      reason: "ask first",
      method: "policy",
    });

    const firstPage = auditLog.readAuditLog({ limit: 1, offset: 0 });
    const secondPage = auditLog.readAuditLog({ limit: 1, offset: 1 });

    expect(firstPage).toHaveLength(1);
    expect(firstPage[0].id).toBe("newest");
    expect(secondPage).toHaveLength(1);
    expect(secondPage[0].id).toBe("oldest");
  });

  it("calculates aggregate stats", () => {
    auditLog.appendAuditEntry({
      toolName: "Bash",
      action: "webauthn",
      decision: "allow",
      reason: "approved",
      method: "webauthn",
    });
    auditLog.appendAuditEntry({
      toolName: "Bash",
      action: "webauthn",
      decision: "deny",
      reason: "denied",
      method: "webauthn",
    });
    auditLog.appendAuditEntry({
      toolName: "Read",
      action: "allow",
      decision: "allow",
      reason: "allowed",
      method: "policy",
    });

    const stats = auditLog.getAuditStats();
    expect(stats.total).toBe(3);
    expect(stats.approvals).toBe(2);
    expect(stats.denials).toBe(1);
    expect(stats.asks).toBe(0);
    expect(stats.byTool.Bash).toBe(2);
    expect(stats.byTool.Read).toBe(1);
  });
});

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

type PolicyLoaderModule = typeof import("../../src/policy/policy-loader.js");

describe("policy-loader", () => {
  const originalDataDir = process.env.AGENT_2FA_DIR;
  let tempHome = "";
  let tempDataDir = "";
  let loader: PolicyLoaderModule;

  beforeEach(async () => {
    tempHome = fs.mkdtempSync(path.join(os.tmpdir(), "agent-2fa-policy-"));
    tempDataDir = path.join(tempHome, ".agent-2fa");
    process.env.AGENT_2FA_DIR = tempDataDir;
    vi.resetModules();
    loader = await import("../../src/policy/policy-loader.js");
  });

  afterEach(() => {
    process.env.AGENT_2FA_DIR = originalDataDir;
    fs.rmSync(tempHome, { recursive: true, force: true });
  });

  it("saves policy YAML and round-trips through loadPolicy", () => {
    loader.savePolicy({
      defaultAction: "deny",
      rules: [
        {
          match: { tool: "Read|Glob" },
          action: "allow",
        },
      ],
    });

    const loaded = loader.loadPolicy(true);
    expect(loaded).toEqual({
      defaultAction: "deny",
      rules: [
        {
          match: { tool: "Read|Glob" },
          action: "allow",
        },
      ],
    });

    const policyPath = path.join(tempDataDir, "policy.yaml");
    const raw = fs.readFileSync(policyPath, "utf-8");
    expect(raw).toContain("defaultAction: deny");
    expect(raw).toContain("tool: Read|Glob");
  });

  it("rejects invalid policy values", () => {
    expect(() =>
      loader.savePolicy({
        defaultAction: "allow",
        rules: [
          {
            match: { tool: "Bash" },
            action: "invalid-action" as never,
          },
        ],
      }),
    ).toThrow();
  });
});

import { describe, it, expect, beforeEach, afterEach, beforeAll } from "vitest";
import { execFile, execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

const HOOK_PATH = path.resolve("dist/src/hook.js");
let tempHome = "";
let tempDataDir = "";

function runHook(
  input: object,
  dataDir: string,
): Promise<{ stdout: string; stderr: string; code: number }> {
  return new Promise((resolve) => {
    const child = execFile(
      process.execPath,
      [HOOK_PATH],
      {
        timeout: 10000,
        env: {
          ...process.env,
          AGENT_2FA_DIR: dataDir,
        },
      },
      (error, stdout, stderr) => {
        resolve({
          stdout,
          stderr,
          code: error?.code !== undefined ? (typeof error.code === "number" ? error.code : 1) : 0,
        });
      },
    );
    child.stdin!.write(JSON.stringify(input));
    child.stdin!.end();
  });
}

describe("hook integration", () => {
  beforeAll(() => {
    execFileSync("npm", ["run", "build"], { stdio: "pipe" });
  }, 20000);

  beforeEach(() => {
    tempHome = fs.mkdtempSync(path.join(os.tmpdir(), "agent-2fa-hook-"));
    tempDataDir = path.join(tempHome, ".agent-2fa");
    const policyPath = path.join(tempDataDir, "policy.yaml");

    // Write test policy
    fs.mkdirSync(tempDataDir, { recursive: true });
    fs.writeFileSync(
      policyPath,
      `
defaultAction: allow
rules:
  - match:
      tool: "Bash"
    action: ask
  - match:
      tool: "Edit|Write"
    action: ask
  - match:
      tool: "Read|Glob|Grep"
    action: allow
  - match:
      tool: "BlockedTool"
    action: deny
`,
      "utf-8",
    );
  });

  afterEach(() => {
    fs.rmSync(tempHome, { recursive: true, force: true });
  });

  it("returns ask for Bash", async () => {
    const { stdout } = await runHook(
      { tool_name: "Bash", tool_input: { command: "ls" } },
      tempDataDir,
    );
    const output = JSON.parse(stdout);
    expect(output.hookSpecificOutput.permissionDecision).toBe("ask");
    expect(output.hookSpecificOutput.hookEventName).toBe("PreToolUse");
  });

  it("returns allow for Read", async () => {
    const { stdout } = await runHook(
      { tool_name: "Read", tool_input: { file_path: "/tmp/x" } },
      tempDataDir,
    );
    const output = JSON.parse(stdout);
    expect(output.hookSpecificOutput.permissionDecision).toBe("allow");
  });

  it("returns deny for BlockedTool", async () => {
    const { stdout } = await runHook(
      { tool_name: "BlockedTool", tool_input: {} },
      tempDataDir,
    );
    const output = JSON.parse(stdout);
    expect(output.hookSpecificOutput.permissionDecision).toBe("deny");
  });

  it("returns allow for unknown tool (default action)", async () => {
    const { stdout } = await runHook({ tool_name: "WebSearch", tool_input: {} }, tempDataDir);
    const output = JSON.parse(stdout);
    expect(output.hookSpecificOutput.permissionDecision).toBe("allow");
  });

  it("handles missing tool_input gracefully", async () => {
    const { stdout } = await runHook({ tool_name: "Bash" }, tempDataDir);
    const output = JSON.parse(stdout);
    expect(output.hookSpecificOutput.permissionDecision).toBe("ask");
  });

  it("appends an audit entry for each decision", async () => {
    await runHook({ tool_name: "Read", tool_input: { file_path: "/tmp/a" } }, tempDataDir);
    await runHook({ tool_name: "BlockedTool", tool_input: {} }, tempDataDir);

    const auditPath = path.join(tempDataDir, "audit.jsonl");
    const lines = fs
      .readFileSync(auditPath, "utf-8")
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));

    expect(lines).toHaveLength(2);
    expect(lines[0].toolName).toBe("Read");
    expect(lines[0].decision).toBe("allow");
    expect(lines[0].method).toBe("policy");
    expect(lines[1].toolName).toBe("BlockedTool");
    expect(lines[1].decision).toBe("deny");
  });
});

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const MOCK_SERVER = path.resolve("test/fixtures/mock-mcp-server.ts");
const SERVE_SCRIPT = path.resolve("src/cli/serve.ts");

let tempDir = "";
let client: Client;
let transport: StdioClientTransport;

/**
 * Spins up the Latch proxy as a child process via stdio,
 * connects to it as an MCP client, and runs assertions.
 */
describe("ProxyServer integration", () => {
  beforeEach(() => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "latch-proxy-test-"));

    // Write servers.yaml
    const serversYaml = `servers:
  - alias: mock
    command: tsx
    args: ["${MOCK_SERVER}"]
`;
    fs.writeFileSync(path.join(tempDir, "servers.yaml"), serversYaml, "utf-8");

    // Write a policy that allows mock__echo and mock__add, denies mock__fail
    const policyYaml = `defaultAction: allow
rules:
  - match:
      tool: "mock__fail"
    action: deny
`;
    fs.writeFileSync(path.join(tempDir, "policy.yaml"), policyYaml, "utf-8");
  });

  afterEach(async () => {
    if (client) {
      await client.close().catch(() => {});
    }
    fs.rmSync(tempDir, { recursive: true, force: true });
  });

  it("lists namespaced tools from downstream servers", async () => {
    transport = new StdioClientTransport({
      command: "tsx",
      args: [SERVE_SCRIPT, "--config-dir", tempDir],
      env: { ...process.env, AGENT_2FA_DIR: tempDir } as Record<string, string>,
      stderr: "pipe",
    });

    client = new Client({ name: "test-client", version: "1.0.0" });
    await client.connect(transport);

    const result = await client.listTools();
    const names = result.tools.map((t) => t.name);

    expect(names).toContain("mock__echo");
    expect(names).toContain("mock__add");
    expect(names).toContain("mock__fail");
  }, 20000);

  it("forwards allowed tool calls to downstream", async () => {
    transport = new StdioClientTransport({
      command: "tsx",
      args: [SERVE_SCRIPT, "--config-dir", tempDir],
      env: { ...process.env, AGENT_2FA_DIR: tempDir } as Record<string, string>,
      stderr: "pipe",
    });

    client = new Client({ name: "test-client", version: "1.0.0" });
    await client.connect(transport);

    const result = await client.callTool({
      name: "mock__echo",
      arguments: { message: "hello from proxy" },
    });

    expect(result).toHaveProperty("content");
    const content = result.content as Array<{ type: string; text: string }>;
    expect(content[0].text).toBe("hello from proxy");
  }, 20000);

  it("blocks denied tool calls", async () => {
    transport = new StdioClientTransport({
      command: "tsx",
      args: [SERVE_SCRIPT, "--config-dir", tempDir],
      env: { ...process.env, AGENT_2FA_DIR: tempDir } as Record<string, string>,
      stderr: "pipe",
    });

    client = new Client({ name: "test-client", version: "1.0.0" });
    await client.connect(transport);

    const result = await client.callTool({
      name: "mock__fail",
      arguments: {},
    });

    expect(result.isError).toBe(true);
    const content = result.content as Array<{ type: string; text: string }>;
    expect(content[0].text).toContain("Blocked by policy");
  }, 20000);

  it("writes audit entries with mode: mcp", async () => {
    transport = new StdioClientTransport({
      command: "tsx",
      args: [SERVE_SCRIPT, "--config-dir", tempDir],
      env: { ...process.env, AGENT_2FA_DIR: tempDir } as Record<string, string>,
      stderr: "pipe",
    });

    client = new Client({ name: "test-client", version: "1.0.0" });
    await client.connect(transport);

    // Make a call to generate an audit entry
    await client.callTool({
      name: "mock__echo",
      arguments: { message: "audit test" },
    });

    // Close so the proxy flushes
    await client.close();

    // Small delay for file write
    await new Promise((r) => setTimeout(r, 500));

    const auditPath = path.join(tempDir, "audit.jsonl");
    expect(fs.existsSync(auditPath)).toBe(true);

    const lines = fs
      .readFileSync(auditPath, "utf-8")
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));

    expect(lines.length).toBeGreaterThanOrEqual(1);
    const entry = lines[0];
    expect(entry.mode).toBe("mcp");
    expect(entry.toolName).toBe("mock__echo");
    expect(entry.decision).toBe("allow");
  }, 20000);
});

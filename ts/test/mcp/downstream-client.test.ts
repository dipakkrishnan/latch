import { describe, it, expect, afterEach } from "vitest";
import path from "node:path";
import { DownstreamClient } from "../../src/mcp/downstream-client.js";

const MOCK_SERVER = path.resolve("test/fixtures/mock-mcp-server.ts");

describe("DownstreamClient", () => {
  let client: DownstreamClient;

  afterEach(async () => {
    if (client) {
      await client.close().catch(() => {});
    }
  });

  it("connects to a downstream MCP server and lists tools", async () => {
    client = new DownstreamClient({
      alias: "mock",
      command: "tsx",
      args: [MOCK_SERVER],
    });
    await client.connect();

    const tools = await client.listTools();
    expect(tools.length).toBe(3);

    const names = tools.map((t) => t.name);
    expect(names).toContain("echo");
    expect(names).toContain("add");
    expect(names).toContain("fail");
  }, 15000);

  it("calls a tool and returns the result", async () => {
    client = new DownstreamClient({
      alias: "mock",
      command: "tsx",
      args: [MOCK_SERVER],
    });
    await client.connect();

    const result = await client.callTool("echo", { message: "hello" });
    expect(result.content).toEqual([{ type: "text", text: "hello" }]);
    expect(result.isError).toBeUndefined();
  }, 15000);

  it("returns isError for failing tools", async () => {
    client = new DownstreamClient({
      alias: "mock",
      command: "tsx",
      args: [MOCK_SERVER],
    });
    await client.connect();

    const result = await client.callTool("fail", {});
    expect(result.isError).toBe(true);
  }, 15000);

  it("stores the server alias", () => {
    client = new DownstreamClient({
      alias: "test-alias",
      command: "echo",
    });
    expect(client.alias).toBe("test-alias");
  });
});

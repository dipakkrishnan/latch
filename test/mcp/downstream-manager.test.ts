import { describe, it, expect, afterEach } from "vitest";
import path from "node:path";
import { DownstreamManager } from "../../src/mcp/downstream-manager.js";

const MOCK_SERVER = path.resolve("test/fixtures/mock-mcp-server.ts");

describe("DownstreamManager", () => {
  let manager: DownstreamManager;

  afterEach(async () => {
    if (manager) {
      await manager.closeAll().catch(() => {});
    }
  });

  it("connects to multiple servers and lists all tools with namespacing", async () => {
    manager = new DownstreamManager();
    await manager.connectAll([
      { alias: "srv1", command: "tsx", args: [MOCK_SERVER] },
      { alias: "srv2", command: "tsx", args: [MOCK_SERVER] },
    ]);

    const tools = await manager.listAllTools();
    // Each mock server has 3 tools, so 6 total
    expect(tools.length).toBe(6);

    const names = tools.map((t) => t.namespacedName);
    expect(names).toContain("srv1__echo");
    expect(names).toContain("srv1__add");
    expect(names).toContain("srv1__fail");
    expect(names).toContain("srv2__echo");
    expect(names).toContain("srv2__add");
    expect(names).toContain("srv2__fail");

    // Verify serverAlias is set
    const srv1Tools = tools.filter((t) => t.serverAlias === "srv1");
    expect(srv1Tools.length).toBe(3);
  }, 20000);

  it("routes a call to the correct downstream server", async () => {
    manager = new DownstreamManager();
    await manager.connectAll([
      { alias: "mock", command: "tsx", args: [MOCK_SERVER] },
    ]);

    const result = await manager.routeCall("mock__add", { a: 3, b: 4 });
    expect(result.content).toEqual([{ type: "text", text: "7" }]);
  }, 15000);

  it("throws for invalid namespaced tool name", async () => {
    manager = new DownstreamManager();
    await manager.connectAll([
      { alias: "mock", command: "tsx", args: [MOCK_SERVER] },
    ]);

    await expect(manager.routeCall("noSeparator", {})).rejects.toThrow(
      'missing "__" separator',
    );
  }, 15000);

  it("throws for unknown server alias", async () => {
    manager = new DownstreamManager();
    await manager.connectAll([
      { alias: "mock", command: "tsx", args: [MOCK_SERVER] },
    ]);

    await expect(
      manager.routeCall("unknown__echo", { message: "hi" }),
    ).rejects.toThrow('No downstream server with alias "unknown"');
  }, 15000);

  it("handles partial connection failures gracefully", async () => {
    manager = new DownstreamManager();
    // One valid, one invalid command
    await manager.connectAll([
      { alias: "good", command: "tsx", args: [MOCK_SERVER] },
      { alias: "bad", command: "nonexistent-command-xyz-12345" },
    ]);

    // Should still be able to use the good server
    const tools = await manager.listAllTools();
    expect(tools.length).toBe(3);
    expect(tools[0].serverAlias).toBe("good");
  }, 15000);
});

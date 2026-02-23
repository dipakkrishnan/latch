import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { DownstreamManager } from "./downstream-manager.js";
import { loadPolicy } from "../policy/policy-loader.js";
import { evaluatePolicy } from "../policy/policy-engine.js";
import { appendAuditEntry } from "../audit/audit-log.js";
import { startApprovalFlow } from "../approval/approval-server.js";
import type { ServerConfig } from "./types.js";

export class ProxyServer {
  private server: Server;
  private manager: DownstreamManager;

  constructor() {
    this.server = new Server(
      { name: "latch-proxy", version: "0.1.0" },
      { capabilities: { tools: {} } },
    );
    this.manager = new DownstreamManager();

    this.registerHandlers();
  }

  private registerHandlers(): void {
    this.server.setRequestHandler(ListToolsRequestSchema, async () => {
      const tools = await this.manager.listAllTools();
      return {
        tools: tools.map((t) => ({
          name: t.namespacedName,
          description: t.description,
          inputSchema: t.inputSchema,
        })),
      };
    });

    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const toolName = request.params.name;
      const toolArgs = (request.params.arguments ?? {}) as Record<string, unknown>;

      const policy = loadPolicy();
      const result = evaluatePolicy(toolName, policy);

      const appendAuditSafe = (extra: {
        decision: "allow" | "ask" | "deny";
        reason: string;
        method: "policy" | "browser" | "webauthn";
      }) => {
        try {
          appendAuditEntry({
            toolName,
            toolInput: toolArgs,
            action: result.action,
            decision: extra.decision,
            reason: extra.reason,
            method: extra.method,
            mode: "mcp",
          });
        } catch (err) {
          process.stderr.write(`Audit log error (ignored): ${err}\n`);
        }
      };

      // Handle deny
      if (result.action === "deny") {
        appendAuditSafe({
          decision: "deny",
          reason: result.reason,
          method: "policy",
        });
        return {
          content: [{ type: "text" as const, text: `Blocked by policy: ${result.reason}` }],
          isError: true,
        };
      }

      // Handle ask — MCP clients don't support interactive ask, return error
      if (result.action === "ask") {
        appendAuditSafe({
          decision: "deny",
          reason: `${result.reason} (ask not supported in MCP mode, denied)`,
          method: "policy",
        });
        return {
          content: [
            {
              type: "text" as const,
              text: `Blocked: tool "${toolName}" requires interactive approval (ask), which is not supported in MCP mode. Update policy to "allow", "browser", or "webauthn" for MCP usage.`,
            },
          ],
          isError: true,
        };
      }

      // Handle browser/webauthn — fire approval flow
      if (result.action === "browser" || result.action === "webauthn") {
        const approved = await startApprovalFlow(
          toolName,
          toolArgs,
          result.action === "webauthn",
        );

        if (!approved) {
          appendAuditSafe({
            decision: "deny",
            reason: `Denied in browser (${result.action})`,
            method: result.action,
          });
          return {
            content: [{ type: "text" as const, text: `Denied by user in browser (${result.action})` }],
            isError: true,
          };
        }

        appendAuditSafe({
          decision: "allow",
          reason: `Approved in browser (${result.action})`,
          method: result.action,
        });
      } else {
        // allow
        appendAuditSafe({
          decision: "allow",
          reason: result.reason,
          method: "policy",
        });
      }

      // Forward to downstream
      try {
        const callResult = await this.manager.routeCall(toolName, toolArgs);
        return {
          content: callResult.content,
          isError: callResult.isError,
        };
      } catch (err) {
        return {
          content: [{ type: "text" as const, text: `Downstream call failed: ${err}` }],
          isError: true,
        };
      }
    });
  }

  async start(servers: ServerConfig[]): Promise<void> {
    await this.manager.connectAll(servers);
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    process.stderr.write(
      `Latch MCP proxy started with ${servers.length} downstream server(s)\n`,
    );
  }

  async close(): Promise<void> {
    await this.manager.closeAll();
    await this.server.close();
  }
}

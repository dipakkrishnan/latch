import { DownstreamClient, type ToolInfo } from "./downstream-client.js";
import type { ServerConfig } from "./types.js";

const NAMESPACE_SEPARATOR = "__";

export interface NamespacedTool extends ToolInfo {
  /** The namespaced name shown to the agent: alias__toolName */
  namespacedName: string;
  /** Which downstream server alias owns this tool */
  serverAlias: string;
}

export class DownstreamManager {
  private clients: Map<string, DownstreamClient> = new Map();

  async connectAll(servers: ServerConfig[]): Promise<void> {
    const results = await Promise.allSettled(
      servers.map(async (config) => {
        const client = new DownstreamClient(config);
        await client.connect();
        this.clients.set(config.alias, client);
      }),
    );

    for (let i = 0; i < results.length; i++) {
      const result = results[i];
      if (result.status === "rejected") {
        process.stderr.write(
          `Failed to connect to server "${servers[i].alias}": ${result.reason}\n`,
        );
      }
    }

    if (this.clients.size === 0 && servers.length > 0) {
      throw new Error("All downstream server connections failed");
    }
  }

  async listAllTools(): Promise<NamespacedTool[]> {
    const allTools: NamespacedTool[] = [];

    for (const [alias, client] of this.clients) {
      const tools = await client.listTools();
      for (const tool of tools) {
        allTools.push({
          ...tool,
          namespacedName: `${alias}${NAMESPACE_SEPARATOR}${tool.name}`,
          serverAlias: alias,
        });
      }
    }

    return allTools;
  }

  async routeCall(
    namespacedTool: string,
    args: Record<string, unknown>,
  ): Promise<{ content: unknown[]; isError?: boolean }> {
    const sepIndex = namespacedTool.indexOf(NAMESPACE_SEPARATOR);
    if (sepIndex === -1) {
      throw new Error(
        `Invalid namespaced tool name "${namespacedTool}": missing "${NAMESPACE_SEPARATOR}" separator`,
      );
    }

    const alias = namespacedTool.slice(0, sepIndex);
    const toolName = namespacedTool.slice(sepIndex + NAMESPACE_SEPARATOR.length);

    const client = this.clients.get(alias);
    if (!client) {
      throw new Error(
        `No downstream server with alias "${alias}" (from tool "${namespacedTool}")`,
      );
    }

    return client.callTool(toolName, args);
  }

  async closeAll(): Promise<void> {
    const closeTasks = Array.from(this.clients.values()).map((c) =>
      c.close().catch(() => {}),
    );
    await Promise.all(closeTasks);
    this.clients.clear();
  }
}

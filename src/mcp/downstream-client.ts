import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import type { ServerConfig } from "./types.js";

export interface ToolInfo {
  name: string;
  description?: string;
  inputSchema: {
    type: "object";
    properties?: Record<string, object>;
    required?: string[];
    [key: string]: unknown;
  };
}

export class DownstreamClient {
  readonly alias: string;
  private client: Client;
  private transport: StdioClientTransport;

  constructor(private config: ServerConfig) {
    this.alias = config.alias;
    this.client = new Client(
      { name: `latch-proxy/${config.alias}`, version: "0.1.0" },
    );
    this.transport = new StdioClientTransport({
      command: config.command,
      args: config.args,
      env: config.env ? { ...process.env, ...config.env } as Record<string, string> : undefined,
      stderr: "pipe",
    });
  }

  async connect(): Promise<void> {
    await this.client.connect(this.transport);
  }

  async listTools(): Promise<ToolInfo[]> {
    const result = await this.client.listTools();
    return result.tools.map((t) => ({
      name: t.name,
      description: t.description,
      inputSchema: t.inputSchema,
    }));
  }

  async callTool(
    name: string,
    args: Record<string, unknown>,
  ): Promise<{ content: unknown[]; isError?: boolean }> {
    const result = await this.client.callTool({ name, arguments: args });
    return {
      content: "content" in result ? (result.content as unknown[]) : [],
      isError: "isError" in result ? (result.isError as boolean) : undefined,
    };
  }

  async close(): Promise<void> {
    await this.client.close();
  }
}

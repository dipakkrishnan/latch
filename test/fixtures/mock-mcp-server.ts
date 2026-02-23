/**
 * A simple MCP server for testing. Exposes three tools:
 *   - echo: returns the input message
 *   - add: adds two numbers
 *   - fail: always returns an error
 *
 * Usage: tsx test/fixtures/mock-mcp-server.ts
 */
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

const server = new Server(
  { name: "mock-server", version: "1.0.0" },
  { capabilities: { tools: {} } },
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "echo",
      description: "Echoes the input message",
      inputSchema: {
        type: "object" as const,
        properties: {
          message: { type: "string", description: "The message to echo" },
        },
        required: ["message"],
      },
    },
    {
      name: "add",
      description: "Adds two numbers",
      inputSchema: {
        type: "object" as const,
        properties: {
          a: { type: "number", description: "First number" },
          b: { type: "number", description: "Second number" },
        },
        required: ["a", "b"],
      },
    },
    {
      name: "fail",
      description: "Always fails",
      inputSchema: {
        type: "object" as const,
        properties: {},
      },
    },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  switch (name) {
    case "echo":
      return {
        content: [{ type: "text" as const, text: String((args as Record<string, unknown>)?.message ?? "") }],
      };
    case "add": {
      const a = Number((args as Record<string, unknown>)?.a ?? 0);
      const b = Number((args as Record<string, unknown>)?.b ?? 0);
      return {
        content: [{ type: "text" as const, text: String(a + b) }],
      };
    }
    case "fail":
      return {
        content: [{ type: "text" as const, text: "This tool always fails" }],
        isError: true,
      };
    default:
      return {
        content: [{ type: "text" as const, text: `Unknown tool: ${name}` }],
        isError: true,
      };
  }
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((err) => {
  process.stderr.write(`Mock MCP server error: ${err}\n`);
  process.exit(1);
});

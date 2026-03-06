import fs from "node:fs";
import path from "node:path";
import { parse as parseYaml } from "yaml";
import { ServersConfigSchema, type ServersConfig } from "./types.js";

const CONFIG_DIR =
  process.env.AGENT_2FA_DIR ??
  path.join(process.env.HOME ?? process.env.USERPROFILE ?? "~", ".agent-2fa");
const SERVERS_PATH = path.join(CONFIG_DIR, "servers.yaml");

const DEFAULT_SERVERS = `# Latch MCP server configuration
# Each entry defines a downstream MCP server that Latch proxies.
#
# servers:
#   - alias: fs
#     command: npx
#     args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
#   - alias: github
#     command: npx
#     args: ["-y", "@modelcontextprotocol/server-github"]
#     env:
#       GITHUB_TOKEN: "ghp_..."

servers: []
`;

let cached: ServersConfig | null = null;

/**
 * Load and validate the server registry from ~/.agent-2fa/servers.yaml.
 * Creates the default file if it doesn't exist.
 */
export function loadServers(forceReload = false): ServersConfig {
  if (cached && !forceReload) return cached;

  if (!fs.existsSync(SERVERS_PATH)) {
    fs.mkdirSync(CONFIG_DIR, { recursive: true });
    fs.writeFileSync(SERVERS_PATH, DEFAULT_SERVERS, "utf-8");
  }

  const raw = fs.readFileSync(SERVERS_PATH, "utf-8");
  const parsed = parseYaml(raw);
  cached = ServersConfigSchema.parse(parsed);
  return cached;
}

/**
 * Load server config from an arbitrary YAML string (useful for testing).
 */
export function loadServersFromString(yaml: string): ServersConfig {
  const parsed = parseYaml(yaml);
  return ServersConfigSchema.parse(parsed);
}

export function clearServersCache(): void {
  cached = null;
}

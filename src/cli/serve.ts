import { loadServers } from "../mcp/server-registry.js";
import { ProxyServer } from "../mcp/proxy-server.js";

async function main(): Promise<void> {
  // Allow overriding config dir via --config-dir flag
  const configDirIdx = process.argv.indexOf("--config-dir");
  if (configDirIdx !== -1 && process.argv[configDirIdx + 1]) {
    process.env.AGENT_2FA_DIR = process.argv[configDirIdx + 1];
  }

  const config = loadServers();

  if (config.servers.length === 0) {
    process.stderr.write(
      "No downstream servers configured in servers.yaml. " +
      "Add server entries to ~/.agent-2fa/servers.yaml and restart.\n",
    );
    process.exit(1);
  }

  const proxy = new ProxyServer();

  // Graceful shutdown
  const shutdown = async () => {
    process.stderr.write("Shutting down Latch MCP proxy...\n");
    await proxy.close();
    process.exit(0);
  };

  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);

  await proxy.start(config.servers);
}

main().catch((err) => {
  process.stderr.write(`Latch MCP proxy error: ${err}\n`);
  process.exit(1);
});

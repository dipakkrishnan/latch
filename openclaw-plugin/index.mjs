import { execFileSync } from "node:child_process";

function isOnPath(cmd) {
  try {
    execFileSync("which", [cmd], { stdio: "pipe" });
    return true;
  } catch {
    return false;
  }
}

function installLatch() {
  if (isOnPath("latch-serve")) {
    return true;
  }

  console.log("[openclaw-latch] latch-serve not found on PATH. Installing latch-agent...");

  if (!isOnPath("pipx")) {
    console.error(
      "[openclaw-latch] pipx is required for automatic installation.",
    );
    console.error(
      "[openclaw-latch] Install pipx, then run: pipx install latch-agent && latch init",
    );
    return false;
  }

  try {
    execFileSync("pipx", ["install", "latch-agent"], { stdio: "inherit" });
    return true;
  } catch (err) {
    console.error("[openclaw-latch] pipx install failed:", err.message);
    console.error(
      "[openclaw-latch] Please run: pipx install latch-agent && latch init",
    );
    return false;
  }
}

function initLatch() {
  try {
    execFileSync("latch", ["init"], { stdio: "inherit" });
  } catch {
    // init is idempotent, ignore errors
  }
}

export default function activate(api) {
  // Docker / sidecar mode: connect to latch over the network
  const latchUrl = process.env.LATCH_URL;
  if (latchUrl) {
    console.log(`[openclaw-latch] Using network latch at ${latchUrl}`);
    if (api && typeof api.registerMcpServer === "function") {
      api.registerMcpServer("latch", {
        url: latchUrl,
      });
      console.log("[openclaw-latch] Registered latch (network) as MCP server.");
    } else {
      console.log("[openclaw-latch] MCP server config for manual setup:");
      console.log(
        JSON.stringify(
          { mcpServers: { latch: { url: latchUrl } } },
          null,
          2,
        ),
      );
    }
    return;
  }

  // Local mode: spawn latch-serve as a subprocess
  const installed = installLatch();

  if (!installed) {
    console.error(
      "[openclaw-latch] Latch is not installed. Plugin will not register MCP server.",
    );
    console.error(
      "[openclaw-latch] Run: pipx install latch-agent && latch init",
    );
    return;
  }

  initLatch();

  if (api && typeof api.registerMcpServer === "function") {
    api.registerMcpServer("latch", {
      command: "latch-serve",
      args: [],
    });
    console.log("[openclaw-latch] Registered latch-serve as MCP server.");
  } else {
    console.log("[openclaw-latch] MCP server config for manual setup:");
    console.log(
      JSON.stringify(
        { mcpServers: { latch: { command: "latch-serve", args: [] } } },
        null,
        2,
      ),
    );
  }
}

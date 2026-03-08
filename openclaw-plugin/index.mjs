import { execSync, execFileSync } from "node:child_process";

function isOnPath(cmd) {
  try {
    execFileSync("which", [cmd], { stdio: "pipe" });
    return true;
  } catch {
    return false;
  }
}

function runCommand(command, purpose) {
  try {
    execSync(command, { stdio: "inherit" });
    return true;
  } catch (err) {
    console.error(`[openclaw-latch] Failed to ${purpose}:`, err?.message ?? err);
    return false;
  }
}

function installLatch(config = {}) {
  if (isOnPath("latch-serve")) {
    console.log("[openclaw-latch] Found latch-serve on PATH.");
    return true;
  }

  if (config.autoInstall === false) {
    console.error("[openclaw-latch] latch-serve not found and autoInstall=false.");
    console.error("[openclaw-latch] Run: pipx install latch-agent && latch init");
    return false;
  }

  console.log("[openclaw-latch] latch-serve not found on PATH. Installing latch-agent...");
  const customInstall = typeof config.pythonInstallCommand === "string"
    ? config.pythonInstallCommand.trim()
    : "";
  if (customInstall) {
    console.log("[openclaw-latch] Using custom pythonInstallCommand.");
    if (runCommand(customInstall, "install latch-agent via custom command")) {
      return true;
    }
  }

  if (isOnPath("pipx")) {
    console.log("[openclaw-latch] Trying installer: pipx");
    if (runCommand("pipx install latch-agent", "install latch-agent with pipx")) {
      return true;
    }
  }

  if (isOnPath("pip")) {
    console.log("[openclaw-latch] Trying installer: pip");
    if (runCommand("pip install latch-agent", "install latch-agent with pip")) {
      return true;
    }
  } else {
    console.error("[openclaw-latch] pip not found on PATH.");
  }

  if (isOnPath("python3")) {
    console.log("[openclaw-latch] Trying installer: python3 -m pip");
    if (runCommand("python3 -m pip install latch-agent", "install latch-agent with python3 -m pip")) {
      return true;
    }
  }

  console.error("[openclaw-latch] Could not install latch-agent automatically.");
  console.error("[openclaw-latch] Please run: pipx install latch-agent && latch init");
  return false;
}

function resolveArgs(config = {}) {
  const extra = Array.isArray(config.additionalArgs) ? config.additionalArgs : [];
  return extra.filter((arg) => typeof arg === "string");
}

function initLatch() {
  if (!runCommand("latch init", "initialize latch config")) {
    // latch init is idempotent; hard failure here does not block registration
    console.error("[openclaw-latch] Continuing despite latch init failure.");
  }
}

export default function activate(api, config = {}) {
  const installed = installLatch(config);

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
  const args = resolveArgs(config);

  if (api && typeof api.registerMcpServer === "function") {
    api.registerMcpServer("latch", {
      command: "latch-serve",
      args,
    });
    console.log("[openclaw-latch] Registered latch-serve as MCP server.");
    return true;
  } else {
    console.log("[openclaw-latch] MCP server config for manual setup:");
    console.log(
      JSON.stringify(
        { mcpServers: { latch: { command: "latch-serve", args } } },
        null,
        2,
      ),
    );
  }
}

import { execFileSync } from "node:child_process";
import { appendAuditEntry } from "./audit/audit-log.js";
import { loadPolicy } from "./policy/policy-loader.js";
import { evaluatePolicy } from "./policy/policy-engine.js";
import { HookInputSchema, type HookOutput, type Action } from "./policy/policy-types.js";
import { startApprovalFlow } from "./approval/approval-server.js";

type AgentClient = "claude-code" | "codex" | "openclaw" | "unknown";

const DETECTED_CLIENT = detectAgentClient();
const AGENT_ID = process.env.AGENT_2FA_AGENT_ID ?? defaultAgentId(DETECTED_CLIENT);

/**
 * Read all of stdin as a string.
 */
function readStdin(): Promise<string> {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf-8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

/**
 * Map extended action types to the three Claude Code understands.
 */
function toPermissionDecision(action: Action): "allow" | "ask" | "deny" {
  switch (action) {
    case "allow":
      return "allow";
    case "deny":
      return "deny";
    case "ask":
    case "browser":
    case "webauthn":
      return "ask";
  }
}

function writeOutput(output: HookOutput): void {
  process.stdout.write(JSON.stringify(output));
  process.exit(0);
}

function appendAuditEntrySafe(
  entry: Parameters<typeof appendAuditEntry>[0],
): void {
  try {
    appendAuditEntry(entry);
  } catch (err) {
    process.stderr.write(`Audit log error (ignored): ${err}\n`);
  }
}

async function main(): Promise<void> {
  const raw = await readStdin();
  const input = HookInputSchema.parse(JSON.parse(raw));

  const policy = loadPolicy();
  const result = evaluatePolicy(input.tool_name, policy);

  // For browser/webauthn actions, launch the approval flow
  if (result.action === "browser" || result.action === "webauthn") {
    const decision = await startApprovalFlow(
      input.tool_name,
      input.tool_input ?? {},
      result.action === "webauthn",
    );
    const permissionDecision = decision ? "allow" : "deny";
    const permissionDecisionReason = decision
      ? `Approved in browser (${result.action})`
      : `Denied in browser (${result.action})`;
    const output: HookOutput = {
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision,
        permissionDecisionReason,
      },
    };
    appendAuditEntrySafe({
      agentId: AGENT_ID,
      agentClient: DETECTED_CLIENT,
      toolName: input.tool_name,
      toolInput: input.tool_input,
      action: result.action,
      decision: permissionDecision,
      reason: permissionDecisionReason,
      method: result.action,
      mode: "hook",
    });
    writeOutput(output);
  }

  const permissionDecision = toPermissionDecision(result.action);
  const output: HookOutput = {
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision,
      permissionDecisionReason: result.reason,
    },
  };

  appendAuditEntrySafe({
    agentId: AGENT_ID,
    agentClient: DETECTED_CLIENT,
    toolName: input.tool_name,
    toolInput: input.tool_input,
    action: result.action,
    decision: permissionDecision,
    reason: result.reason,
    method: "policy",
    mode: "hook",
  });
  writeOutput(output);
}

main().catch((err) => {
  process.stderr.write(`Hook error: ${err}\n`);
  // On error, fail open with allow so we don't block the agent
  appendAuditEntrySafe({
    agentId: AGENT_ID,
    agentClient: DETECTED_CLIENT,
    toolName: "unknown",
    action: "allow",
    decision: "allow",
    reason: `Hook error (fail-open): ${err}`,
    method: "fail-open",
    mode: "hook",
  });
  const fallback: HookOutput = {
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "allow",
      permissionDecisionReason: `Hook error (fail-open): ${err}`,
    },
  };
  writeOutput(fallback);
});

function detectAgentClient(): AgentClient {
  const explicit = process.env.AGENT_2FA_CLIENT;
  if (explicit) {
    const normalized = normalizeClient(explicit);
    if (normalized !== "unknown") return normalized;
  }

  const envDetected = detectFromKnownEnvironment();
  if (envDetected !== "unknown") return envDetected;

  const fromId = process.env.AGENT_2FA_AGENT_ID;
  if (fromId) {
    const normalized = normalizeClient(fromId);
    if (normalized !== "unknown") return normalized;
  }

  const ancestry = getProcessAncestryCommandLine(6);
  return normalizeClient(ancestry);
}

function defaultAgentId(client: AgentClient): string {
  return client === "unknown" ? "unknown" : `${client}-adhoc`;
}

function normalizeClient(value: string): AgentClient {
  const source = value.toLowerCase();
  if (source.includes("claude")) return "claude-code";
  if (source.includes("codex")) return "codex";
  if (source.includes("openclaw")) return "openclaw";
  return "unknown";
}

function detectFromKnownEnvironment(): AgentClient {
  const env = process.env;

  // Codex session/runtime signals.
  if (env.CODEX_THREAD_ID || env.CODEX_SANDBOX || env.CODEX_CI) {
    return "codex";
  }

  // Claude Code signals (explicit prefixes and common binary marker).
  const envKeys = Object.keys(env);
  if (envKeys.some((key) => key.toLowerCase().startsWith("claude"))) {
    return "claude-code";
  }

  // OpenClaw signals.
  if (envKeys.some((key) => key.toLowerCase().startsWith("openclaw"))) {
    return "openclaw";
  }

  return "unknown";
}

function getProcessAncestryCommandLine(maxDepth: number): string {
  let pid = process.ppid;
  const commands: string[] = [];
  for (let depth = 0; depth < maxDepth && pid > 1; depth += 1) {
    const info = readProcessInfo(pid);
    if (!info) break;
    if (info.command) commands.push(info.command);
    pid = info.ppid;
  }
  return commands.join(" ");
}

function readProcessInfo(pid: number): { command: string; ppid: number } | null {
  try {
    const output = execFileSync("ps", ["-o", "ppid=,command=", "-p", String(pid)], {
      encoding: "utf-8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
    if (!output) return null;
    const match = output.match(/^(\d+)\s+(.*)$/);
    if (!match) return null;
    const nextPpid = Number.parseInt(match[1], 10);
    const command = match[2] ?? "";
    if (!Number.isFinite(nextPpid)) return null;
    return { command, ppid: nextPpid };
  } catch {
    return null;
  }
}

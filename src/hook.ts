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

  const fromId = process.env.AGENT_2FA_AGENT_ID;
  if (fromId) {
    const normalized = normalizeClient(fromId);
    if (normalized !== "unknown") return normalized;
  }

  const parentCmd = getParentCommandLine();
  return normalizeClient(parentCmd);
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

function getParentCommandLine(): string {
  try {
    return execFileSync("ps", ["-o", "command=", "-p", String(process.ppid)], {
      encoding: "utf-8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return "";
  }
}

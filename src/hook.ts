import { appendAuditEntry } from "./audit/audit-log.js";
import { loadPolicy } from "./policy/policy-loader.js";
import { evaluatePolicy } from "./policy/policy-engine.js";
import { HookInputSchema, type HookOutput, type Action } from "./policy/policy-types.js";
import { startApprovalFlow } from "./approval/approval-server.js";

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

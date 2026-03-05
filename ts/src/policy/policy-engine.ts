import type { Action, PolicyConfig } from "./policy-types.js";

export interface PolicyResult {
  action: Action;
  reason: string;
}

/**
 * Evaluate a tool call against the policy rules.
 * First matching rule wins; falls back to defaultAction.
 */
export function evaluatePolicy(
  toolName: string,
  config: PolicyConfig,
): PolicyResult {
  for (const rule of config.rules) {
    const regex = new RegExp(`^(?:${rule.match.tool})$`);
    if (regex.test(toolName)) {
      return {
        action: rule.action,
        reason: `Policy rule: "${rule.match.tool}" → ${rule.action}`,
      };
    }
  }

  return {
    action: config.defaultAction,
    reason: `Default policy action: ${config.defaultAction}`,
  };
}

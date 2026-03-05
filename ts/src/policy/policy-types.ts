import { z } from "zod";

export const ActionSchema = z.enum(["allow", "ask", "deny", "browser", "webauthn"]);
export type Action = z.infer<typeof ActionSchema>;

export const PolicyRuleSchema = z.object({
  match: z.object({
    tool: z.string(), // regex pattern against tool_name
  }),
  action: ActionSchema,
});
export type PolicyRule = z.infer<typeof PolicyRuleSchema>;

export const PolicyConfigSchema = z.object({
  defaultAction: ActionSchema.default("allow"),
  rules: z.array(PolicyRuleSchema).default([]),
});
export type PolicyConfig = z.infer<typeof PolicyConfigSchema>;

/**
 * The JSON that Claude Code sends to a PreToolUse hook on stdin.
 */
export const HookInputSchema = z.object({
  tool_name: z.string(),
  tool_input: z.record(z.unknown()).optional(),
});
export type HookInput = z.infer<typeof HookInputSchema>;

/**
 * The JSON the hook writes to stdout.
 */
export interface HookOutput {
  hookSpecificOutput: {
    hookEventName: "PreToolUse";
    permissionDecision: "allow" | "ask" | "deny";
    permissionDecisionReason: string;
  };
}

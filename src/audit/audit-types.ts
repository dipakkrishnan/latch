import { z } from "zod";
import { ActionSchema } from "../policy/policy-types.js";

export const AuditDecisionSchema = z.enum(["allow", "ask", "deny"]);
export type AuditDecision = z.infer<typeof AuditDecisionSchema>;

export const AuditMethodSchema = z.enum(["policy", "browser", "webauthn", "fail-open"]);
export type AuditMethod = z.infer<typeof AuditMethodSchema>;

export const AuditModeSchema = z.enum(["hook", "mcp"]);
export type AuditMode = z.infer<typeof AuditModeSchema>;

export const AuditEntrySchema = z.object({
  id: z.string().min(1),
  timestamp: z.string().datetime(),
  agentId: z.string().min(1).optional(),
  agentClient: z.enum(["claude-code", "codex", "openclaw", "unknown"]).optional(),
  toolName: z.string().min(1),
  toolInput: z.record(z.unknown()).optional(),
  action: ActionSchema,
  decision: AuditDecisionSchema,
  reason: z.string(),
  method: AuditMethodSchema,
  mode: AuditModeSchema.optional(),
});
export type AuditEntry = z.infer<typeof AuditEntrySchema>;

export const AppendAuditEntrySchema = AuditEntrySchema.omit({
  id: true,
  timestamp: true,
}).extend({
  id: z.string().min(1).optional(),
  timestamp: z.string().datetime().optional(),
});
export type AppendAuditEntry = z.infer<typeof AppendAuditEntrySchema>;

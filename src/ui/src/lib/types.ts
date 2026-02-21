export type Action = "allow" | "ask" | "deny" | "browser" | "webauthn";

export interface PolicyRule {
  match: { tool: string };
  action: Action;
}

export interface PolicyConfig {
  defaultAction: Action;
  rules: PolicyRule[];
}

export interface StoredCredential {
  credentialID: string;
  counter: number;
  transports?: string[];
  createdAt: string;
}

export interface AuditEntry {
  id: string;
  timestamp: string;
  agentId?: string;
  agentClient?: "claude-code" | "codex" | "openclaw" | "unknown";
  toolName: string;
  toolInput?: Record<string, unknown>;
  action: Action;
  decision: "allow" | "ask" | "deny";
  reason: string;
  method: "policy" | "browser" | "webauthn" | "fail-open";
}

export interface AuditStats {
  total: number;
  approvals: number;
  denials: number;
  asks: number;
  byTool: Record<string, number>;
}

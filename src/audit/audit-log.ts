import fs from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import {
  AppendAuditEntrySchema,
  AuditEntrySchema,
  type AppendAuditEntry,
  type AuditEntry,
} from "./audit-types.js";

const AUDIT_DIR =
  process.env.AGENT_2FA_DIR ??
  path.join(process.env.HOME ?? process.env.USERPROFILE ?? "~", ".agent-2fa");
const AUDIT_PATH = path.join(AUDIT_DIR, "audit.jsonl");

export interface ReadAuditLogOptions {
  limit?: number;
  offset?: number;
}

export interface AuditStats {
  total: number;
  approvals: number;
  denials: number;
  asks: number;
  byTool: Record<string, number>;
}

export function appendAuditEntry(entry: AppendAuditEntry): AuditEntry {
  const parsed = AppendAuditEntrySchema.parse(entry);
  const fullEntry = AuditEntrySchema.parse({
    ...parsed,
    id: parsed.id ?? randomUUID(),
    timestamp: parsed.timestamp ?? new Date().toISOString(),
  });

  fs.mkdirSync(AUDIT_DIR, { recursive: true });
  fs.appendFileSync(AUDIT_PATH, `${JSON.stringify(fullEntry)}\n`, "utf-8");
  return fullEntry;
}

export function readAuditLog(options: ReadAuditLogOptions = {}): AuditEntry[] {
  const limit = Math.max(0, options.limit ?? 50);
  const offset = Math.max(0, options.offset ?? 0);
  const all = readAllEntriesNewestFirst();
  return all.slice(offset, offset + limit);
}

export function getAuditStats(): AuditStats {
  const all = readAllEntriesNewestFirst();
  const stats: AuditStats = {
    total: all.length,
    approvals: 0,
    denials: 0,
    asks: 0,
    byTool: {},
  };

  for (const entry of all) {
    if (entry.decision === "allow") stats.approvals += 1;
    if (entry.decision === "deny") stats.denials += 1;
    if (entry.decision === "ask") stats.asks += 1;
    stats.byTool[entry.toolName] = (stats.byTool[entry.toolName] ?? 0) + 1;
  }

  return stats;
}

function readAllEntriesNewestFirst(): AuditEntry[] {
  if (!fs.existsSync(AUDIT_PATH)) return [];

  const raw = fs.readFileSync(AUDIT_PATH, "utf-8");
  const lines = raw.split("\n").filter((line) => line.trim().length > 0);
  const parsed: AuditEntry[] = [];

  for (const line of lines) {
    try {
      const result = AuditEntrySchema.safeParse(JSON.parse(line));
      if (result.success) parsed.push(result.data);
    } catch {
      // Ignore malformed lines to keep reads resilient.
    }
  }

  return parsed.reverse();
}

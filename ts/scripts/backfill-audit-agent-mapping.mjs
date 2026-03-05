#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

const VALID_CLIENTS = new Set(["codex", "claude-code", "openclaw"]);

function main() {
  const args = parseArgs(process.argv.slice(2));

  if (args.help) {
    printHelp();
    process.exit(0);
  }

  const auditPath = args.file ?? defaultAuditPath();
  if (!fs.existsSync(auditPath)) {
    console.error(`Audit log not found: ${auditPath}`);
    process.exit(1);
  }

  const client = resolveClient(args.client);
  if (!client) {
    console.error(
      "Unable to infer client. Pass --client codex|claude-code|openclaw.",
    );
    process.exit(1);
  }

  const raw = fs.readFileSync(auditPath, "utf-8");
  const lines = raw.split("\n");
  const out = [];

  let touched = 0;
  let malformed = 0;
  let clientPatched = 0;
  let agentPatched = 0;

  for (const line of lines) {
    if (!line.trim()) {
      out.push(line);
      continue;
    }

    let parsed;
    try {
      parsed = JSON.parse(line);
    } catch {
      malformed += 1;
      out.push(line);
      continue;
    }

    if (!parsed || typeof parsed !== "object") {
      out.push(line);
      continue;
    }

    let changed = false;

    if (parsed.agentClient === undefined || parsed.agentClient === "unknown") {
      parsed.agentClient = client;
      clientPatched += 1;
      changed = true;
    }

    if (parsed.agentId === undefined || parsed.agentId === "unknown") {
      parsed.agentId = args.agentId ?? `${client}-adhoc`;
      agentPatched += 1;
      changed = true;
    }

    if (changed) {
      touched += 1;
      out.push(JSON.stringify(parsed));
    } else {
      out.push(line);
    }
  }

  console.log(`Audit file: ${auditPath}`);
  console.log(`Client mapping: ${client}`);
  console.log(`Entries patched: ${touched}`);
  console.log(`agentClient updated: ${clientPatched}`);
  console.log(`agentId updated: ${agentPatched}`);
  console.log(`Malformed lines skipped: ${malformed}`);

  if (!args.write) {
    console.log("Dry run only. Re-run with --write to apply changes.");
    return;
  }

  const backupPath = `${auditPath}.bak.${Date.now()}`;
  fs.copyFileSync(auditPath, backupPath);
  fs.writeFileSync(auditPath, out.join("\n"), "utf-8");

  console.log(`Backup created: ${backupPath}`);
  console.log("Backfill applied.");
}

function parseArgs(argv) {
  const args = {
    file: undefined,
    client: undefined,
    agentId: undefined,
    write: false,
    help: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (token === "--help" || token === "-h") {
      args.help = true;
      continue;
    }
    if (token === "--write") {
      args.write = true;
      continue;
    }
    if (token === "--file") {
      args.file = argv[i + 1];
      i += 1;
      continue;
    }
    if (token === "--client") {
      args.client = argv[i + 1];
      i += 1;
      continue;
    }
    if (token === "--agent-id") {
      args.agentId = argv[i + 1];
      i += 1;
      continue;
    }
    throw new Error(`Unknown argument: ${token}`);
  }

  return args;
}

function defaultAuditPath() {
  const dataDir = process.env.AGENT_2FA_DIR ?? path.join(os.homedir(), ".agent-2fa");
  return path.join(dataDir, "audit.jsonl");
}

function resolveClient(explicit) {
  if (explicit) {
    const normalized = normalizeClient(explicit);
    if (!VALID_CLIENTS.has(normalized)) {
      throw new Error(`Invalid --client value: ${explicit}`);
    }
    return normalized;
  }

  const envExplicit = process.env.AGENT_2FA_CLIENT;
  if (envExplicit) {
    const normalized = normalizeClient(envExplicit);
    if (VALID_CLIENTS.has(normalized)) return normalized;
  }

  if (process.env.CODEX_THREAD_ID || process.env.CODEX_SANDBOX || process.env.CODEX_CI) {
    return "codex";
  }

  if (Object.keys(process.env).some((k) => k.toLowerCase().startsWith("claude"))) {
    return "claude-code";
  }

  if (Object.keys(process.env).some((k) => k.toLowerCase().startsWith("openclaw"))) {
    return "openclaw";
  }

  return undefined;
}

function normalizeClient(value) {
  const source = String(value).toLowerCase();
  if (source.includes("claude")) return "claude-code";
  if (source.includes("codex")) return "codex";
  if (source.includes("openclaw")) return "openclaw";
  return source;
}

function printHelp() {
  console.log(`Backfill unknown agent/client fields in audit.jsonl.

Usage:
  node scripts/backfill-audit-agent-mapping.mjs [options]

Options:
  --write                     Apply changes (default is dry-run)
  --file <path>               Path to audit.jsonl (default: $AGENT_2FA_DIR/audit.jsonl or ~/.agent-2fa/audit.jsonl)
  --client <name>             codex | claude-code | openclaw
  --agent-id <id>             Agent id to set when missing/unknown (default: <client>-adhoc)
  -h, --help                  Show this help
`);
}

main();
